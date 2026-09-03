"""Helpers that make the HTML reports self-contained.

Reports link their figures as sibling files (`<img src='phase2_series.png'>`), which works when opening them
from `output/` but leaves the report with no images as soon as it is emailed or copied elsewhere.
`embed_images` replaces every link with the image encoded inside the HTML itself.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path


def embed_images(html: Path, log=print) -> Path:
    """Rewrite `html`, replacing the `src` of local files with the embedded image."""
    text = html.read_text(encoding="utf-8")
    base = html.parent
    done, missing = 0, []

    def replace(m: re.Match) -> str:
        nonlocal done
        quote, ref = m.group(1), m.group(2)
        if ref.startswith(("data:", "http://", "https://")):
            return m.group(0)
        f = base / ref
        if not f.exists():
            missing.append(ref)
            return m.group(0)
        kind = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        done += 1
        return f"src={quote}data:{kind};base64,{base64.b64encode(f.read_bytes()).decode()}{quote}"

    text = re.sub(r"src=(['\"])([^'\"]+)\1", replace, text)
    html.write_text(text, encoding="utf-8", newline="\n")
    log(f"  {html.name}: {done} embedded images, {len(html.read_bytes()) / 1e6:.1f} MB"
        + (f"; not found: {', '.join(missing)}" if missing else ""))
    return html
