import QtQuick
import QtQuick.Templates as T
import Dogear

// A highlight color choice. `hint` shows the key that picks it.
T.AbstractButton {
    id: control

    property string colorName: "yellow"
    property bool current: false
    property string hint: ""

    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    focusPolicy: Qt.TabFocus
    hoverEnabled: true

    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    contentItem: Item {}
    background: Item {
        Rectangle {
            anchors.centerIn: parent
            width: parent.width - 2 * Theme.spaceSm
            height: width
            radius: width / 2
            color: Theme.highlights[control.colorName]
            border.width: control.current ? Theme.focusWidth : control.hovered ? 1 : 0
            border.color: Theme.fg

            DgText {
                anchors.centerIn: parent
                visible: control.hint.length > 0
                text: control.hint
                role: "caption"
                color: "#202020"
                font.weight: Font.DemiBold
            }
        }
        DgFocusFrame { shown: control.visualFocus }
    }
}
