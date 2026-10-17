import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import QtQuick.Pdf
import Dogear
import "../components"

// One page: rendered image, highlight/search/selection overlays, margin
// markers for highlight notes, a dog-ear when bookmarked, and mouse
// handling for text selection, highlight clicks and internal links.
Item {
    id: page

    required property int index
    required property var pageView
    readonly property var size: pageView.pageSize(index)
    readonly property real s: pageView.pxPerPt
    readonly property Flickable flick: pageView.flick
    // Before the first layout every page sits at y = 0; nothing is near yet.
    readonly property bool near: pageView.ready && y + height > flick.contentY - flick.height
        && y < flick.contentY + 2 * flick.height

    width: size[0] * s
    height: size[1] * s
    x: pageView.pageX(index)
    y: pageView.tops[index] || 0

    // Overlays only exist while the page is near the viewport.
    readonly property var highlights: (Doc.revision, near ? Doc.highlightsOnPage(index) : [])
    readonly property var bookmarks: (Doc.revision, near ? Doc.bookmarksOnPage(index) : [])
    readonly property var hits: {
        const out = []
        if (!near) return out
        const all = pageView.searchHits
        for (let i = 0; i < all.length; i++) {
            if (all[i].page !== index) continue
            for (const r of all[i].rects) out.push({ r: r, current: i === pageView.searchIndex })
        }
        return out
    }

    function toPt(mx, my) {
        return { x: Math.max(0, Math.min(size[0], mx / s)), y: Math.max(0, Math.min(size[1], my / s)) }
    }
    function inRect(p, r, pad) {
        return p.x >= r[0] - pad && p.x <= r[0] + r[2] + pad && p.y >= r[1] - pad && p.y <= r[1] + r[3] + pad
    }
    function highlightAt(p) {
        // Last drawn wins, matching what is on top visually.
        for (let i = highlights.length - 1; i >= 0; i--)
            for (const r of highlights[i].rects)
                if (inRect(p, r, 1)) return highlights[i].id
        return ""
    }
    function linkAt(p) {
        // Looked up on demand (and cached in Python): most pages are never clicked.
        for (const l of Doc.linksOnPage(index))
            if (inRect(p, l.rect, 0)) return l
        return null
    }

    Rectangle {
        // Paper with a hairline edge so white pages read on light themes too.
        anchors.fill: parent
        anchors.margins: -1
        color: "white"
        border.width: 1
        border.color: Theme.border
    }

    PdfPageImage {
        id: image
        anchors.fill: parent
        document: page.near ? page.pageView.pdf : null
        currentFrame: page.index
        asynchronous: true
        retainWhileLoading: true
        smooth: true
        fillMode: Image.Stretch
        sourceSize.width: Math.round(page.size[0] * page.pageView.renderPxPerPt * Screen.devicePixelRatio)
        sourceSize.height: Math.round(page.size[1] * page.pageView.renderPxPerPt * Screen.devicePixelRatio)
    }

    DgText {
        anchors.centerIn: parent
        visible: image.status !== Image.Ready
        text: "Page " + (page.index + 1)
        color: "#888888"
    }

    // Search hits: all hits faint, the current one strong.
    Repeater {
        model: page.hits
        Rectangle {
            required property var modelData
            x: modelData.r[0] * page.s - 1
            y: modelData.r[1] * page.s - 1
            width: modelData.r[2] * page.s + 2
            height: modelData.r[3] * page.s + 2
            radius: 2
            color: Theme.tint(Theme.accent, modelData.current ? 0.35 : 0.18)
            border.width: modelData.current ? 2 : 0
            border.color: Theme.accent
        }
    }

    // Highlights.
    Repeater {
        model: page.highlights
        Item {
            id: hl
            required property var modelData
            readonly property color tone: Theme.highlights[modelData.color]
            anchors.fill: parent
            Repeater {
                model: hl.modelData.rects
                Rectangle {
                    required property var modelData
                    x: modelData[0] * page.s
                    y: modelData[1] * page.s
                    width: modelData[2] * page.s
                    height: modelData[3] * page.s
                    color: Theme.tint(hl.tone, 0.42)
                }
            }
        }
    }

    // Current text selection.
    Repeater {
        model: page.pageView.selection && page.pageView.selection.page === page.index ? page.pageView.selection.rects : []
        Rectangle {
            required property var modelData
            x: modelData[0] * page.s
            y: modelData[1] * page.s
            width: modelData[2] * page.s
            height: modelData[3] * page.s
            color: Theme.tint(Theme.accent, 0.3)
        }
    }

    // Dog-ear on bookmarked pages.
    Shape {
        id: ear
        visible: page.bookmarks.length > 0
        anchors.top: parent.top
        anchors.right: parent.right
        width: Math.max(14, 26 * page.s / page.pageView.basePx)
        height: width
        ShapePath {
            strokeWidth: -1
            fillColor: Theme.accent
            startX: 0; startY: 0
            PathLine { x: ear.width; y: 0 }
            PathLine { x: ear.width; y: ear.height }
            PathLine { x: 0; y: 0 }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        preventStealing: true
        hoverEnabled: true
        cursorShape: Qt.IBeamCursor

        property var start: null
        property bool dragging: false

        onPressed: m => {
            page.pageView.forceActiveFocus(Qt.MouseFocusReason)
            start = page.toPt(m.x, m.y)
            dragging = false
        }
        onPositionChanged: m => {
            const p = page.toPt(m.x, m.y)
            if (!pressed) {
                cursorShape = page.highlightAt(p) || page.linkAt(p) ? Qt.PointingHandCursor : Qt.IBeamCursor
                return
            }
            if (!(m.buttons & Qt.LeftButton) || !start) return
            if (!dragging && Math.abs(p.x - start.x) * page.s + Math.abs(p.y - start.y) * page.s < 4) return
            dragging = true
            page.pageView.selecting = true
            const r = Doc.select(page.index, start.x, start.y, p.x, p.y)
            page.pageView.selection = r.text && r.rects.length ? { page: page.index, rects: r.rects, text: r.text } : null
            // Drag-scroll near the viewport edges.
            const v = mapToItem(page.flick, m.x, m.y)
            if (v.y < 30) page.pageView.scrollBy(-20)
            else if (v.y > page.flick.height - 30) page.pageView.scrollBy(20)
        }
        onReleased: m => {
            page.pageView.selecting = false
            if (dragging) {
                dragging = false
                if (page.pageView.selection) page.pageView.selectionMade()
                return
            }
            const p = page.toPt(m.x, m.y)
            const hid = page.highlightAt(p)
            if (hid) {
                page.pageView.selection = null
                page.pageView.openHighlight(hid, false)
                return
            }
            if (m.button === Qt.RightButton) return
            const link = page.linkAt(p)
            if (link) {
                page.pageView.goToPage(link.page, link.y, true)
                return
            }
            page.pageView.selection = null
        }
        onDoubleClicked: m => {
            const p = page.toPt(m.x, m.y)
            const w = Doc.wordAt(page.index, p.x, p.y)
            if (w.text && w.rects.length) page.pageView.selection = { page: page.index, rects: w.rects, text: w.text }
        }
    }

    // Margin markers for highlights that carry a note.
    Repeater {
        model: page.highlights
        Rectangle {
            required property var modelData
            visible: modelData.note.length > 0 && modelData.rects.length > 0
            readonly property var r0: modelData.rects.length ? modelData.rects[0] : [0, 0, 0, 0]
            x: page.width + (page.pageView.gutter - width) / 2
            y: r0[1] * page.s + (r0[3] * page.s - height) / 2
            width: Math.round(page.pageView.gutter * 0.6)
            height: width
            radius: Theme.radius > 0 ? 3 : 0
            color: Theme.highlights[modelData.color]
            border.width: markerMouse.containsMouse ? 2 : 1
            border.color: Theme.fg

            DgText {
                anchors.centerIn: parent
                text: "✎"
                role: "caption"
                color: "#202020"
            }
            MouseArea {
                id: markerMouse
                anchors.fill: parent
                anchors.margins: -3
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: page.pageView.openHighlight(parent.modelData.id, true)
            }
        }
    }
}
