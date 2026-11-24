// Pure Kotlin/JVM library: the qbible rules (books, references, text, search,
// user data) with no Android dependency, so they run as plain JVM unit tests.
plugins {
    id("org.jetbrains.kotlin.jvm")
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    // org.json is part of the Android platform; on the JVM the tests supply it.
    compileOnly("org.json:json:20240303")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    // SQLite for the JVM tests (with FTS4), standing in for Android's built-in SQLite.
    testImplementation("org.xerial:sqlite-jdbc:3.47.1.0")
}

val repoRoot: File = rootDir.parentFile
tasks.test {
    dependsOn(":qbibleTestData")
    systemProperty("qbible.repoRoot", repoRoot.path)
    systemProperty("qbible.assetsDir", rootProject.layout.buildDirectory.dir("qbible-assets").get().asFile.path)
    systemProperty("qbible.testDir", rootProject.layout.buildDirectory.dir("qbible-test").get().asFile.path)
    inputs.dir(File(repoRoot, "spec"))
    inputs.file(File(repoRoot, "qbible/resources/books.json"))
    testLogging {
        events("failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
