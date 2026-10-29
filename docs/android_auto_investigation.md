# Brave Debug / Android Auto investigation

## Status

**Implemented — Awaiting Real-Car Verification.** Launch through Android Auto's
Desktop Head Unit (DHU) is runtime-verified on the Galaxy A53, and the user
subsequently confirmed that their test worked. A full real-car acceptance run
has not been recorded. At the user's request, this implementation uses AA
Browser's experimental game-category/native-activity approach in local Debug
builds only. Brave remains a browser; this is not official Android Auto browser
support.

This report supersedes the earlier workspace-level `ANDROID_AUTO_BRAVE.md` and
its claims that navigation intent categories grant a browser a car surface.
In particular, its driving-mode instructions are not applicable: the browser
must not be made available to the driver while driving.

## A. Evidence and root cause

Input: `/home/hassan/brave-development/Document from Hassan/dumpstate.txt`.
Line references below refer to that report, not the earlier October 28 report.

| Time on October 29 | Line | Evidence |
| --- | --- | --- |
| 17:38:37.254 | 304014 | Media provider enumerates `com.brave.browser_default/com.brave.playlist.playback_service.VideoPlaybackService` as `appCategory=MEDIA`, `isNativeApp=false`, `isParkedOnly=false`. |
| 17:38:37.279–.280 | 304033–304036 | Native-app module is present; car compatibility and touch checks pass. |
| 17:38:37.305 | 304074 | `CAR.VALIDATOR: Package DENIED; Not allowed native app -1 [com.brave.browser_default]`. |
| 17:38:37.306–.308 | 304075–304077 | `No opted-in native apps found`; `App provider CNA found available apps {}`. |
| 17:38:51.427 | 318113 | Media intent processor handles an explicit intent targeting Brave's **Playlist service**. |
| 17:38:52.493 | 318996 | ActivityManager denies that bind: `requires android.permission.BIND_MEDIA_BROWSER_SERVICE`. |
| 17:38:52.494 | 318999 | `GH.MediaBCConnection: onConnectionFailed`. |

The October 29 report shows **two independent failed paths**:

1. The native parked-app path stops at host eligibility validation, before
   `ChromeTabbedActivity` is launched. The capture contains no ActivityTaskManager
   `START`, `Displayed`, or activity-create/resume event for Brave's browser
   activity. The host's native-app list is empty. There is consequently no
   evidence here of a Chromium renderer, lifecycle, or secondary-display crash.
2. The visible launcher entry selects the Playlist media component. The
   application-level `<uses name="media"/>` descriptor added by our integration,
   combined with the existing media-browser service action, advertises that
   separate component. A media browser connection is a media hierarchy/session
   contract, **not a request to project an arbitrary browser activity**. Making
   that bind succeed would not establish full-browser launch.

Playlist is supplied by
`third_party/android_deps/libs/com_brave_playlist/playlist_release.aar`, rather
than a `VideoPlaybackService.java` in this checkout. Inspecting its manifest and
`javap` output confirms the original private service, `MediaLibraryService`
superclass, ExoPlayer/media session, and a session activity PendingIntent from
`PlaylistUtils.playlistNotificationIntent`. The class does not override media
library root/children browsing callbacks. Its existing media actions predate
our car integration; the added application descriptor made them relevant to
this host's media discovery. Phone Playlist callers remain in the app's UID.

The permission added in commit `1e9b5a7ef46` caused the new bind denial. It did
not repair native-app eligibility. The host cannot satisfy that service
permission in this capture. The public API 37 SDK's `android.Manifest.permission`
does not even contain a `BIND_MEDIA_BROWSER_SERVICE` constant; it was not a
verified Android Auto binding contract and should not have been introduced.

