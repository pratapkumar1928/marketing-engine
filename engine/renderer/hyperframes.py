"""Recipe renderer: one HyperFrames composition drawn from fixed blocks, in the app's brand tokens.

Every piece of text is HTML-escaped. Every text box sits inside SAFE_BOX (TikTok/Reels UI keeps the
bottom 20% and right 12%). Roast lines come from the content item verbatim, never from AI copy.
"""
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from engine.recipes import pool
from engine.types import Copy

RENDERER_DIR = Path(__file__).resolve().parent.parent.parent / "renderer"
SAFE_BOX = {"left": 80, "top": 220, "width": 870, "height": 1316}
CLIP_MAX = 8.0
L, W = SAFE_BOX["left"], SAFE_BOX["width"]


def _e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def timeline(recipe: dict, content: dict) -> list[tuple[dict, float, float]]:
    out, t = [], 0.0
    for b in recipe["beats"]:
        d = min(float(content.get("dur", CLIP_MAX)), CLIP_MAX) if b["dur"] == "clip" else float(b["dur"])
        out.append((b, round(t, 3), round(d, 3)))
        t += d
    return out


def _fit(text: str, sizes: tuple[int, int, int]) -> int:
    n = len(text)
    return sizes[0] if n <= 22 else sizes[1] if n <= 44 else sizes[2]


def _text_for(beat: dict, ctx: dict) -> str:
    key = beat.get("text")
    copy: Copy = ctx["copy"]
    if not key:
        return ""
    if key == "hook":
        return copy.hook
    if key.startswith("line:"):
        return copy.texts.get(key.split(":", 1)[1], "")
    c = ctx["content"]  # "content": the item itself, verbatim
    return c.get("text") or c.get("headline") or copy.hook


def _enter(sel: str, t0: float, transition: str) -> str:
    if transition == "punch":
        return (f'tl.fromTo("{sel}", {{ opacity: 0, scale: 1.3 }}, {{ opacity: 1, scale: 1, duration: 0.16, '
                f'ease: "power4.in" }}, {t0});\n      shake("{sel}", {t0} + 0.16, 30);')
    if transition == "slide_up":
        return f'tl.fromTo("{sel}", {{ opacity: 0, y: 80 }}, {{ opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }}, {t0});'
    if transition == "fade":
        return f'tl.fromTo("{sel}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.4 }}, {t0});'
    return f'tl.fromTo("{sel}", {{ opacity: 0, y: 24 }}, {{ opacity: 1, y: 0, duration: 0.25, ease: "power3.out" }}, {t0} + 0.05);'


def _bg(i: int, beat: dict, t0: float, dur: float, ctx: dict) -> str:
    want = beat.get("bg", "dark")
    span = f'data-start="{t0}" data-duration="{dur}"'
    if want == "broll" and ctx["srcs"].get("broll"):
        return (f'      <video id="bg{i}" class="clip bgvid" src="{ctx["srcs"]["broll"]}" {span} data-track-index="0" '
                f'muted playsinline></video>\n      <div id="scrim{i}" class="clip scrim" {span} data-track-index="1"></div>\n')
    if want == "clip":
        return ""
    return f'      <div id="dark{i}" class="clip bg-dark" {span} data-track-index="1"></div>\n'


def _text_block(cls: str, top: int, sizes) -> callable:
    def block(i, beat, t0, dur, ctx):
        text = _text_for(beat, ctx)
        html_ = _bg(i, beat, t0, dur, ctx)
        js = ""
        if text:
            size = _fit(text, sizes)
            html_ += (f'      <div id="c{i}" class="clip" data-start="{t0}" data-duration="{dur}" data-track-index="3"><div>'
                      f'<span id="t{i}" class="txt display {cls}" style="left:{L}px;top:{top}px;width:{W}px;font-size:{size}px">'
                      f'{_e(text)}</span></div></div>\n')
            js = _enter(f"#t{i}", t0, beat.get("transition", "cut"))
        return html_, js, ""
    return block


block_hook_text = _text_block("hook", 560, (96, 80, 64))
block_text_beat = _text_block("beat", 640, (76, 64, 54))
block_fact = _text_block("fact", 600, (72, 60, 50))
block_broll = _text_block("hook", 560, (96, 80, 64))


