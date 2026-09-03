"""Fase 3b: cuánta luz artificial encuentra el paso nocturno en cada ciudad.

El aviso de «luces fuera» solo tiene sentido donde coinciden dos cosas: muchas aves pasando por encima y mucha
luz encendida debajo. Aquí se mide la segunda y se combinan las dos en un índice de exposición, al estilo de
Horton y col. (2019), que ordenaron las ciudades de Estados Unidos multiplicando la luz que emiten por la
densidad de aves que el radar veía sobre ellas.

**La capa de luz** es el Nuevo Atlas Mundial del Brillo Artificial del Cielo Nocturno (Falchi y col., 2016), que
da el componente artificial del brillo del cielo en el cenit, en milicandelas por metro cuadrado, con una malla
de unos 30 segundos de arco. Se resume con la media dentro de un disco de 10 km alrededor del centro urbano,
que es el orden de magnitud de la mancha iluminada de una ciudad media y una regla igual para todas.

Dos advertencias importantes:

- El atlas mide el brillo del cielo *visto desde el suelo*, que incluye la luz dispersada por la atmósfera y la
  que llega de poblaciones vecinas. Lo que de verdad interpela a un ave que vuela a 1.000 m es la radiancia que
  la ciudad emite hacia arriba, que es lo que mide el sensor nocturno de los satélites VIIRS. Para ordenar
  ciudades ambas medidas van casi de la mano, pero no son la misma cosa.
- Los datos son de 2015 y su licencia **prohíbe redistribuir los ficheros**: se pueden usar y se pueden publicar
  resultados derivados citando las dos referencias, pero el raster no se sube a ningún sitio. Para una versión
  pública conviene sustituirlo por la radiancia VIIRS, que es de dominio público y se actualiza cada año;
  descargarla solo pide registrarse gratis en el Earth Observation Group.

Citas obligatorias del atlas:
  Falchi F. y col. (2016). The new world atlas of artificial night sky brightness. Science Advances 2(6):e1600377.
  Falchi F. y col. (2016). Supplement to: ... GFZ Data Services. doi:10.5880/GFZ.1.4.2016.001
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ATLAS_URL = "https://datapub.gfz-potsdam.de/download/10.5880.GFZ.1.4.2016.001/World_Atlas_2015.zip"
ATLAS_TIF = "World_Atlas_2015.tif"
RADIO_KM = 10.0
# Brillo natural del cielo en el cenit, en milicandelas por metro cuadrado; sirve de referencia para leer las
# cifras: un valor de 0,17 en el atlas significa duplicar el brillo natural del cielo.
BRILLO_NATURAL = 0.174


def asegurar_atlas(dir_luces: Path, log=print) -> Path:
    """Devuelve la ruta del GeoTIFF, extrayéndolo del zip si hace falta. No descarga nada por su cuenta."""
    tif = dir_luces / ATLAS_TIF
    if tif.exists():
        return tif
    z = dir_luces / "World_Atlas_2015.zip"
    if not z.exists():
        raise FileNotFoundError(f"falta {z}; descárgalo de {ATLAS_URL}")
    log(f"extrayendo {ATLAS_TIF} (3 GB) de {z.name}")
    zipfile.ZipFile(z).extract(ATLAS_TIF, dir_luces)
    return tif


def muestrear(tif: Path, ciudades: list[tuple[str, str, float, float]], radio_km: float = RADIO_KM,
              log=print) -> pd.DataFrame:
    """Estadísticos de brillo artificial en un disco de `radio_km` alrededor de cada ciudad."""
    import rasterio
    from rasterio.warp import transform as warp_transform

    filas = []
    with rasterio.open(tif) as src:
        nodata = src.nodata
        for nombre, pais, lat, lon in ciudades:
            xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
            fila, col = src.index(xs[0], ys[0])
            # tamaño del píxel en las unidades del raster, para traducir el radio en kilómetros a píxeles
            px = abs(src.transform.a), abs(src.transform.e)
            grados = src.crs.is_geographic
            rx = radio_km / (111.32 * np.cos(np.deg2rad(lat))) / px[0] if grados else radio_km * 1000 / px[0]
            ry = radio_km / 110.57 / px[1] if grados else radio_km * 1000 / px[1]
            r = int(np.ceil(max(rx, ry)))
            v = src.read(1, window=((fila - r, fila + r + 1), (col - r, col + r + 1)), boundless=True,
                         fill_value=np.nan).astype("float64")
            # disco, no cuadrado: se pesa cada píxel por su distancia real al centro
            dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
            dentro = (dx / max(rx, 1e-9)) ** 2 + (dy / max(ry, 1e-9)) ** 2 <= 1
            if nodata is not None:
                v[v == nodata] = np.nan
            sel = v[dentro & np.isfinite(v)]
            if sel.size == 0:
                log(f"  {nombre}: sin píxeles válidos")
                continue
            filas.append({"ciudad": nombre, "pais": pais, "lat": lat, "lon": lon, "pixeles": int(sel.size),
                          "luz_media": float(sel.mean()), "luz_centro": float(np.nanmedian(v[r - 1:r + 2, r - 1:r + 2])),
                          "luz_max": float(sel.max()),
                          "veces_natural": float(sel.mean() / BRILLO_NATURAL)})
            log(f"  {nombre}: brillo artificial medio {filas[-1]['luz_media']:.2f} mcd/m² "
                f"({filas[-1]['veces_natural']:.0f} veces el cielo natural)")
    return pd.DataFrame(filas)


def indice_migracion(clima: pd.DataFrame) -> pd.DataFrame:
    """Intensidad típica del paso sobre cada ciudad, a partir de las predicciones del archivo 2021-hoy.

    Se resume con dos cifras por temporada: la densidad media prevista, que dice cuánta ave pasa por ahí en un
    año normal, y la media de las diez noches más intensas, que es cuando el aviso importa.
    """
    d = clima[clima["season"] != "fuera de temporada"].copy()
    d["vid"] = d["pred"].clip(lower=0) ** 3  # el modelo trabaja con la raíz cúbica del VID
    filas = []
    for (ciudad, temporada), g in d.groupby(["ciudad" if "ciudad" in d else "radar", "season"]):
        top = g.nlargest(10, "vid")["vid"].mean()
        filas.append({"ciudad": ciudad, "season": temporada, "noches": len(g),
                      "vid_medio": g["vid"].mean(), "vid_picos": top})
    return pd.DataFrame(filas)


def ranking(luz: pd.DataFrame, mig: pd.DataFrame) -> pd.DataFrame:
    """Índice de exposición: luz artificial × intensidad del paso, normalizado a 100 en la ciudad más expuesta.

    Se da por temporada, porque el paso de primavera y el de otoño no son iguales en el mismo sitio, y con las
    dos versiones de la intensidad (la media de la temporada y la de las noches punta).
    """
    d = mig.merge(luz, on="ciudad", how="inner")
    for base, etiqueta in (("vid_medio", "exposicion_media"), ("vid_picos", "exposicion_picos")):
        bruto = d["luz_media"] * d[base]
        d[etiqueta] = 100 * bruto / bruto.max()
    return d.sort_values(["season", "exposicion_picos"], ascending=[True, False]).reset_index(drop=True)