The log's `-1` is an opaque validator value. The inspected APK has no explicit
`appCategory` (Android's undefined category is also -1), but without the host's
implementation we cannot prove that this number is exclusively a category
check, nor exclude additional host eligibility/allowlist checks.

The report records the installer as `com.google.android.packageinstaller`
(for example, line 307050) and PlayGearheadService reports `app owners empty`
(300220). Those facts do **not** prove an installer-only cause. We do not spoof
the installer, modify the Android Auto host, or claim that “Unknown sources”
overrides native parked-app eligibility.

### Platform documentation

Google's [parked-app overview](https://developer.android.com/training/cars/parked)
lists browsers for **Android Automotive OS**, not Android Auto. The
[Android Auto parked-app guide](https://developer.android.com/training/cars/parked/auto)
explicitly states: “Games are the only parked app category supported by Android
Auto at this time.” It also explains that `MAIN` + `CAR_LAUNCHER` is the activity
discovery declaration, not automatic eligibility. Navigation uses the
[Car App Library](https://developer.android.com/training/cars/apps), category
requirements and templates; its surface permission does not turn a browser
activity into an approved navigation app. Documentation checked October 29, 2026.

Thus the failed APK's host rejection is consistent with the documented
limitation. With the experimental Debug category and corrected launcher, the
same phone's host accepted Brave's native activity during the subsequent DHU
test. Other hosts may enforce additional checks; real-car compatibility still
needs verification. This is not a claim that Chromium cannot render on a
secondary Android display.

## B. AA Browser comparison

Cloned source: `/tmp/opencode/AABrowser-reference`, commit
`878c0b5aaf0d8ddbfbf275fac4f9d218cf6738e6` (version 3.3).
An existing workspace reference checkout at
`/home/hassan/brave-development/reference/AABrowser`, commit
`1c2200c4cb0d054532d2e74528d1e8d000fc71b5`, also declares `appCategory="game"`.
Neither is proven to be the exact APK installed by the user.

| Aspect | AA Browser source inspected | Brave before this cleanup |
| --- | --- | --- |
| Rendering | `MainActivity`, AppCompat/Compose UI with Android WebView tabs | Actual Chromium `ChromeTabbedActivity`, native initialization, compositor, tab/profile system |
| Launcher | `MainActivity`: `MAIN`, `LAUNCHER`, `CAR_LAUNCHER` | Phone launcher alias targets `ChromeTabbedActivity`; separate car filter added directly to that activity |
| Application category | **`android:appCategory="game"`** | No explicit category in packaged APK |
| Other declarations | Navigation/maps categories, `distractionOptimized`, Car App permissions, media descriptor | Previously copied the latter declarations, but not the game category |
| Media service | No media service declared in the app manifest | Existing private Playlist `MediaLibraryService` was accidentally advertised, then exported with an unusable permission |
| Display handling | Resizable `singleTop` activity; configuration-change declarations; normal activity window/WebView contexts | Resizable `singleTask` activity, existing Chromium multi-window handling and launcher dispatch |
| Lifecycle | Warm WebView in `onCreate`, inflate real view tree, `onNewIntent` processes URLs, WebView resume/pause and session cleanup | Staged Java/native Chromium startup; bytecode rewriter inserts `BraveActivity` as the superclass of `ChromeTabbedActivity` |
| OS/build | Minimum SDK 35; current target/compile SDK 37 | Inspected Debug APK minimum SDK 29, target SDK 37; phone reported as Android 16 |

AA Browser's inspected code does not implement a browser `CarAppService` or
bind a media service to draw its UI. It does not create/select a car display ID
with `VirtualDisplay`, `Presentation`, or `setLaunchDisplayId`; the host chooses
the activity display. Its UI uses activity resources, view insets and window
fullscreen controls. We found no installer-spoofing code in the inspected app
sources. Those are source observations, not verification of a particular
installed AA Browser version or a guarantee of compatibility across host versions.

The game declaration is a meaningful difference consistent with current parked
app support. It was excluded under the initial task constraints; the user's
subsequent instruction explicitly authorizes trying this approach. The current
candidate reproduces game-category/native-launcher eligibility, not the
reference app's unrelated navigation/media claims or distraction exemptions.
Changing Brave's launch mode or hardware acceleration was not justified by
the original host rejection. The subsequent DHU test reached Chromium native
initialization without a WebView replacement or secondary-display rewrite.

AA Browser is GPLv3. No implementation code was copied. Incorporating its code
into a distributed derivative would require a separate license compatibility
review, corresponding source, notices and applicable GPLv3 obligations.

There is no `com.kododake.aabrowser`/`aabrowser` match in the supplied report.
A same-phone successful AA Browser baseline, installed manifest comparison and
first runtime divergence remain unverified until the next capture.

## C. Implementation

- `android/java/AndroidManifest.xml`: remove the added car metadata/media
  advertisement; restore Playlist to upstream `exported="false"` without the
  added binding permission. Its existing actions and phone playback code stay
  unchanged. This restores the original private service boundary; it does not
  grant untrusted media controllers access.
- `android/BUILD.gn`, `android/java/brave-res/xml/automotive_app_desc.xml`: remove
  only the resource/registration introduced by the integration, which advertised
  media instead of a browser.
- `android/java/AndroidManifest_car_launcher.xml`: add `CAR_LAUNCHER` to the
  existing `MAIN` + `LAUNCHER` phone launcher alias only when `channel=default`
  and `is_debug=true`. Like AA Browser, the same launcher component serves both
  displays. The alias targets the real `ChromeTabbedActivity`; no second phone
  icon, wrapper activity, or media-service browser launch.
- `build/android/config.gni`: register the new Jinja include as a declared
  manifest input, so the build checks it and tracks its dependencies.
- `rewrite/chrome/android/java/AndroidManifest.xml.yaml` and its generated
  `patches/chrome-android-java-AndroidManifest.xml.patch`: include the above
  category fragment and declare `appCategory="game"` only for local Debug;
  remove earlier navigation/maps filters, surface permissions and arbitrary
  layout metadata. These changes are generated by Plaster, rather than editing
  a managed patch without its owning rewrite.
- `rewrite/chrome/android/chrome_public_apk_tmpl.gni.yaml` and generated
  `patches/chrome-android-chrome_public_apk_tmpl.gni.patch`: pass the actual GN
  `is_debug` value to Jinja. Release and public-channel manifests do not gain
  the experimental category or car launcher entry.
- `android/java/org/chromium/chrome/browser/app/BraveActivity.java`: debuggable
  apps log pre/post-inflation, new intents, resume, focus and native startup
  milestones under `BraveDisplay`. Each records actual display/task IDs,
  configuration size/density, action/component and initialization state.
  No URL/extras, fixed display IDs, car detection assumptions, rendering changes
  or swallowed exceptions. Non-default display does not imply Android Auto.
- `tools/android/collect_android_auto.sh`: serial-selected capture with model
  confirmation, optional exact installed base-APK hash check, reference/Brave
  package/intent resolution, activity/display/window snapshots, live logcat and
  user observations. Does not clear logs or force-start on a car display.
- `tools/android/android_auto_manifest_test.py` and
  `tools/android/collect_android_auto_test.py`: six rendered-manifest regression
  checks and three synthetic ADB-tooling checks. These are not device tests.

No new dependency on the Car App Library, no profile/network changes, no host
security/parked-state bypass. Phone browsing and Playlist still require runtime
regression testing, despite preserving their original architecture.

## D. Build and artifact verification

Build from `src/brave` with the existing pnpm Debug/Android/ARM64 APK target,
symbol level 1, Blink/V8 symbols 0, requested Ninja jobs 3. Output:
`../out/android_Debug_arm64/apks/BraveMonoarm64.apk`.

Inspect the **packaged** manifest using SDK `aapt dump xmltree`, not only the
Jinja source. Expected: `com.brave.browser_default`, debuggable, game category;
the existing phone launcher alias gains the car category and still targets
`ChromeTabbedActivity`; Playlist stays private; no media car descriptor,
navigation/maps claims, distraction exemptions or extra media bind permission.
Release and public channels must not gain the game category or car filter.
Record the build log,
SHA-256, source base plus worktree diff, and generated manifest alongside the
artifact. These checks prove packaging only, not browser launch.

The ARM64 Debug APK built successfully (build ID
`effbe647-ee7c-4d20-a357-82d6991f1ddf`). The recorded background static analysis
finished 353 jobs with no failures. All nine manifest/tooling tests passed.
The final APK's manifest was inspected and its installed base APK was checked
on the phone. Both SHA-256 values match:

```text
a6d517682ad048d1678816f63c72eb2ac597f1e07ef6ce682414c7e5bcdd6b12
```

Build records, manifest dumps and a preserved APK are in the local workspace
directory `android-auto-investigation-artifacts/` (outside `brave-core`). The
compiled source was based on `1e9b5a7ef46` with this implementation applied;
documentation was finalized after runtime testing.

## E. Runtime evidence and acceptance

On October 30, 2026, wireless ADB connected to the Galaxy A53 (SM-A536E,
Android 16). USB transfers had failed with a truncated APK; wireless transfer
completed, its checksum matched, installation succeeded, and the installed
base APK's checksum was independently verified. VersionCode alone is not
sufficient: local rebuilds reuse `430000004`.

The simulator was connected to Android Auto's head unit server, and Brave was
tapped in its launcher, not force-started with an ADB activity command. Evidence
in the local `android-auto-dhu-Pr4gMd/phone-logcat-retry.txt` capture:

| Time on October 30 | Runtime evidence |
| --- | --- |
| 04:38:14.490 | `GH.ParkedNativeApps` includes `com.brave.browser_default/com.google.android.apps.chrome.Main` in the opted-in native-app list. |
| 04:38:48.619 | `ParkedNativeApp intent processor` processes that launcher component, not Playlist. |
| 04:38:49.410 | ActivityTaskManager starts it from Android Auto's UID; the host creates native display 82. |
| 04:38:52.267 | Brave first-run activity is displayed. DHU screenshots capture the rendered onboarding UI. |
| 04:39:14.756 | `cr_BraveDisplay: postInflation activity=ChromeTabbedActivity ... display=82`. |
| 04:39:18.238 | `cr_BraveDisplay: nativeInitialization.ready ... display=82 ... nativeReady=true`. |

After interacting with the simulator, the user reported: "i have tested it it
is working" and requested shutdown and commit. This is user confirmation in
the DHU test context, not a recorded pass of every physical-car criterion.
The simulator and its log capture were stopped; runtime logs and screenshots
remain local and are not included in the commit.

The host still emits media/projection discovery warnings for interfaces Brave
does not advertise. Those warnings are separate from the successful native
activity launch and must not be mistaken for another Playlist launch failure.

Actual car UI, touch/address-bar/HTTPS/back behavior, three consecutive launches,
phone/Playlist regressions and parked-state enforcement on the physical head
unit remain unverified as a complete checklist. Successful DHU launch is not
physical-car verification.

## F. Remaining restrictions

The requested browser category has no documented Android Auto native parked-app
support today. This Debug candidate attempts AA Browser's unofficial game-category
path instead. It may fail additional host validation and can stop working after
host updates; it must not be represented as an approved browser integration or
promoted to a public release. Android Automotive OS browser support is a different
deployment target, not a solution for this phone-to-car projection setup.

DHU now provides evidence that the host starts `ChromeTabbedActivity` on a
non-default display and reaches native initialization. Any remaining real-car
failure needs its own activity/display/startup trace; do not infer a rendering
failure from the earlier media error screen.

## G. Next test

1. Keep the car parked. Enable wireless debugging on the Galaxy A53 if its USB
   connection is occupied by Android Auto. Pair/connect using the phone's actual
   IP and ports (`adb pair IP:PAIR_PORT`, `adb connect IP:DEBUG_PORT`). Do not
   publish pairing codes. Check `adb devices -l` and use that serial explicitly.
2. Install the new diagnostic APK with `adb -s SERIAL install -r APK`. Do not
   uninstall/clear Brave data to solve a signature conflict; report the error.
3. From `src/brave`, run:

   ```bash
   bash tools/android/collect_android_auto.sh SERIAL \
     "$HOME/brave-development/android-auto-real-car-capture" \
     ../out/android_Debug_arm64/apks/BraveMonoarm64.apk
   ```

   Use a new output directory each time. Override `AA_REFERENCE_PACKAGE` if your
   working AA Browser uses a different package. Follow the reference and Brave
   prompts while leaving each actual head-unit UI/error visible for snapshots.
   Do not force-start Brave with `am start --display`: that skips the host gate.
4. Record AA Browser's installed version and whether it actually works in the
   same session. If Brave's icon disappears, report that explicitly; the removed
   media icon was never a valid full-browser entry point. No repeated rebuild is
   warranted solely to recreate that misleading icon.
5. If permitted to launch, test HTTPS (`https://example.com`), touch/address bar,
   back, close/reopen and three launches, then phone browsing and Playlist.
   Do not operate controls while driving or disable restrictions. Parked-state
   enforcement needs separate safe confirmation; do not mark it passed without
   observing it.
6. Share the capture directory after reviewing private data. If useful also run
   `adb -s SERIAL bugreport OUTPUT_DIRECTORY` immediately after reproduction.
   For exact installed AA Browser manifest comparison, its `pm path` results are
   captured; pull its base APK and any splits locally and inspect those, rather
   than assuming the current GitHub manifest is the installed one.
