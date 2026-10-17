import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import Dogear
import "../components"

DgDialog {
    id: dialog
    title: "Settings"
    signal aboutRequested()

    onOpened: {
        libraryField.text = App.libraryFolderIsDefault ? "" : App.libraryFolder
        libraryError.text = ""
        field.text = App.exportDirIsDefault ? "" : App.exportDir
        keepCopies.checked = App.keepCopies
        copiesSize.text = "Copies use " + App.copiesSize() + " in " + App.libraryDir + "."
        libraryField.forceActiveFocus()
    }

    function save() {
        // Moving the library first: the export folder's default lives in it.
        const error = App.setLibraryFolder(libraryField.text)
        if (error) {
            libraryError.text = error
            return
        }
        App.setExportDir(field.text)
        App.setKeepCopies(keepCopies.checked)
        close()
    }

    DgText {
        text: "Library folder"
        font.weight: Font.DemiBold
    }
    DgText {
        Layout.fillWidth: true
        text: "Your notes, categories and copies of the PDFs live here. To have the same library on several "
            + "computers, pick a folder you sync with Syncthing, Dropbox, Google Drive or the like."
        secondary: true
        role: "small"
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.spaceLg
        DgTextField {
            id: libraryField
            objectName: "libraryFolderField"
            Layout.fillWidth: true
            placeholderText: App.libraryFolderIsDefault ? App.libraryFolder : "Default folder"
            Keys.onReturnPressed: dialog.save()
            Keys.onEnterPressed: dialog.save()
        }
        DgButton { text: "Choose…"; onClicked: libraryDialog.open() }
    }
    DgText {
        Layout.fillWidth: true
        text: "Leave empty for the default. Changing it moves your library there; a Dogear library "
            + "already in that folder (from another computer) is merged with this one."
        muted: true
        role: "caption"
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }
    DgText {
        id: libraryError
        Layout.fillWidth: true
        visible: text.length > 0
        color: Theme.danger
        role: "small"
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }

    DgText {
        Layout.topMargin: Theme.spaceLg
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
        text: "Leave empty for the Notes folder in your library folder. Your PDFs are never modified."
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
        id: libraryDialog
        title: "Library folder"
        onAccepted: libraryField.text = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
    }
    FolderDialog {
        id: folderDialog
        title: "Markdown export folder"
        onAccepted: field.text = selectedFolder.toString().replace(/^file:\/\//, "")
    }

    buttons: [
        DgButton { text: "About Dogear"; variant: "ghost"; onClicked: dialog.aboutRequested() },
        DgButton { text: "Cancel"; hint: "Esc"; onClicked: dialog.close() },
        DgButton { text: "Save"; hint: "Enter"; variant: "primary"; onClicked: dialog.save() }
    ]
}
