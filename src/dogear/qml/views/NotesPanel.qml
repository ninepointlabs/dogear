import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Dogear
import "../components"

// General notes about the document, not tied to a page.
FocusScope {
    id: panel
    signal done()

    function focusList() {
        if (list.count > 0) {
            list.currentIndex = 0
            list.itemAtIndex(0) && list.itemAtIndex(0).edit()
        } else {
            addButton.forceActiveFocus()
        }
    }
    function newNote() {
        Doc.addNote("")
        Qt.callLater(() => {
            list.positionViewAtEnd()
            const item = list.itemAtIndex(list.count - 1)
            if (item) item.edit()
        })
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spaceMd

        DgButton {
            id: addButton
            Layout.fillWidth: true
            Layout.leftMargin: Theme.spaceLg
            Layout.rightMargin: Theme.spaceLg
            text: "New note"
            hint: "Ctrl+N"
            onClicked: panel.newNote()
            Keys.onEscapePressed: panel.done()
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: Theme.spaceLg
            boundsBehavior: Flickable.StopAtBounds
            model: Doc.notes
            T.ScrollBar.vertical: DgScrollBar {}

            delegate: Item {
                id: card
                required property var modelData
                required property int index
                width: list.width
                implicitHeight: col.implicitHeight

                function edit() { area.forceActiveFocus() }
                function save() { saveTimer.stop(); Doc.updateNote(modelData.id, area.text) }

                Component.onDestruction: if (saveTimer.running) save()

                Timer {
                    id: saveTimer
                    interval: 400
                    onTriggered: card.save()
                }

                ColumnLayout {
                    id: col
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: Theme.spaceLg
                    anchors.rightMargin: Theme.spaceLg
                    spacing: Theme.spaceXs

                    DgTextArea {
                        id: area
                        Layout.fillWidth: true
                        text: card.modelData.text
                        placeholderText: "Write a note about this document…"
                        onTextChanged: if (activeFocus) saveTimer.restart()
                        onActiveFocusChanged: if (!activeFocus && saveTimer.running) card.save()
                        Keys.onEscapePressed: { card.save(); panel.done() }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        DgText {
                            text: (card.modelData.updated || "").replace("T", " ").slice(0, 16)
                            role: "caption"
                            muted: true
                        }
                        Item { Layout.fillWidth: true }
                        DgText {
                            text: "Delete"
                            role: "caption"
                            color: delMouse.containsMouse ? Theme.danger : Theme.fgMuted
                            MouseArea {
                                id: delMouse
                                anchors.fill: parent
                                anchors.margins: -4
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Doc.removeNote(card.modelData.id)
                            }
                        }
                    }
                }
            }
        }

        DgText {
            Layout.fillWidth: true
            Layout.margins: Theme.spaceLg
            visible: list.count === 0
            text: "Notes about the whole document: what to study, questions for class, a summary."
            muted: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
    }
}
