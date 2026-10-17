import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Dogear
import "../components"

// Edit one highlight: color, note, copy, delete. The note saves when the
// popup closes (Esc, click outside, Done) and on Ctrl+Enter.
T.Popup {
    id: popup

    property string hid: ""
    readonly property var hl: (Doc.revision, hid ? Doc.highlight(hid) : ({}))
    property var restoreFocus: null

    function openFor(id, px, py, editNote, restore) {
        hid = id
        restoreFocus = restore || null
        note.text = hl.note || ""
        const p = parent
        x = Math.max(Theme.spaceLg, Math.min(px, p.width - width - Theme.spaceLg))
        y = py + Theme.spaceMd
        if (y + implicitHeight > p.height - Theme.spaceLg) y = Math.max(Theme.spaceLg, py - implicitHeight - 40)
        open()
        if (editNote) note.forceActiveFocus()
        else colorRow.forceActiveFocus()
    }

    function saveNote() {
        if (hid && hl.id && note.text !== (hl.note || "")) Doc.setHighlightNote(hid, note.text)
    }

    width: Math.min(30 * Theme.fontBody, parent ? parent.width - 2 * Theme.spaceLg : 400)
    implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
    padding: Theme.spaceXl
    modal: false
    focus: true
    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside

    onAboutToHide: saveNote()
    onClosed: {
        hid = ""
        if (restoreFocus) restoreFocus()
    }

    background: Rectangle {
        color: Theme.bgRaised
        radius: Theme.radius
        border.width: Theme.borderWidth
        border.color: Theme.focusRing
    }

    contentItem: ColumnLayout {
        spacing: Theme.spaceLg

        RowLayout {
            Layout.fillWidth: true
            DgText {
                text: popup.hl.page !== undefined ? "Page " + (popup.hl.page + 1) : ""
                role: "small"
                muted: true
            }
            Item { Layout.fillWidth: true }
            Row {
                id: colorRow
                spacing: Theme.spaceXs
                focus: true
                Keys.onPressed: event => {
                    const t = event.text
                    if (t >= "1" && t <= "5") { Doc.setHighlightColor(popup.hid, Doc.colors[Number(t) - 1]); event.accepted = true }
                    else if (event.key === Qt.Key_Delete || t === "d") { Doc.removeHighlight(popup.hid); popup.close(); event.accepted = true }
                    else if (t === "e" || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { note.forceActiveFocus(); event.accepted = true }
                    else if (t === "c") { Doc.copyText(popup.hl.text || ""); event.accepted = true }
                }
                Repeater {
                    model: Doc.colors
                    DgSwatch {
                        required property string modelData
                        required property int index
                        colorName: modelData
                        hint: String(index + 1)
                        current: popup.hl.color === modelData
                        onClicked: Doc.setHighlightColor(popup.hid, modelData)
                    }
                }
            }
        }

        DgText {
            Layout.fillWidth: true
            text: "“" + (popup.hl.text || "") + "”"
            wrapMode: Text.Wrap
            maximumLineCount: 4
            elide: Text.ElideRight
            secondary: true
            font.italic: true
        }

        DgTextArea {
            id: note
            Layout.fillWidth: true
            Layout.maximumHeight: 14 * Theme.fontBody
            placeholderText: "Add a note… (Ctrl+Enter to save)"
            Keys.onPressed: event => {
                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                    popup.close()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape) {
                    popup.close()
                    event.accepted = true
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceLg
            DgButton { text: "Delete"; hint: "d"; variant: "danger"; onClicked: { Doc.removeHighlight(popup.hid); popup.close() } }
            DgButton { text: "Copy"; hint: "c"; onClicked: Doc.copyText(popup.hl.text || "") }
            Item { Layout.fillWidth: true }
            DgButton { text: "Done"; hint: "Esc"; variant: "primary"; onClicked: popup.close() }
        }
    }
}
