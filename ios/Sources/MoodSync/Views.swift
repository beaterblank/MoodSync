import SwiftUI
import UIKit
import UniformTypeIdentifiers

private let lime = Color(red: 0.73, green: 0.98, blue: 0.40)

struct RootView: View {
  @Environment(\.scenePhase) private var scenePhase
  @EnvironmentObject var library: LibraryStore
  @EnvironmentObject var player: AudioPlayer
  @StateObject private var discovery = ServerDiscovery()
  @State private var showSync = false
  @State private var showImporter = false
  @State private var showFilters = false
  @State private var showPrecision = false
  @State private var tab = 0

  var body: some View {
    TabView(selection: $tab) {
      NavigationStack {
        ScrollView {
          VStack(alignment: .leading, spacing: 22) {
            Button {
              showFilters = true
            } label: {
              Label("Artists, languages & more", systemImage: "line.3.horizontal.decrease.circle")
                .frame(maxWidth: .infinity)
            }.buttonStyle(.bordered)
            HStack {
              Label("Mood plane", systemImage: "sparkles").font(.headline)
              Spacer()
              Button("Fine-tune") { showPrecision = true }
            }
            MoodPlane(
              mood: $library.filters.mood, tracks: library.filtered,
              onHold: { showPrecision = true }
            )
            .frame(height: 310)
            HStack {
              Text("DARKER")
              Spacer()
              Text("BRIGHTER")
            }.font(.caption2.bold()).foregroundStyle(.secondary)
            HStack {
              Text("Valence \(library.filters.mood.valence, specifier: "%.3f")")
              Spacer()
              Text("Arousal \(library.filters.mood.arousal, specifier: "%.3f")")
            }.font(.caption.monospacedDigit())
            Button {
              tab = 1
            } label: {
              HStack {
                VStack(alignment: .leading) {
                  Text("\(library.filtered.count) matching songs").font(.title3.bold())
                  Text("Open your filtered music").font(.subheadline)
                }
                Spacer()
                Image(systemName: "arrow.right")
              }.padding()
            }.buttonStyle(.borderedProminent).tint(lime).foregroundStyle(.black)
          }.padding(20)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { if player.current != nil { MiniPlayer() } }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
          ToolbarItem(placement: .principal) {
            Text("Find the feeling.").font(.headline)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
          }
          ToolbarItem(placement: .topBarTrailing) { syncButton }
        }
      }.tabItem { Label("Discover", systemImage: "sparkles") }.tag(0)
      NavigationStack {
        SongListView(showFilters: $showFilters)
          .safeAreaInset(edge: .bottom, spacing: 0) { if player.current != nil { MiniPlayer() } }
          .navigationTitle("Songs")
          .searchable(text: $library.filters.search, prompt: "Songs, artists or albums")
          .toolbar { syncButton }
      }.tabItem { Label("Songs", systemImage: "music.note.list") }.tag(1)
    }
    .tint(lime)
    .task { discovery.requestLocalNetworkAccess() }
    .onChange(of: scenePhase) { _, phase in
      if phase == .active { discovery.resumeNetworkAccess() }
    }
    .sheet(isPresented: $showSync) { SyncView(discovery: discovery, showImporter: $showImporter) }
    .sheet(isPresented: $showFilters) { FilterView() }
    .sheet(isPresented: $showPrecision) { PrecisionView() }
    .fileImporter(isPresented: $showImporter, allowedContentTypes: [.folder]) { result in
      if case .success(let url) = result { Task { await library.importFolder(url) } }
    }
  }
  var syncButton: some View {
    Button {
      showSync = true
    } label: {
      Image(systemName: "arrow.triangle.2.circlepath")
    }.accessibilityLabel("Sync library")
  }
}

struct SongListView: View {
  @EnvironmentObject var library: LibraryStore
  @EnvironmentObject var player: AudioPlayer
  @Binding var showFilters: Bool

