import QtQuick
import QtQuick.Templates as T
import Dogear

// Multi-line themed text input that grows with its content.
T.TextArea {
    id: control

    implicitWidth: 24 * Theme.fontBody
    implicitHeight: Math.max(Theme.controlHeight * 2, contentHeight + topPadding + bottomPadding)
    padding: Theme.spaceLg
    leftPadding: Theme.controlPaddingX
    rightPadding: Theme.controlPaddingX

    color: Theme.fg
    placeholderTextColor: Theme.fgMuted
    selectionColor: Theme.selection
    selectedTextColor: Theme.fg
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    wrapMode: TextEdit.Wrap
    selectByMouse: true
    persistentSelection: true

    background: Rectangle {
        radius: Theme.radius
        color: Theme.bgInset
        border.width: Theme.borderWidth
        border.color: control.activeFocus ? Theme.focusRing : control.hovered ? Theme.borderStrong : Theme.border

        DgText {
            x: control.leftPadding
            y: control.topPadding
            width: control.width - control.leftPadding - control.rightPadding
            visible: control.text.length === 0 && control.preeditText.length === 0
            text: control.placeholderText
            color: control.placeholderTextColor
            font: control.font
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
    }
}
