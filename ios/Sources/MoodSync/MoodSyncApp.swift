import SwiftUI

@main struct MoodSyncApp:App {
  @UIApplicationDelegateAdaptor(SyncAppDelegate.self) private var appDelegate
  @StateObject private var library:LibraryStore
  @StateObject private var player:AudioPlayer
  init(){let store=LibraryStore();_library=StateObject(wrappedValue:store);let audio=AudioPlayer();audio.library=store;_player=StateObject(wrappedValue:audio)}
  var body:some Scene{WindowGroup{RootView().environmentObject(library).environmentObject(player).preferredColorScheme(.dark)}}
}