def block_app_overlay(i, beat, t0, dur, ctx):
    c, app = ctx["content"], ctx["app"]
    partial = Path(app["dir"]) / "blocks" / "app_overlay.html"
    if not partial.is_file():  # an app without its own overlay gets a fact-style card
        return block_fact(i, {**beat, "bg": "dark"}, t0, dur, ctx)
    src = re.sub(r"<!--.*?-->", "", partial.read_text(encoding="utf-8"), flags=re.S)
    headline = c.get("headline", "")
    values = {"persona": _e(c.get("persona")), "headline": _e(headline), "subtitle": _e(c.get("subtitle")),
              "headline_size": "96" if len(headline) <= 18 else "76", "t": str(t0)}
    src = re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), ""), src)
    css = "\n".join(re.findall(r"<style>(.*?)</style>", src, flags=re.S))
    js = "\n".join(re.findall(r"<script data-timeline>(.*?)</script>", src, flags=re.S))
    markup = re.sub(r"<style>.*?</style>|<script data-timeline>.*?</script>", "", src, flags=re.S).strip()
    html_ = (f'      <div id="c{i}" class="clip bg-dark" data-start="{t0}" data-duration="{dur}" data-track-index="4"><div>\n'
             f'{markup}\n      </div></div>\n'
             f'      <audio id="sfx{i}" src="assets/sfx/impact.mp3" data-start="{t0}" data-duration="2.1" '
             f'data-track-index="11" data-volume="0.8"></audio>\n')
    return html_, js, css


def block_app_clip(i, beat, t0, dur, ctx):
    src = ctx["srcs"].get("clip")
    span = f'data-start="{t0}" data-duration="{dur}"'
    html_ = ""
    if src:
        html_ += (f'      <video id="v{i}" class="clip bgvid" src="{src}" {span} data-track-index="2" muted playsinline></video>\n'
                  f'      <audio id="a{i}" src="{src}" {span} data-track-index="10" data-volume="1"></audio>\n')
    else:
        html_ += _bg(i, {"bg": "dark"}, t0, dur, ctx)
    if ctx["content"].get("floor"):
        html_ += f'      <div id="floor{i}" class="clip floor-fade" {span} data-track-index="5"></div>\n'
    js = ""
    text = _text_for(beat, ctx) if beat.get("text") else ""
    if text:
        html_ += (f'      <div id="c{i}" class="clip" {span} data-track-index="6"><div>'
                  f'<span id="t{i}" class="txt cap" style="left:{L}px;top:1250px;width:{W}px">{_e(text)}</span></div></div>\n')
        js = _enter(f"#t{i}", t0 + 0.2, "fade")
    return html_, js, ""


def block_end_card(i, beat, t0, dur, ctx):
    app, srcs = ctx["app"], ctx["srcs"]
    facts = pool(app, "fact")
    line = facts[0]["text"] if facts else ""
    icon = f'<img id="icon{i}" class="end-icon" src="{srcs["icon"]}" alt="" />' if srcs.get("icon") else ""
    badge = _e("▶  " + str(app.get("tagline", "Free on Google Play")).upper())
    html_ = (f'      <div id="c{i}" class="clip bg-dark" data-start="{t0}" data-duration="{dur}" data-track-index="7"><div>\n'
             f'        {icon}\n'
             f'        <span id="n{i}" class="txt display end-c" style="left:{L}px;top:720px;width:{W}px;font-size:84px">{_e(app.get("name"))}</span>\n'
             f'        <span id="f{i}" class="txt fact end-c" style="left:{L}px;top:880px;width:{W}px;font-size:40px;font-weight:700">{_e(line)}</span>\n'
             f'        <div id="b{i}" class="txt end-badge end-c" style="left:190px;top:1180px;width:700px">{badge}</div>\n'
             f'      </div></div>\n')
    js = (f'tl.fromTo("#icon{i}", {{ opacity: 0, scale: 1.6 }}, {{ opacity: 1, scale: 1, duration: 0.18, ease: "power4.in" }}, {t0});\n'
          f'      tl.fromTo("#c{i} .end-c", {{ opacity: 0, y: 40 }}, {{ opacity: 1, y: 0, duration: 0.3, stagger: 0.08, ease: "power3.out" }}, {t0} + 0.15);\n'
          f'      tl.to("#b{i}", {{ backgroundColor: "var(--accent2)", color: "#000000", duration: 0.2 }}, {t0} + 0.9);')
    return html_, js, ""


BLOCKS = {"hook_text": block_hook_text, "text_beat": block_text_beat, "broll": block_broll, "fact": block_fact,
          "app_overlay": block_app_overlay, "app_clip": block_app_clip, "end_card": block_end_card}


def _font_faces(dirs: list[Path]) -> str:
    out = []
    for d in dirs:
        for f in sorted(d.glob("*.ttf")) if d.is_dir() else []:
            stem = f.stem
            bold = stem.endswith("_bold")
            family = stem.removesuffix("_bold").replace("_", " ").title()
            out.append(f'      @font-face {{ font-family: "{family}"; font-weight: {700 if bold else 400}; '
                       f'src: url("assets/fonts/{f.name}"); }}')
    return "\n".join(out)


