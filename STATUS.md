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

Verified by `PYTHONPATH=src python3 -m unittest discover -s tests` (42 tests, all pass,
stable over 6 consecutive runs) and by a short run on the real Hyprland session.

- Open from the CLI argument, `Ctrl+O` file dialog, drag and drop, and the recent files list on the start screen. The start screen marks missing files, and `Del` removes an entry.
- Remembers page, scroll offset, zoom and fit-width per file. The smoke test closes and reopens a file and checks the page and zoom.
- Text selection by drag, or double-click for a word. Five highlight colors (keys `1`–`5` or the floating bar). Click a highlight to recolor it, edit its note, copy or delete it.
- Mouse-wheel scrolling glides smoothly. Touchpads scroll 1:1, and `Shift`+wheel scrolls sideways.
- Hovering a highlight that has a note, or its margin marker, shows the note in a tooltip after a short delay.
- Highlight notes appear in the Highlights sidebar and as markers in the page margin. General per-document notes are in the Notes sidebar.
- Named bookmarks, defaulting to the page's table of contents entry. They have a sidebar panel and a dog-ear on the page corner. The PDF outline appears in the Contents panel, with the current section highlighted.
- Incremental search with match count. Enter/`n` and Shift+Enter/`N` jump between matches, starting from the page you're reading.
- Markdown export (`Ctrl+E`) grouped by page, with quoted highlights, page numbers and labels, notes and bookmarks, plus YAML front matter. The export folder is configurable in Settings (`Ctrl+,`). Default is `~/Documents/Dogear`.
- Storage is a central store keyed by SHA-256 in `~/.local/share/dogear`. The PDF is never written to, and tests check that nothing appears next to it. Annotations survive renames and moves.
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
- **The PKGBUILD is untested.** There's no remote or release tarball yet, so `source`/`sha256sums` are placeholders. The wheel build was checked: it includes the QML, assets and the `dogear` entry point.

## Decisions made without asking

- **Omarchy-DB's source isn't on this machine.** Only its briefs and notes are, under `~/Projects/.admin-briefs`. I reused the theme-follow code (Omarchy theme parser and watcher, fontconfig font, Hyprland rounding) and the themed QML components from **Repokase**, Nine Point Labs' sibling PySide6/QML app with the same approach. These are adapted, not third-party code. Everything else is new.
- **Rendering uses QtPdf, not PyMuPDF.** QtPdf ships with `pyside6`, so there's no extra dependency, and it covers rendering, selection geometry, search rectangles, the outline, page labels and links. Pages render through QML's `PdfPageImage` in C++. My first version used a Python image provider, and it deadlocked under test (Qt's pdfium lock against the GIL on the render thread). Python now touches pdfium only on the UI thread.
- **Storage is a central store keyed by content hash, not a sidecar file.** This way annotations survive renames, nothing is written into class folders (which may be synced or read-only), and the PDF is untouched. When a file at a known path changes (a revised handout), its annotations are carried over with a notice. They may sit slightly off if the layout changed.
- **Export details:** one regenerated `<pdf name>.md` per PDF. It never overwrites a file Dogear didn't write. Two PDFs with the same name get a hash suffix.
- **Keybindings:** Super is left to Hyprland. Commands use Ctrl, and reading uses Vim-style plain keys (`j`/`k`, `J`/`K`, `g`/`G`, `/`, `n`/`N`).
- **Tests use stdlib `unittest`,** since pytest isn't installed for the system Python. pytest can run them too.
- **I didn't install anything into the system or `~/.local`** (desktop file, icons). They're in `packaging/` for when Dogear gets packaged through omarchy-pkgs.

## Repo

Local only. All work is on branch `v0.1` (small commits). There is no remote and nothing was pushed. `main` has no commits yet, so merge `v0.1` when you accept it.
