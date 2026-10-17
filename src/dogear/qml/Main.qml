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

    Shortcut { sequences: [StandardKey.Quit, "Ctrl+Q"]; onActivated: { Doc.close(); Qt.quit() } }
    Shortcut { sequences: [StandardKey.Open]; onActivated: openDialog.open() }
    Shortcut { sequences: ["Ctrl+W"]; enabled: Doc.loaded; onActivated: Doc.close() }
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
        StartView { onOpenRequested: openDialog.open() }
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
    SettingsDialog { id: settings }
    KeysDialog { id: keys }
    DgToast { id: toast }

    Connections {
        target: Doc
        function onMessage(text) { toast.show(text) }
    }
}
