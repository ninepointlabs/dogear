import QtQuick
import Dogear

// Transient notice at the bottom of the window.
Rectangle {
    id: toast

    function show(text) {
        label.text = text
        visible = true
        opacity = 1
        hideTimer.restart()
    }

    visible: false
    opacity: 0
    z: 100
    width: Math.min(parent.width - 4 * Theme.spaceHuge, label.implicitWidth + 2 * Theme.panelPadding)
    height: label.implicitHeight + 2 * Theme.spaceXl
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: Theme.spaceHuge * 2
    radius: Theme.radius
    color: Theme.bgRaised
    border.width: Theme.borderWidth
    border.color: Theme.focusRing

    Behavior on opacity { NumberAnimation { duration: 180 } }
    onOpacityChanged: if (opacity === 0) visible = false

    DgText {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, toast.width - 2 * Theme.panelPadding)
        wrapMode: Text.Wrap
        elide: Text.ElideNone
        horizontalAlignment: Text.AlignHCenter
    }

    Timer {
        id: hideTimer
        interval: 4000
        onTriggered: toast.opacity = 0
    }

    MouseArea {
        anchors.fill: parent
        onClicked: toast.opacity = 0
    }
}
