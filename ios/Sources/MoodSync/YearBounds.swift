import SwiftUI

struct YearBounds: View {
  @Binding var lower: Int
  @Binding var upper: Int
  @State private var lowerText = ""
  @State private var upperText = ""
  private var valid: Bool {
    guard let from = Int(lowerText), let to = Int(upperText) else { return false }
    return (1000...2100).contains(from) && (from...2100).contains(to)
  }
  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Release year").font(.headline)
      HStack {
        VStack(alignment: .leading) {
          Text("From").font(.caption)
          TextField("1900", text: $lowerText).keyboardType(.numberPad)
        }
        VStack(alignment: .leading) {
          Text("Through").font(.caption)
          TextField("2100", text: $upperText).keyboardType(.numberPad)
        }
      }.textFieldStyle(.roundedBorder)
      if !valid {
        Text("Enter whole years from 1000 to 2100, with From no later than Through.")
          .font(.caption).foregroundStyle(.orange)
      }
    }
    .onAppear { lowerText = String(lower); upperText = String(upper) }
    .onChange(of: lowerText) { _, _ in apply() }
    .onChange(of: upperText) { _, _ in apply() }
  }
  private func apply() {
    if valid, let from = Int(lowerText), let to = Int(upperText) { lower = from; upper = to }
  }
}
