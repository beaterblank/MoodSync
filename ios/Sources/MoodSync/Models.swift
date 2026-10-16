import Foundation

struct Track: Codable, Identifiable, Hashable {
  let id: String
  var title: String
  var artist: String
  var album: String?
  var language: String?
  var releaseDate: String?
  var releaseYear: Int?
  var duration: Double?
  var thumbnail: String?
  var valence: Double?
  var arousal: Double?
  var tempo: Double?
  var energy: Double?
  var acousticness: Double?
  var danceability: Double?
  var instrumentalness: Double?
  var rhythmConfidence: Double?
  var brightness: Double?
  var bassEmphasis: Double?
  var dynamicRange: Double?
  var transientPunch: Double?
  var tags: [String]?
  var analysisModel: String?
  var status: String?
  var audio: String?
  var artwork: String?
  enum CodingKeys: String, CodingKey {
    case id, title, artist, album, language, duration, thumbnail, valence, arousal, tempo, energy,
      acousticness, danceability, instrumentalness, brightness, tags, status, audio, artwork
    case analysisModel = "analysis_model"
    case releaseDate = "release_date"
    case releaseYear = "release_year"
    case rhythmConfidence = "rhythm_confidence"
    case bassEmphasis = "bass_emphasis"
    case dynamicRange = "dynamic_range"
    case transientPunch = "transient_punch"
  }
  func distance(to mood: MoodPoint) -> Double {
    hypot((valence ?? 0.5) - mood.valence, (arousal ?? 0.5) - mood.arousal)
  }
  var normalizedLanguage: String {
    let value = (language ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased().replacingOccurrences(of: "_", with: "-")
    if value.isEmpty || ["unknown", "und", "none"].contains(value) { return "Unknown" }
    let aliases = ["english": "en", "eng": "en", "french": "fr", "fra": "fr",
                   "spanish": "es", "spa": "es", "hindi": "hi", "german": "de",
                   "deu": "de", "japanese": "ja"]
    return aliases[value] ?? String(value.split(separator: "-", maxSplits: 1)[0])
  }
  var languageLabel: String? {
    let code = normalizedLanguage
    guard code != "Unknown" else { return nil }
    return Locale.current.localizedString(forLanguageCode: code)?.capitalized ?? code
  }
}
struct Manifest: Codable {
  let version: Int
  let generatedAt: String?
  let tracks: [Track]
  enum CodingKeys: String, CodingKey {
    case version, tracks
    case generatedAt = "generated_at"
  }
}
struct MoodPoint: Equatable {
  var valence = 0.5
  var arousal = 0.5
}
enum TrackSort: String, CaseIterable, Identifiable {
  case mood = "Mood match"
  case title = "Title"
  case artist = "Artist"
  case album = "Album"
  case year = "Year"
  case tempo = "Tempo"
  case duration = "Duration"
  case energy = "Energy"
  case acousticness = "Acousticness"
  case danceability = "Danceability"
  case instrumentalness = "Instrumentalness"
  case valence = "Valence"
  case arousal = "Arousal"
  case beatStrength = "Beat strength"
  case brightness = "Brightness"
  case bassEmphasis = "Bass emphasis"
  case dynamicRange = "Dynamic range"
  case transientPunch = "Transient punch"
  var id: String { rawValue }
}

struct FilterState {
  var mood = MoodPoint()
  var radius = 1.42
  var valenceWeight = 1.0
  var arousalWeight = 1.0
  var artists: Set<String> = []
  var languages: Set<String> = []
  var albums: Set<String> = []
  var tags: Set<String> = []
  var yearMin = 1900, yearMax = 2100
  var tempoMin = 0.0, tempoMax = 300.0
  var durationMin = 0.0, durationMax = 7200.0
  var energyMin = 0.0, energyMax = 1.0
  var acousticMin = 0.0, acousticMax = 1.0
  var danceMin = 0.0, danceMax = 1.0
  var instrumentalMin = 0.0, instrumentalMax = 1.0
  var valenceMin = 0.0, valenceMax = 1.0
  var arousalMin = 0.0, arousalMax = 1.0
  var beatMin = 0.0, beatMax = 1.0
  var brightnessMin = 0.0, brightnessMax = 1.0
  var bassMin = 0.0, bassMax = 1.0
  var dynamicsMin = 0.0, dynamicsMax = 1.0
  var punchMin = 0.0, punchMax = 1.0
  var includeUnknown = true
  var search = ""
  var sort = TrackSort.mood
  var descending = false

