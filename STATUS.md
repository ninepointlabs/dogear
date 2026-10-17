# Status

STATUS: v0.1 ready for Tim to try

## Launch

```sh
~/Projects/dogear/bin/dogear                  # start screen with recent files
~/Projects/dogear/bin/dogear ~/path/to/book.pdf
```

Needs only Arch's `pyside6` package, which is already installed on this machine
(6.11.2, includes QtPdf). Press `F1` in the app for the keyboard shortcuts.

## What works (verified)

Verified by `PYTHONPATH=src python3 -m unittest discover -s tests` (92 tests, all pass,
stable over 3 consecutive runs) and by a short run on the real Hyprland session.

- Open from the CLI argument, `Ctrl+O` file dialog, drag and drop, and the library.
- **Library** (added after v0.1). The start screen (and `Ctrl+L`) lists every PDF ever opened, with counts of marks and last opened. It's searchable by title, folder, category and the text inside your highlights, notes, answers and bookmarks. It sorts by Recent, Title, Most marked or Added. Categories can be created, renamed (renaming onto an existing name merges), deleted and ticked per document (`c`), with a filter for each category and Uncategorized. Categories are exported as tags.
- **Rename and remove documents** in the library (`F2`/`Del` or the row's buttons). A name is Dogear's own label: the file isn't renamed and the PDF's title still shows and is searchable. Removing asks first and moves the marks and the copy to `.dogear/removed/` in the library folder instead of deleting them.
- **Copies** (on by default, Settings toggle with disk use shown). Marked-up PDFs are copied into `Library/` in the library folder, under their own file name (with a hash suffix if two differ). A PDF already inside the library folder isn't copied. When the original is gone, the library opens the copy and says so. PDFs marked up earlier are copied a few seconds after start.
- **Other copies of a book.** Opening an unmarked PDF that matches a marked-up one (same PDF ID, or same name apart from versions and dates, with page counts within about 5%) offers to bring the marks over. Checked on the real Ruhi Book 3 editions 2.1.1 → 2.2.1, which have different IDs and the same page count.
- Remembers page, scroll offset, zoom and fit-width per file. The smoke test closes and reopens a file and checks the page and zoom.
- Text selection by drag, or double-click for a word. Five highlight colors (keys `1`–`5` or the floating bar). Click a highlight to recolor it, edit its note, copy or delete it.
- Mouse-wheel scrolling glides smoothly. Each notch moves about 26 lines of text, and notches in quick succession go further, up to 3×. Touchpads scroll 1:1, and `Shift`+wheel scrolls sideways.
- Hovering a highlight that has a note, or its margin marker, shows the note in a tooltip after a short delay.
- Highlight notes appear in the Highlights sidebar and as markers in the page margin. General per-document notes are in the Notes sidebar.
- **Answer lines** (added after v0.1): click on or just above a blank line and type. No text box to place. Dogear finds drawn rules, underscore runs and dotted lines in the rendered page. Ruled lines under a question become one multi-line answer. `Tab`/`Enter` go to the next blank, `Shift+Tab` back, `i` starts on the first line in view, and an emptied answer is removed. While you type, `Ctrl+=`/`Ctrl+-` or the A−/A+ bar at the bottom change that answer's text size; each answer keeps its own. Short blanks (`____ sentence` columns, down to about 14 pt) are found too. Answers are exported with the question text around them. Checked offscreen on the Ruhi Book 5 workbook by drawing what was detected over several pages and looking at it. On the fill-in-the-blank pages every blank was found, the boxed quotations' borders were skipped, and detection took about 20 ms per page. Typed answers stay on their lines when zooming.
- Named bookmarks, defaulting to the page's table of contents entry. They have a sidebar panel and a dog-ear on the page corner. The PDF outline appears in the Contents panel, with the current section highlighted.
- Incremental search with match count. Enter/`n` and Shift+Enter/`N` jump between matches, starting from the page you're reading.
- Markdown export (`Ctrl+E`) grouped by page, with quoted highlights, page numbers and labels, notes and bookmarks, plus YAML front matter. The export folder is configurable in Settings (`Ctrl+,`). Default is `Notes/` in the library folder.
- Storage is keyed by SHA-256. The PDF is never written to, and tests check that nothing appears next to it. Annotations survive renames and moves.
- **Library folder for several computers** (added after v0.1). Marks, categories and PDF copies live in one folder, `~/Documents/Dogear` by default, changeable in Settings ("Library folder"; changing it moves the library and merges with one already there). Recent files and the hash cache stay per computer in `~/.local/share/dogear`. The first start moves the old `~/.local/share/dogear` layout over, keeping the old notes files renamed next to a `MOVED.txt`. Dogear watches the folder: edits synced in while a document is open are merged in (three-way, per mark, against what this computer last read or wrote), and sync conflict copies (Syncthing, Dropbox, Google Drive naming) are merged back in, keeping every mark, with the conflict file set aside in `.dogear/removed/conflicts/`. Checked with a pretend second computer (a second local data dir on the same library folder), offscreen, on a copy of the real data; the migration of the real data was rehearsed on a copy first and only the new `copy` field differed.
- Live Omarchy theme follow, checked by simulating `omarchy theme set`. Highlight colors repaint too.
- Wayland app id / Hyprland class is `dogear` (confirmed with `hyprctl clients`). The window tiles normally and picked up the live theme (yakiiro).
- Performance with a generated 400-page PDF: open in about 0.4 s. Only pages near the viewport render, off the UI thread.
- No network code and no telemetry.

## What doesn't (yet)

- **Highlights can't cross pages.** A drag that leaves the page selects to the end of the starting page. Highlight each page separately.
- **External links (URLs) aren't followed**, by design (no network). Internal links (table of contents pages, cross-references) are implemented but untested, because the sample PDF has none.
- **Scanned PDFs without a text layer** can't be selected, highlighted or searched. There's no OCR.
- **The file and folder dialogs** (`Ctrl+O`, Settings → Choose…) were not exercised by the automated tests, which run offscreen. The CLI path and drag and drop are covered.
- **There's no undo** for deleting a highlight, bookmark or note.
- **Notes are plain text** in the app. Markdown you type passes through to the export unchanged.
- **There's no dark or inverted page mode.** Pages always render on white.
- **Highlights already in the PDF** (made in other apps) aren't imported or shown as editable.
- **It hasn't been tried on real class PDFs**, only on generated ones. Selection boxes come from pdfium's line boxes and may look a little loose on some PDFs.
- **Answer lines need a line.** An empty box, or open space under a question with no line, can't be typed into. Table cells aren't either, because table borders are skipped on purpose.
- **Answers on fill-in-the-blank sentences are one blank each.** A long answer shrinks to fit its blank, then wraps below it. It doesn't flow on to the next blank.
- **Answers don't appear in the sidebar or in search.** They're on the page and in the export.
- **`Ctrl+-` can't be sent by the offscreen test platform.** The tests instead check that no shortcut lists a key twice (Qt fires nothing for that: this is what broke `Ctrl+-` and `Ctrl+Q`) and call the resize directly. Real `Ctrl+-` presses were checked by hand on Hyprland with `wtype`.
- **The detector can be fooled.** A long horizontal rule with empty space above it, such as a separator under a heading, also counts as an answer line. A click there opens an empty answer, which disappears again when you click elsewhere.
- **Brought-over marks aren't realigned.** They keep their page and position. If a new edition moved text, they sit off and need redoing.
- **Only one matching copy is offered**, the one with the most marks. Marks from two older copies can't be merged in one go.
- **Library search reads every annotation file on each keystroke.** That's instant for dozens of documents. With hundreds it may need an index.
- **The PKGBUILD is untested.** There's no remote or release tarball yet, so `source`/`sha256sums` are placeholders. The wheel build was checked: it includes the QML, assets and the `dogear` entry point.

- **Syncing wasn't tried with a real second computer or a real sync service.** It was checked with two local data dirs sharing one library folder, files replaced underneath an open document, and hand-made conflict files using Syncthing's naming. Dropbox's and Google Drive's conflict names are matched by pattern (`<hash>…json`) but weren't seen for real.
- **A document removed on one computer while it's open on another comes back** when the other one saves. Nothing is lost, but it has to be removed again.
- **Moving the library in Settings runs in the foreground.** Copies moving to another drive can freeze the window for a moment with a big library.
- **An edit arriving while you type an answer** rebuilds the page's answer editors, so the cursor leaves the answer.

## Decisions made without asking

- **Omarchy-DB's source isn't on this machine.** Only its briefs and notes are, under `~/Projects/.admin-briefs`. I reused the theme-follow code (Omarchy theme parser and watcher, fontconfig font, Hyprland rounding) and the themed QML components from **Repokase**, Nine Point Labs' sibling PySide6/QML app with the same approach. These are adapted, not third-party code. Everything else is new.
- **Rendering uses QtPdf, not PyMuPDF.** QtPdf ships with `pyside6`, so there's no extra dependency, and it covers rendering, selection geometry, search rectangles, the outline, page labels and links. Pages render through QML's `PdfPageImage` in C++. My first version used a Python image provider, and it deadlocked under test (Qt's pdfium lock against the GIL on the render thread). Python now touches pdfium only on the UI thread.
- **Storage is a central store keyed by content hash, not a sidecar file.** This way annotations survive renames, nothing is written into class folders (which may be synced or read-only), and the PDF is untouched. When a file at a known path changes (a revised handout), its annotations are carried over with a notice. They may sit slightly off if the layout changed.
- **Export details:** one regenerated `<pdf name>.md` per PDF. It never overwrites a file Dogear didn't write. Two PDFs with the same name get a hash suffix.
- **Answer lines are found from pixels, not the text layer.** Worksheets draw blanks in too many ways (rules, underscores, dots) for the text layer alone. Answers are stored with the line's position in points, like highlights, so they keep their place at any zoom. They're typed in a proportional sans font in blue ink, at the page's own text size, so they read as filled in, not as part of the print.
- **The library folder holds copies, not your originals.** Moving originals into it would surprise you, break other links to them and risk a half-done move. Copies cost a few MB per book. Copies are named after the PDF's file name (not its hash) so the folder is browsable; they're still matched by hash, so renaming one in the folder is fine.
- **Sync merges never drop a mark.** An edit wins over a deletion from the other computer, and conflict copies are merged with nothing removed. The worst case is a deleted mark coming back, not a lost one. The reading position is last-writer-wins.
- **Categories moved out of the local index** into `.dogear/library.json`. The recent list changes on every open and stays local, so it doesn't cause constant sync conflicts.
- **The library doesn't hold your files.** There's no import step and PDFs stay where you keep them (file manager, sync). The private copy is only a fallback. The library lists what's in Dogear's store, so it needs no folder scanning.
- **Matching other copies asks first.** Copying marks silently could put them on the wrong text in a new edition.
- **Keybindings:** Super is left to Hyprland. Commands use Ctrl, and reading uses Vim-style plain keys (`j`/`k`, `J`/`K`, `g`/`G`, `/`, `n`/`N`).
- **Tests use stdlib `unittest`,** since pytest isn't installed for the system Python. pytest can run them too.
- **I didn't install anything into the system or `~/.local`** (desktop file, icons). They're in `packaging/` for when Dogear gets packaged through omarchy-pkgs.

## Repo

Local only. `v0.1` was merged into `main` (fast-forward). There is no remote and nothing was pushed.
