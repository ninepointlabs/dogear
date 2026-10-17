# Dogear

**Read, highlight and remember your PDFs.**

Dogear is a PDF reader for studying, built for [Omarchy](https://omarchy.org). It does
what you'd do to a paper textbook: highlight in several colors, write notes next to
what you highlighted, bookmark pages, fill in the blanks on worksheets, and keep
general notes about the document. It
remembers where you stopped reading in every file. When you're done, export everything
to Markdown, for example straight into your Obsidian vault.

- A library of every PDF you've opened: search (titles, folders, and the text of your
  highlights, notes and answers), sort and file them under categories.
- Keeps a copy of each PDF you mark up, so your marks never lose their PDF.
- Keeps the whole library in one folder (`~/Documents/Dogear` by default) that you can
  sync between computers with Syncthing, Dropbox, Google Drive and the like.
- Recognizes another copy of a book you've marked up (a re-download, a new edition)
  and offers to bring your marks over.
- Opens PDFs from the file dialog, the command line, drag and drop, or the library.
- Remembers the page, scroll position and zoom for each file.
- Highlights in five colors. Click a highlight to change its color, add or edit its note, copy it, or delete it.
- Highlight notes show in the sidebar and as markers in the page margin. There are also general notes per document.
- Answer lines: click a blank line in a worksheet and type. Your answer sits on the line.
- Named bookmarks (bookmarked pages get a folded corner) and the PDF's own table of contents.
- Search with jumping between matches.
- Exports highlights, notes, bookmarks and answers to Markdown, grouped by page.
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
| `Ctrl+W`, `Ctrl+L` | Close the PDF, back to the library |
| `Ctrl+E` | Export to Markdown |
| `Ctrl+,` | Settings (library folder, export folder, copies) |
| `Ctrl+Q` | Quit |
| `F1`, `?` | Keyboard shortcuts |
| `j` `k`, `↓` `↑`, mouse wheel | Scroll (the wheel glides, and goes further the faster you spin it; touchpads follow your fingers) |
| `Shift`+wheel | Scroll sideways |
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
| hover a highlight | Shows its note, if it has one (also when hovering its margin marker) |
| click a highlight | Change color (`1`–`5`), edit note (`e`/`Enter`), copy (`c`), delete (`d`/`Del`) |
| click an answer line, `i` | Type an answer on it (`i`: the first answer line in view) |
| `Tab`, `Shift+Tab` (while answering) | Next or previous answer line |
| `Enter` (while answering) | Next answer line; on ruled lines under a question, a new line |
| `Ctrl+=`, `Ctrl+-` (while answering) | Answer text bigger or smaller (instead of zooming) |
| `Esc` (while answering) | Done typing |
| `b`, `Ctrl+D` | Bookmark the page (named after its table of contents entry) |
| `Ctrl+N` | New document note |
| `/`, `Ctrl+F` | Search |
| `Enter`/`n`, `Shift+Enter`/`N`, `F3`/`Shift+F3` | Next or previous match |
| `Ctrl+\`, `F9` | Show or hide the sidebar |
| `Ctrl+1` … `Ctrl+4` | Sidebar: Contents, Highlights, Bookmarks, Notes |
| `Esc` | Close search or popup, back to the page |

In the sidebar lists: `↑` `↓` to move, `Enter` to jump. In Highlights, `e` edits the note
and `Del` deletes. In Bookmarks, `r`/`F2` renames and `Del` deletes.

In the library: `/` searches, `s` changes the sort order, `F2` renames a document, `Del`
removes it, `c` sets its categories, `n` makes a new category, `←` `→` move between categories and documents, and
in the category list `F2` renames and `Del` deletes a category. Settings is the button next to
Open PDF, or `Ctrl+,` anywhere.

## Answer lines

Worksheets and workbooks leave lines to write answers on. Click just above (or on) such
a line and start typing. There's no text box to place: Dogear finds the line, writes on
it in blue ink at the size of the page's own text, and shrinks a long answer to fit a
short blank. When the mouse is over an empty answer line it lights up, so you can see
where you can write.

- Ruled lines under a question (evenly spaced, same length) are one answer. The text
  wraps from line to line, and `Enter` starts a new line.
- `Tab` and `Enter` move to the next blank, so a fill-in-the-blank page can be done from
  the keyboard. `Shift+Tab` goes back. `i` starts on the first line in view.
- To fit more on a line, make the answer's text smaller with `Ctrl+-` (`Ctrl+=` makes it
  bigger), or with the A− / A+ buttons in the bar at the bottom of the view while typing.
  Each answer keeps its own size.
- Click an answer to change it. Empty it to remove it.

Lines are found in the rendered page, not the text, so drawn rules, runs of underscores
and dotted lines all work. Edges of boxes and tables, underlines under text and thick
bars are ignored. Short blanks (down to about 14 pt, like `____ sentence` lists) count
when they have space on both sides and nothing right below them, which tells them apart
from dashes and letters.

## Library

With no PDF open (or after `Ctrl+L`), Dogear shows its library: every PDF you've opened,
with how many highlights, notes, answers and bookmarks it has and when you last read it.

- **Search** matches titles, file names, folders and categories, and also the text of
  your highlights, notes, answers and bookmark names ("found in your marks").
- **Sort** by Recent, Title, Most marked or Added (`s` cycles).
- **Categories** organize a long list. A document can be in several. Press `c` on a
  document to tick categories or type a new one. Pick a category on the left to see
  only its documents, or *Uncategorized* for the ones not filed yet. Renaming a category
  onto an existing name merges the two. Deleting one leaves its documents in the library.
  Categories are exported as Obsidian tags.

- **Rename** a document (`F2`, or the Rename button on the row) to call it something
  you'll recognize, such as "Book 3: Children's Classes" instead of
  `RUHI0110_CC1_BK3_EN_2.2.1.PE_FullText_20210930`. The name is Dogear's only. The file
  isn't renamed, the PDF's own title still shows underneath and is searchable, and the
  name is used for the window title and the export heading. Clear the name to go back.
- **Remove** a document (`Del`, or Remove) to take it out of the library, after you
  confirm. Its marks and Dogear's copy aren't deleted outright: they move to
  `.dogear/removed/<sha256>-<time>/` in the library folder. To restore, move the `.json`
  back into `.dogear/annotations/` and the `.pdf` into `Library/`. The PDF itself is never
  touched. Opening it again later starts fresh.

**Your marks always have their PDF.** Dogear never changes your PDFs, and it keeps a
copy of every PDF you mark up in the `Library/` folder of the library folder, under the
PDF's own file name (Settings → "Keep a copy of every PDF I mark up", on by default;
Settings shows the disk space). Your files stay where they are, and the library opens
the original when it can. If the original is moved, renamed or deleted, or you're on
another computer, it opens the copy instead. A PDF you keep inside the library folder
yourself needs no copy, so it isn't copied. Documents marked up before copies existed
get theirs a few seconds after Dogear starts.

## Using several computers

Everything Dogear keeps for you lives in one folder, `~/Documents/Dogear` by default:

```
~/Documents/Dogear/
├── Library/          copies of the PDFs you mark up ("Ruhi Book 5.pdf", …)
├── Notes/            Markdown exports (the default export folder)
└── .dogear/          your marks (one file per PDF), categories, removed documents
```

Sync that folder (Syncthing, Dropbox, Google Drive, Nextcloud…) and every computer has
the same library: the same documents, marks, categories, names and reading position.
On a computer that never had the PDF, the library opens the copy in `Library/`. To use
another folder, for example one your sync service already covers, change **Library
folder** in Settings (`Ctrl+,`). Dogear moves the library there. If that folder already
has a Dogear library (from another computer), the two are merged.

What happens when both computers change things:

- **While a document is open**, Dogear notices when its file changes underneath (another
  computer's edits arriving) and takes them in. Your own unsaved changes are kept: marks
  are merged one by one, so a highlight added here and a note added there both stay, and
  a mark deleted on one computer stays deleted.
- **If both computers changed the same document before syncing**, the sync service keeps
  both versions (Syncthing's `….sync-conflict-….json`, Dropbox's "conflicted copy",
  Google Drive's `(1)`). Dogear merges the conflict copy back in, keeping every mark from
  both, and moves the conflict file to `.dogear/removed/conflicts/`.
- A mark changed on both computers keeps the newer edit. A mark deleted on one and edited
  on the other is kept. The reading position is whichever computer saved last.

What stays on each computer: recent files (in `~/.local/share/dogear`),
and settings (in `~/.config/dogear`). If the library folder isn't there (sync not set up
yet, a drive not mounted), Dogear starts an empty library in it.

**Other copies of the same book.** Marks belong to the exact bytes of a file. A
re-download or a new edition is a different file and would open blank. When a PDF with
no marks looks like one you've marked up, Dogear asks whether to bring the marks over. It
counts as the same book when it has the same PDF document ID, or when its title or file
name matches apart from version numbers and dates (`…_2.1.1…_20210325` and
`…_2.2.1…_20210930`) and the page counts are within about 5%. "Lecture 1" and "Lecture 2"
don't match. "Not this one" stops it asking about that copy. `Esc` decides nothing and it
asks again next time. If the editions' pages differ, some brought-over marks may sit off.

## Markdown export

`Ctrl+E` writes `<pdf name>.md` into the export folder. The default folder is `Notes/` in
the library folder (`~/Documents/Dogear/Notes`). To use your Obsidian vault, open Settings (`Ctrl+,`) and pick a folder
inside the vault.

```markdown
---
title: "Biology 101"
source: "/home/tim/Classes/Biology 101.pdf"
sha256: 3f1c…
exported: 2026-10-16T20:30:00-04:00
highlights: 3
bookmarks: 1
answers: 2
tags: [dogear, biology]
---

