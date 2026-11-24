package org.qbible.app

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** End-to-end checks of the real UI on a device or emulator. */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class UiTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    private fun waitFor(text: String, substring: Boolean = false) =
        rule.waitUntilAtLeastOneExists(hasText(text, substring = substring), timeoutMillis = 20_000)

    private fun goTo(ref: String) {
        val field = rule.onNode(hasSetTextAction() and hasText("Go to passage", substring = true))
        field.performTextClearance()
        field.performTextInput(ref)
        field.performImeAction()
    }

    @Test
    fun referenceBoxOpensPassagesAndExplainsErrors() {
        waitFor("Go to passage")
        goTo("mar 4:1-")
        waitFor("Mark 4:1-41")
        goTo("John 22")
        waitFor("John has 21 chapters; there is no chapter 22.")
        // Nothing else was opened: the reader still shows Mark.
        rule.onAllNodesWithText("Mark 4:1-41")[0].assertIsDisplayed()
        goTo("1s 4:1")
        waitFor("1 Samuel 4:1")
        goTo("genesi 1:1")
        waitFor("Genesis 1:1")
    }

    @Test
    fun chapterNavigationCrossesBooks() {
        waitFor("Go to passage")
        goTo("Malachi 4")
        waitFor("Malachi 4")
        rule.onNodeWithContentDescription("Next chapter, Matthew 1").performClick()
        waitFor("Matthew 1")
    }

    @Test
    fun searchHighlightsAndOffersReferences() {
        waitFor("Go to passage")
        rule.onNodeWithText("Search").performClick()
        val field = rule.onNode(hasSetTextAction())
        field.performTextInput("\"Jesus wept\"")
        field.performImeAction()
        waitFor("1 verse matches", substring = true)
        rule.onNodeWithText("John 11:35").assertIsDisplayed()
        field.performTextClearance()
        field.performTextInput("john 3:16")
        field.performImeAction()
        waitFor("Open John 3:16")
        rule.onNodeWithText("Open John 3:16").performClick()
        waitFor("For God so loved the world", substring = true)
    }

    @Test
    fun bookmarkAPassage() {
        waitFor("Go to passage")
        goTo("Psalm 117")
        waitFor("Psalm 117")
        rule.onNode(SemanticsMatcher("bookmark button") {
            it.config.getOrNull(SemanticsProperties.ContentDescription)?.any { d -> d.endsWith("Psalm 117") && (d.startsWith("Bookmark") || d.startsWith("Edit bookmark")) } == true
        }).performClick()
        waitFor("Label (optional)")
        rule.onNodeWithText("Save").performClick()
        rule.onNodeWithText("Saved").performClick()
        waitFor("Bookmarks", substring = true)
        rule.waitUntilAtLeastOneExists(hasText("Psalm 117"), 10_000)
    }
}
