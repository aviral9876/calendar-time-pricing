"""Render paper/weekend.md to a typeset PDF.

Pandoc plus XeLaTeX. XeLaTeX rather than pdfLaTeX because the draft is written
in real Unicode -- minus signs, times signs, Greek in running text -- and
transliterating that into LaTeX macros in the source would make the markdown
worse to read for the sake of the build.

The markdown is the single source of truth; nothing here edits content. The
preamble below only handles what markdown cannot express: page geometry, table
sizing, and keeping figures near the text that refers to them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "paper" / "weekend.md"
OUT = ROOT / "paper" / "weekend.pdf"

# Companion notes render through the same machinery. They are separate
# documents, not sections: the price-impact note restates the paper's results in
# premium and nothing in the paper depends on it, so it gets its own title block
# and its own PDF rather than an appendix.
DOCS = {
    "weekend": {
        "title": "The Price of Calendar Time in a Market That Never Closes",
        "subtitle": "Weekend variance and its option pricing, in a venue that "
                    "never shuts",
    },
    "decay": {
        "title": "The Half-Life of a Pricing Error",
        "subtitle": "Trading the crypto weekend, 2017-2026: seven constructions, "
                    "and why the fee schedule beat all of them",
    },
    "price_impact": {
        "title": "What the Weekend Clock Does to Option Prices",
        "subtitle": "A companion note: the weekend variance discount, "
                    "translated into premium",
    },
}

# Wide tables (the day-of-week rows run to eight columns) overflow the text
# block at body size, and pandoc gives no per-table sizing hook. Shrinking every
# longtable is the blunt fix and reads acceptably.
PREAMBLE = r"""
\usepackage{etoolbox}
\usepackage{booktabs}
\usepackage{float}
\AtBeginEnvironment{longtable}{\small}
\AtBeginEnvironment{tabular}{\small}

% Figures are placed exactly where the source puts them. With LaTeX's default
% float placement a figure introduced by "the identification is visible in the
% data:" migrated past the section break, orphaning the sentence that set it up.
\floatplacement{figure}{H}

\usepackage{caption}
\captionsetup{font=small, labelformat=empty, justification=justified,
              singlelinecheck=false, skip=6pt}

\usepackage{sectsty}
\allsectionsfont{\normalfont\sffamily\bfseries}

\setlength{\emergencystretch}{3em}
\clubpenalty=10000
\widowpenalty=10000
"""

# A note that reads as an editorial aside in markdown should not become a
# heading-sized block in print.
def meta_for(stem: str) -> dict[str, str]:
    d = DOCS.get(stem, {"title": stem.replace("_", " ").title(), "subtitle": ""})
    return {**d, "date": dt.date.today().strftime("%d %B %Y")}


def font_available(name: str) -> bool:
    """Does XeLaTeX have this font? fc-list is not on a stock Windows box."""
    win = Path("C:/Windows/Fonts")
    stems = {p.stem.lower().replace(" ", "") for p in win.glob("*.tt*")}
    return name.lower().replace(" ", "") in stems


def pick_fonts() -> dict[str, str]:
    """First available of each family, or fall back to LaTeX's own."""
    serif = ["Cambria", "Constantia", "Georgia", "Times New Roman"]
    sans = ["Calibri", "Segoe UI", "Arial"]
    mono = ["Consolas", "Courier New"]
    out = {}
    for key, cands in (("mainfont", serif), ("sansfont", sans),
                       ("monofont", mono)):
        for c in cands:
            if font_available(c):
                out[key] = c
                break
    return out


def preprocess(text: str) -> str:
    """Markdown tweaks that only make sense in print.

    The blockquote data-provenance note and the H1 are both handled by the title
    block instead, and section symbols confuse pandoc's smart-quote pass when
    they abut a digit.
    """
    # Drop the H1: the title block carries it.
    text = re.sub(r"\A# .*?\n", "", text, count=1)
    # Drop the draft line under it.
    text = re.sub(r"\A\*Draft\..*?\*\n", "", text, count=1, flags=re.S)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC),
                    help="markdown to render (default: the paper)")
    ap.add_argument("--out", default=None,
                    help="output PDF (default: the source with a .pdf suffix)")
    ap.add_argument("--keep-tex", action="store_true")
    a = ap.parse_args()
    src = Path(a.src)
    if not src.exists():
        print(f"no such source: {src}", file=sys.stderr)
        return 1

    if not shutil.which("pandoc"):
        print("pandoc not found on PATH", file=sys.stderr)
        return 1

    out = Path(a.out) if a.out else src.with_suffix(".pdf")
    build = ROOT / "paper" / "_build"
    build.mkdir(parents=True, exist_ok=True)

    md = build / f"{src.stem}_print.md"
    md.write_text(preprocess(src.read_text(encoding="utf-8")), encoding="utf-8")

    header = build / "preamble.tex"
    header.write_text(PREAMBLE, encoding="utf-8")

    cmd = [
        "pandoc", str(md),
        "-o", str(out),
        "--from", "markdown+pipe_tables+tex_math_dollars+raw_tex",
        "--pdf-engine", "xelatex",
        "--include-in-header", str(header),
        "--resource-path", str(ROOT),
        "--toc", "--toc-depth=2",
        "-V", "documentclass=article",
        "-V", "papersize=a4",
        "-V", "geometry:margin=2.4cm",
        "-V", "fontsize=11pt",
        "-V", "linkcolor=black", "-V", "urlcolor=black",
        "-V", "colorlinks=true", "-V", "toccolor=black",
    ]
    for k, v in meta_for(src.stem).items():
        cmd += ["-M", f"{k}={v}"]
    for k, v in pick_fonts().items():
        cmd += ["-V", f"{k}={v}"]
    if a.keep_tex:
        subprocess.run(cmd[:3] + [str(out.with_suffix(".tex"))] + cmd[3:],
                       check=False, cwd=ROOT)

    print("running pandoc ->", out)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip()[-4000:], file=sys.stderr)
        return r.returncode
    # Missing glyphs are warnings, not errors: XeLaTeX prints a box and carries
    # on, so an unwatched build can silently drop characters from the output.
    miss = sorted(set(re.findall(r"Missing character: There is no (\S+)",
                                 r.stderr)))
    if miss:
        print(f"WARNING: {len(miss)} glyphs missing from the chosen font: "
              f"{' '.join(miss[:20])}", file=sys.stderr)
    print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
