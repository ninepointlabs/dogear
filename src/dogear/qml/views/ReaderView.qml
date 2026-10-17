import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

// The open document: toolbar, optional search bar, sidebar and pages.
Item {
    id: reader

    required property var prompt
    property bool sidebarOpen: true
    property bool searchOpen: false
    readonly property alias pages: pages

    signal settingsRequested()
    signal keysRequested()
    signal openRequested()

    function focusPages() { pages.forceActiveFocus() }
    function openSearch() {
        searchOpen = true
        Qt.callLater(() => { searchField.forceActiveFocus(); searchField.selectAll() })
    }
    function closeSearch() {
        searchOpen = false
        searchField.text = ""
        Doc.setSearch("")
        pages.searchIndex = -1
        focusPages()
    }
    function showPanel(i) {
        sidebarOpen = true
        sidebar.show(i)
    }
    function toggleSidebar() {
        sidebarOpen = !sidebarOpen
        if (!sidebarOpen) focusPages()
    }
    function goToPagePrompt() {
        prompt.ask("Go to page (1–" + Doc.pageCount + ")", String(pages.currentPage + 1), value => {
            const n = parseInt(value, 10)
            if (!isNaN(n)) pages.goToPage(n - 1, 0, true)
            else {
                // Accept the PDF's own page labels too (e.g. "iv").
                for (let i = 0; i < Doc.pageCount; i++)
                    if (Doc.pageLabel(i) === value.trim()) { pages.goToPage(i, 0, true); break }
            }
        }, focusPages)
    }
    function addBookmark() {
        const p = pages.currentPage
        const y = pages.viewTopInPage(p)
        prompt.ask("Bookmark page " + Doc.pageLabel(p), Doc.suggestBookmarkName(p),
                   name => Doc.addBookmark(p, y, name), focusPages)
    }
    function newNote() {
        showPanel(3)
        Qt.callLater(() => sidebar.newNoteRequested())
    }

    Component.onCompleted: focusPages()

    // Incremental search: jump to the first hit as soon as one exists.
    Connections {
        target: Doc
        function onSearchChanged() {
            if (reader.searchOpen && pages.searchIndex < 0 && Doc.searchResults.length > 0)
                pages.nextSearchHit(1)
        }
    }

    Shortcut { sequences: ["Ctrl+F"]; onActivated: reader.openSearch() }
    Shortcut { sequences: ["F3"]; onActivated: pages.nextSearchHit(1) }
    Shortcut { sequences: ["Shift+F3"]; onActivated: pages.nextSearchHit(-1) }
    Shortcut { sequences: ["Ctrl+G"]; onActivated: reader.goToPagePrompt() }
    Shortcut { sequences: ["Ctrl+D"]; onActivated: reader.addBookmark() }
    Shortcut { sequences: ["Ctrl+E"]; onActivated: Doc.exportMarkdown() }
    Shortcut { sequences: ["Ctrl+N"]; onActivated: reader.newNote() }
    Shortcut { sequences: ["Ctrl+\\", "F9"]; onActivated: reader.toggleSidebar() }
    Shortcut { sequences: ["Ctrl+1"]; onActivated: reader.showPanel(0) }
    Shortcut { sequences: ["Ctrl+2"]; onActivated: reader.showPanel(1) }
    Shortcut { sequences: ["Ctrl+3"]; onActivated: reader.showPanel(2) }
    Shortcut { sequences: ["Ctrl+4"]; onActivated: reader.showPanel(3) }
    Shortcut { sequences: ["Ctrl+=", "Ctrl++", StandardKey.ZoomIn]; onActivated: if (!pages.resizeAnswer(1)) pages.zoomBy(1.15) }
    Shortcut { sequences: ["Ctrl+-", StandardKey.ZoomOut]; onActivated: if (!pages.resizeAnswer(-1)) pages.zoomBy(1 / 1.15) }
    Shortcut { sequences: ["Ctrl+0"]; onActivated: pages.zoomFit() }
    Shortcut { sequences: ["Alt+Left"]; onActivated: pages.back() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Toolbar
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: bar.implicitHeight + 2 * Theme.spaceLg
            color: Theme.bg
            z: 2

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: Theme.borderWidth
                color: Theme.border
            }

            RowLayout {
                id: bar
                anchors.fill: parent
                anchors.leftMargin: Theme.spaceLg
                anchors.rightMargin: Theme.spaceLg
                spacing: Theme.spaceMd

                DgButton {
                    text: "☰"
                    variant: "ghost"
                    onClicked: reader.toggleSidebar()
                }
                DgText {
                    Layout.fillWidth: true
                    text: Doc.title
                    font.weight: Font.DemiBold
                }
                DgButton {
                    text: "Page " + Doc.pageLabel(pages.currentPage) + " / " + Doc.pageCount
                    variant: "ghost"
                    hint: "Ctrl+G"
                    onClicked: reader.goToPagePrompt()
                }
                DgButton { text: "−"; variant: "ghost"; onClicked: pages.zoomBy(1 / 1.15) }
                DgText {
                    text: Math.round(pages.zoom * 100) + "%"
                    role: "small"
                    secondary: true
                    Layout.minimumWidth: 4 * Theme.fontBody
                    horizontalAlignment: Text.AlignHCenter
                }
                DgButton { text: "+"; variant: "ghost"; onClicked: pages.zoomBy(1.15) }
                DgButton {
                    text: "Fit"
                    variant: pages.fitWidth ? "secondary" : "ghost"
                    onClicked: pages.zoomFit()
                }
                DgButton { text: "Search"; hint: "/"; variant: "ghost"; onClicked: reader.openSearch() }
                DgButton { text: "Export"; hint: "Ctrl+E"; variant: "ghost"; onClicked: Doc.exportMarkdown() }
                DgButton { text: "⚙"; variant: "ghost"; onClicked: reader.settingsRequested() }
                DgButton { text: "?"; variant: "ghost"; onClicked: reader.keysRequested() }
            }
        }

        // Search bar
        Rectangle {
            Layout.fillWidth: true
            visible: reader.searchOpen
            implicitHeight: searchRow.implicitHeight + 2 * Theme.spaceMd
            color: Theme.bg

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: Theme.borderWidth
                color: Theme.border
            }

            RowLayout {
                id: searchRow
                anchors.fill: parent
                anchors.leftMargin: Theme.spaceLg
                anchors.rightMargin: Theme.spaceLg
                spacing: Theme.spaceMd

                DgTextField {
                    id: searchField
                    Layout.preferredWidth: 28 * Theme.fontBody
                    placeholderText: "Search this PDF"
                    onTextChanged: searchDebounce.restart()
                    Keys.onReturnPressed: event => {
                        Doc.setSearch(text)
                        pages.nextSearchHit(event.modifiers & Qt.ShiftModifier ? -1 : 1)
                    }
                    Keys.onEnterPressed: event => pages.nextSearchHit(event.modifiers & Qt.ShiftModifier ? -1 : 1)
                    Keys.onEscapePressed: reader.closeSearch()
                    Keys.onDownPressed: reader.focusPages()
                }
                Timer {
                    id: searchDebounce
                    interval: 250
                    onTriggered: { pages.searchIndex = -1; Doc.setSearch(searchField.text) }
                }
                DgText {
                    role: "small"
                    secondary: true
                    text: !Doc.searchTerm ? ""
                        : Doc.searchResults.length === 0 ? "No matches"
                        : pages.searchIndex < 0 ? Doc.searchResults.length + " matches"
                        : (pages.searchIndex + 1) + " of " + Doc.searchResults.length
                }
                DgButton { text: "↑"; variant: "ghost"; hint: "Shift+Enter"; onClicked: pages.nextSearchHit(-1) }
                DgButton { text: "↓"; variant: "ghost"; hint: "Enter"; onClicked: pages.nextSearchHit(1) }
                Item { Layout.fillWidth: true }
                DgButton { text: "Close"; variant: "ghost"; hint: "Esc"; onClicked: reader.closeSearch() }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Sidebar {
                id: sidebar
                Layout.fillHeight: true
                Layout.preferredWidth: Math.min(26 * Theme.fontBody, reader.width * 0.4)
                visible: reader.sidebarOpen
                reader: pages
                prompt: reader.prompt
                onDone: reader.focusPages()
            }

            PageView {
                id: pages
                Layout.fillWidth: true
                Layout.fillHeight: true
                focus: true
                onBookmarkRequested: reader.addBookmark()
                onSearchRequested: reader.openSearch()
                onHighlightActivated: (hid, x, y, editNote) => highlightPopup.openFor(hid, x, y, editNote, reader.focusPages)
                Keys.onEscapePressed: if (reader.searchOpen) reader.closeSearch()

                HighlightPopup {
                    id: highlightPopup
                }
            }
        }
    }
}