  var body: some View {
    let songs = library.filtered
    List {
      Section {
        HStack {
          Button {
            if let first = songs.first { player.play(first, in: songs) }
          } label: {
            Label("Play", systemImage: "play.fill").frame(maxWidth: .infinity)
          }
          Button {
            let shuffled = songs.shuffled()
            if let first = shuffled.first { player.play(first, in: shuffled) }
          } label: {
            Label("Shuffle", systemImage: "shuffle").frame(maxWidth: .infinity)
          }
        }
        .buttonStyle(.borderedProminent)
        .tint(lime)
        .foregroundStyle(Color(red: 0.07, green: 0.10, blue: 0.04))
        .disabled(songs.isEmpty)
        HStack {
          Text("\(songs.count) songs").foregroundStyle(.secondary)
          Spacer()
          Menu {
            Picker("Sort by", selection: $library.filters.sort) {
              ForEach(TrackSort.allCases) { Text($0.rawValue).tag($0) }
            }
            Toggle("Descending", isOn: $library.filters.descending)
          } label: {
            Label(library.filters.sort.rawValue, systemImage: "arrow.up.arrow.down")
          }
          Button {
            showFilters = true
          } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
          }.accessibilityLabel("Filter songs")
        }
      }
      if songs.isEmpty {
        ContentUnavailableView(
          library.tracks.isEmpty ? "Your music belongs here" : "No matches",
          systemImage: library.tracks.isEmpty ? "music.note" : "line.3.horizontal.decrease.circle",
          description: Text(
            library.tracks.isEmpty
              ? "Tap Sync to find your library on Wi-Fi."
              : "Widen the mood radius or adjust your filters.")
        )
      } else {
        Section {
          ForEach(songs) { track in
            Button {
              player.play(track, in: songs)
            } label: {
              TrackRow(track: track)
            }
            .buttonStyle(.plain)
          }
        }
      }
    }.listStyle(.plain)
  }
}

struct MoodPlane: View {
  @Binding var mood: MoodPoint
  let tracks: [Track]
  var onHold: () -> Void = {}
  var body: some View {
    GeometryReader { geo in
      ZStack {
        RoundedRectangle(cornerRadius: 18).fill(
          LinearGradient(
            colors: [
              Color.blue.opacity(0.28), Color.purple.opacity(0.2), Color.orange.opacity(0.25),
              Color.yellow.opacity(0.3),
            ], startPoint: .bottomLeading, endPoint: .topTrailing))
        Canvas { context, size in
          for step in 1..<5 {
            let x = size.width * CGFloat(step) / 5
            let y = size.height * CGFloat(step) / 5
            context.stroke(
              Path { p in
                p.move(to: CGPoint(x: x, y: 0))
                p.addLine(to: CGPoint(x: x, y: size.height))
                p.move(to: CGPoint(x: 0, y: y))
                p.addLine(to: CGPoint(x: size.width, y: y))
              }, with: .color(.white.opacity(0.08)), lineWidth: 1)
          }
          for t in tracks {
            guard let valence = t.valence, let arousal = t.arousal else { continue }
            let p = CGPoint(
              x: CGFloat(valence) * size.width,
              y: CGFloat(1 - arousal) * size.height)
            context.fill(
              Path(ellipseIn: CGRect(x: p.x - 3, y: p.y - 3, width: 6, height: 6)),
              with: .color(.white.opacity(0.35)))
          }
        }
        Circle().fill(lime).overlay(Circle().stroke(.white, lineWidth: 3)).shadow(
          color: lime, radius: 12
        ).frame(width: 24, height: 24).position(
          x: CGFloat(mood.valence) * geo.size.width, y: CGFloat(1 - mood.arousal) * geo.size.height)
        VStack {
          Text("ENERGETIC").padding(8)
          Spacer()
          Text("CALM").padding(8)
        }.font(.caption2.bold()).foregroundStyle(.white.opacity(0.55)).frame(maxWidth: .infinity)
      }.contentShape(Rectangle()).simultaneousGesture(
        LongPressGesture(minimumDuration: 0.45).onEnded { _ in onHold() }
      ).gesture(
        DragGesture(minimumDistance: 8).onChanged { v in
          mood.valence = Double(min(1, max(0, v.location.x / geo.size.width)))
          mood.arousal = Double(min(1, max(0, 1 - v.location.y / geo.size.height)))
        })
    }
  }
}

