import QtQuick
import Dogear
import "../components"

// Row background for panel lists: hover, current (keyboard) and focus states.
Rectangle {
    id: row

    required property int index
    property ListView list: ListView.view
    readonly property bool isCurrent: list && list.currentIndex === index
    default property alias content: inner.data
    signal clicked()
    signal doubleClicked()

    width: list ? list.width : 0
    implicitHeight: inner.childrenRect.height + 2 * Theme.spaceMd
    color: isCurrent && list.activeFocus ? Theme.selectedFill : isCurrent ? Theme.focusFill : rowMouse.containsMouse ? Theme.hoverFill : "transparent"

    Item {
        id: inner
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.spaceMd
        anchors.leftMargin: Theme.rowPaddingX
        anchors.rightMargin: Theme.rowPaddingX
        height: childrenRect.height
    }

    MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { row.list.currentIndex = row.index; row.clicked() }
        onDoubleClicked: row.doubleClicked()
    }
}