  func distance(_ track: Track) -> Double {
    let v = (track.valence ?? 0.5) - mood.valence
    let a = (track.arousal ?? 0.5) - mood.arousal
    return sqrt(
      (v * v * valenceWeight + a * a * arousalWeight) * 2 / (valenceWeight + arousalWeight))
  }

  func matches(_ t: Track) -> Bool {
    func range(_ value: Double?, _ low: Double, _ high: Double) -> Bool {
      guard let value else { return includeUnknown }
      return value >= low && value <= high
    }
    return distance(t) <= radius
      && (includeUnknown || (t.valence != nil && t.arousal != nil))
      && (artists.isEmpty || artists.contains(t.artist))
      && (languages.isEmpty || languages.contains(t.normalizedLanguage))
      && (albums.isEmpty || albums.contains(t.album ?? "Unknown"))
      && (tags.isEmpty || !tags.isDisjoint(with: t.tags ?? []))
      && range(t.releaseYear.map(Double.init), Double(yearMin), Double(yearMax))
      && range(t.tempo, tempoMin, tempoMax) && range(t.duration, durationMin, durationMax)
      && range(t.energy, energyMin, energyMax) && range(t.acousticness, acousticMin, acousticMax)
      && ((danceMin == 0 && danceMax == 1) || range(t.danceability, danceMin, danceMax))
      && ((instrumentalMin == 0 && instrumentalMax == 1) || range(t.instrumentalness, instrumentalMin, instrumentalMax))
      && range(t.valence, valenceMin, valenceMax) && range(t.arousal, arousalMin, arousalMax)
      && ((beatMin == 0 && beatMax == 1) || range(t.rhythmConfidence, beatMin, beatMax))
      && ((brightnessMin == 0 && brightnessMax == 1)
          || (t.brightness != nil && range(t.brightness, brightnessMin, brightnessMax)))
      && ((bassMin == 0 && bassMax == 1)
          || (t.bassEmphasis != nil && range(t.bassEmphasis, bassMin, bassMax)))
      && ((dynamicsMin == 0 && dynamicsMax == 1)
          || (t.dynamicRange != nil && range(t.dynamicRange, dynamicsMin, dynamicsMax)))
      && ((punchMin == 0 && punchMax == 1)
          || (t.transientPunch != nil && range(t.transientPunch, punchMin, punchMax)))
      && (search.isEmpty || searchMatches(t))
  }

  private func searchMatches(_ t: Track) -> Bool {
    ([t.title, t.artist, t.album ?? ""] + (t.tags ?? []))
      .contains { $0.localizedCaseInsensitiveContains(search) }
  }

  func ordered(_ lhs: Track, _ rhs: Track) -> Bool {
    func number(_ t: Track) -> Double? {
      switch sort {
      case .mood: return distance(t)
      case .year: return t.releaseYear.map(Double.init)
      case .tempo: return t.tempo
      case .duration: return t.duration
      case .energy: return t.energy
      case .acousticness: return t.acousticness
      case .danceability: return t.danceability
      case .instrumentalness: return t.instrumentalness
      case .valence: return t.valence
      case .arousal: return t.arousal
      case .beatStrength: return t.rhythmConfidence
      case .brightness: return t.brightness
      case .bassEmphasis: return t.bassEmphasis
      case .dynamicRange: return t.dynamicRange
      case .transientPunch: return t.transientPunch
      default: return nil
      }
    }
    func string(_ t: Track) -> String {
      switch sort {
      case .artist: return t.artist
      case .album: return t.album ?? ""
      default: return t.title
      }
    }
    if [.title, .artist, .album].contains(sort) {
      let order = string(lhs).localizedStandardCompare(string(rhs))
      if order != .orderedSame {
        return descending ? order == .orderedDescending : order == .orderedAscending
      }
    } else {
      let l = number(lhs)
      let r = number(rhs)
      if l == nil && r != nil { return false }
      if l != nil && r == nil { return true }
      if let l, let r, l != r { return descending ? l > r : l < r }
    }
    return lhs.id < rhs.id
  }
}