# Biology 101

## Notes

Exam covers chapters 1–3.

## Page 3

- **Bookmark:** Chapter 2: Photosynthesis

> The Calvin cycle fixes carbon dioxide into sugars.
> — p. 3 · green

Key exam point.

**Q:** 3. Plants absorb ___ and ___ light.  
**A:** red  
**A:** blue  
```

Document notes come first, then one section per page that has bookmarks, highlights
or answers. Within a page, highlights and answers are in reading order (top to
bottom), and each note sits under its highlight. An answer comes with the printed
text around its line (`**Q:**`, blanks shown as `___`), so the export reads without the PDF. When the PDF labels pages differently (roman numerals in a
preface, for example), the heading shows both: `## Page 5 (iv)`.

The export is generated and is overwritten on every export, so keep your own notes in
a separate file. Dogear never overwrites a Markdown file it didn't write (it checks
for its `sha256:` front matter). If two different PDFs have the same file name, the
second one is exported as `<name> (<hash prefix>).md`.

## Storage

Annotations live in the library folder, one JSON file per PDF:

```
~/Documents/Dogear/                 the library folder (Settings, or $DOGEAR_LIBRARY_DIR)
├── Library/<file name>.pdf         copies of marked-up PDFs
├── Notes/                          Markdown exports, by default
└── .dogear/
    ├── annotations/<sha256>.json   one PDF's highlights, notes, bookmarks, answers, position
    ├── library.json                categories
    └── removed/                    removed documents, set-aside sync conflict copies
~/.local/share/dogear/index.json    this computer's recent files and path → hash cache
                                    ($XDG_DATA_HOME/dogear, or $DOGEAR_DATA_DIR)
~/.config/dogear/settings.json      library folder, export folder, copies on/off
```

