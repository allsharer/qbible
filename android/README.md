# qbible for Android

A native Android client for qbible: the King James Version, fully offline, with the same
reference rules, search and bookmark keys as the desktop app. No adverts, no analytics, no
accounts and **no permissions at all** (in particular, no network permission).

Status: first working version (0.1.0). It has been tested on an Android 15 (API 35) emulator,
not yet on a real phone. The application id `org.qbible.app` is a placeholder.

## Layout

| Path | What it is |
|---|---|
| `core/` | Pure Kotlin/JVM library: ports of `books.py`, `reference.py`, `textfmt.py`, `search.py` and `userdata.py`. No Android dependency, so it is tested with plain JVM unit tests. |
| `app/` | The Android app (Jetpack Compose, Material 3, single activity). |
| `tools/make_android_pack.py` | Makes the Android copy of the KJV pack (FTS5 index replaced by FTS4). Run by Gradle. |
| `tools/differential_vectors.py` | Runs the desktop Python engine on thousands of generated inputs for the Kotlin tests. Run by Gradle. |

Nothing is copied by hand into the app: at build time Gradle copies
`../qbible/resources/books.json` and converts `../build/translations/kjv.sqlite` (building it
with `python3 -m qbible.build_data` first if it is missing) into `build/qbible-assets/`, which
becomes the app's assets.

## How it works

- **Data.** The app ships `kjv-android.sqlite`: the desktop `kjv.sqlite` with its contents
  unchanged, except that the FTS5 table `verses_fts` is replaced by an FTS4 table
  `verses_fts4`. Android's built-in SQLite does not include FTS5 (checked: the API 35
  emulator has SQLite 3.44.3 without FTS5), but always includes FTS4. The FTS4 table stores
  each verse's tokens exactly as the FTS5 index holds them (verified token by token at build
  time), indexed with the `simple` tokenizer. On first start the pack is copied from the APK
  into app storage and opened read-only.
- **Search.** Each search term becomes one quoted FTS4 `MATCH` (a word, a phrase or a prefix),
  and the terms are combined with SQL `INTERSECT`, `UNION` and `EXCEPT`. This avoids FTS4's
  AND/OR/NOT query syntax, which depends on a compile option. Relevance order is SQLite FTS5's
  `bm25()` formula, recomputed in Kotlin from the same statistics, so results come back in the
  same order as on the desktop.
- **Rules.** The Kotlin port uses explicit Unicode character classes in place of Python's
  `\s`, `\d` and `\w`, so it behaves the same on the JVM and on Android's ICU regex engine.
- **User data.** `user.sqlite` in the app's database directory has the desktop's tables,
  migrations, timestamps and reference keys (`JHN.3.16-JHN.3.21`). A desktop `user.sqlite`
  opens unchanged (tested). Settings → Export/Import writes and reads a JSON file
  (`format: qbible-user-data`, version 1). Cloud backup is switched off; device-to-device
  transfer includes bookmarks, history and settings.

## Building

Requirements on Ubuntu: JDK 17, Python 3.10+, and the Android SDK (platform 35 and
build-tools 34 or 35). Gradle 8.11.1 is downloaded by the wrapper.

```sh
sudo apt install openjdk-17-jdk python3 unzip
# Android SDK command-line tools: https://developer.android.com/studio#command-line-tools-only
mkdir -p ~/android-sdk/cmdline-tools && cd ~/android-sdk/cmdline-tools
unzip ~/Downloads/commandlinetools-linux-*_latest.zip && mv cmdline-tools latest
yes | ~/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses
~/android-sdk/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"

cd qbible/android
echo "sdk.dir=$HOME/android-sdk" > local.properties
./gradlew :core:test          # JVM tests (shared vectors, differential tests, user data)
./gradlew assembleDebug       # app/build/outputs/apk/debug/app-debug.apk
~/android-sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
./gradlew connectedDebugAndroidTest   # with a device or emulator attached
```

Gradle properties: `-Pqbible.python=/path/to/python3`, `-Pqbible.pack=/path/to/kjv.sqlite`.

## Release signing (not set up)

The repository has **no signing keys** and no signing configuration. To publish:

1. Create an upload key once and keep it outside the repository, backed up:
   `keytool -genkeypair -v -keystore ~/keys/qbible-upload.jks -alias qbible -keyalg RSA -keysize 4096 -validity 10000`
2. Build the release APK or bundle: `./gradlew assembleRelease` (APK) or `./gradlew bundleRelease`
   (AAB for Google Play). Release builds are shrunk with R8.
3. Sign:
   - APK: `~/android-sdk/build-tools/35.0.0/zipalign -p 4 app-release-unsigned.apk aligned.apk` then
     `~/android-sdk/build-tools/35.0.0/apksigner sign --ks ~/keys/qbible-upload.jks --out qbible.apk aligned.apk`
   - AAB for Play: `jarsigner -keystore ~/keys/qbible-upload.jks app-release.aab qbible`, and enrol in
     Play App Signing.
4. Or add a `signingConfigs` block that reads the keystore path and passwords from
   `~/.gradle/gradle.properties` or environment variables. Never commit them.

Before publishing, confirm the application id (currently the placeholder `org.qbible.app`),
the app name and the icon, and raise `targetSdk` to whatever Google Play requires at the time.
