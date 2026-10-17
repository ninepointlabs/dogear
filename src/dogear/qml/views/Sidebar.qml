import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

// Left panel: Contents, Highlights, Bookmarks, Notes (Ctrl+1..4).
Rectangle {
    id: sidebar

    required property var reader      // PageView
    required property var prompt      // DgPrompt
    property int tab: 0
    readonly property var tabs: ["Contents", "Highlights", "Bookmarks", "Notes"]

    signal done()  // Esc in a panel: hand focus back to the page

    function newNoteRequested() { notesPanel.newNote() }

    function show(i) {
        tab = i
        Qt.callLater(() => stack.children[i].focusList())
    }

    color: Theme.bgSunken

    Rectangle {
        anchors.right: parent.right
        width: Theme.borderWidth
        height: parent.height
        color: Theme.border
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.rightMargin: Theme.borderWidth
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.spaceLg
            spacing: Theme.spaceXs
            Repeater {
                model: sidebar.tabs
                Rectangle {
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    implicitHeight: Theme.controlHeight
                    radius: Theme.radius
                    color: sidebar.tab === index ? Theme.selectedFill : tabMouse.containsMouse ? Theme.hoverFill : "transparent"
                    DgText {
                        anchors.centerIn: parent
                        width: Math.min(implicitWidth, parent.width - 4)
                        text: modelData
                        role: "small"
                        color: sidebar.tab === index ? Theme.fg : Theme.fgSecondary
                        font.weight: sidebar.tab === index ? Font.DemiBold : Font.Normal
                    }
                    MouseArea {
                        id: tabMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: sidebar.show(index)
                    }
                }
            }
        }

        StackLayout {
            id: stack
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: sidebar.tab

            OutlinePanel { reader: sidebar.reader; onDone: sidebar.done() }
            HighlightsPanel { reader: sidebar.reader; onDone: sidebar.done() }
            BookmarksPanel { reader: sidebar.reader; prompt: sidebar.prompt; onDone: sidebar.done() }
            NotesPanel { id: notesPanel; onDone: sidebar.done() }
        }
    }
}