Earlier versions kept everything in `~/.local/share/dogear`. The first start of this
version moves it into the library folder (merging with a library already there) and
leaves the old notes files, renamed `annotations.moved-<time>/`, next to a `MOVED.txt`.

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
  ],
  "answers": [
    {
      "id": "…", "page": 2, "x": 162.0, "y": 623.0, "w": 107.0,
      "pitch": 0.0, "lines": 1, "size": 11.5,
      "text": "red", "context": "3. Plants absorb ___ and ___ light.",
      "created": "…", "updated": "…"
    }
  ],
  "categories": ["Biology"],
  "added": "2026-10-16T20:30:00-04:00",
  "opened": 1792245000.0,
  "page_count": 204,
  "pdf_id": "4216DE69CFB8A749BFB2482F35376307",
  "declined": [],
  "label": "Book 3: Children's Classes"
}
```

Pages are 0-based in the file and 1-based everywhere you see them. Rectangles are
`[x, y, width, height]` in PDF points (1/72 inch) from the page's top-left corner, so
they don't depend on zoom. `view.offset` is how far down the top page you'd scrolled (0–1).
For an answer, `x`/`y`/`w` are the left end, height and length of its line, and
`pitch` and `lines` describe ruled lines below it (`pitch` 0 means a single line).
`page_count`, `pdf_id` (the PDF's own document ID) and the title are what recognize
other copies of the same book. `declined` lists copies you said not to take marks from.
`label` is your own name for the document (empty: use its title).
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
  no Qt imports, and they're unit tested. So is the answer-line detector in `rules.py`:
  it scans 8-bit grayscale bytes of a page rendered at 2 px/pt, about 20 ms a page, and
  caches the result per page.

```
src/dogear/
├── __main__.py      entry point, CLI
├── controllers.py   Doc and App objects exposed to QML
├── pdf.py           selection, word, outline, link and text line helpers
├── rules.py         finds answer lines in a rendered page (no Qt in the detector)
├── store.py         annotation store, categories, library copies (no Qt)
├── library.py       library rows, search, sort, finding other copies (no Qt)
├── export.py        Markdown export (no Qt)
├── config.py        XDG paths, settings
├── theme/           Omarchy theme follow
└── qml/             Main.qml, views/, components/
```

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

This runs the store, library, export, answer-line and theme tests, plus offscreen end-to-end smoke tests.
The smoke test drives the real QML app with mouse and keyboard input: it selects and
highlights text, writes a note, recolors a highlight, adds a bookmark and a document
note, types answers on a worksheet page (click, `Tab`, `Enter`), searches, exports,
then closes and reopens the file and checks that everything was restored. It needs Ghostscript to build its sample PDF and is skipped without it.
`tools/make_sample_pdf.py` builds that sample on its own.

## License

MIT. See [LICENSE](LICENSE).
