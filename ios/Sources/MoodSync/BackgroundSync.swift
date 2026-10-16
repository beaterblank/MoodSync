import Foundation
import UIKit

@MainActor final class BackgroundSync: NSObject, @preconcurrency URLSessionDownloadDelegate {
  static let shared = BackgroundSync()
  static let identifier = "dev.moodsync.player.library-downloads"
  var completionHandler: (() -> Void)?
  var onChange: ((Bool, Double, String, Bool) -> Void)?
  private var active = false
  private var progress = 0.0
  private var message = ""
  private let fm = FileManager.default
  private var plan: Plan?
  private var reconnecting = false
  private struct Plan: Codable {
    var manifest: Manifest
    var server: URL
    var authenticated: Bool
    var completed: Set<String> = []
    var failures: [String: String] = [:]
  }
  private var root: URL {
    fm.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Library")
  }
  private var stateURL: URL { root.appendingPathComponent("sync-plan.json") }
  private lazy var session: URLSession = {
    let configuration = URLSessionConfiguration.background(withIdentifier: Self.identifier)
    configuration.sessionSendsLaunchEvents = true
    configuration.isDiscretionary = false
    configuration.allowsCellularAccess = false
    configuration.waitsForConnectivity = true
    configuration.timeoutIntervalForResource = 7 * 24 * 3600
    configuration.httpMaximumConnectionsPerHost = 3
    return URLSession(configuration: configuration, delegate: self, delegateQueue: .main)
  }()

  private override init() {
    super.init()
    try? fm.createDirectory(at: root, withIntermediateDirectories: true)
    if let data = try? Data(contentsOf: stateURL) { plan = try? JSONDecoder().decode(Plan.self, from: data) }
  }

  func reconnect() {
    guard !reconnecting else { return }
    reconnecting = true
    session.getAllTasks { tasks in
      Task { @MainActor in
        self.reconnecting = false
        self.active = !tasks.isEmpty
        if let plan = self.plan {
          self.active = plan.failures.isEmpty
          if self.active {
            self.enqueueMissing(existing: Set(tasks.compactMap(\.taskDescription)))
          } else {
            self.message = "Sync needs a retry. Completed downloads are saved."
          }
        } else if self.active { self.message = "Preparing your library…" }
        self.publish()
      }
    }
  }