struct TrackRow: View {
  @EnvironmentObject var library: LibraryStore
  @EnvironmentObject var player: AudioPlayer
  let track: Track
  var body: some View {
    HStack(spacing: 13) {
      Group {
        if let url = library.artworkURL(track), let image = UIImage(contentsOfFile: url.path) {
          Image(uiImage: image).resizable().scaledToFill()
        } else {
          Image(systemName: "music.note").foregroundStyle(lime)
        }
      }.frame(width: 52, height: 52).background(.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 8))
      VStack(alignment: .leading, spacing: 4) {
        Text(track.title).font(.subheadline.bold()).lineLimit(1)
          .foregroundStyle(player.current?.id == track.id ? lime : .white)
        Text([track.artist, track.album].compactMap { $0 }.joined(separator: " · "))
          .font(.caption).foregroundStyle(.secondary).lineLimit(1)
        Text(metadata).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
      }
      Spacer(minLength: 4)
      if player.current?.id == track.id {
        Image(systemName: player.isPlaying ? "waveform" : "pause.fill").foregroundStyle(lime)
      }
      if let duration = track.duration {
        Text(timeLabel(duration)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
      }
    }.padding(.vertical, 4)
  }
  var metadata: String {
    [
      track.languageLabel, track.tags?.first, track.releaseYear.map(String.init),
      track.tempo.map { String(format: "%.0f BPM", $0) },
    ]
    .compactMap { $0 }.joined(separator: " · ")
  }
}

private func timeLabel(_ seconds: Double) -> String {
  guard seconds.isFinite, seconds >= 0 else { return "0:00" }
  let value = Int(seconds)
  return String(format: "%d:%02d", value / 60, value % 60)
}

struct AlbumArtwork: View {
  @EnvironmentObject var library: LibraryStore
  let track: Track
  var body: some View {
    ZStack {
      RoundedRectangle(cornerRadius: 14).fill(Color.white.opacity(0.06))
      if let url = library.artworkURL(track), let image = UIImage(contentsOfFile: url.path) {
        Image(uiImage: image).resizable().scaledToFit()
      } else {
        Image(systemName: "music.note").resizable().scaledToFit().padding(40).foregroundStyle(lime)
      }
    }.aspectRatio(1, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: 14))
  }
}

struct MiniPlayer: View {
  @EnvironmentObject var player: AudioPlayer
  @State private var expanded = false
  var body: some View {
    VStack(spacing: 0) {
      Divider()
      HStack(spacing: 12) {
        Button { expanded = true } label: {
          HStack(spacing: 12) {
            if let track = player.current {
              AlbumArtwork(track: track).frame(width: 46, height: 46)
              VStack(alignment: .leading, spacing: 4) {
                Text(track.title).font(.subheadline.bold()).lineLimit(1)
                Text(track.artist).font(.caption).foregroundStyle(.secondary).lineLimit(1)
              }
            }
            Spacer(minLength: 0)
          }.contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityLabel("Open now playing")
        Button { player.toggle() } label: {
          Image(systemName: player.isPlaying ? "pause.fill" : "play.fill").frame(width: 36, height: 44)
        }.accessibilityLabel(player.isPlaying ? "Pause" : "Play")
        Button { player.next() } label: {
          Image(systemName: "forward.fill").frame(width: 36, height: 44)
        }.accessibilityLabel("Next song")
      }.padding(.horizontal, 16).padding(.vertical, 8)
      ProgressView(value: min(player.progress, max(1, player.duration)), total: max(1, player.duration)).tint(lime)
    }.background(Color(red: 0.09, green: 0.11, blue: 0.09))
      .foregroundStyle(.primary)
      .sheet(isPresented: $expanded) { NowPlayingView() }
  }
}

struct NowPlayingView: View {
  @EnvironmentObject var player: AudioPlayer
  @EnvironmentObject var library: LibraryStore
  @Environment(\.dismiss) var dismiss
  var body: some View {
    NavigationStack {
      ScrollView {
        if let track = player.current {
          VStack(spacing: 24) {
            AlbumArtwork(track: track).frame(maxWidth: 330).padding(.top, 12)
            VStack(spacing: 6) {
              Text(track.title).font(.title2.bold()).multilineTextAlignment(.center)
              Text(track.artist).font(.title3).foregroundStyle(.secondary)
              if let album = track.album, !album.isEmpty {
                Text(album).font(.subheadline).foregroundStyle(.secondary)
              }
            }
            VStack(spacing: 6) {
              Slider(value: Binding(get: { min(player.progress, max(1, player.duration)) }, set: { player.seek($0) }),
                     in: 0...max(1, player.duration)).tint(lime)
              HStack {
                Text(timeLabel(player.progress)); Spacer(); Text(timeLabel(player.duration))
              }.font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
            HStack(spacing: 48) {
              Button { player.previous() } label: { Image(systemName: "backward.fill") }
                .accessibilityLabel("Previous song")
              Button { player.toggle() } label: {
                Image(systemName: player.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                  .font(.system(size: 64)).foregroundStyle(lime)
              }.accessibilityLabel(player.isPlaying ? "Pause" : "Play")
              Button { player.next() } label: { Image(systemName: "forward.fill") }
                .accessibilityLabel("Next song")
            }.font(.title).buttonStyle(.plain)
            VStack(spacing: 12) {
              Text("Song details").font(.headline).frame(maxWidth: .infinity, alignment: .leading)
              if let year = track.releaseYear { LabeledContent("Released", value: String(year)) }
              if let language = track.languageLabel { LabeledContent("Language", value: language) }
              if let tags = track.tags, !tags.isEmpty {
                LabeledContent("Genres and styles", value: tags.joined(separator: " · "))
              }
              if let tempo = track.tempo { LabeledContent("Tempo", value: "\(Int(tempo.rounded())) BPM") }
              metric("Valence · darker to brighter", track.valence)
              metric("Arousal · calm to energetic", track.arousal)
              metric("Acoustic", track.acousticness)
              metric("Danceable", track.danceability)
              metric("Beat strength", track.rhythmConfidence)
              metric("Instrumental", track.instrumentalness)
              metric("Brightness", track.brightness)
              metric("Bass emphasis", track.bassEmphasis)
              metric("Dynamic range", track.dynamicRange)
              metric("Transient punch", track.transientPunch)
              Text(track.analysisModel == nil ? "Mood analysis pending" : "Mood and sound values are relative to your library.")
                .font(.caption).foregroundStyle(.secondary)
            }.padding().background(.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 16))
          }.padding(.horizontal, 24).padding(.bottom, 24)
        }
      }
      .background(Color(red: 0.045, green: 0.055, blue: 0.045))
      .navigationTitle("Now playing").navigationBarTitleDisplayMode(.inline)
      .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
    }.tint(lime)
  }
  @ViewBuilder func metric(_ title: String, _ value: Double?) -> some View {
    if let value { LabeledContent(title, value: "\(Int((value * 100).rounded()))%") }
  }
}

struct SyncView: View {
  @EnvironmentObject var library: LibraryStore
  @Environment(\.dismiss) var dismiss
  @ObservedObject var discovery: ServerDiscovery
  @Binding var showImporter: Bool
  @AppStorage("syncToken") private var token = ""

