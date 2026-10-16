import Foundation

struct LibraryServer: Identifiable, Sendable {
  let url: URL
  let name: String
  let requiresToken: Bool
  var id: String { url.absoluteString }
}

@MainActor final class ServerDiscovery: NSObject, ObservableObject, @preconcurrency NetServiceBrowserDelegate, @preconcurrency NetServiceDelegate {
  @Published var server: LibraryServer?
  @Published var searching = false
  @Published var message = "Find your music library on Wi-Fi"
  @Published var localNetworkDenied = false
  private var browser: NetServiceBrowser?
  private var services: [NetService] = []
  private var probes: [String: Task<Void, Never>] = [:]
  private var timeout: Task<Void, Never>?

  func requestLocalNetworkAccess() { if browser == nil { start() } }
  func resumeNetworkAccess() { if localNetworkDenied { stop(); start() } }

  func start() {
    stop()
    server = nil
    localNetworkDenied = false
    searching = true
    message = "Looking for music libraries on Wi-Fi…"
    let browser = NetServiceBrowser()
    browser.delegate = self
    self.browser = browser
    browser.searchForServices(ofType: "_moodsync._tcp.", inDomain: "local.")
    timeout = Task { [weak self] in
      try? await Task.sleep(for: .seconds(12))
      guard !Task.isCancelled, let self, self.server == nil else { return }
      self.message = "No library found yet. Keep MoodSync running on your computer and connect both devices to the same Wi-Fi."
    }
  }

  func stop() {
    browser?.stop()
    browser = nil
    services.forEach { $0.stop() }
    services.removeAll()
    probes.values.forEach { $0.cancel() }
    probes.removeAll()
    timeout?.cancel()
    searching = false
  }

  func netServiceBrowser(_ browser: NetServiceBrowser, didNotSearch errorDict: [String: NSNumber]) {
    localNetworkDenied = errorDict[NetService.errorCode]?.intValue == -72008
      || errorDict[NetService.errorCode]?.intValue == -65570
    searching = false
    timeout?.cancel()
    message = localNetworkDenied
      ? "Allow Local Network access in Settings to find your music computer."
      : "Discovery could not start. Check Wi-Fi and try again."
  }

  func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
    services.append(service)
    service.delegate = self
    service.resolve(withTimeout: 10)
  }

  func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
    services.removeAll { $0 == service }
    if let host = service.hostName, server?.url.host?.trimmingCharacters(in: CharacterSet(charactersIn: ".")) == host.trimmingCharacters(in: CharacterSet(charactersIn: ".")) {
      server = nil
      searching = true
      message = "Library disconnected. Looking for it again…"
    }
  }

  func netServiceDidResolveAddress(_ sender: NetService) {
    guard let host = sender.hostName, sender.port > 0 else { return }
    var components = URLComponents()
    components.scheme = "http"
    components.host = host.trimmingCharacters(in: CharacterSet(charactersIn: "."))
    components.port = sender.port
    guard let url = components.url, probes[url.absoluteString] == nil else { return }
    probes[url.absoluteString] = Task { [weak self] in
      let config = URLSessionConfiguration.ephemeral
      config.waitsForConnectivity = true
      config.timeoutIntervalForResource = 15
      config.allowsCellularAccess = false
      let session = URLSession(configuration: config)
      defer { session.invalidateAndCancel() }
      guard let result = await Self.probe(url, session: session), !Task.isCancelled else { return }
      guard let self else { return }
      self.server = result
      self.searching = false
      self.message = "Connected"
      self.timeout?.cancel()
    }
  }

  nonisolated static func probe(_ url: URL, session: URLSession) async -> LibraryServer? {
    struct Health: Decodable {
      let service: String
      let version: Int
      let name: String
      let requires_token: Bool
    }
    do {
      let (data, response) = try await session.data(from: url.appendingPathComponent("api/device/health"))
      guard (response as? HTTPURLResponse)?.statusCode == 200,
        let health = try? JSONDecoder().decode(Health.self, from: data),
        health.service == "moodsync", health.version == 1 else { return nil }
      return LibraryServer(url: url, name: health.name, requiresToken: health.requires_token)
    } catch { return nil }
  }
}
