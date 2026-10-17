import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

// No document open: open button and recent files.
FocusScope {
    id: start

    signal openRequested()

    Component.onCompleted: { App.refreshRecents(); list.forceActiveFocus() }

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * Theme.spaceHuge, 44 * Theme.fontBody)
        height: Math.min(parent.height - 2 * Theme.spaceHuge, implicitHeight)
        spacing: Theme.spaceXl

        DgText {
            text: AppInfo.name
            role: "display"
            font.weight: Font.Bold
        }
        DgText {
            text: AppInfo.tagline
            secondary: true
        }
        RowLayout {
            spacing: Theme.spaceLg
            DgButton {
                text: "Open PDF"
                hint: "Ctrl+O"
                variant: "primary"
                onClicked: start.openRequested()
            }
            DgText {
                text: "or drop a PDF on this window"
                muted: true
                role: "small"
            }
        }

        DgText {
            Layout.topMargin: Theme.spaceXl
            visible: list.count > 0
            text: "Recent"
            role: "subtitle"
            font.weight: Font.DemiBold
        }

        PanelList {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: Math.min(contentHeight, 18 * Theme.fontBody * 2)
            Layout.minimumHeight: count > 0 ? Theme.controlHeight * 2 : 0
            visible: count > 0
            model: App.recents
            onActivated: (i, item) => { if (item.exists) Doc.open(item.path) }
            Keys.onPressed: event => {
                const item = currentIndex >= 0 ? model[currentIndex] : null
                if (item && event.key === Qt.Key_Delete) { App.forgetRecent(item.path); event.accepted = true }
            }

            delegate: PanelRow {
                id: row
                required property var modelData
                opacity: modelData.exists ? 1 : 0.5
                onClicked: if (modelData.exists) Doc.open(modelData.path)

                RowLayout {
                    width: parent.width
                    spacing: Theme.spaceLg
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        DgText {
                            Layout.fillWidth: true
                            text: row.modelData.title
                        }
                        DgText {
                            Layout.fillWidth: true
                            text: row.modelData.exists ? row.modelData.folder + "/" + row.modelData.fileName
                                : "Missing: " + row.modelData.folder + "/" + row.modelData.fileName
                            role: "caption"
                            muted: true
                            elide: Text.ElideMiddle
                        }
                    }
                    DgText {
                        text: row.modelData.opened
                        role: "caption"
                        muted: true
                    }
                }
            }
        }
        DgText {
            visible: list.count > 0
            text: "Enter open · Del remove from list"
            role: "caption"
            muted: true
        }
    }
}