  var body: some View {
    NavigationStack {
      Form {
        Section {
          HStack(spacing: 14) {
            if discovery.searching {
              ProgressView()
            } else {
              Image(systemName: discovery.server == nil ? "wifi" : "checkmark.circle.fill")
                .foregroundStyle(lime)
            }
            VStack(alignment: .leading, spacing: 4) {
              Text(discovery.server?.name ?? "Your music library").font(.headline)
              Text(discovery.message).font(.subheadline).foregroundStyle(.secondary)
            }
          }.padding(.vertical, 12)
          if let server = discovery.server {
            if server.requiresToken {
              SecureField("Library sync key", text: $token)
              Text("This library is protected. Enter its sync key to download music.").font(
                .caption)
            }
            Button(library.isSyncing ? "Syncing…" : "Sync music") {
              Task {
                await library.sync(server: server.id, token: server.requiresToken ? token : "")
              }
            }.disabled(library.isSyncing || (server.requiresToken && token.isEmpty))
          }
          if discovery.searching {
            Button("Stop searching") { discovery.stop() }
          } else {
            Button("Find library again") { discovery.start() }.disabled(library.isSyncing)
          }
          if discovery.localNetworkDenied {
            Button("Open Settings") {
              if let url = URL(string: UIApplication.openSettingsURLString) {
                UIApplication.shared.open(url)
              }
            }
          }
          if library.isSyncing { ProgressView(value: library.syncProgress) }
          if !library.syncMessage.isEmpty { Text(library.syncMessage).font(.caption) }
        } header: {
          Text("Wi-Fi sync")
        }
        Section("Import from Files") {
          Button("Choose a MoodSync folder") {
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { showImporter = true }
          }
          Text("Import your exported tracks folder to listen offline.").font(.caption)
            .foregroundStyle(.secondary)
        }
      }.navigationTitle("Library sync")
        .toolbar { Button("Done") { dismiss() } }
        .onAppear { discovery.start() }
        .onDisappear { discovery.stop() }
    }
  }
}
