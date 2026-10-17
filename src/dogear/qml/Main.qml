import QtQuick
import QtQuick.Window
import QtQuick.Dialogs
import Dogear
import "components"
import "views"

Window {
    id: window
    title: Doc.loaded ? Doc.title + " — " + AppInfo.name : AppInfo.name
    width: 1280
    height: 880
    minimumWidth: 640
    minimumHeight: 420
    visible: true
    color: Theme.bg

    function restoreFocus() {
        if (page.item && page.item.focusPages) page.item.focusPages()
        else if (page.item) page.item.forceActiveFocus()
    }

    onClosing: Doc.flush()

    Shortcut { sequence: "Ctrl+Q"; onActivated: { Doc.close(); Qt.quit() } }
    Shortcut { sequences: [StandardKey.Open]; onActivated: openDialog.open() }
    Shortcut { sequences: ["Ctrl+W", "Ctrl+L"]; enabled: Doc.loaded; onActivated: Doc.close() }
    Shortcut { sequences: ["Ctrl+,"]; onActivated: settings.show(window.restoreFocus) }
    Shortcut {
        sequences: ["F1", "?"]
        onActivated: keys.visible ? keys.close() : keys.show(window.restoreFocus)
    }

    Loader {
        id: page
        anchors.fill: parent
        focus: true
        sourceComponent: Doc.loaded ? reader : start
    }

    Component {
        id: start
        StartView {
            prompt: promptDialog
            confirm: confirmDialog
            categoriesDialog: categories
            onOpenRequested: openDialog.open()
        }
    }
    Component {
        id: reader
        ReaderView {
            prompt: promptDialog
            onSettingsRequested: settings.show(window.restoreFocus)
            onKeysRequested: keys.show(window.restoreFocus)
            onOpenRequested: openDialog.open()
        }
    }

    DropArea {
        anchors.fill: parent
        keys: ["text/uri-list"]
        onDropped: drop => {
            const url = drop.urls.length ? drop.urls[0].toString() : ""
            if (url.toLowerCase().endsWith(".pdf")) { Doc.open(url); drop.accept() }
        }
    }

    FileDialog {
        id: openDialog
        title: "Open PDF"
        nameFilters: ["PDF files (*.pdf *.PDF)", "All files (*)"]
        onAccepted: Doc.open(selectedFile.toString())
    }

    DgPrompt { id: promptDialog }
    DgConfirm { id: confirmDialog; objectName: "confirmDialog" }
    CategoriesDialog { id: categories }

    // Another copy of this document (a re-download, a new edition) already
    // has marks: offer to bring them over. Esc decides nothing; it asks again
    // next time.
    DgDialog {
        id: copyDialog
        objectName: "copyDialog"
        property var other: null
        title: "Bring your marks over?"
        message: {
            const o = other
            if (!o) return ""
            const parts = []
            if (o.highlights) parts.push(o.highlights + " highlight" + (o.highlights > 1 ? "s" : ""))
            if (o.notes) parts.push(o.notes + " note" + (o.notes > 1 ? "s" : ""))
            if (o.answers) parts.push(o.answers + " answer" + (o.answers > 1 ? "s" : ""))
            if (o.bookmarks) parts.push(o.bookmarks + " bookmark" + (o.bookmarks > 1 ? "s" : ""))
            return "This looks like another copy of “" + o.title + "” (" + o.fileName + "), where you have "
                + parts.join(", ") + ". Copy them into this one? If the pages differ, some may sit off and need fixing."
        }
        buttons: [
            DgButton { text: "Not this one"; onClicked: { Doc.declineCopy(copyDialog.other.sha256); copyDialog.close() } },
            DgButton { text: "Bring them over"; hint: "Enter"; variant: "primary"; onClicked: { Doc.adoptMarks(copyDialog.other.sha256); copyDialog.close() } }
        ]
        Shortcut {
            enabled: copyDialog.opened
            sequences: ["Return", "Enter"]
            onActivated: { Doc.adoptMarks(copyDialog.other.sha256); copyDialog.close() }
        }
    }
    SettingsDialog { id: settings }
    KeysDialog { id: keys }
    DgToast { id: toast }

    Connections {
        target: Doc
        function onMessage(text) { toast.show(text) }
        function onCopyFound(other) { copyDialog.other = other; copyDialog.show(window.restoreFocus) }
    }
}
