// Root build for the qbible Android client. See README.md in this directory.
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.jvm") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
}

// ---------------------------------------------------------------------------
// Shared data generated from the repository (never copied into the source tree):
// App assets, in build/qbible-assets/ (packaged into the APK):
//   books.json         <- ../qbible/resources/books.json (the single book list)
//   kjv-android.sqlite <- ../build/translations/kjv.sqlite via tools/make_android_pack.py
//                         (FTS5 search index replaced by an equivalent FTS4 index)
// Test-only data, in build/qbible-test/ (never packaged):
//   differential.json, desktop-user.sqlite <- tools/differential_vectors.py
// ---------------------------------------------------------------------------
val repoRoot: File = rootDir.parentFile
val packDir = layout.buildDirectory.dir("qbible-assets")
val testDataDir = layout.buildDirectory.dir("qbible-test")
val python = providers.gradleProperty("qbible.python").getOrElse("python3")
val desktopPack: File = providers.gradleProperty("qbible.pack").map { File(it) }
    .getOrElse(File(repoRoot, "build/translations/kjv.sqlite"))

val buildDesktopPack by tasks.registering(Exec::class) {
    description = "Builds the desktop KJV pack (python3 -m qbible.build_data) if it is missing."
    onlyIf { !desktopPack.isFile }
    workingDir = repoRoot
    commandLine(python, "-m", "qbible.build_data")
    outputs.file(desktopPack)
}

val makeAndroidPack by tasks.registering(Exec::class) {
    description = "Converts the desktop pack's FTS5 index to FTS4 for Android's built-in SQLite."
    dependsOn(buildDesktopPack)
    val out = packDir.map { it.file("kjv-android.sqlite") }
    inputs.file(desktopPack)
    inputs.file(File(rootDir, "tools/make_android_pack.py"))
    inputs.dir(File(repoRoot, "qbible")).withPropertyName("qbiblePython")
    outputs.file(out)
    workingDir = repoRoot
    commandLine(python, File(rootDir, "tools/make_android_pack.py").path, desktopPack.path,
        out.get().asFile.path)
}

val copyBooksJson by tasks.registering(Copy::class) {
    from(File(repoRoot, "qbible/resources/books.json"))
    into(packDir)
}

val differentialVectors by tasks.registering(Exec::class) {
    description = "Runs the desktop engine on thousands of inputs for the Kotlin differential tests."
    dependsOn(buildDesktopPack)
    inputs.file(desktopPack)
    inputs.file(File(rootDir, "tools/differential_vectors.py"))
    inputs.dir(File(repoRoot, "qbible")).withPropertyName("qbiblePython")
    outputs.file(testDataDir.map { it.file("differential.json") })
    outputs.file(testDataDir.map { it.file("desktop-user.sqlite") })
    workingDir = repoRoot
    commandLine(python, File(rootDir, "tools/differential_vectors.py").path, testDataDir.get().asFile.path)
}

tasks.register("qbibleData") {
    description = "Generates every data file the app and the tests read."
    dependsOn(makeAndroidPack, copyBooksJson)
}

tasks.register("qbibleTestData") {
    description = "Generates the data the core unit tests read (including differential vectors)."
    dependsOn(makeAndroidPack, copyBooksJson, differentialVectors)
}
