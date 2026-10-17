"""Merging two versions of a document's annotations (no Qt).

The library folder can be shared between computers with Syncthing, Dropbox,
Google Drive and the like. Two versions of one document's file then meet in
two ways:

- the file changed on disk (another computer's edits synced in) while this
  computer has it open: a three-way merge against the version this computer
  last read or wrote, so deletions on either side stick;
- the sync service kept both versions as a conflict copy: no common base is
  known, so everything on either side is kept.

Highlights, bookmarks, notes and answers have ids, so they merge one by one.
An item changed on both sides keeps the newer edit. An item deleted on one
side and edited on the other is kept: losing an edit is worse than seeing a
deleted mark again.
"""

from __future__ import annotations

from .store import DocAnnotations

ITEMS = ("highlights", "bookmarks", "notes", "answers")
# Lists that are combined when there is no base, instead of one side winning.
_UNION = ("paths", "categories", "declined")


def _stamp(item: dict) -> str:
    return item.get("updated") or item.get("created") or ""


def _newer(mine: dict, theirs: dict) -> dict:
    # ISO stamps with offsets from one person's computers compare as text
    # well enough; a tie keeps this computer's version.
    return theirs if _stamp(theirs) > _stamp(mine) else mine


def _merge_items(base: list[dict] | None, mine: list[dict], theirs: list[dict]) -> list[dict]:
    b = {x["id"]: x for x in base} if base is not None else None
    m = {x["id"]: x for x in mine}
    t = {x["id"]: x for x in theirs}
    out = []
    for iid in list(m) + [i for i in t if i not in m]:
        mi, ti = m.get(iid), t.get(iid)
        bi = b.get(iid) if b is not None else None
        if mi is not None and ti is not None:
            if bi is not None and mi == bi:
                out.append(ti)
            elif bi is not None and ti == bi:
                out.append(mi)
            else:
                out.append(_newer(mi, ti))
        else:
            only = mi if mi is not None else ti
            # Missing on one side: deleted there if it was in the base,
            # unless this side edited it since.
            if bi is None or only != bi:
                out.append(only)
    return out


def merge(base: DocAnnotations | None, mine: DocAnnotations, theirs: DocAnnotations) -> DocAnnotations:
    """Combine this computer's version with the one found on disk.

    `base` is the version both started from (what this computer last read
    or wrote), or None for a sync conflict copy."""
    b = base.to_dict() if base is not None else None
    m = mine.to_dict()
    t = theirs.to_dict()
    out = dict(m)
    for kind in ITEMS:
        out[kind] = _merge_items(b[kind] if b is not None else None, m[kind], t[kind])
    for key in set(m) | set(t):
        if key in ITEMS or key in ("dogear", "sha256"):
            continue
        mv, tv = m.get(key), t.get(key)
        if b is not None:
            out[key] = mv if mv != b.get(key) else tv
        elif key in _UNION:
            out[key] = list(dict.fromkeys([*(mv or []), *(tv or [])]))
        elif key == "opened":
            out[key] = max(mv or 0, tv or 0)
        elif key == "added":
            out[key] = min(v for v in (mv, tv, "~") if v)  # earliest; "~" sorts last
            out[key] = "" if out[key] == "~" else out[key]
        else:
            out[key] = mv if mv not in (None, "", 0, []) else tv
    if b is None and "categories" in out:
        out["categories"] = sorted(out["categories"], key=str.casefold)
    return DocAnnotations.from_dict(out, mine.sha256)
