// swift-tools-version: 6.2
import PackageDescription
let package = Package(
  name: "MoodSync",
  platforms: [.iOS("17.0")],
  products: [.library(name:"MoodSync",targets:["MoodSync"])],
  targets: [.target(name:"MoodSync",path:"Sources/MoodSync",swiftSettings:[.swiftLanguageMode(.v5)])]
)
