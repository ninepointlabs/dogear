import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

// File one document under categories: tick existing ones or type a new one.
DgDialog {
    id: dialog

    property string sha: ""
    property var chosen: []

    function edit(entry, restore) {
        sha = entry.sha256
        title = "Categories for “" + entry.title + "”"
        chosen = entry.categories.slice()
        field.text = ""
        show(restore)
        field.forceActiveFocus()
    }
    function toggle(name, on) {
        const next = chosen.filter(c => c !== name)
        if (on) next.push(name)
        chosen = next
    }
    function addTyped() {
        const name = field.text.trim()
        if (!name) return false
        const made = App.addCategory(name)
        if (made) toggle(made, true)
        field.text = ""
        return true
    }
    function save() {
        addTyped()
        App.setCategories(sha, chosen)
        close()
    }

    DgText {
        Layout.fillWidth: true
        visible: App.categories.length === 0
        text: "No categories yet. Type a name below to make one."
        muted: true
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
    }

    Flow {
        Layout.fillWidth: true
        spacing: Theme.spaceLg
        visible: App.categories.length > 0
        Repeater {
            model: App.categories
            DgCheckBox {
                required property string modelData
                text: modelData
                checked: dialog.chosen.indexOf(modelData) >= 0
                onToggled: dialog.toggle(modelData, checked)
            }
        }
    }

    DgTextField {
        id: field
        Layout.fillWidth: true
        placeholderText: "New category, Enter to add"
        // Enter adds a typed name; on an empty field it saves.
        Keys.onReturnPressed: if (!dialog.addTyped()) dialog.save()
        Keys.onEnterPressed: if (!dialog.addTyped()) dialog.save()
    }

    buttons: [
        DgButton { text: "Cancel"; hint: "Esc"; onClicked: dialog.close() },
        DgButton { text: "Save"; hint: "Ctrl+Enter"; variant: "primary"; onClicked: dialog.save() }
    ]

    Shortcut {
        enabled: dialog.opened
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        onActivated: dialog.save()
    }
}
