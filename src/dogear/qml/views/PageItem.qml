import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import QtQuick.Pdf
import Dogear
import "../components"

// One page: rendered image, highlight/search/selection overlays, margin
// markers for highlight notes, a dog-ear when bookmarked, answers typed on
// the page's answer lines, and mouse handling for text selection,
// highlight clicks, internal links and starting an answer.
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
    readonly property var answers: (Doc.revision, near ? Doc.answersOnPage(index) : [])
    // The empty answer line under the mouse, for the hover hint.
    property var blank: null
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
    function highlightById(hid) {
        return highlights.find(h => h.id === hid) || null
    }
    function highlightAt(p) {
        // Last drawn wins, matching what is on top visually.
        for (let i = highlights.length - 1; i >= 0; i--)
            for (const r of highlights[i].rects)
                if (inRect(p, r, 1)) return highlights[i].id
        return ""
    }
    // Give keyboard focus to answer `aid` if it is on this page.
    function focusAnswer(aid) {
        for (let i = 0; i < answerRepeater.count; i++) {
            const item = answerRepeater.itemAt(i)
            if (item && item.modelData.id === aid) {
                item.forceActiveFocus(Qt.OtherFocusReason)
                item.cursorPosition = item.length
                return true
            }
        }
        return false
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

        onExited: { page.pageView.hoverHighlight(null); page.blank = null }
        onPressed: m => {
            page.pageView.hideNoteTip()
            page.blank = null
            page.pageView.forceActiveFocus(Qt.MouseFocusReason)
            start = page.toPt(m.x, m.y)
            dragging = false
        }
        onPositionChanged: m => {
            const p = page.toPt(m.x, m.y)
            if (!pressed) {
                const hid = page.highlightAt(p)
                const link = !hid && page.linkAt(p)
                cursorShape = hid || link ? Qt.PointingHandCursor : Qt.IBeamCursor
                const b = hid || link ? {} : Doc.blankAt(page.index, p.x, p.y)
                page.blank = b.w ? b : null
                const v = mapToItem(page.pageView, m.x, m.y)
                page.pageView.hoverHighlight(page.highlightById(hid), v.x, v.y)
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
            // A click on an answer line starts typing there.
            const aid = Doc.answerAt(page.index, p.x, p.y)
            if (aid) page.pageView.editAnswer(page.index, aid)
        }
        onDoubleClicked: m => {
            const p = page.toPt(m.x, m.y)
            const w = Doc.wordAt(page.index, p.x, p.y)
            if (w.text && w.rects.length) page.pageView.selection = { page: page.index, rects: w.rects, text: w.text }
        }
    }

    // Hover hint: the writing area of an empty answer line.
    Rectangle {
        readonly property var b: page.blank
        visible: b !== null && !page.pageView.selecting
        x: b ? b.x * page.s : 0
        y: b ? (b.y - b.size * 1.6) * page.s : 0
        width: b ? b.w * page.s : 0
        height: b ? (b.size * 1.6 + (b.lines - 1) * b.pitch) * page.s : 0
        color: Theme.tint(Theme.accent, 0.12)
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 2
            color: Theme.tint(Theme.accent, 0.6)
        }
    }

    // Answers typed on answer lines, in pen-blue ink (pages are always white).
    Repeater {
        id: answerRepeater
        model: page.answers
        TextEdit {
            id: ans
            required property var modelData
            readonly property bool ruled: modelData.lines > 1 && modelData.pitch > 0
            readonly property real basePx: modelData.size * page.s
            // A single line shrinks its text to fit before it wraps.
            readonly property real fitPx: ruled ? basePx
                : Math.max(basePx * 0.6, Math.min(basePx, basePx * width * 0.97 / Math.max(1, natural.advanceWidth)))
            readonly property real lift: Math.max(1.5, modelData.size * 0.25) * page.s

            // The first baseline sits just above the first line. Qt puts the
            // text of a fixed-height line at its bottom, descent included.
            readonly property real firstBaseline: ruled ? pitchPx - metrics.descent : baselineOffset
            x: modelData.x * page.s
            y: modelData.y * page.s - lift - firstBaseline
            width: modelData.w * page.s
            z: activeFocus ? 2 : 1
            text: modelData.text
            color: "#1d3f94"
            selectionColor: Theme.tint(Theme.accent, 0.35)
            selectedTextColor: "#1d3f94"
            // Proportional, like handwriting on paper (the theme font is mono).
            font.family: "sans-serif"
            font.pixelSize: Math.max(1, fitPx)
            wrapMode: TextEdit.WrapAtWordBoundaryOrAnywhere
            // Ruled answers put one line of text on each printed line.
            readonly property real pitchPx: ruled ? modelData.pitch * page.s : 0
            function applyPitch() { if (ruled) Doc.setLinePitch(textDocument, pitchPx) }
            onPitchPxChanged: applyPitch()
            onLineCountChanged: applyPitch()
            selectByMouse: true
            persistentSelection: false
            cursorVisible: activeFocus

            FontMetrics {
                id: metrics
                font: ans.font
            }
            TextMetrics {
                id: natural
                font.family: ans.font.family
                font.pixelSize: ans.basePx
                text: ans.text
            }

            // While typing, tint the whole writing area.
            Rectangle {
                z: -1
                visible: ans.activeFocus
                x: -2
                y: ans.firstBaseline + ans.lift - ans.modelData.size * 1.6 * page.s
                width: ans.width + 4
                height: Math.max(ans.modelData.size * 1.6 * page.s + (ans.modelData.lines - 1) * ans.modelData.pitch * page.s,
                                 ans.height - y) + 3
                color: Theme.tint(Theme.accent, 0.10)
                border.width: 1
                border.color: Theme.tint(Theme.accent, 0.5)
            }

            onTextChanged: Doc.setAnswerText(modelData.id, text)
            onActiveFocusChanged: {
                if (activeFocus) {
                    page.pageView.hideNoteTip()
                    page.blank = null
                    return
                }
                const aid = modelData.id
                Qt.callLater(() => Doc.finishAnswer(aid))
            }
            Keys.onPressed: event => {
                const aid = modelData.id
                const ctrl = event.modifiers & Qt.ControlModifier
                const shift = event.modifiers & Qt.ShiftModifier
                const enter = event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                if (event.key === Qt.Key_Escape || (enter && ctrl)) {
                    page.pageView.forceActiveFocus()
                } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                    const step = event.key === Qt.Key_Backtab || shift ? -1 : 1
                    // Later: moving on rebuilds this editor.
                    Qt.callLater(() => page.pageView.moveAnswer(aid, step))
                } else if (enter && !shift && !ans.ruled) {
                    Qt.callLater(() => page.pageView.moveAnswer(aid, 1))
                } else {
                    return
                }
                event.accepted = true
            }
            Component.onCompleted: {
                applyPitch()
                if (page.pageView.focusAnswer === modelData.id) page.pageView.applyAnswerFocus()
            }
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
                onEntered: {
                    const v = mapToItem(page.pageView, width / 2, height / 2)
                    page.pageView.hoverHighlight(parent.modelData, v.x, v.y)
                }
                onExited: { page.pageView.hoverHighlight(null); page.blank = null }
                onClicked: page.pageView.openHighlight(parent.modelData.id, true)
            }
        }
    }
}
