import QtQuick
import QtQuick.Templates as T
import Dogear
import "../components"

// Keyboard-navigable list used by the sidebar panels.
ListView {
    id: list

    property string emptyText: ""
    signal activated(int index, var item)
    signal done()

    clip: true
    focus: true
    keyNavigationEnabled: true
    boundsBehavior: Flickable.StopAtBounds
    highlightMoveDuration: 0
    currentIndex: -1
    spacing: Theme.spaceXxs
    T.ScrollBar.vertical: DgScrollBar {}

    Keys.onReturnPressed: if (currentIndex >= 0) activated(currentIndex, model[currentIndex])
    Keys.onEnterPressed: if (currentIndex >= 0) activated(currentIndex, model[currentIndex])
    Keys.onEscapePressed: done()
    onActiveFocusChanged: if (activeFocus && currentIndex < 0 && count > 0) currentIndex = 0

    DgText {
        anchors.centerIn: parent
        width: parent.width - 2 * Theme.panelPadding
        visible: list.count === 0
        text: list.emptyText
        muted: true
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        horizontalAlignment: Text.AlignHCenter
    }
}