  func start(server: String, token: String) {
    guard !active, let base = URL(string: server) else { return }
    active = true
    progress = 0
    message = "Preparing your library…"
    publish()
    session.getAllTasks { tasks in
      Task { @MainActor in
        guard tasks.isEmpty else {
          self.active = true
          self.message = "Sync is continuing in the background."
          self.publish()
          return
        }
        if self.plan?.server == base {
          self.plan?.failures.removeAll()
          self.save()
          self.enqueueMissing()
          return
        }
        self.plan = nil
        try? self.fm.removeItem(at: self.stateURL)
        var request = URLRequest(url: base.appendingPathComponent("api/device/manifest"))
        if !token.isEmpty { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        let task = self.session.downloadTask(with: request)
        task.taskDescription = "manifest"
        task.resume()
      }
    }
  }

  private func files(_ manifest: Manifest) -> [String] {
    manifest.tracks.flatMap { track in
      [track.id + "/audio.m4a"] + (track.artwork == nil ? [] : [track.id + "/cover.jpg"])
    }
  }

  private func enqueueMissing(existing: Set<String> = []) {
    guard var plan else { return }
    let expected = files(plan.manifest)
    for key in expected where !plan.completed.contains(key) {
      let target = root.appendingPathComponent(key)
      if fm.fileExists(atPath: target.path) {
        plan.completed.insert(key)
        continue
      }
      guard !existing.contains(key) else { continue }
      var request = URLRequest(url: plan.server.appendingPathComponent("api/device/tracks/" + key))
      if plan.authenticated, let token = UserDefaults.standard.string(forKey: "syncToken"), !token.isEmpty {
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
      }
      let task = session.downloadTask(with: request)
      task.taskDescription = key
      task.resume()
    }
    self.plan = plan
    save()
    finishIfReady()
  }

  private func save() {
    guard let plan else { return }
    do {
      try JSONEncoder().encode(plan).write(to: stateURL, options: .atomic)
    } catch {
      message = "Could not save sync progress. Check available storage."
      active = false
    }
  }

  private func publish(committed: Bool = false) {
    onChange?(active, progress, message, committed)
  }

  private func finishIfReady() {
    guard let plan else { publish(); return }
    let expected = files(plan.manifest)
    let completedSongs = plan.manifest.tracks.filter { plan.completed.contains($0.id + "/audio.m4a") }.count
    progress = Double(completedSongs) / Double(max(1, plan.manifest.tracks.count))
    if !plan.failures.isEmpty {
      message = "Sync interrupted: \(plan.failures.values.first ?? "download failed"). Retry to continue."
      // Other downloads may still be active; do not start an overlapping plan.
      session.getAllTasks { tasks in
        Task { @MainActor in self.active = !tasks.isEmpty; self.publish() }
      }
      publish()
      return
    }
    guard expected.allSatisfy(plan.completed.contains) else {
      active = true
      message = "Downloaded \(completedSongs) of \(plan.manifest.tracks.count) songs. Sync continues in the background."
      publish()
      return
    }
    do {
      for track in plan.manifest.tracks {
        let folder = root.appendingPathComponent(track.id)
        try fm.createDirectory(at: folder, withIntermediateDirectories: true)
        try JSONEncoder().encode(track).write(to: folder.appendingPathComponent("metadata.json"), options: .atomic)
      }
      try JSONEncoder().encode(plan.manifest).write(to: root.appendingPathComponent("manifest.json"), options: .atomic)
      try? fm.removeItem(at: stateURL)
      self.plan = nil
      active = false
      progress = 1
      message = "Ready to listen · \(plan.manifest.tracks.count) songs offline"
      publish(committed: true)
    } catch {
      active = false
      message = "Could not save the library. Free some storage and retry."
      publish()
    }
  }

  func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
    guard let key = downloadTask.taskDescription else { return }
    let status = (downloadTask.response as? HTTPURLResponse)?.statusCode ?? 0
    if key.hasSuffix("/cover.jpg"), status == 404 {
      plan?.completed.insert(key)
      save()
      finishIfReady()
      return
    }
    guard status == 200 else {
      fail(key, reason: status == 401 ? "Library key not accepted" : "Server returned HTTP \(status)")
      return
    }
    do {
      if key == "manifest" {
        let manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: location))
        guard manifest.version == 1, manifest.tracks.allSatisfy({
          !$0.id.isEmpty && $0.id != "." && $0.id != ".." && !$0.id.contains("/") && !$0.id.contains("\\")
        }), let request = downloadTask.originalRequest, let url = request.url else { throw URLError(.cannotParseResponse) }
        let base = url.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        plan = Plan(manifest: manifest, server: base, authenticated: request.value(forHTTPHeaderField: "Authorization") != nil)
        save()
        enqueueMissing()
      } else {
        guard let plan, files(plan.manifest).contains(key) else { return }
        let target = root.appendingPathComponent(key)
        try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
        if fm.fileExists(atPath: target.path) { _ = try fm.replaceItemAt(target, withItemAt: location) }
        else { try fm.moveItem(at: location, to: target) }
        self.plan?.completed.insert(key)
        save()
        finishIfReady()
      }
    } catch { fail(key, reason: error.localizedDescription) }
  }

  func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    if let error { fail(task.taskDescription ?? "download", reason: error.localizedDescription) }
    else if plan?.failures.isEmpty == false { finishIfReady() }
  }

  private func fail(_ key: String, reason: String) {
    if plan != nil {
      plan?.failures[key] = reason
      save()
      finishIfReady()
    } else {
      active = false
      message = "Sync failed: \(reason)"
      publish()
    }
  }

  func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
    let handler = completionHandler
    completionHandler = nil
    handler?()
  }
}

final class SyncAppDelegate: NSObject, UIApplicationDelegate {
  func application(_ application: UIApplication, handleEventsForBackgroundURLSession identifier: String,
                   completionHandler: @escaping () -> Void) {
    guard identifier == BackgroundSync.identifier else { completionHandler(); return }
    BackgroundSync.shared.completionHandler = completionHandler
    BackgroundSync.shared.reconnect()
  }
}
