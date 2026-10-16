import Foundation

@main struct FilterChecks {
  static func main() throws {
    let json = """
      [
        {"id":"a","title":"Alpha","artist":"One","album":"First","language":"English","release_year":2020,"duration":180,"tempo":100,"energy":0.2,"acousticness":0.9,"valence":0.8,"arousal":0.5,"tags":["Rock"],"rhythm_confidence":0.2,"brightness":0.2,"bass_emphasis":0.8,"dynamic_range":0.3,"transient_punch":0.2},
        {"id":"b","title":"Beta","artist":"Two","album":"Second","language":"French","release_year":1990,"duration":300,"tempo":140,"energy":0.8,"acousticness":0.1,"valence":0.5,"arousal":0.8,"tags":["Hip Hop","Rap"],"rhythm_confidence":0.9,"brightness":0.8,"bass_emphasis":0.2,"dynamic_range":0.7,"transient_punch":0.9},
        {"id":"c","title":"Gamma","artist":"Three"}
      ]
      """
    let tracks = try JSONDecoder().decode([Track].self, from: Data(json.utf8))
    var regionalEnglish = tracks[0]
    regionalEnglish.language = "en-US"
    assert(Set([tracks[0].normalizedLanguage, regionalEnglish.normalizedLanguage]).count == 1)
    assert(regionalEnglish.normalizedLanguage == "en")
    var f = FilterState()
    f.languages = ["en"]
    assert(f.matches(tracks[0]) && f.matches(regionalEnglish))
    f = FilterState()
    assert(tracks.filter(f.matches).count == 3)
    f.artists = ["One", "Two"]
    assert(tracks.filter(f.matches).count == 2)
    f.languages = ["fr"]
    assert(tracks.filter(f.matches).map(\.id) == ["b"])
    f.albums = ["First"]
    assert(tracks.filter(f.matches).isEmpty)
    f = FilterState()
    f.includeUnknown = false
    f.yearMin = 2000
    assert(tracks.filter(f.matches).map(\.id) == ["a"])
    f = FilterState()
    f.includeUnknown = false
    f.energyMin = 0.5
    f.acousticMax = 0.5
    f.tempoMin = 130
    f.durationMin = 240
    assert(tracks.filter(f.matches).map(\.id) == ["b"])
    f = FilterState()
    f.search = "second"
    assert(tracks.filter(f.matches).map(\.id) == ["b"])
    f = FilterState()
    f.radius = 0.001
    assert(tracks.filter(f.matches).map(\.id) == ["c"])
    f.includeUnknown = false
    assert(tracks.filter(f.matches).isEmpty)
    f = FilterState()
    f.valenceWeight = 3
    f.arousalWeight = 0.1
    assert(f.distance(tracks[1]) < f.distance(tracks[0]))
    f.sort = .year
    assert(tracks.sorted(by: f.ordered).map(\.id) == ["b", "a", "c"])
    f.descending = true
    assert(tracks.sorted(by: f.ordered).map(\.id) == ["a", "b", "c"])
    f = FilterState()
    f.tags = ["Rap"]
    f.beatMin = 0.8
    f.brightnessMin = 0.7
    f.punchMin = 0.8
    assert(tracks.filter(f.matches).map(\.id) == ["b"])
    f = FilterState()
    f.bassMin = 0.7
    assert(tracks.filter(f.matches).map(\.id) == ["a"])
    print("Filter checks passed")
  }
}
