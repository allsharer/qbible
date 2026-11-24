plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    // PLACEHOLDER application id: confirm before publishing (see HANDBACK.md).
    namespace = "org.qbible.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.qbible.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // No signing config here on purpose: see "Release signing" in HANDBACK.md / android/README.md.
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    sourceSets["main"].assets.srcDir(rootProject.layout.buildDirectory.dir("qbible-assets"))
    // Instrumented tests read the shared vectors from the repository's spec/.
    sourceSets["androidTest"].assets.srcDir(layout.buildDirectory.dir("spec-assets"))
    // ...and the generated differential vectors (see tools/differential_vectors.py).
    sourceSets["androidTest"].assets.srcDir(rootProject.layout.buildDirectory.dir("qbible-test"))
    packaging {
        resources.excludes += listOf("META-INF/{AL2.0,LGPL2.1}", "META-INF/*.kotlin_module")
    }
    lint {
        abortOnError = true
        warningsAsErrors = false
        disable += listOf("GradleDependency", "AndroidGradlePluginVersion", "OldTargetApi", "NewerVersionAvailable")
    }
    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
}

val copySpecAssets by tasks.registering(Copy::class) {
    from(File(rootDir.parentFile, "spec")) { include("*.json") }
    into(layout.buildDirectory.dir("spec-assets/spec"))
}
tasks.named("preBuild") { dependsOn(":qbibleData", copySpecAssets) }
tasks.matching { it.name == "preDebugAndroidTestBuild" }.configureEach { dependsOn(":qbibleTestData") }

dependencies {
    implementation(project(":core"))

    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    debugImplementation("androidx.compose.ui:ui-tooling")

    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
