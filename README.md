# Dogear

**Read, highlight and remember your PDFs.**

Dogear is a PDF reader for studying, built for [Omarchy](https://omarchy.org). It does
what you'd do to a paper textbook: highlight in several colors, write notes next to
what you highlighted, bookmark pages, and keep general notes about the document. It
remembers where you stopped reading in every file. When you're done, export everything
to Markdown, for example straight into your Obsidian vault.

- Opens PDFs from the file dialog, the command line, drag and drop, or the recent files list.
- Remembers the page, scroll position and zoom for each file.
- Highlights in five colors. Click a highlight to change its color, add or edit its note, copy it, or delete it.
- Highlight notes show in the sidebar and as markers in the page margin. There are also general notes per document.
- Named bookmarks (bookmarked pages get a folded corner) and the PDF's own table of contents.
- Search with jumping between matches.
- Exports highlights, notes and bookmarks to Markdown, grouped by page.
- Keyboard first. Repaints immediately when you run `omarchy theme set`.
- Never modifies your PDFs. No network access, no telemetry.

## Run it

Dogear needs Python 3.12+ and PySide6 with QtPdf. On Arch/Omarchy that's the official
`pyside6` package:

```sh
sudo pacman -S --needed pyside6
```

Then run it from the source checkout:

```sh
~/Projects/dogear/bin/dogear                  # start screen with recent files
~/Projects/dogear/bin/dogear path/to/book.pdf # open a file
```

Or the equivalent: `PYTHONPATH=src python3 -m dogear [file.pdf]`.

The window's Wayland app id is `dogear`, so in Hyprland it's `class:dogear` in window
rules. `packaging/` holds a `.desktop` entry (registered for `application/pdf`), icons
and a PKGBUILD for when Dogear is packaged.

## Keyboard

Dogear leaves Super to Hyprland. Inside the app it uses Ctrl for commands and plain,
Vim-style keys for reading. Press `F1` or `?` to see this list in the app.

| Keys | Action |
| --- | --- |
| `Ctrl+O` | Open a PDF |
| `Ctrl+W` | Close the PDF (back to recent files) |
| `Ctrl+E` | Export to Markdown |
| `Ctrl+,` | Settings (export folder) |
| `Ctrl+Q` | Quit |
| `F1`, `?` | Keyboard shortcuts |
| `j` `k`, `↓` `↑` | Scroll |
| `h` `l`, `←` `→` | Scroll sideways (when zoomed in) |
| `Space`, `Shift+Space`, `PgDn`, `PgUp` | Down or up one screen |
| `J` `K` | Next or previous page |
| `g` `G`, `Home` `End` | First or last page |
| `Ctrl+G` | Go to a page (number or the PDF's page label) |
| `+` `-`, `Ctrl+=` `Ctrl+-`, `Ctrl`+wheel | Zoom |
| `0`, `Ctrl+0` | Fit width |
| `Alt+←`, `Backspace` | Back to where you were before a jump |
| drag, double-click | Select text, select a word |
| `1`–`5` | Highlight the selection (yellow, green, blue, pink, purple) |
| `a` | Highlight the selection in the last used color and write a note |
| `Ctrl+C` | Copy the selection |
| click a highlight | Change color (`1`–`5`), edit note (`e`/`Enter`), copy (`c`), delete (`d`/`Del`) |
| `b`, `Ctrl+D` | Bookmark the page (named after its table of contents entry) |
| `Ctrl+N` | New document note |
| `/`, `Ctrl+F` | Search |
| `Enter`/`n`, `Shift+Enter`/`N`, `F3`/`Shift+F3` | Next or previous match |
| `Ctrl+\`, `F9` | Show or hide the sidebar |
| `Ctrl+1` … `Ctrl+4` | Sidebar: Contents, Highlights, Bookmarks, Notes |
| `Esc` | Close search or popup, back to the page |

In the sidebar lists: `↑` `↓` to move, `Enter` to jump. In Highlights, `e` edits the note
and `Del` deletes. In Bookmarks, `r`/`F2` renames and `Del` deletes. On the start screen,
`Del` removes a file from the recent list.

## Markdown export

`Ctrl+E` writes `<pdf name>.md` into the export folder. The default folder is
`~/Documents/Dogear`. To use your Obsidian vault, open Settings (`Ctrl+,`) and pick a folder
inside the vault.

```markdown
---
title: "Biology 101"
source: "/home/tim/Classes/Biology 101.pdf"
sha256: 3f1c…
exported: 2026-10-16T20:30:00-04:00
highlights: 3
bookmarks: 1
tags: [dogear]
---

# Biology 101

## Notes

Exam covers chapters 1–3.

## Page 3

- **Bookmark:** Chapter 2: Photosynthesis

> The Calvin cycle fixes carbon dioxide into sugars.
> — p. 3 · green

Key exam point.
```

Document notes come first, then one section per page that has bookmarks or highlights.
Within a page, highlights are in reading order (top to bottom), and each note sits
under its highlight. When the PDF labels pages differently (roman numerals in a
preface, for example), the heading shows both: `## Page 5 (iv)`.

The export is generated and is overwritten on every export, so keep your own notes in
a separate file. Dogear never overwrites a Markdown file it didn't write (it checks
for its `sha256:` front matter). If two different PDFs have the same file name, the
second one is exported as `<name> (<hash prefix>).md`.

## Storage

Annotations live in a central store, one JSON file per PDF:

```
~/.local/share/dogear/              ($XDG_DATA_HOME/dogear, or $DOGEAR_DATA_DIR)
├── index.json                      recent files + path → hash cache
└── annotations/<sha256>.json       one PDF's highlights, notes, bookmarks, position
~/.config/dogear/settings.json      export folder
```

**Why a central store keyed by file hash and not a sidecar file next to the PDF:**

- Annotations survive renaming and moving the PDF, because the key is the SHA-256 of the
  file's bytes, not its path. An identical copy elsewhere shares the same annotations.
- Nothing is written into class folders. Those are often synced, shared or read-only
  (for example a downloads folder or a course's shared drive), and stray `.json`
  files there would be clutter or fail to write.
- The original PDF is never opened for writing.

Hashing is cached by path, size and modification time, so large PDFs are only hashed again
after they change. If the file at a known path changes (for example the instructor uploads
a revised handout under the same name), Dogear carries the annotations over to the new
version and tells you. The highlights may sit slightly off if the layout changed.

Writes are atomic (temp file, then rename). An unreadable JSON file is moved aside as
`<name>.corrupt-<timestamp>` instead of being overwritten.

Annotation file format (`"dogear": 1` is the schema version):

```json
{
  "dogear": 1,
  "sha256": "3f1c…",
  "file_name": "Biology 101.pdf",
  "title": "Biology 101",
  "paths": ["/home/tim/Classes/Biology 101.pdf"],
  "view": { "page": 12, "offset": 0.31, "zoom": 1.25, "fit_width": false, "x": 0.5 },
  "highlights": [
    {
      "id": "a1b2c3d4e5f6",
      "page": 2,
      "rects": [[72.0, 400.0, 210.5, 12.0]],
      "text": "The Calvin cycle fixes carbon dioxide into sugars.",
      "color": "green",
      "note": "Key exam point.",
      "created": "2026-10-16T20:31:02-04:00",
      "updated": "2026-10-16T20:31:40-04:00"
    }
  ],
  "bookmarks": [
    { "id": "…", "page": 2, "name": "Chapter 2: Photosynthesis", "y": 0.0, "created": "…" }
  ],
  "notes": [
    { "id": "…", "text": "Exam covers chapters 1–3.", "created": "…", "updated": "…" }
  ]
}
```

Pages are 0-based in the file and 1-based everywhere you see them. Rectangles are
`[x, y, width, height]` in PDF points (1/72 inch) from the page's top-left corner, so
they don't depend on zoom. `view.offset` is how far down the top page you'd scrolled (0–1).
Colors are `yellow`, `green`, `blue`, `pink` and `purple`. On screen they use the Omarchy
theme's matching colors when those are bright enough to read on paper, and classic
highlighter colors otherwise.

## How it's built

- **UI:** Qt Quick (QML) with a PySide6 host, using Basic-style templates that bind every
  color, font and spacing value to the live Omarchy theme. The theme code (parser and
  watcher for `~/.local/state/omarchy/current/theme`, fontconfig font and Hyprland rounding)
  comes from Nine Point Labs' Repokase.
- **PDF:** Qt PDF (`QtPdf`, pdfium), which ships with Arch's `pyside6` package, so there's
  no extra dependency. It covers everything Dogear needs: rendering, text selection
  geometry, search with match rectangles, the outline (table of contents), page labels
  and links. QML's `PdfPageImage` renders pages in C++ off the UI thread. Python uses its
  own `QPdfDocument` for text, search and outline, and only on the UI thread. That's on
  purpose: running Python on a render thread can deadlock Qt's pdfium lock against
  Python's GIL. PyMuPDF wasn't needed.
- **Core:** `store.py` (annotation store) and `export.py` (Markdown) are pure Python with
  no Qt imports, and they're unit tested.

```
src/dogear/
├── __main__.py      entry point, CLI
├── controllers.py   Doc and App objects exposed to QML
├── pdf.py           selection, word, outline and link helpers
├── store.py         annotation store (no Qt)
├── export.py        Markdown export (no Qt)
├── config.py        XDG paths, settings
├── theme/           Omarchy theme follow
└── qml/             Main.qml, views/, components/
```

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

This runs the store, export and theme tests, plus an offscreen end-to-end smoke test.
The smoke test drives the real QML app with mouse and keyboard input: it selects and
highlights text, writes a note, recolors a highlight, adds a bookmark and a document
note, searches, exports, then closes and reopens the file and checks that everything
was restored. It needs Ghostscript to build its sample PDF and is skipped without it.
`tools/make_sample_pdf.py` builds that sample on its own.

## License

MIT. See [LICENSE](LICENSE).
