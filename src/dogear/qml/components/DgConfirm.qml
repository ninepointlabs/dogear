import QtQuick
import QtQuick.Layouts
import Dogear

// Yes/no question: ask(title, message, acceptText, onAccept, restore).
// Enter confirms, Esc cancels.
DgDialog {
    id: confirm

    property string acceptText: "OK"
    property bool danger: false
    property var onAccept: null

    function ask(title, message, acceptText, accept, restore, danger) {
        confirm.title = title
        confirm.message = message
        confirm.acceptText = acceptText || "OK"
        confirm.danger = !!danger
        onAccept = accept
        show(restore)
    }

    function accept() {
        const cb = onAccept
        onAccept = null
        close()
        if (cb) cb()
    }

    buttons: [
        DgButton { text: "Cancel"; hint: "Esc"; onClicked: confirm.close() },
        DgButton { text: confirm.acceptText; hint: "Enter"; variant: confirm.danger ? "danger" : "primary"; onClicked: confirm.accept() }
    ]

    Shortcut {
        enabled: confirm.opened
        sequences: ["Return", "Enter"]
        onActivated: confirm.accept()
    }
}
