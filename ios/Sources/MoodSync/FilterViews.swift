import SwiftUI

struct RangeFilter: View {
  let title: String
  @Binding var lower: Double
  @Binding var upper: Double
  let limits: ClosedRange<Double>
  var step = 1.0
  var unit = ""
  var explanation = ""
  func formatted(_ value: Double) -> String {
    if limits == 0...1 { return "\(Int((value * 100).rounded()))%" }
    if unit == " s" { return String(format: "%d:%02d", Int(value) / 60, Int(value) % 60) }
    return "\(Int(value.rounded()))\(unit)"
  }
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        Text(title).font(.headline)
        Spacer()
        Text("\(formatted(lower)) – \(formatted(upper))")
          .monospacedDigit().font(.subheadline).foregroundStyle(.tint)
      }
      if !explanation.isEmpty { Text(explanation).font(.caption).foregroundStyle(.secondary) }
      GeometryReader { geo in
        let width = max(1, geo.size.width - 28)
        let left = width * CGFloat((lower - limits.lowerBound) / (limits.upperBound - limits.lowerBound)) + 14
        let right = width * CGFloat((upper - limits.lowerBound) / (limits.upperBound - limits.lowerBound)) + 14
        ZStack(alignment: .leading) {
          Capsule().fill(Color.secondary.opacity(0.25)).frame(height: 7).padding(.horizontal, 14)
          Capsule().fill(Color.accentColor)
            .frame(width: max(0, right - left), height: 7)
            .position(x: (left + right) / 2, y: 20)
          thumb(at: left, width: width, isLower: true)
          thumb(at: right, width: width, isLower: false)
        }
        .frame(width: geo.size.width, height: 40)
        .coordinateSpace(name: "rangeTrack")
      }
      .frame(height: 40)
      HStack {
        Text(formatted(limits.lowerBound))
        Spacer()
        Text(formatted(limits.upperBound))
      }.font(.caption2).foregroundStyle(.secondary)
    }
    .padding(.vertical, 6)
  }
  private func thumb(at x: CGFloat, width: CGFloat, isLower: Bool) -> some View {
    Circle().fill(.regularMaterial).frame(width: 28, height: 28)
      .overlay(Circle().stroke(Color.accentColor, lineWidth: 3))
      .shadow(radius: 2)
      .gesture(DragGesture(minimumDistance: 0, coordinateSpace: .named("rangeTrack")).onChanged { drag in
        let fraction = min(1, max(0, (drag.location.x - 14) / width))
        let raw = limits.lowerBound + Double(fraction) * (limits.upperBound - limits.lowerBound)
        let snapped = limits.lowerBound + ((raw - limits.lowerBound) / step).rounded() * step
        if isLower { lower = min(upper, max(limits.lowerBound, snapped)) }
        else { upper = max(lower, min(limits.upperBound, snapped)) }
      })
      .accessibilityLabel("\(title) \(isLower ? "minimum" : "maximum")")
      .accessibilityValue(formatted(isLower ? lower : upper))
      .accessibilityAdjustableAction { direction in
        let change = direction == .increment ? step : -step
        if isLower { lower = min(upper, max(limits.lowerBound, lower + change)) }
        else { upper = max(lower, min(limits.upperBound, upper + change)) }
      }
      .position(x: x, y: 20)
  }
}

struct MultiSelectView: View {
  let title: String
  let values: [String]
  @Binding var selected: Set<String>
  var display: (String) -> String = { $0 }
  @State private var search = ""
  var body: some View {
    List {
      Button("Include all") { selected.removeAll() }
      Text("Select several to include any of them. No selection includes all.").font(.caption)
        .foregroundStyle(.secondary)
      ForEach(
        values.filter { search.isEmpty || display($0).localizedCaseInsensitiveContains(search) }, id: \.self
      ) { value in
        Button {
          if selected.contains(value) { selected.remove(value) } else { selected.insert(value) }
        } label: {
          HStack {
            Text(display(value)).foregroundStyle(.primary)
            Spacer()
            Image(systemName: selected.contains(value) ? "checkmark.circle.fill" : "circle")
          }
        }
      }
    }.navigationTitle(title).searchable(text: $search)
  }
}

