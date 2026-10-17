import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

FocusScope {
    id: panel
    required property var reader
    signal done()
    function focusList() { list.forceActiveFocus() }

    // The outline entry for the page being read.
    readonly property int activeEntry: {
        const items = Doc.outline
        let best = -1
        for (let i = 0; i < items.length; i++)
            if (items[i].page <= reader.currentPage) best = i
        return best
    }

    PanelList {
        id: list
        anchors.fill: parent
        model: Doc.outline
        emptyText: "This PDF has no table of contents."
        onActivated: (i, item) => panel.reader.goToPage(item.page, item.y, true)
        onDone: panel.done()

        delegate: PanelRow {
            id: row
            required property var modelData
            onClicked: panel.reader.goToPage(modelData.page, modelData.y, true)

            RowLayout {
                width: parent.width
                spacing: Theme.spaceLg
                DgText {
                    Layout.fillWidth: true
                    Layout.leftMargin: row.modelData.level * Theme.spaceXxl
                    text: row.modelData.title
                    color: row.index === panel.activeEntry ? Theme.accent : Theme.fg
                    font.weight: row.modelData.level === 0 ? Font.DemiBold : Font.Normal
                    role: row.modelData.level === 0 ? "body" : "small"
                }
                DgText {
                    text: Doc.pageLabel(row.modelData.page)
                    role: "caption"
                    muted: true
                }
            }
        }
    }
}
