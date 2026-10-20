"""The bar every page carries: Tonight · Routes · Wind farms · Method · ES/EN.

The public pages call `nav()` while they are built. The technical reports are written by other commands, in
English and with their own look, so `stamp()` adds the bar to them afterwards; it is idempotent (the bar sits
between two markers and is replaced, not added again) so `web` can run it every night.
"""

from __future__ import annotations

import re
from pathlib import Path

from .logo import LOGO_SVG

# page key -> path from the repository root, per language
PAGES = {
    "home": {"es": "", "en": "en/"},
    "routes": {"es": "rutas.html", "en": "en/routes.html"},
    "farms": {"es": "parques.html", "en": "en/windfarms.html"},
    "method": {"es": "metodo.html", "en": "en/method.html"},
}
LABEL = {
    "es": {"home": "Esta noche", "routes": "Rutas", "farms": "Parques eólicos", "method": "Método",
           "aria": "Secciones", "switch": "English"},
    "en": {"home": "Tonight", "routes": "Routes", "farms": "Wind farms", "method": "Method",
           "aria": "Sections", "switch": "Español"},
}
OTHER = {"es": "en", "en": "es"}
START, END = "<!--sn-nav-->", "<!--/sn-nav-->"

# Self-contained: the reports do not load common.css, so the bar brings its own colours and falls back to
# system fonts there. Dark like the routes map, so it reads the same on every page and in both themes.
CSS = """
.sn-nav{position:sticky;top:0;z-index:20;background:#0b1424;color:#e8ecf4;border-bottom:1px solid #2a3a56;
  font:600 15px/1 "Barlow Condensed","Arial Narrow",sans-serif;text-transform:uppercase;letter-spacing:.06em}
.sn-nav .sn-in{max-width:1000px;margin:0 auto;padding:0 16px;display:flex;align-items:center;gap:6px 14px}
.sn-nav a{color:inherit;text-decoration:none}
.sn-nav .sn-brand{display:flex;align-items:center;gap:6px;padding:10px 0;white-space:nowrap;font-weight:700}
.sn-nav .sn-brand span{color:#ffb36b}
.sn-nav .logo{width:20px;height:20px;margin:0;color:#e8ecf4;vertical-align:-4px}
.sn-nav .logo .logo-breast{fill:#ff8a3d}
.sn-nav ul{display:flex;gap:2px;margin:0;padding:0;list-style:none;overflow-x:auto;scrollbar-width:none;flex:1}
.sn-nav li a{display:block;padding:13px 10px 11px;white-space:nowrap;border-bottom:3px solid transparent;color:#cfd6e4}
.sn-nav li a:hover{color:#fff}
.sn-nav li a[aria-current=page]{color:#fff;border-bottom-color:#ffb36b}
.sn-nav .sn-lang{padding:6px 9px 5px;border:1.5px solid #3a4a66;font-size:13px;white-space:nowrap;color:#cfd6e4}
.sn-nav .sn-lang:hover{border-color:#ffb36b;color:#fff}
.sn-nav a:focus-visible{outline:2px solid #ffb36b;outline-offset:-2px}
@media (max-width:640px){.sn-nav .sn-in{flex-wrap:wrap;gap:0 10px}.sn-nav .sn-brand{order:1}
  .sn-nav .sn-lang{order:2;margin-left:auto}.sn-nav ul{order:3;flex-basis:100%;margin:0 -10px}}
"""


def href(key: str, lang: str, depth: int) -> str:
    """Relative link to a page from a file `depth` folders below the root."""
    return "../" * depth + PAGES[key][lang] or "./"


def nav(lang: str, current: str | None, depth: int, switch: str | None = None) -> str:
    """The bar. `current` is the page key highlighted; `switch` overrides where the language link goes."""
    t, other = LABEL[lang], OTHER[lang]
    items = "".join(
        f"<li><a href='{href(k, lang, depth)}'{' aria-current=page' if k == current else ''}>{t[k]}</a></li>"
        for k in PAGES)
    to = switch if switch is not None else href(current or "home", other, depth)
    return (f"<nav class='sn-nav' aria-label='{t['aria']}' data-lang='{lang}'><div class='sn-in'>"
            f"<a class='sn-brand' href='{href('home', lang, depth)}'>{LOGO_SVG}Sub <span>Nocte</span></a>"
            f"<ul>{items}</ul>"
            f"<a class='sn-lang' href='{to}' hreflang='{other}' lang='{other}'>{t['switch']}</a></div></nav>")


def page_bar(lang: str, current: str, depth: int) -> str:
    """What a public page puts first in its body: the bar, and a note of the reader's language so the
    technical reports (English only) show the bar in the language the reader came from."""
    return nav(lang, current, depth) + f"<script>try{{localStorage.setItem('sn-lang','{lang}')}}catch(e){{}}</script>"


def stamp(path: Path, root: Path, default: str = "es") -> bool:
    """Put the bar on a report written by another command. Both languages go in, one is shown."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    text = re.sub(re.escape(START) + ".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)
    depth = len(path.relative_to(root).parts) - 1
    bars = "".join(nav(lang, "method", depth, switch=href("method", OTHER[lang], depth)) for lang in ("es", "en"))
    # the reader's language from the public pages, else the report's own default
    script = ("<script>(function(){var l='" + default + "';try{l=localStorage.getItem('sn-lang')||l}catch(e){}"
              "document.querySelectorAll('.sn-nav').forEach(function(n){"
              "if(n.dataset.lang!==l)n.remove();else n.style.display='block'})})()</script>")
    hide = f".sn-nav[data-lang={OTHER[default]}]{{display:none}}"   # without script, only the default one
    # the reports in output/ are drawn for a white page but never say so; a browser in dark mode may then paint
    # dark behind dark text. The documents in docs/ carry their own themes and are left alone.
    light = "html{background:#fff;color-scheme:light}" if path.relative_to(root).parts[0] == "output" else ""
    block = f"{START}<style>{CSS}{hide}{light}body{{margin-top:0}}</style>{bars}{script}{END}\n"
    m = (re.search(r"<body[^>]*>\s*", text, re.I) or re.search(r"</style>\s*", text[:20000])
         or re.search(r"<meta charset=[^>]*>\s*", text[:2000], re.I))
    at = m.end() if m else 0
    path.write_text(text[:at] + block + text[at:], encoding="utf-8", newline="\n")
    return True
