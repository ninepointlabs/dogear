import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

// No document open: the library. Every PDF opened in Dogear, searchable
// (titles, folders, categories and the text of your marks), sortable and
// filed under categories.
FocusScope {
    id: start
    objectName: "library"

    property var prompt: null
    property var confirm: null
    property var categoriesDialog: null
    signal openRequested()

    readonly property var sorts: [
        { key: "recent", name: "Recent" }, { key: "title", name: "Title" },
        { key: "marks", name: "Most marked" }, { key: "added", name: "Added" }
    ]
    property string sort: "recent"
    property string category: ""
    property int rev: 0
    readonly property string query: search.text
    readonly property var rows: (rev, App.library(query, sort, category))
    readonly property var cats: (rev, App.categoryList())

    function refresh() { rev++ }
    function cycleSort() {
        const i = sorts.findIndex(s => s.key === sort)
        sort = sorts[(i + 1) % sorts.length].key
    }
    function openRow(row) { if (row && row.path) Doc.open(row.path) }
    function focusList() { list.forceActiveFocus() }
    function editCategories(row) {
        if (row && categoriesDialog) categoriesDialog.edit(row, start.focusList)
    }
    function renameDocument(row) {
        if (!prompt || !row) return
        prompt.placeholder = row.pdfTitle || row.fileName
        prompt.ask("Rename “" + row.title + "”", row.label || row.title, name => {
            // Clearing the name (or typing the PDF's own title) goes back to it.
            App.renameDocument(row.sha256, name.trim() === (row.pdfTitle || "") ? "" : name)
        }, () => { prompt.placeholder = ""; start.focusList() })
    }
    function removeDocument(row) {
        if (!confirm || !row) return
        const marks = row.marks ? row.marks + " mark" + (row.marks > 1 ? "s" : "") : "no marks"
        confirm.ask("Remove “" + row.title + "” from the library?",
            "Its " + marks + (row.copy ? " and Dogear's copy of the PDF" : "") + " go to a removed folder in "
            + App.dataDir + ", where you can get them back. The PDF itself"
            + (row.original ? " (" + row.folder + "/" + row.fileName + ")" : "") + " is not touched.",
            "Remove", () => {
                const at = list.currentIndex
                if (App.removeDocument(row.sha256)) Qt.callLater(() => {
                    list.currentIndex = Math.min(at, list.count - 1)
                })
            }, start.focusList, true)
    }
    function newCategory() {
        if (!prompt) return
        prompt.ask("New category", "", name => {
            const made = App.addCategory(name)
            if (made) start.category = made
        }, () => catList.forceActiveFocus())
    }
    function renameCategory(c) {
        if (!prompt || !c || !c.user) return
        prompt.ask("Rename category", c.name, name => {
            App.renameCategory(c.key, name)
            if (start.category === c.key) start.category = ""
        }, () => catList.forceActiveFocus())
    }

    Component.onCompleted: { refresh(); list.forceActiveFocus() }
    Connections {
        target: App
        function onLibraryChanged() { start.refresh() }
    }

    Keys.onPressed: event => {
        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier)) return
        if (event.text === "/") { search.forceActiveFocus(); event.accepted = true }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spaceHuge
        spacing: Theme.spaceXl

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceLg
            DgText {
                text: AppInfo.name
                role: "display"
                font.weight: Font.Bold
            }
            DgText {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignBaseline
                text: AppInfo.tagline
                secondary: true
            }
            DgText {
                text: "or drop a PDF here"
                muted: true
                role: "small"
            }
            DgButton {
                text: "Open PDF"
                hint: "Ctrl+O"
                variant: "primary"
                onClicked: start.openRequested()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spaceXl

            // Categories.
            ColumnLayout {
                Layout.preferredWidth: 15 * Theme.fontBody
                Layout.fillHeight: true
                spacing: Theme.spaceSm
                DgText {
                    text: "Categories"
                    role: "subtitle"
                    font.weight: Font.DemiBold
                }
                PanelList {
                    id: catList
                    objectName: "categoryList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    focus: false
                    model: start.cats
                    currentIndex: Math.max(0, start.cats.findIndex(c => c.key === start.category))
                    onCurrentIndexChanged: if (activeFocus && currentIndex >= 0 && model[currentIndex]) start.category = model[currentIndex].key
                    onActivated: start.focusList()
                    onDone: start.focusList()
                    Keys.onPressed: event => {
                        const c = currentIndex >= 0 ? model[currentIndex] : null
                        if (event.key === Qt.Key_Right || event.key === Qt.Key_L || event.key === Qt.Key_Tab) start.focusList()
                        else if (event.key === Qt.Key_N) start.newCategory()
                        else if (c && c.user && (event.key === Qt.Key_F2 || event.key === Qt.Key_R)) start.renameCategory(c)
                        else if (c && c.user && event.key === Qt.Key_Delete) { start.category = ""; App.removeCategory(c.key) }
                        else return
                        event.accepted = true
                    }
                    delegate: PanelRow {
                        id: crow
                        required property var modelData
                        onClicked: start.category = modelData.key
                        onDoubleClicked: start.renameCategory(modelData)
                        RowLayout {
                            width: parent.width
                            DgText {
                                Layout.fillWidth: true
                                text: crow.modelData.name
                                font.italic: !crow.modelData.user
                            }
                            DgText {
                                text: crow.modelData.count
                                role: "caption"
                                muted: true
                            }
                        }
                    }
                }
                DgButton {
                    text: "New category"
                    hint: "n"
                    variant: "ghost"
                    focusPolicy: Qt.NoFocus
                    onClicked: start.newCategory()
                }
            }

            // Documents.
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.spaceMd

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spaceLg
                    DgTextField {
                        id: search
                        objectName: "librarySearch"
                        Layout.fillWidth: true
                        placeholderText: "Search titles, folders, categories and your marks  ( / )"
                        Keys.onDownPressed: start.focusList()
                        Keys.onReturnPressed: { start.focusList(); start.openRow(list.model[0]) }
                        Keys.onEnterPressed: { start.focusList(); start.openRow(list.model[0]) }
                        Keys.onEscapePressed: { text = ""; start.focusList() }
                    }
                    Row {
                        spacing: Theme.spaceXxs
                        DgText {
                            anchors.verticalCenter: parent.verticalCenter
                            rightPadding: Theme.spaceSm
                            text: "Sort"
                            muted: true
                            role: "small"
                        }
                        Repeater {
                            model: start.sorts
                            DgButton {
                                required property var modelData
                                text: modelData.name
                                variant: start.sort === modelData.key ? "secondary" : "ghost"
                                focusPolicy: Qt.NoFocus
                                onClicked: start.sort = modelData.key
                            }
                        }
                    }
                }

                PanelList {
                    id: list
                    objectName: "libraryList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: start.rows
                    emptyText: start.query ? "Nothing matches “" + start.query + "”."
                        : start.category ? "No documents in this category yet. Press c on a document to file it here."
                        : "Open a PDF to start your library."
                    onActivated: (i, item) => start.openRow(item)
                    onDone: if (start.query) search.text = ""
                    Keys.onPressed: event => {
                        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier)) return
                        const row = currentIndex >= 0 ? model[currentIndex] : null
                        if (event.key === Qt.Key_Left || event.key === Qt.Key_H || event.key === Qt.Key_Backtab) catList.forceActiveFocus()
                        else if (event.key === Qt.Key_C && row) start.editCategories(row)
                        else if ((event.key === Qt.Key_F2 || event.key === Qt.Key_R) && row) start.renameDocument(row)
                        else if (event.key === Qt.Key_Delete && row) start.removeDocument(row)
                        else if (event.key === Qt.Key_S) start.cycleSort()
                        else if (event.key === Qt.Key_N) start.newCategory()
                        else if (event.key === Qt.Key_J) incrementCurrentIndex()
                        else if (event.key === Qt.Key_K) decrementCurrentIndex()
                        else return
                        event.accepted = true
                    }

                    delegate: PanelRow {
                        id: row
                        required property var modelData
                        opacity: modelData.path ? 1 : 0.5
                        onClicked: list.forceActiveFocus()
                        onDoubleClicked: start.openRow(modelData)

                        RowLayout {
                            width: parent.width
                            spacing: Theme.spaceLg
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                DgText {
                                    Layout.fillWidth: true
                                    text: row.modelData.title
                                    font.weight: Font.DemiBold
                                }
                                DgText {
                                    // A renamed document still shows what it's called on disk.
                                    Layout.fillWidth: true
                                    visible: row.modelData.label.length > 0 && row.modelData.pdfTitle.length > 0
                                        && row.modelData.pdfTitle !== row.modelData.label
                                    text: row.modelData.pdfTitle
                                    role: "caption"
                                    secondary: true
                                    elide: Text.ElideRight
                                }
                                DgText {
                                    Layout.fillWidth: true
                                    text: row.modelData.original ? row.modelData.folder + "/" + row.modelData.fileName
                                        : row.modelData.path ? "Original not found · opens Dogear's copy"
                                        : "Missing: " + row.modelData.folder + "/" + row.modelData.fileName
                                    role: "caption"
                                    muted: true
                                    elide: Text.ElideMiddle
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    Layout.topMargin: visible ? Theme.spaceXs : 0
                                    visible: row.modelData.categories.length > 0 || row.modelData.inMarks
                                    spacing: Theme.spaceXs
                                    Repeater {
                                        model: row.modelData.categories
                                        Rectangle {
                                            required property string modelData
                                            width: chip.implicitWidth + 2 * Theme.spaceSm
                                            height: chip.implicitHeight + Theme.spaceXxs * 2
                                            radius: height / 2
                                            color: Theme.tint(Theme.accent, 0.18)
                                            DgText {
                                                id: chip
                                                anchors.centerIn: parent
                                                text: parent.modelData
                                                role: "caption"
                                            }
                                        }
                                    }
                                    DgText {
                                        visible: row.modelData.inMarks
                                        text: "found in your marks"
                                        role: "caption"
                                        color: Theme.accent
                                    }
                                }
                            }
                            // Mouse actions for the row under the pointer or selected.
                            Row {
                                visible: row.hovered || row.isCurrent
                                spacing: Theme.spaceXxs
                                DgButton { text: "Rename"; hint: "F2"; variant: "ghost"; focusPolicy: Qt.NoFocus; onClicked: start.renameDocument(row.modelData) }
                                DgButton { text: "Categories"; hint: "c"; variant: "ghost"; focusPolicy: Qt.NoFocus; onClicked: start.editCategories(row.modelData) }
                                DgButton { text: "Remove"; hint: "Del"; variant: "ghost"; focusPolicy: Qt.NoFocus; onClicked: start.removeDocument(row.modelData) }
                            }
                            ColumnLayout {
                                spacing: 0
                                DgText {
                                    Layout.alignment: Qt.AlignRight
                                    text: {
                                        const m = row.modelData, parts = []
                                        if (m.highlights) parts.push(m.highlights + " highlight" + (m.highlights > 1 ? "s" : ""))
                                        if (m.notes) parts.push(m.notes + " note" + (m.notes > 1 ? "s" : ""))
                                        if (m.answers) parts.push(m.answers + " answer" + (m.answers > 1 ? "s" : ""))
                                        if (m.bookmarks) parts.push(m.bookmarks + " bookmark" + (m.bookmarks > 1 ? "s" : ""))
                                        return parts.length ? parts.join(" · ") : "No marks yet"
                                    }
                                    role: "small"
                                    secondary: true
                                }
                                DgText {
                                    Layout.alignment: Qt.AlignRight
                                    text: row.modelData.openedText
                                    role: "caption"
                                    muted: true
                                }
                            }
                        }
                    }
                }

                DgText {
                    text: "Enter open · / search · s sort · F2 rename · c categories · Del remove · n new category · ← categories"
                    role: "caption"
                    muted: true
                }
            }
        }
    }
}
