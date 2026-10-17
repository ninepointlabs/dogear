import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import Dogear
import "../components"

DgDialog {
    id: dialog
    title: "Settings"

    onOpened: { field.text = App.exportDirIsDefault ? "" : App.exportDir; field.forceActiveFocus() }

    function save() {
        App.setExportDir(field.text)
        close()
    }

    DgText {
        text: "Markdown export folder"
        font.weight: Font.DemiBold
    }
    DgText {
        Layout.fillWidth: true
        text: "Point this at a folder in your Obsidian vault. Each PDF exports to <name>.md there."
        secondary: true
        role: "small"
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.spaceLg
        DgTextField {
            id: field
            Layout.fillWidth: true
            placeholderText: App.exportDirIsDefault ? App.exportDir : "Default folder"
            Keys.onReturnPressed: dialog.save()
            Keys.onEnterPressed: dialog.save()
        }
        DgButton { text: "Choose…"; onClicked: folderDialog.open() }
    }
    DgText {
        Layout.fillWidth: true
        text: "Leave empty for the default. Annotations are stored in " + App.dataDir + " (your PDFs are never modified)."
        muted: true
        role: "caption"
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }

    FolderDialog {
        id: folderDialog
        title: "Markdown export folder"
        onAccepted: field.text = selectedFolder.toString().replace(/^file:\/\//, "")
    }

    buttons: [
        DgButton { text: "Cancel"; hint: "Esc"; onClicked: dialog.close() },
        DgButton { text: "Save"; hint: "Enter"; variant: "primary"; onClicked: dialog.save() }
    ]
}