struct PrecisionView: View {
  @EnvironmentObject var library: LibraryStore
  @Environment(\.dismiss) var dismiss
  var body: some View {
    NavigationStack {
      Form {
        Section("Exact position") {
          precision(
            "Valence · darker to brighter", value: $library.filters.mood.valence, range: 0...1,
            step: 0.001)
          precision(
            "Arousal · calmer to energetic", value: $library.filters.mood.arousal, range: 0...1,
            step: 0.001)
        }
        Section("Match tolerance") {
          precision("Radius", value: $library.filters.radius, range: 0.001...1.42, step: 0.001)
          Text("\(library.filtered.count) matching songs").foregroundStyle(.secondary)
        }
        Section("Sound") {
          RangeFilter(
            title: "Tempo", lower: $library.filters.tempoMin, upper: $library.filters.tempoMax,
            limits: 0...300, unit: " BPM")
          RangeFilter(
            title: "Energy", lower: $library.filters.energyMin, upper: $library.filters.energyMax,
            limits: 0...1, step: 0.01, explanation: "Quiet recording → loud recording. Separate from emotional arousal.")
          RangeFilter(
            title: "Acousticness", lower: $library.filters.acousticMin,
            upper: $library.filters.acousticMax, limits: 0...1, step: 0.01, explanation: "Electronic/amplified → acoustic sound likelihood.")
          RangeFilter(
            title: "Danceability", lower: $library.filters.danceMin, upper: $library.filters.danceMax,
            limits: 0...1, step: 0.01, explanation: "Compared with songs in your library: less → more danceable.")
          RangeFilter(
            title: "Beat strength", lower: $library.filters.beatMin, upper: $library.filters.beatMax,
            limits: 0...1, step: 0.01, explanation: "Compared with your library: weak/irregular → strong, steady beat.")
          RangeFilter(
            title: "Instrumentalness", lower: $library.filters.instrumentalMin, upper: $library.filters.instrumentalMax,
            limits: 0...1, step: 0.01, explanation: "Vocals → instrumental music likelihood.")
          RangeFilter(
            title: "Valence range", lower: $library.filters.valenceMin, upper: $library.filters.valenceMax,
            limits: 0...1, step: 0.01, explanation: "Darker/sadder → brighter/happier sound.")
          RangeFilter(
            title: "Arousal range", lower: $library.filters.arousalMin, upper: $library.filters.arousalMax,
            limits: 0...1, step: 0.01, explanation: "Calm → activated/intense. Sad music can still be intense.")
          RangeFilter(
            title: "Brightness", lower: $library.filters.brightnessMin, upper: $library.filters.brightnessMax,
            limits: 0...1, step: 0.01, explanation: "Darker, softer high end → brighter treble.")
          RangeFilter(
            title: "Bass emphasis", lower: $library.filters.bassMin, upper: $library.filters.bassMax,
            limits: 0...1, step: 0.01, explanation: "Less → more low frequency weight.")
          RangeFilter(
            title: "Dynamic range", lower: $library.filters.dynamicsMin, upper: $library.filters.dynamicsMax,
            limits: 0...1, step: 0.01, explanation: "Even loudness → larger quiet and loud contrast.")
          RangeFilter(
            title: "Transient punch", lower: $library.filters.punchMin, upper: $library.filters.punchMax,
            limits: 0...1, step: 0.01, explanation: "Smooth changes → sharper attacks.")
          RangeFilter(
            title: "Duration", lower: $library.filters.durationMin,
            upper: $library.filters.durationMax, limits: 0...7200, step: 5, unit: " s")
        }
        Section("Ranking importance") {
          precision(
            "Valence weight", value: $library.filters.valenceWeight, range: 0.1...3, step: 0.1)
          precision(
            "Arousal weight", value: $library.filters.arousalWeight, range: 0.1...3, step: 0.1)
          Text(
            "A higher weight makes differences on that axis matter more. Choose Mood match in Songs to sort by this distance."
          )
          .font(.caption).foregroundStyle(.secondary)
        }
      }
      .navigationTitle("Mood & sound")
      .toolbar { Button("Done") { dismiss() } }
    }
  }
  func precision(_ title: String, value: Binding<Double>, range: ClosedRange<Double>, step: Double)
    -> some View
  {
    VStack(alignment: .leading) {
      Text(title)
      Slider(value: value, in: range, step: step)
      Stepper(value: value, in: range, step: step) {
        Text("\(value.wrappedValue, specifier: "%.3f")").monospacedDigit()
      }
    }
  }
}

struct FilterView: View {
  @EnvironmentObject var library: LibraryStore
  @Environment(\.dismiss) var dismiss
  var body: some View {
    NavigationStack {
      Form {
        Section {
          Text("\(library.filtered.count) of \(library.tracks.count) songs")
          Button("Reset all filters and mood") { library.filters = FilterState() }
          Toggle("Include missing metadata", isOn: $library.filters.includeUnknown)
        }
        Section("People and releases") {
          selection("Artists", values: library.artists, selected: $library.filters.artists)
          selection("Languages", values: library.languages, selected: $library.filters.languages,
                    display: { $0 == "Unknown" ? "Undetermined" : Locale.current.localizedString(forLanguageCode: $0) ?? $0 })
          selection("Albums", values: library.albums, selected: $library.filters.albums)
          YearBounds(lower: $library.filters.yearMin, upper: $library.filters.yearMax)
        }
        Section("Music") {
          selection("Genres and styles", values: library.tags, selected: $library.filters.tags)
        }

      }.navigationTitle("Filters")
        .toolbar { Button("Show \(library.filtered.count) songs") { dismiss() } }
    }
  }
  func selection(_ title: String, values: [String], selected: Binding<Set<String>>,
                 display: @escaping (String) -> String = { $0 }) -> some View {
    NavigationLink {
      MultiSelectView(title: title, values: values, selected: selected, display: display)
    } label: {
      LabeledContent(
        title,
        value: selected.wrappedValue.isEmpty ? "All" : "\(selected.wrappedValue.count) selected")
    }
  }
}
