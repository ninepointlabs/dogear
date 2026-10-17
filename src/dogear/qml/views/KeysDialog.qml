import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

DgDialog {
    id: dialog
    title: "Keyboard shortcuts"
    width: Math.min(parent ? parent.width - 2 * Theme.spaceHuge : 720, 60 * Theme.fontBody)

    readonly property var groups: [
        { name: "Files", keys: [
            ["Ctrl+O", "Open a PDF"], ["Ctrl+W  Ctrl+L", "Close, back to the library"], ["Ctrl+E", "Export to Markdown"],
            ["Ctrl+,", "Settings"], ["Ctrl+Q", "Quit"], ["F1  ?", "This list"]] },
        { name: "Reading", keys: [
            ["j k  ↓ ↑", "Scroll"], ["h l  ← →", "Scroll sideways"], ["Space  Shift+Space", "Screen down / up"],
            ["J K", "Next / previous page"], ["g G  Home End", "First / last page"], ["Ctrl+G", "Go to page"],
            ["+ -  Ctrl+wheel", "Zoom"], ["0  Ctrl+0", "Fit width"], ["Alt+←  Backspace", "Back after a jump"]] },
        { name: "Annotate", keys: [
            ["drag", "Select text (double-click: word)"], ["1–5", "Highlight selection in a color"],
            ["a", "Highlight and add a note"], ["Ctrl+C", "Copy selection"], ["click highlight", "Color, note, delete"], ["hover highlight", "Show its note"],
            ["b  Ctrl+D", "Bookmark this page"], ["Ctrl+N", "New document note"]] },
        { name: "Answer lines", keys: [
            ["click a line  i", "Type on it (i: first line in view)"], ["Tab  Shift+Tab", "Next / previous line"],
            ["Enter", "Next line (ruled lines: new line)"], ["Ctrl+=  Ctrl+-", "Answer text bigger / smaller"],
            ["Esc", "Done typing"]] },
        { name: "Find and panels", keys: [
            ["/  Ctrl+F", "Search"], ["Enter  n", "Next match"], ["Shift+Enter  N", "Previous match"],
            ["Ctrl+\\  F9", "Toggle sidebar"], ["Ctrl+1 … 4", "Contents, Highlights, Bookmarks, Notes"],
            ["Esc", "Back to the page"]] },
        { name: "Library", keys: [
            ["/", "Search (also inside your marks)"], ["s", "Next sort order"], ["c", "Categories of a document"], ["F2  Del", "Rename / remove a document"],
            ["n", "New category"], ["← →", "Categories / documents"], ["F2  Del (categories)", "Rename / delete a category"]] }
    ]

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: Theme.spaceHuge * 2
        rowSpacing: Theme.spaceXl

        Repeater {
            model: dialog.groups
            ColumnLayout {
                required property var modelData
                Layout.alignment: Qt.AlignTop
                Layout.fillWidth: true
                spacing: Theme.spaceSm
                DgText { text: modelData.name; font.weight: Font.DemiBold; color: Theme.accent }
                Repeater {
                    model: modelData.keys
                    RowLayout {
                        required property var modelData
                        spacing: Theme.spaceLg
                        DgText {
                            Layout.preferredWidth: 10 * Theme.fontBody
                            Layout.alignment: Qt.AlignTop
                            text: modelData[0]
                            role: "small"
                            font.weight: Font.DemiBold
                        }
                        DgText {
                            Layout.fillWidth: true
                            text: modelData[1]
                            role: "small"
                            secondary: true
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                        }
                    }
                }
            }
        }
    }

    buttons: [ DgButton { text: "Close"; hint: "Esc"; variant: "primary"; onClicked: dialog.close() } ]
}