def build_html(recipe: dict, copy: Copy, content: dict, app: dict, srcs: dict[str, str | None]) -> str:
    ctx = {"copy": copy, "content": content, "app": app, "srcs": srcs}
    body, js, css = [], [], []
    tl = timeline(recipe, content)
    for i, (beat, t0, dur) in enumerate(tl):
        h, j, c = BLOCKS[beat["block"]](i, beat, t0, dur, ctx)
        body.append(h)
        js.append(j)
        css.append(c)
    total = round(sum(d for _b, _t, d in tl), 3)
    if srcs.get("music"):
        vol = 0.12 if any(b["block"] == "app_clip" for b, _t, _d in tl) else 0.35
        body.append(f'      <audio id="music" src="{srcs["music"]}" data-start="0" data-duration="{total}" '
                    f'data-track-index="9" data-volume="{vol}"></audio>\n')
    brand = app.get("brand", {})
    colors, fonts = brand.get("colors", {}), brand.get("fonts", {})
    tpl = (RENDERER_DIR / "base.html.tpl").read_text(encoding="utf-8")
    repl = {
        "FONTS": _font_faces([RENDERER_DIR / "fonts", Path(app["dir"]) / "brand" / "fonts"]),
        "BG": colors.get("bg", "#000000"), "ACCENT": colors.get("accent", "#FF2D2D"),
        "ACCENT2": colors.get("accent2", "#FFD400"), "TEXT": colors.get("text", "#FFFFFF"),
        "MUTED": colors.get("muted", "#B5B5B5"),
        "DISPLAY": _e(fonts.get("display", "Archivo Black")), "MONO": _e(fonts.get("mono", "JetBrains Mono")),
        "CSS": "\n".join(c for c in css if c), "BODY": "".join(body),
        "JS": "      " + "\n      ".join(j for j in js if j), "TOTAL": f"{total:g}",
    }
    return re.sub(r"@@(\w+)@@", lambda m: repl[m.group(1)], tpl)


def stage_assets(*, broll: Path | None, music: Path | None, clip: Path | None, icon: Path | None):
    """-> (srcs for build_html, files {dest name in assets/: local path} for render)."""
    srcs, files = {}, {}
    for name, p in (("broll", broll), ("music", music), ("clip", clip), ("icon", icon)):
        if p and Path(p).is_file():
            dest = f"{name}{Path(p).suffix}"
            srcs[name], files[dest] = f"assets/{dest}", Path(p)
        else:
            srcs[name] = None
    return srcs, files


_ENV_ALLOW = {"PATH", "PATHEXT", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR",
              "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PROGRAMFILES", "PROGRAMFILES(X86)",
              "PROGRAMDATA", "LANG", "LC_ALL", "TZ", "CI", "DISPLAY"}
_ENV_PREFIX = ("HYPERFRAMES_", "NODE_", "NPM_CONFIG_", "XDG_", "PUPPETEER_")


def _clean_env() -> dict[str, str]:
    """npx runs third-party code: hand it only what Node, npm and Chrome need (allowlist, never secrets)."""
    return {k: v for k, v in os.environ.items()
            if k.upper() in _ENV_ALLOW or k.upper().startswith(_ENV_PREFIX)}


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=_clean_env())


def render(html_: str, files: dict[str, Path], workdir: Path, out: Path, version: str) -> Path:
    workdir, out = Path(workdir), Path(out)
    if workdir.exists():
        shutil.rmtree(workdir)
    (workdir / "assets").mkdir(parents=True)
    for name in ("package.json", "hyperframes.json"):
        shutil.copy(RENDERER_DIR / name, workdir / name)
    shutil.copytree(RENDERER_DIR / "fonts", workdir / "assets" / "fonts")
    shutil.copytree(RENDERER_DIR / "sfx", workdir / "assets" / "sfx")
    (workdir / "meta.json").write_text(json.dumps({"id": "engine", "name": "engine"}), encoding="utf-8")
    (workdir / "index.html").write_text(html_, encoding="utf-8")
    for dest, src in files.items():
        shutil.copy(src, workdir / "assets" / dest)

    hf = [shutil.which("npx") or "npx", "--yes", f"hyperframes@{version}"]
    chk = _run(hf + ["check"], workdir)
    if chk.returncode != 0:
        raise RuntimeError("hyperframes check failed:\n" + (chk.stdout + chk.stderr)[-1500:])
    raw = workdir / "renders" / "raw.mp4"
    res = _run(hf + ["render", "-o", str(raw), "--quiet"], workdir)
    if res.returncode != 0 or not raw.is_file():  # known fix for drawElementImage failures with system Chrome
        res = _run(hf + ["render", "-o", str(raw), "--quiet", "--experimental-fast-capture=false"], workdir)
    if res.returncode != 0 or not raw.is_file():
        raise RuntimeError("hyperframes render failed:\n" + (res.stdout + res.stderr)[-1500:])
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-movflags", "+faststart", str(out)], workdir)
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg normalize failed:\n" + ff.stderr[-800:])
    return out
