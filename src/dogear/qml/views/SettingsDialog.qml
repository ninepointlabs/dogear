import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import Dogear
import "../components"

DgDialog {
    id: dialog
    title: "Settings"

    onOpened: {
        field.text = App.exportDirIsDefault ? "" : App.exportDir
        keepCopies.checked = App.keepCopies
        copiesSize.text = "Copies use " + App.copiesSize() + " in " + App.libraryDir + "."
        field.forceActiveFocus()
    }

    function save() {
        App.setExportDir(field.text)
        App.setKeepCopies(keepCopies.checked)
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

    DgText {
        Layout.topMargin: Theme.spaceLg
        text: "Library"
        font.weight: Font.DemiBold
    }
    DgCheckBox {
        id: keepCopies
        text: "Keep a copy of every PDF I mark up"
    }
    DgText {
        Layout.fillWidth: true
        text: "Your marks then always have their PDF, even if the original is moved, renamed or deleted."
        secondary: true
        role: "small"
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }
    DgText {
        id: copiesSize
        Layout.fillWidth: true
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
