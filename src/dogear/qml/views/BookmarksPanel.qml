import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

FocusScope {
    id: panel
    required property var reader
    required property var prompt
    signal done()
    function focusList() { list.forceActiveFocus() }

    function rename(item) {
        prompt.ask("Rename bookmark", item.name, name => Doc.renameBookmark(item.id, name), () => list.forceActiveFocus())
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spaceMd

        DgButton {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.spaceLg
            Layout.rightMargin: Theme.spaceLg
            text: "Bookmark this page"
            hint: "b"
            onClicked: panel.reader.addBookmarkHere()
        }

        PanelList {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: Doc.bookmarks
            emptyText: "No bookmarks yet.\nPress b to bookmark the page you are reading."
            onActivated: (i, item) => panel.reader.goToPage(item.page, item.y, true)
            onDone: panel.done()
            Keys.onPressed: event => {
                const item = currentIndex >= 0 ? model[currentIndex] : null
                if (!item) return
                if (event.key === Qt.Key_F2 || event.text === "r") { panel.rename(item); event.accepted = true }
                else if (event.key === Qt.Key_Delete) { Doc.removeBookmark(item.id); event.accepted = true }
            }

            delegate: PanelRow {
                id: row
                required property var modelData
                onClicked: panel.reader.goToPage(modelData.page, modelData.y, true)
                onDoubleClicked: panel.rename(modelData)

                RowLayout {
                    width: parent.width
                    spacing: Theme.spaceLg
                    DgText {
                        Layout.fillWidth: true
                        text: row.modelData.name
                    }
                    DgText {
                        text: "p. " + Doc.pageLabel(row.modelData.page)
                        role: "caption"
                        muted: true
                    }
                    DgText {
                        text: "×"
                        muted: !delMouse.containsMouse
                        color: delMouse.containsMouse ? Theme.danger : Theme.fgMuted
                        MouseArea {
                            id: delMouse
                            anchors.fill: parent
                            anchors.margins: -4
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Doc.removeBookmark(row.modelData.id)
                        }
                    }
                }
            }
        }

        DgText {
            Layout.fillWidth: true
            Layout.margins: Theme.spaceLg
            visible: list.count > 0
            text: "Enter jump · r rename · Del remove"
            role: "caption"
            muted: true
        }
    }
}
