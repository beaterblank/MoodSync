import AVFoundation
import MediaPlayer
import SwiftUI

@MainActor final class AudioPlayer: ObservableObject {
  @Published var current: Track?
  @Published var isPlaying = false
  @Published var progress = 0.0
  @Published var duration = 0.0
  private var player: AVPlayer?
  private var observer: Any?
  private var ended: NSObjectProtocol?
  private var queue: [Track] = []
  weak var library: LibraryStore?

  init() {
    try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
    try? AVAudioSession.sharedInstance().setActive(true)
    configureCommands()
  }

  func play(_ track: Track, in tracks: [Track]) {
    guard let library else { return }
    if let observer, let player { player.removeTimeObserver(observer) }
    if let ended { NotificationCenter.default.removeObserver(ended) }
    queue = tracks
    current = track
    progress = 0
    duration = track.duration ?? 0
    let item = AVPlayerItem(url: library.audioURL(track))
    player = AVPlayer(playerItem: item)
    observer = player?.addPeriodicTimeObserver(
      forInterval: CMTime(seconds: 0.5, preferredTimescale: 600), queue: .main
    ) { [weak self] time in
      Task { @MainActor in
        guard let self, self.player?.currentItem === item else { return }
        self.progress = time.seconds.isFinite ? max(0, time.seconds) : 0
        if item.duration.seconds.isFinite { self.duration = max(0, item.duration.seconds) }
        self.updateNowPlaying()
      }
    }
    ended = NotificationCenter.default.addObserver(
      forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
    ) { [weak self] _ in
      Task { @MainActor in
        guard let self, self.player?.currentItem === item else { return }
        if let index = self.queue.firstIndex(of: track), index + 1 < self.queue.count {
          self.play(self.queue[index + 1], in: self.queue)
        } else {
          self.isPlaying = false
          self.updateNowPlaying()
        }
      }
    }
    player?.play()
    isPlaying = true
    updateNowPlaying()
  }

  func toggle() {
    guard let player else { return }
    if isPlaying {
      player.pause()
    } else {
      if duration > 0 && progress >= duration - 0.1 { seek(0) }
      player.play()
    }
    isPlaying.toggle()
    updateNowPlaying()
  }
  func seek(_ value: Double) {
    progress = max(0, min(value, duration))
    player?.seek(to: CMTime(seconds: progress, preferredTimescale: 600))
    updateNowPlaying()
  }
  func next() {
    guard let current, let i = queue.firstIndex(of: current), !queue.isEmpty else { return }
    play(queue[(i + 1) % queue.count], in: queue)
  }
  func previous() {
    if progress > 3 {
      seek(0)
      return
    }
    guard let current, let i = queue.firstIndex(of: current), !queue.isEmpty else { return }
    play(queue[(i - 1 + queue.count) % queue.count], in: queue)
  }
  private func configureCommands() {
    let c = MPRemoteCommandCenter.shared()
    c.playCommand.addTarget { [weak self] _ in
      Task { @MainActor in if self?.isPlaying == false { self?.toggle() } }
      return .success
    }
    c.pauseCommand.addTarget { [weak self] _ in
      Task { @MainActor in if self?.isPlaying == true { self?.toggle() } }
      return .success
    }
    c.nextTrackCommand.addTarget { [weak self] _ in
      Task { @MainActor in self?.next() }
      return .success
    }
    c.previousTrackCommand.addTarget { [weak self] _ in
      Task { @MainActor in self?.previous() }
      return .success
    }
    c.changePlaybackPositionCommand.addTarget { [weak self] event in
      guard let event = event as? MPChangePlaybackPositionCommandEvent else {
        return .commandFailed
      }
      Task { @MainActor in self?.seek(event.positionTime) }
      return .success
    }
  }
  private func updateNowPlaying() {
    guard let current else { return }
    MPNowPlayingInfoCenter.default().nowPlayingInfo = [
      MPMediaItemPropertyTitle: current.title,
      MPMediaItemPropertyArtist: current.artist,
      MPNowPlayingInfoPropertyElapsedPlaybackTime: progress,
      MPMediaItemPropertyPlaybackDuration: duration,
      MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1 : 0,
    ]
  }
}
