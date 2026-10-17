import QtQuick
import QtQuick.Window
import QtQuick.Templates as T
import QtQuick.Pdf
import Dogear
import "../components"

// Continuous vertical page view. Pages are laid out by hand (not a ListView)
// so every page has an exact position: restoring the reading position,
// jumping to a search hit or bookmark and anchoring zoom are plain math.
// Only pages near the viewport load an image and build overlays.
// Not a FocusScope: forceActiveFocus() on the view must take the keyboard
// back from an answer being typed on a page.
Item {
    id: view
    objectName: "pageView"

    property real zoom: 1.0
    property bool fitWidth: true
    readonly property real basePx: 96 / 72
    readonly property real pxPerPt: zoom * basePx
    // Render resolution trails the zoom so a burst of zoom steps renders once.
    property real renderPxPerPt: pxPerPt
    readonly property int gap: Theme.spaceXxl
    readonly property int gutter: Math.round(Theme.controlHeight * 0.9)
    readonly property int margin: Theme.spaceHuge
    property var tops: []
    property real contentH: 0
    property real maxW: 612
    readonly property real contentW: Math.max(flick.width, maxW * pxPerPt + 2 * margin + 2 * gutter)
    readonly property alias flick: flick
    // Rendering uses Qt's own PDF document (C++ only, rendered off the UI
    // thread). Python's QPdfDocument handles text, search and outline, and
    // only ever runs on the UI thread.
    readonly property alias pdf: pdfDoc
    readonly property real scrollX: flick.contentX
    readonly property real scrollY: flick.contentY

    property int currentPage: 0
    // {page, rects: [[x,y,w,h]...], text} in PDF points, or null.
    property var selection: null
    property bool selecting: false
    property int searchIndex: -1
    readonly property var searchHits: Doc.searchResults
    property bool ready: false
    property var history: []

    signal highlightActivated(string hid, real x, real y, bool editNote)
    signal selectionMade()
    signal bookmarkRequested()
    signal searchRequested()

    function addBookmarkHere() { bookmarkRequested() }

    readonly property real minZoom: 0.25
    readonly property real maxZoom: 6.0

    function pageSize(i) {
        const s = Doc.pageSizes[i]
        return s ? s : [612, 792]
    }
    function pageW(i) { return pageSize(i)[0] * pxPerPt }
    function pageH(i) { return pageSize(i)[1] * pxPerPt }
    function pageX(i) { return (contentW - pageW(i)) / 2 }
    function maxContentY() { return Math.max(0, contentH - flick.height) }
    function maxContentX() { return Math.max(0, contentW - flick.width) }
    function clampY(y) { return Math.max(0, Math.min(maxContentY(), y)) }

    function relayout() {
        const sizes = Doc.pageSizes
        const t = []
        let y = margin
        let mw = 0
        for (let i = 0; i < sizes.length; i++) {
            t.push(y)
            y += sizes[i][1] * pxPerPt + gap
            mw = Math.max(mw, sizes[i][0])
        }
        maxW = mw || 612
        tops = t
        contentH = sizes.length ? y - gap + margin : 0
    }

    function pageAt(y) {
        let lo = 0, hi = tops.length - 1
        if (hi < 0) return 0
        while (lo < hi) {
            const mid = (lo + hi + 1) >> 1
            if (tops[mid] <= y) lo = mid
            else hi = mid - 1
        }
        return lo
    }

    function fitZoom() {
        const avail = flick.width - 2 * margin - 2 * gutter
        return Math.max(minZoom, Math.min(maxZoom, avail / (maxW * basePx)))
    }

    // Reading position: the page at the top edge and how far into it.
    function anchor() {
        const p = pageAt(flick.contentY + 1)
        const off = (flick.contentY - (tops[p] || 0)) / Math.max(1, pageH(p))
        const mx = maxContentX()
        return { page: p, offset: off, x: mx > 0 ? flick.contentX / mx : 0.5 }
    }

    function restoreAnchor(a) {
        if (!tops.length) return
        stopSmooth()
        const p = Math.max(0, Math.min(tops.length - 1, a.page))
        flick.contentY = clampY(tops[p] + a.offset * pageH(p))
        flick.contentX = maxContentX() * Math.max(0, Math.min(1, a.x))
    }

    function setZoom(z, fit) {
        const a = anchor()
        fitWidth = !!fit
        zoom = Math.max(minZoom, Math.min(maxZoom, z))
        relayout()
        restoreAnchor(a)
        renderTimer.restart()
        saveTimer.restart()
    }
    function zoomBy(factor) { setZoom(zoom * factor, false) }
    function zoomFit() { setZoom(fitZoom(), true) }

    function restoreFromStore() {
        if (flick.width <= 0 || flick.height <= 0) {
            Qt.callLater(restoreFromStore)
            return
        }
        const v = Doc.view()
        fitWidth = v.fit_width
        relayout()
        zoom = fitWidth ? fitZoom() : Math.max(minZoom, Math.min(maxZoom, v.zoom))
        renderPxPerPt = pxPerPt
        relayout()
        restoreAnchor({ page: v.page, offset: v.offset, x: v.x })
        ready = true
        updateCurrentPage()
    }

    function updateCurrentPage() {
        currentPage = pageAt(flick.contentY + flick.height * 0.3)
    }

    function scrollBy(dy) { stopSmooth(); flick.contentY = clampY(flick.contentY + dy) }

    // Mouse-wheel scrolling glides to its target. Successive notches add to
    // the target, so a fast spin keeps accelerating instead of stuttering,
    // and notches in quick succession go further each (up to wheelMaxBoost).
    readonly property real wheelStep: Theme.fontBody * 26
    readonly property real wheelMaxBoost: 3
    property real wheelBoost: 1
    property double lastWheel: 0
    function wheelNotches(notches) {
        const now = Date.now()
        // Within 120 ms of the last notch in the same direction: speed up.
        const sameWay = Math.sign(notches) === Math.sign(lastWheelNotches)
        wheelBoost = sameWay && now - lastWheel < 120 ? Math.min(wheelMaxBoost, wheelBoost * 1.2) : 1
        lastWheel = now
        lastWheelNotches = notches
        smoothScrollBy(-notches * wheelStep * wheelBoost)
    }
    property real lastWheelNotches: 0
    property real smoothTarget: 0
    function smoothScrollBy(dy) {
        const base = smoothY.running ? smoothTarget : flick.contentY
        smoothTarget = clampY(base + dy)
        smoothY.stop()
        smoothY.from = flick.contentY
        smoothY.to = smoothTarget
        smoothY.start()
    }
    function stopSmooth() { if (smoothY.running) smoothY.stop() }

    // Hover tooltip showing a highlight's note. `tip` is the shown one,
    // `pendingTip` waits out a short delay so sweeping across text doesn't flash.
    property var tip: null          // {id, note, color, x, y} in view coordinates
    property var pendingTip: null
    readonly property bool noteTipVisible: tip !== null && noteTip.visible
    function hoverHighlight(hl, x, y) {
        if (!hl || !hl.note || selecting) { hideNoteTip(); return }
        if (tip && tip.id === hl.id) return
        pendingTip = { id: hl.id, note: hl.note, color: hl.color, x: x, y: y }
        if (tip) { tip = pendingTip; pendingTip = null }
        else tipTimer.restart()
    }
    // Content moving under a still mouse makes the tip point at the wrong text.
    function hideNoteTipIfMoved() { if (tip || pendingTip) hideNoteTip() }
    function hideNoteTip() {
        tipTimer.stop()
        pendingTip = null
        tip = null
    }
    function scrollXBy(dx) { flick.contentX = Math.max(0, Math.min(maxContentX(), flick.contentX + dx)) }

    function pushHistory() {
        const h = history.slice(-49)
        h.push(anchor())
        history = h
    }
    function back() {
        if (!history.length) return false
        const h = history.slice()
        const a = h.pop()
        history = h
        restoreAnchor(a)
        return true
    }

    // Jump to a page, optionally to a y position (PDF points) within it.
    function goToPage(p, yPt, remember) {
        if (!tops.length) return
        stopSmooth()
        if (remember) pushHistory()
        p = Math.max(0, Math.min(tops.length - 1, p))
        if (yPt === undefined || yPt <= 0)
            flick.contentY = clampY(tops[p] - gap / 2)
        else
            flick.contentY = clampY(tops[p] + yPt * pxPerPt - flick.height * 0.25)
    }
    function nextPage() { goToPage(pageAt(flick.contentY + gap) + 1) }
    function prevPage() {
        const p = pageAt(flick.contentY + gap)
        goToPage(flick.contentY > tops[p] + gap ? p : p - 1)
    }

    function showSearchHit(i) {
        if (i < 0 || i >= searchHits.length) return
        searchIndex = i
        const hit = searchHits[i]
        const r = hit.rects[0] || [0, 0, 0, 0]
        const top = (tops[hit.page] || 0) + r[1] * pxPerPt
        // Leave the view alone if the hit is already comfortably visible.
        if (top < flick.contentY + 20 || top > flick.contentY + flick.height - 40)
            goToPage(hit.page, r[1])
        if (maxContentX() > 0) {
            const left = pageX(hit.page) + r[0] * pxPerPt
            if (left < flick.contentX || left > flick.contentX + flick.width - 40)
                flick.contentX = Math.max(0, Math.min(maxContentX(), left - flick.width / 3))
        }
    }
    function nextSearchHit(step) {
        const n = searchHits.length
        if (!n) return
        if (searchIndex < 0) {
            // Start from the first hit at or after the page being read.
            let i = searchHits.findIndex(h => h.page >= currentPage)
            if (step < 0) i = i <= 0 ? n - 1 : i - 1
            showSearchHit(i < 0 ? 0 : i)
            return
        }
        showSearchHit((searchIndex + step + n) % n)
    }

    // Selection actions.
    function highlightSelection(color, withNote) {
        if (!selection || !selection.rects.length) return ""
        const sel = selection
        const hid = Doc.addHighlight(sel.page, sel.rects, sel.text, color)
        selection = null
        if (hid && withNote) {
            const pos = rectInView(sel.page, sel.rects[sel.rects.length - 1])
            highlightActivated(hid, pos.x, pos.y + pos.h, true)
        }
        return hid
    }
    function copySelection() {
        if (selection && selection.text) Doc.copyText(selection.text)
    }

    function rectInView(page, r) {
        return {
            x: pageX(page) + r[0] * pxPerPt - flick.contentX,
            y: (tops[page] || 0) + r[1] * pxPerPt - flick.contentY,
            w: r[2] * pxPerPt,
            h: r[3] * pxPerPt
        }
    }

    function openHighlight(hid, editNote) {
        hideNoteTip()
        const hl = Doc.highlight(hid)
        if (!hl.id) return
        const r = hl.rects[hl.rects.length - 1] || [0, 0, 0, 0]
        if (!tops.length) return
        const first = hl.rects[0] || r
        const topY = (tops[hl.page] || 0) + first[1] * pxPerPt
        if (topY < flick.contentY || topY > flick.contentY + flick.height - 60)
            goToPage(hl.page, first[1], true)
        const pos = rectInView(hl.page, r)
        highlightActivated(hid, pos.x, pos.y + pos.h, editNote)
    }

    // Answers on answer lines. `focusAnswer` holds the answer that should
    // get the keyboard until its editor exists (it may be on a page that is
    // only now scrolling into view).
    property string focusAnswer: ""
    // The answer editor that has the keyboard, if any.
    property var activeAnswer: null
    // Ctrl+= / Ctrl+- resize the answer being typed instead of zooming.
    function resizeAnswer(step) {
        if (!activeAnswer || !activeAnswer.activeFocus) return false
        activeAnswer.resize(step)
        return true
    }
    property int focusAnswerPage: -1
    function editAnswer(page, aid) {
        hideNoteTip()
        selection = null
        const a = Doc.answer(aid)
        if (!a.id || !tops.length) return
        const top = (tops[page] || 0) + (a.y - a.size * 2) * pxPerPt
        const bottom = (tops[page] || 0) + (a.y + (a.lines - 1) * a.pitch + 4) * pxPerPt
        if (top < flick.contentY || bottom > flick.contentY + flick.height) {
            stopSmooth()
            flick.contentY = clampY(top - flick.height * 0.3)
        }
        if (maxContentX() > 0) {
            const left = pageX(page) + a.x * pxPerPt
            if (left < flick.contentX || left > flick.contentX + flick.width - 60)
                flick.contentX = Math.max(0, Math.min(maxContentX(), left - flick.width / 4))
        }
        focusAnswer = aid
        focusAnswerPage = page
        Qt.callLater(applyAnswerFocus)
    }
    function applyAnswerFocus() {
        if (!focusAnswer) return
        const item = pages.itemAt(focusAnswerPage)
        if (item && item.focusAnswer(focusAnswer)) {
            focusAnswer = ""
            focusAnswerPage = -1
        }
    }
    // Tab / Shift+Tab / Enter from an answer: on to the next answer line.
    function moveAnswer(aid, step) {
        const next = Doc.adjacentAnswer(aid, step)
        if (next.id) editAnswer(next.page, next.id)
        else forceActiveFocus()
    }
    // "i": start typing on the first answer line in view.
    function answerInView() {
        const p = pageAt(flick.contentY + 1)
        const next = Doc.answerFrom(p, viewTopInPage(p))
        if (next.id) editAnswer(next.page, next.id)
    }

    // The y (PDF points) of the viewport top within the current page, for bookmarks.
    function viewTopInPage(p) {
        return Math.max(0, (flick.contentY - (tops[p] || 0)) / pxPerPt)
    }

    Connections {
        target: Doc
        function onOpened() { view.restoreFromStore() }
        function onSearchChanged() {
            if (view.searchIndex >= view.searchHits.length) view.searchIndex = -1
        }
    }

    Component.onCompleted: if (Doc.loaded) restoreFromStore()

    onWidthChanged: if (ready && fitWidth) zoomFit()

    Timer {
        id: tipTimer
        interval: 150
        onTriggered: { view.tip = view.pendingTip; view.pendingTip = null }
    }
    NumberAnimation {
        id: smoothY
        target: flick
        property: "contentY"
        duration: 220
        easing.type: Easing.OutCubic
    }
    Timer {
        id: renderTimer
        interval: 180
        onTriggered: view.renderPxPerPt = view.pxPerPt
    }
    Timer {
        id: saveTimer
        interval: 300
        onTriggered: {
            if (!view.ready) return
            const a = view.anchor()
            Doc.saveView(a.page, Math.max(0, Math.min(1, a.offset)), view.zoom, view.fitWidth, a.x)
        }
    }

    Keys.onPressed: event => {
        const ctrl = event.modifiers & Qt.ControlModifier
        const shift = event.modifiers & Qt.ShiftModifier
        const alt = event.modifiers & Qt.AltModifier
        const step = Theme.fontBody * 9
        const t = event.text
        let handled = true
        if (alt && event.key === Qt.Key_Left) { view.back() }
        else if (ctrl && event.key === Qt.Key_C) { view.copySelection() }
        else if (ctrl || alt) { handled = false }
        else if (shift && event.key === Qt.Key_J) view.nextPage()
        else if (shift && event.key === Qt.Key_K) view.prevPage()
        else if (shift && event.key === Qt.Key_G) view.goToPage(view.tops.length - 1)
        else if (shift && event.key === Qt.Key_N) view.nextSearchHit(-1)
        else if (event.key === Qt.Key_J || event.key === Qt.Key_Down) view.scrollBy(step)
        else if (event.key === Qt.Key_K || event.key === Qt.Key_Up) view.scrollBy(-step)
        else if (event.key === Qt.Key_H || event.key === Qt.Key_Left) view.scrollXBy(-step)
        else if (event.key === Qt.Key_L || event.key === Qt.Key_Right) view.scrollXBy(step)
        else if (event.key === Qt.Key_Space) view.scrollBy((shift ? -1 : 1) * flick.height * 0.9)
        else if (event.key === Qt.Key_PageDown) view.scrollBy(flick.height * 0.9)
        else if (event.key === Qt.Key_PageUp) view.scrollBy(-flick.height * 0.9)
        else if (event.key === Qt.Key_Home || event.key === Qt.Key_G) view.goToPage(0)
        else if (event.key === Qt.Key_End) view.goToPage(view.tops.length - 1)
        else if (t === "+" || t === "=") view.zoomBy(1.15)
        else if (t === "-") view.zoomBy(1 / 1.15)
        else if (t === "0") view.zoomFit()
        else if (event.key === Qt.Key_N) view.nextSearchHit(1)
        else if (t >= "1" && t <= "5" && view.selection) view.highlightSelection(Doc.colors[Number(t) - 1], false)
        else if (event.key === Qt.Key_A && view.selection) view.highlightSelection(App.lastColor, true)
        else if (event.key === Qt.Key_B) view.addBookmarkHere()
        else if (event.key === Qt.Key_I) view.answerInView()
        else if (t === "/") view.searchRequested()
        else if (event.key === Qt.Key_Backspace) view.back()
        else if (event.key === Qt.Key_Escape && view.selection) view.selection = null
        else handled = false
        event.accepted = handled
    }

    PdfDocument {
        id: pdfDoc
        source: Doc.loaded ? Doc.url : ""
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.bgSunken
    }

    Flickable {
        id: flick
        anchors.fill: parent
        clip: true
        contentWidth: view.contentW
        contentHeight: view.contentH
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.AutoFlickIfNeeded
        maximumFlickVelocity: 4000
        T.ScrollBar.vertical: DgScrollBar {}
        T.ScrollBar.horizontal: DgScrollBar {}

        // Ctrl+wheel zooms. Handlers on the Flickable see the wheel before
        // the Flickable scrolls with it.
        WheelHandler {
            target: null
            acceptedModifiers: Qt.ControlModifier
            onWheel: event => view.zoomBy(event.angleDelta.y > 0 ? 1.1 : 1 / 1.1)
        }
        // Plain wheel: smooth steps for mouse wheels. Touchpads already
        // scroll continuously (they report a scroll phase), so follow them 1:1.
        WheelHandler {
            target: null
            acceptedModifiers: Qt.NoModifier
            onWheel: event => {
                view.hideNoteTip()
                const touchpad = event.phase !== Qt.NoScrollPhase
                    || (event.device && event.device.type === PointerDevice.TouchPad)
                if (touchpad && (event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0)) {
                    view.scrollBy(-event.pixelDelta.y)
                    view.scrollXBy(-event.pixelDelta.x)
                    return
                }
                if (event.angleDelta.y !== 0) view.wheelNotches(event.angleDelta.y / 120)
                if (event.angleDelta.x !== 0) view.scrollXBy(-event.angleDelta.x / 120 * view.wheelStep)
            }
        }
        // Shift+wheel scrolls sideways when zoomed in.
        WheelHandler {
            target: null
            acceptedModifiers: Qt.ShiftModifier
            onWheel: event => view.scrollXBy(-(event.angleDelta.y || event.angleDelta.x) / 120 * view.wheelStep)
        }

        onContentYChanged: { view.hideNoteTipIfMoved(); view.updateCurrentPage(); if (view.ready) saveTimer.restart() }
        onContentXChanged: if (view.ready) saveTimer.restart()

        Repeater {
            id: pages
            model: Doc.pageCount
            delegate: PageItem { pageView: view }
        }

        // Floating actions for the current text selection.
        Rectangle {
            id: selBar
            readonly property var sel: view.selection
            readonly property var first: sel && sel.rects.length ? sel.rects[0] : null
            readonly property var last: sel && sel.rects.length ? sel.rects[sel.rects.length - 1] : null
            visible: !!sel && !view.selecting && !!first
            z: 50
            width: barRow.implicitWidth + 2 * Theme.spaceSm
            height: barRow.implicitHeight + 2 * Theme.spaceSm
            radius: Theme.radius
            color: Theme.bgRaised
            border.width: Theme.borderWidth
            border.color: Theme.focusRing
            x: {
                if (!first) return 0
                const px = view.pageX(sel.page) + first[0] * view.pxPerPt
                return Math.max(flick.contentX + 4, Math.min(px, flick.contentX + flick.width - width - 4))
            }
            y: {
                if (!first) return 0
                const top = (view.tops[sel.page] || 0) + first[1] * view.pxPerPt - height - Theme.spaceMd
                if (top >= flick.contentY) return top
                return (view.tops[sel.page] || 0) + (last[1] + last[3]) * view.pxPerPt + Theme.spaceMd
            }

            Row {
                id: barRow
                anchors.centerIn: parent
                spacing: Theme.spaceXs
                Repeater {
                    model: Doc.colors
                    DgSwatch {
                        required property string modelData
                        required property int index
                        colorName: modelData
                        hint: String(index + 1)
                        current: App.lastColor === modelData
                        onClicked: view.highlightSelection(modelData, false)
                    }
                }
                DgButton { text: "Note"; hint: "a"; variant: "ghost"; onClicked: view.highlightSelection(App.lastColor, true) }
                DgButton { text: "Copy"; variant: "ghost"; onClicked: view.copySelection() }
            }
        }
    }


    // While typing an answer: its text size, at the bottom of the view so
    // it never covers the page around the answer.
    Rectangle {
        id: answerBar
        readonly property var a: view.activeAnswer
        visible: a !== null && a.activeFocus
        z: 55
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.spaceXl
        width: answerRow.implicitWidth + 2 * Theme.spaceSm
        height: answerRow.implicitHeight + 2 * Theme.spaceSm
        radius: Theme.radius
        color: Theme.bgRaised
        border.width: Theme.borderWidth
        border.color: Theme.focusRing
        Row {
            id: answerRow
            anchors.centerIn: parent
            spacing: Theme.spaceSm
            DgText {
                anchors.verticalCenter: parent.verticalCenter
                leftPadding: Theme.spaceSm
                text: "Answer text " + (answerBar.a ? answerBar.a.size : "") + " pt"
                muted: true
            }
            DgButton { text: "A−"; hint: "Ctrl+-"; variant: "ghost"; focusPolicy: Qt.NoFocus; onClicked: view.resizeAnswer(-1) }
            DgButton { text: "A+"; hint: "Ctrl+="; variant: "ghost"; focusPolicy: Qt.NoFocus; onClicked: view.resizeAnswer(1) }
            DgText {
                anchors.verticalCenter: parent.verticalCenter
                rightPadding: Theme.spaceSm
                text: "Tab next · Esc done"
                role: "caption"
                muted: true
            }
        }
    }

    Rectangle {
        id: noteTip
        readonly property var t: view.tip
        visible: t !== null && !view.selecting
        z: 60
        width: Math.min(tipText.implicitWidth, 28 * Theme.fontBody) + 2 * Theme.spaceXl + 4
        height: tipText.height + 2 * Theme.spaceLg
        x: t ? Math.max(Theme.spaceMd, Math.min(t.x + 14, view.width - width - Theme.spaceMd)) : 0
        y: !t ? 0 : t.y + 22 + height < view.height - Theme.spaceMd ? t.y + 22 : Math.max(Theme.spaceMd, t.y - height - 10)
        radius: Theme.radius
        color: Theme.bgRaised
        border.width: Theme.borderWidth
        border.color: Theme.focusRing

        Rectangle {
            x: 0
            width: 4
            height: parent.height
            radius: Theme.radius
            color: noteTip.t ? Theme.highlights[noteTip.t.color] : "transparent"
        }
        DgText {
            id: tipText
            x: Theme.spaceXl + 4
            y: Theme.spaceLg
            width: Math.min(implicitWidth, 28 * Theme.fontBody)
            text: noteTip.t ? noteTip.t.note : ""
            wrapMode: Text.Wrap
            elide: Text.ElideRight
            maximumLineCount: 14
        }
    }

    DgText {
        anchors.centerIn: parent
        visible: Doc.loaded && Doc.pageCount === 0
        text: "This PDF has no pages."
        muted: true
    }
}
