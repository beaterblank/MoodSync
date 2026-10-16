import Foundation
import SwiftUI

@MainActor final class LibraryStore: ObservableObject {
  @Published var tracks: [Track] = []
  @Published var filters = FilterState()
  @Published var syncMessage = ""
  @Published var isSyncing = false
  @Published var syncProgress = 0.0
  let fm = FileManager.default
  var root: URL {
    fm.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent(
      "Library", isDirectory: true)
  }
  var indexURL: URL { root.appendingPathComponent("manifest.json") }
  init() {
    try? fm.createDirectory(at: root, withIntermediateDirectories: true)
    load()
    BackgroundSync.shared.onChange = { [weak self] active, progress, message, committed in
      self?.isSyncing = active
      self?.syncProgress = progress
      self?.syncMessage = message
      if committed { self?.load() }
    }
    BackgroundSync.shared.reconnect()
  }
  func load() {
    guard let data = try? Data(contentsOf: indexURL),
      let manifest = try? JSONDecoder().decode(Manifest.self, from: data)
    else { return }
    tracks = manifest.tracks
  }
  var artists: [String] { Set(tracks.map(\.artist)).sorted() }
  var languages: [String] { Set(tracks.map(\.normalizedLanguage)).sorted() }
  var albums: [String] { Set(tracks.map { $0.album ?? "Unknown" }).sorted() }
  var tags: [String] { Set(tracks.flatMap { $0.tags ?? [] }).sorted() }
  var filtered: [Track] { tracks.filter(filters.matches).sorted(by: filters.ordered) }
  func audioURL(_ track: Track) -> URL {
    root.appendingPathComponent(track.id).appendingPathComponent("audio.m4a")
  }
  func artworkURL(_ track: Track) -> URL? {
    let u = root.appendingPathComponent(track.id).appendingPathComponent("cover.jpg")
    return fm.fileExists(atPath: u.path) ? u : nil
  }
  func importFolder(_ picked: URL) async {
    let access = picked.startAccessingSecurityScopedResource()
    defer { if access { picked.stopAccessingSecurityScopedResource() } }
    let enumerator = fm.enumerator(at: picked, includingPropertiesForKeys: nil)
    let metadata = (enumerator?.allObjects as? [URL] ?? []).filter {
      $0.lastPathComponent == "metadata.json"
    }
    var imported = 0
    for url in metadata {
      guard let data = try? Data(contentsOf: url),
        let track = try? JSONDecoder().decode(Track.self, from: data)
      else { continue }
      let destination = root.appendingPathComponent(track.id, isDirectory: true)
      try? fm.createDirectory(at: destination, withIntermediateDirectories: true)
      for name in ["metadata.json", "audio.m4a", "cover.jpg"] {
        let source = url.deletingLastPathComponent().appendingPathComponent(name)
        let target = destination.appendingPathComponent(name)
        if fm.fileExists(atPath: source.path) {
          try? fm.removeItem(at: target)
          try? fm.copyItem(at: source, to: target)
        }
      }
      if let i = tracks.firstIndex(where: { $0.id == track.id }) {
        tracks[i] = track
      } else {
        tracks.append(track)
      }
      imported += 1
    }
    saveManifest()
    syncMessage = "Imported \(imported) tracks"
  }
  func saveManifest() {
    let manifest = Manifest(
      version: 1, generatedAt: ISO8601DateFormatter().string(from: Date()), tracks: tracks)
    if let data = try? JSONEncoder().encode(manifest) {
      try? data.write(to: indexURL, options: .atomic)
    }
  }
  func sync(server: String, token: String) async {
    BackgroundSync.shared.start(server: server, token: token)
  }
}
