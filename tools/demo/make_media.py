#!/usr/bin/env python3
"""Makes the site's screenshots and the narrated demo video from the real app.

    tools/demo/make_media.py           # everything
    tools/demo/make_media.py record    # just record the scenes again
    tools/demo/make_media.py video     # just cut the video from the recordings

Needs ffmpeg, ImageMagick, Chromium, PySide6 and an ElevenLabs API key in
$ELEVENLABS_API_KEY or ~/.config/elevenlabs/api_key. Narration is cached in
work/tts by its text, so re-runs only pay for changed lines.

The app runs offscreen with a scratch library, data and config in work/ and
the site's palette as its theme (theme/colors.toml); your own library, theme
and settings are untouched. The demo PDFs are original handouts printed from
HTML (handout.html and COURSES below) by headless Chromium.

Writes docs/images/*.webp and og.jpg, docs/media/dogear-demo.mp4 and its
poster.
"""

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORK = HERE / "work"
OUT = WORK / "out"
DOCS = ROOT / "docs"
FPS = 30
W, H = 1920, 1080

# Short handouts for the other courses, so the library has a few classes.
COURSES = {
    "Biology 101/Unit 2 - Cell Structure.pdf": ("Unit 2: Cell Structure", [
        ("The parts of a cell", "Every living thing is made of cells. Inside each one, the cell membrane decides "
         "what comes in and what goes out, and the nucleus holds the instructions for everything the cell does."),
        ("Power and packaging", "The mitochondria release the energy stored in sugar. The Golgi apparatus sorts "
         "and packages proteins, like a post office, and sends them where they are needed."),
    ]),
    "History 210/The Scientific Revolution.pdf": ("The Scientific Revolution", [
        ("A new way of knowing", "Between about 1550 and 1700, European thinkers began to test ideas against "
         "observation and experiment. Cheap books from the printing press spread their results quickly."),
        ("Galileo", "Galileo turned a telescope to the sky and saw moons circling Jupiter, evidence that not "
         "everything in the heavens revolves around the Earth."),
    ]),
    "Calculus I/Derivatives.pdf": ("Derivatives", [
        ("The idea", "A derivative measures how fast a quantity changes: the slope of a curve at a single point."),
        ("Rules worth knowing", "The power rule handles polynomials. The product rule handles two functions "
         "multiplied together, and the chain rule handles one function inside another."),
    ]),
    "Spanish 102/Preterite and Imperfect.pdf": ("Preterite and Imperfect", [
        ("Two past tenses", "Spanish has two simple past tenses. The preterite tells what happened and was "
         "completed. The imperfect describes what was happening, or what used to happen."),
        ("Examples", "Ayer comí paella: yesterday I ate paella. De niño comía paella los domingos: as a child "
         "I used to eat paella on Sundays."),
    ]),
}

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title><style>
@page {{ size: Letter; margin: 1in; }}
body {{ font-family: "Liberation Serif", serif; font-size: 12pt; line-height: 1.5; }}
h1, h2 {{ font-family: "Liberation Sans", sans-serif; }} h1 {{ font-size: 22pt; }} h2 {{ font-size: 15pt; }}
</style></head><body><h1>{title}</h1>{body}</body></html>"""


def run(*cmd, **kw):
    print("+", " ".join(str(c) for c in cmd)[:200], flush=True)
    return subprocess.run([str(c) for c in cmd], check=kw.pop("check", True), **kw)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def chromium():
    for name in ["chromium", "google-chrome-stable", "chromium-browser"]:
        if shutil.which(name):
            return name
    sys.exit("needs Chromium")


def print_pdf(html_path: Path, pdf_path: Path):
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    run(chromium(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--generate-pdf-document-outline",
        f"--print-to-pdf={pdf_path}", f"file://{html_path}", stderr=subprocess.DEVNULL)


def env():
    e = dict(os.environ)
    e.update({
        "QT_QPA_PLATFORM": "offscreen",
        "QSG_RENDER_LOOP": "basic",
        "QT_SCALE_FACTOR": "1.5",
        "DOGEAR_DATA_DIR": str(WORK / "data"),
        "DOGEAR_CONFIG_DIR": str(WORK / "config"),
        "DOGEAR_LIBRARY_DIR": str(WORK / "home" / "Documents" / "Dogear"),
        "DOGEAR_THEME_DIR": str(HERE / "theme"),
        # A scratch home, so the library shows ~/Documents/Classes/…
        "HOME": str(WORK / "home"),
    })
    return e


def record():
    """A fresh scratch library, the PDFs, then the scenes."""
    for d in ["data", "config", "home", "out", "src"]:
        shutil.rmtree(WORK / d, ignore_errors=True)
    classes = WORK / "home" / "Documents" / "Classes"
    print_pdf(HERE / "handout.html", classes / "Biology 101" / "Unit 3 - Photosynthesis.pdf")
    for rel, (title, sections) in COURSES.items():
        body = "".join(f"<h2>{html.escape(h)}</h2><p>{html.escape(p)}</p>" for h, p in sections)
        src = WORK / "src" / (Path(rel).stem + ".html")
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(PAGE.format(title=html.escape(title), body=body))
        print_pdf(src, classes / rel)
    run(sys.executable, HERE / "record.py", "setup", env=env())
    run(sys.executable, HERE / "record.py", "video", env=env())


def shots():
    dest = DOCS / "images"
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(OUT.glob("shot-*.png")):
        run("magick", src, "-quality", "86", "-define", "webp:method=6", dest / f"{src.stem[5:]}.webp")
    # The link preview (og:image): the hero, cropped to 1200×630.
    run("magick", OUT / "shot-hero.png", "-resize", "1200x", "-gravity", "center", "-crop", "1200x630+0+0", "+repage",
        "-quality", "85", dest / "og.jpg")


# ---------------------------------------------------------------------- video

def card(spec, path, transparent=False, page=None):
    page = page or HERE / "cards" / "card.html"
    args = [chromium(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={W},{H}",
            "--virtual-time-budget=5000", f"--screenshot={path}", f"file://{page}#{spec}"]
    if transparent:
        args.insert(1, "--default-background-color=00000000")
    run(*args, stderr=subprocess.DEVNULL)


def export_card(path):
    """The real Markdown export, as a note in a vault."""
    md = next((WORK / "home" / "Documents" / "Dogear" / "Notes").glob("*.md"))
    text = md.read_text()
    text = text.split("---\n", 2)[-1].strip()  # the front matter is noise here
    text = "\n".join(line for line in text.splitlines() if not line.startswith("*Exported from Dogear"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    out = []
    for line in html.escape(text).splitlines():
        if line.startswith("#"):
            line = f'<span class="h">{line}</span>'
        elif line.startswith("**Q:**"):
            line = f'<span class="q">{line}</span>'
        elif line.startswith("**A:**"):
            line = f'<span class="a">{line}</span>'
        elif line.startswith("&gt; —"):
            line = f'<span class="k">{line}</span>'
        out.append(line)
    page = WORK / "cards" / "export.html"
    template = (HERE / "cards" / "export.html").read_text()
    page.write_text(template.replace("#EXPORT#", "\n".join(out)).replace("#FILE#", html.escape(md.name)))
    card("export", path, page=page)


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        key = (Path.home() / ".config/elevenlabs/api_key").read_text().strip()
    return key


def narrate(narration):
    """One MP3 per segment, cached by voice, model and text."""
    tts = WORK / "tts"
    tts.mkdir(parents=True, exist_ok=True)
    segments = narration["segments"]
    paths = []
    for i, seg in enumerate(segments):
        body = {
            "text": seg["text"],
            "model_id": narration["model"],
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True},
            # Neighbouring lines, so the read flows from one to the next.
            "previous_text": segments[i - 1]["text"] if i > 0 else "",
            "next_text": segments[i + 1]["text"] if i + 1 < len(segments) else "",
        }
        digest = hashlib.sha256(json.dumps([narration["voice"], body], sort_keys=True).encode()).hexdigest()[:16]
        path = tts / f"{seg['clip']}-{digest}.mp3"
        if not path.exists():
            print(f"  narrating {seg['clip']}", flush=True)
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{narration['voice']}?output_format=mp3_44100_128",
                data=json.dumps(body).encode(), method="POST",
                headers={"xi-api-key": api_key(), "Content-Type": "application/json", "Accept": "audio/mpeg"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                path.write_bytes(resp.read())
        paths.append(path)
    return paths


def segment(seg, audio, out, fade_out):
    """One finished piece: the clip (or card), its narration and caption."""
    lead, tail = 0.35, 0.7
    spoken = duration(audio)
    inputs, filters = [], []
    if "card" in seg:
        png = WORK / "cards" / f"{seg['card']}.png"
        length = lead + spoken + (2.4 if seg["card"] == "end" else 1.2)
        inputs += ["-loop", "1", "-framerate", FPS, "-t", f"{length:.3f}", "-i", png]
        # A slow push in, so the card isn't a still.
        filters.append(f"[0:v]scale={W * 2}:-1,zoompan=z='1+0.04*on/({length:.3f}*{FPS})':d=1:s={W}x{H}:fps={FPS}"
                       f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'[v0]")
    else:
        clip = OUT / f"{seg['clip']}.mp4"
        length = max(duration(clip), lead + spoken + tail)
        inputs += ["-i", clip]
        # Hold the last frame if the narration runs longer than the clip.
        filters.append(f"[0:v]tpad=stop_mode=clone:stop_duration={length:.3f},trim=duration={length:.3f},"
                       f"setpts=PTS-STARTPTS[v0]")
    inputs += ["-i", audio]
    last = "v0"
    if "caption" in seg:
        png = WORK / "cards" / f"caption-{seg['clip']}.png"
        inputs += ["-loop", "1", "-framerate", FPS, "-t", f"{length:.3f}", "-i", png]
        filters.append("[2:v]format=rgba,fade=in:st=0.3:d=0.4:alpha=1,fade=out:st=3.4:d=0.5:alpha=1[cap]")
        filters.append("[v0][cap]overlay=0:0:shortest=1[v1]")
        last = "v1"
    fades = []
    if seg.get("fade_in") or seg.get("card") == "title":
        fades.append(f"fade=in:st=0:d={0.8 if seg.get('card') == 'title' else 0.35}")
    if fade_out:
        d = 1.2 if seg.get("card") == "end" else 0.35
        fades.append(f"fade=out:st={length - d:.3f}:d={d}")
    filters.append(f"[{last}]" + ",".join(fades + ["format=yuv420p"]) + "[v]")
    delay = int(lead * 1000)
    filters.append(f"[1:a]adelay={delay}|{delay},apad,atrim=duration={length:.3f},aresample=48000[a]")
    run("ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", "[a]", "-r", FPS, "-c:v", "libx264", "-preset", "slow", "-crf", "12",
        "-c:a", "pcm_s16le", "-t", f"{length:.3f}", out)


def video():
    narration = json.loads((HERE / "narration.json").read_text())
    segments = narration["segments"]
    cards = WORK / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    card("title", cards / "title.png")
    card("end", cards / "end.png")
    export_card(cards / "export.png")
    run("magick", cards / "export.png", "-quality", "86", "-define", "webp:method=6", DOCS / "images" / "export.webp")
    for seg in segments:
        if "caption" in seg:
            card(f"caption={seg['caption']}", cards / f"caption-{seg['clip']}.png", transparent=True)
    audio = narrate(narration)
    pieces = WORK / "pieces"
    pieces.mkdir(parents=True, exist_ok=True)
    listing = []
    for i, seg in enumerate(segments):
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        fade_out = nxt is None or bool(nxt.get("fade_in")) or "card" in seg or (nxt is not None and "card" in nxt)
        path = pieces / f"{seg['clip']}.mkv"
        segment(seg, audio[i], path, fade_out)
        listing.append(f"file '{path}'")
    (pieces / "list.txt").write_text("\n".join(listing) + "\n")
    joined = WORK / "joined.mkv"
    run("ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", pieces / "list.txt", "-c", "copy", joined)
    media = DOCS / "media"
    media.mkdir(parents=True, exist_ok=True)
    final = media / "dogear-demo.mp4"
    run("ffmpeg", "-loglevel", "error", "-y", "-i", joined,
        "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", final)
    run("magick", cards / "title.png", "-resize", "1600x", "-quality", "82", media / "dogear-demo-poster.jpg")
    print(f"{final}: {duration(final):.1f}s, {final.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "record"):
        record()
        shots()
    if what in ("all", "video"):
        video()
