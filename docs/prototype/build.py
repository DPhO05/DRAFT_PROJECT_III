#!/usr/bin/env python3
"""Build dist/app-draft.html (full document) and dist/artifact.html (artifact body) from src/."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
# Parallel builders: own output dir and only their own tab files.
DIST = Path(os.environ.get("PROTO_DIST", ROOT / "dist"))
ONLY = {s for s in os.environ.get("PROTO_TABS", "").split(",") if s}
BODY_MARK = "<!--__BODY__-->"
HEAD = (
    '<!doctype html>\n<html lang="vi">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def guard(text: str, closing: str, name: str) -> str:
    # A literal closing tag inside injected code would end the <script>/<style> early.
    if re.search(closing, text, re.I):
        sys.exit(f"build: {name} contains {closing!r}; escape it")
    return text


def main() -> None:
    shell = read(SRC / "shell.html")
    for mark in ("/*__MOCK__*/", "/*__TABS_CSS__*/", "/*__TABS_JS__*/", BODY_MARK):
        if shell.count(mark) != 1:
            sys.exit(f"build: shell.html must contain {mark} exactly once")
    mock_p = SRC / "mock.js"
    mock = guard(read(mock_p), r"</script", "mock.js") if mock_p.exists() else "window.MOCK = {};"
    tab_dir = SRC / "tabs"
    css_files = sorted(tab_dir.glob("*.css")) if tab_dir.is_dir() else []
    js_files = sorted(tab_dir.glob("*.js")) if tab_dir.is_dir() else []
    if ONLY:
        css_files = [p for p in css_files if p.stem in ONLY]
        js_files = [p for p in js_files if p.stem in ONLY]
    css = "\n".join(f"/* tabs/{p.name} */\n" + guard(read(p), r"</style", p.name) for p in css_files)
    # One <script> per tab file: a syntax error in one tab cannot take down the others.
    js = "\n</script>\n<script>\n".join(f"/* tabs/{p.name} */\n" + guard(read(p), r"</script", p.name) for p in js_files)
    parts = {"/*__MOCK__*/": mock, "/*__TABS_CSS__*/": css, "/*__TABS_JS__*/": js}
    out = re.sub(r"/\*__(?:MOCK|TABS_CSS|TABS_JS)__\*/", lambda m: parts[m.group(0)], shell)
    head, body = out.split(BODY_MARK)
    DIST.mkdir(parents=True, exist_ok=True)
    full = HEAD + head.strip() + "\n</head>\n<body>\n" + body.strip() + "\n</body>\n</html>\n"
    art = head.strip() + "\n" + body.strip() + "\n"
    assert art.lstrip().startswith("<title>"), "artifact must start with <title>"
    (DIST / "app-draft.html").write_text(full, encoding="utf-8")
    (DIST / "artifact.html").write_text(art, encoding="utf-8")
    kb = len(art.encode()) / 1024
    print(f"build: mock={'yes' if mock_p.exists() else 'no ({})'} css={len(css_files)} js={len(js_files)} "
          f"artifact={kb:.0f} KB -> {DIST / 'app-draft.html'}, {DIST / 'artifact.html'}")


if __name__ == "__main__":
    main()
