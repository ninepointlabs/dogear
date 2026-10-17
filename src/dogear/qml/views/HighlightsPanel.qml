import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

FocusScope {
    id: panel
    required property var reader
    signal done()
    function focusList() { list.forceActiveFocus() }

    PanelList {
        id: list
        anchors.fill: parent
        model: Doc.highlights
        emptyText: "No highlights yet.\nSelect text on a page, then press 1–5."
        onActivated: (i, item) => panel.reader.openHighlight(item.id, false)
        onDone: panel.done()
        Keys.onPressed: event => {
            const item = currentIndex >= 0 ? model[currentIndex] : null
            if (!item) return
            if (event.text === "e") { panel.reader.openHighlight(item.id, true); event.accepted = true }
            else if (event.key === Qt.Key_Delete) { Doc.removeHighlight(item.id); event.accepted = true }
        }

        delegate: PanelRow {
            id: row
            required property var modelData
            onClicked: panel.reader.openHighlight(modelData.id, false)

            RowLayout {
                width: parent.width
                spacing: Theme.spaceLg
                Rectangle {
                    Layout.fillHeight: true
                    Layout.preferredWidth: 4
                    radius: 2
                    color: Theme.highlightColor(row.modelData.color)
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceXs
                    DgText {
                        text: "Page " + Doc.pageLabel(row.modelData.page)
                        role: "caption"
                        muted: true
                    }
                    DgText {
                        Layout.fillWidth: true
                        text: row.modelData.text || "(no text)"
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        role: "small"
                    }
                    DgText {
                        Layout.fillWidth: true
                        visible: row.modelData.note.length > 0
                        text: "✎ " + row.modelData.note
                        wrapMode: Text.Wrap
                        maximumLineCount: 4
                        role: "small"
                        color: Theme.accent
                    }
                }
            }
        }
    }
}
