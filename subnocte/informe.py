"""Utilidades para que los informes HTML sean autocontenidos.

Los informes enlazan las figuras como ficheros vecinos (`<img src='fase2_series.png'>`), lo que funciona al
abrirlos desde `output/` pero deja el informe sin imágenes en cuanto se envía o se copia a otro sitio.
`incrustar_imagenes` sustituye cada enlace por la imagen codificada dentro del propio HTML.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path


def incrustar_imagenes(html: Path, log=print) -> Path:
    """Reescribe `html` sustituyendo los `src` de ficheros locales por la imagen incrustada."""
    texto = html.read_text(encoding="utf-8")
    base = html.parent
    hechas, faltan = 0, []

    def sustituir(m: re.Match) -> str:
        nonlocal hechas
        comilla, ref = m.group(1), m.group(2)
        if ref.startswith(("data:", "http://", "https://")):
            return m.group(0)
        f = base / ref
        if not f.exists():
            faltan.append(ref)
            return m.group(0)
        tipo = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        hechas += 1
        return f"src={comilla}data:{tipo};base64,{base64.b64encode(f.read_bytes()).decode()}{comilla}"

    texto = re.sub(r"src=(['\"])([^'\"]+)\1", sustituir, texto)
    html.write_text(texto, encoding="utf-8", newline="\n")
    log(f"  {html.name}: {hechas} imágenes incrustadas, {len(html.read_bytes()) / 1e6:.1f} MB"
        + (f"; sin encontrar: {', '.join(faltan)}" if faltan else ""))
    return html
