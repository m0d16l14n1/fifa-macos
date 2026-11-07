// Keeps macOS from treating the game as idle background work.
//
// Without it, a game whose window is not frontmost (behind other apps, or a background test run) is App-Napped
// and its threads demoted to efficiency-core speed: frames come at uneven times. A user-initiated,
// latency-critical NSProcessInfo activity, held for the life of the process, prevents both (LibertyRecomp
// measured 7.7 against 51 FPS for the same scene on an M5 Air).
#import <Foundation/Foundation.h>

void Fifa19BeginGameActivity() {
  static id<NSObject> activity = [NSProcessInfo.processInfo
      beginActivityWithOptions:NSActivityUserInitiated | NSActivityLatencyCritical
                        reason:@"Running FIFA 19"];
  (void)activity;
}
