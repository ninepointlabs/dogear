import QtQuick
import QtQuick.Layouts
import Dogear

// One-line question: ask(title, initial, onAccept).
DgDialog {
    id: prompt

    property string placeholder: ""
    property string acceptText: "OK"
    property var onAccept: null

    function ask(title, initial, accept, restore) {
        prompt.title = title
        field.text = initial || ""
        onAccept = accept
        show(restore)
        field.forceActiveFocus()
        field.selectAll()
    }

    function accept() {
        const cb = onAccept
        const value = field.text
        close()
        if (cb) cb(value)
    }

    onOpened: { field.forceActiveFocus(); field.selectAll() }

    DgTextField {
        id: field
        Layout.fillWidth: true
        placeholderText: prompt.placeholder
        Keys.onReturnPressed: prompt.accept()
        Keys.onEnterPressed: prompt.accept()
    }

    buttons: [
        DgButton { text: "Cancel"; hint: "Esc"; onClicked: prompt.close() },
        DgButton { text: prompt.acceptText; hint: "Enter"; variant: "primary"; onClicked: prompt.accept() }
    ]
}
