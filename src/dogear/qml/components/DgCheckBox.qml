import QtQuick
import QtQuick.Templates as T
import Dogear

// Themed check box with a text label. Space toggles it.
T.CheckBox {
    id: control

    implicitWidth: implicitIndicatorWidth + spacing + implicitContentWidth + leftPadding + rightPadding
    implicitHeight: Math.max(Theme.controlHeight, implicitContentHeight)
    padding: 0
    spacing: Theme.spaceMd
    hoverEnabled: true

    indicator: Rectangle {
        x: control.leftPadding
        anchors.verticalCenter: parent.verticalCenter
        implicitWidth: Math.round(Theme.fontBody * 1.2)
        implicitHeight: implicitWidth
        radius: Math.min(Theme.radius, 3)
        color: control.checked ? Theme.accent : Theme.bgInset
        border.width: Theme.borderWidth
        border.color: control.checked ? Theme.accent : control.hovered ? Theme.borderStrong : Theme.border

        DgText {
            anchors.centerIn: parent
            visible: control.checked
            text: "✓"
            color: Theme.accentFg
            role: "small"
            font.weight: Font.Bold
        }
        DgFocusFrame { shown: control.visualFocus }
    }

    contentItem: DgText {
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        text: control.text
    }
}
