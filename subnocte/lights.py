"""Phase 3b: how much artificial light the nocturnal passage meets over each city.

A lights-out alert only makes sense where two things coincide: many birds passing overhead and many lights on
below. Here the second one is measured and both are combined into an exposure index, in the style of Horton et
al. (2019), who ranked the cities of the United States by multiplying the light they emit by the bird density
the radar saw above them.

**The light layer** is the New World Atlas of Artificial Night Sky Brightness (Falchi et al., 2016), which gives
the artificial component of the zenith sky brightness, in millicandelas per square metre, on a grid of about
30 arc seconds. It is summarised by the mean inside a 10 km disc around the city centre, which is the order of
magnitude of the lit patch of a medium-sized city and the same rule for every one of them.

Two important caveats:

- The atlas measures the brightness of the sky *seen from the ground*, which includes light scattered by the
  atmosphere and light arriving from neighbouring towns. What actually matters to a bird flying at 1,000 m is
  the radiance the city emits upwards, which is what the night sensor of the VIIRS satellites measures. For
  ranking cities the two measures go hand in hand, but they are not the same thing.
- The data are from 2015 and their licence **forbids redistributing the files**: they may be used and derived
  results may be published citing both references, but the raster is not uploaded anywhere. For a public
  version it is better to replace it with the VIIRS radiance, which is public domain and updated every year;
  downloading it only requires a free registration with the Earth Observation Group.

Mandatory citations for the atlas:
  Falchi F. et al. (2016). The new world atlas of artificial night sky brightness. Science Advances 2(6):e1600377.
  Falchi F. et al. (2016). Supplement to: ... GFZ Data Services. doi:10.5880/GFZ.1.4.2016.001
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ATLAS_URL = "https://datapub.gfz-potsdam.de/download/10.5880.GFZ.1.4.2016.001/World_Atlas_2015.zip"
ATLAS_TIF = "World_Atlas_2015.tif"
RADIUS_KM = 10.0
# Natural zenith sky brightness, in millicandelas per square metre; it gives a reference to read the figures:
# a value of 0.17 in the atlas means doubling the natural brightness of the sky.
NATURAL_BRIGHTNESS = 0.174


def ensure_atlas(lights_dir: Path, log=print) -> Path:
    """Return the path of the GeoTIFF, extracting it from the zip if needed. It downloads nothing on its own."""
    tif = lights_dir / ATLAS_TIF
    if tif.exists():
        return tif
    z = lights_dir / "World_Atlas_2015.zip"
    if not z.exists():
        raise FileNotFoundError(f"{z} is missing; download it from {ATLAS_URL}")
    log(f"extracting {ATLAS_TIF} (3 GB) from {z.name}")
    zipfile.ZipFile(z).extract(ATLAS_TIF, lights_dir)
    return tif


def sample(tif: Path, cities: list[tuple[str, str, float, float]], radius_km: float = RADIUS_KM,
           log=print) -> pd.DataFrame:
    """Artificial-brightness statistics inside a disc of `radius_km` around each city."""
    import rasterio
    from rasterio.warp import transform as warp_transform

    rows = []
    with rasterio.open(tif) as src:
        nodata = src.nodata
        for name, country, lat, lon in cities:
            xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
            row, col = src.index(xs[0], ys[0])
            # pixel size in the raster units, to translate the radius in kilometres into pixels
            px = abs(src.transform.a), abs(src.transform.e)
            geographic = src.crs.is_geographic
            rx = radius_km / (111.32 * np.cos(np.deg2rad(lat))) / px[0] if geographic else radius_km * 1000 / px[0]
            ry = radius_km / 110.57 / px[1] if geographic else radius_km * 1000 / px[1]
            r = int(np.ceil(max(rx, ry)))
            v = src.read(1, window=((row - r, row + r + 1), (col - r, col + r + 1)), boundless=True,
                         fill_value=np.nan).astype("float64")
            # a disc, not a square: every pixel is weighted by its real distance to the centre
            dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
            inside = (dx / max(rx, 1e-9)) ** 2 + (dy / max(ry, 1e-9)) ** 2 <= 1
            if nodata is not None:
                v[v == nodata] = np.nan
            sel = v[inside & np.isfinite(v)]
            if sel.size == 0:
                log(f"  {name}: no valid pixels")
                continue
            rows.append({"city": name, "country": country, "lat": lat, "lon": lon, "pixels": int(sel.size),
                         "light_mean": float(sel.mean()),
                         "light_centre": float(np.nanmedian(v[r - 1:r + 2, r - 1:r + 2])),
                         "light_max": float(sel.max()),
                         "times_natural": float(sel.mean() / NATURAL_BRIGHTNESS)})
            log(f"  {name}: mean artificial brightness {rows[-1]['light_mean']:.2f} mcd/m² "
                f"({rows[-1]['times_natural']:.0f} times the natural sky)")
    return pd.DataFrame(rows)


def migration_index(clim: pd.DataFrame) -> pd.DataFrame:
    """Typical intensity of the passage over each city, from the predictions of the 2021-today archive.

    It is summarised by two figures per season: the mean predicted density, which says how many birds pass by
    in a normal year, and the mean of the ten busiest nights, which is when the alert matters.
    """
    d = clim[clim["season"] != "off season"].copy()
    d["vid"] = d["pred"].clip(lower=0) ** 3  # the model works with the cube root of the VID
    rows = []
    for (city, season), g in d.groupby(["city" if "city" in d else "radar", "season"]):
        top = g.nlargest(10, "vid")["vid"].mean()
        rows.append({"city": city, "season": season, "nights": len(g),
                     "vid_mean": g["vid"].mean(), "vid_peaks": top})
    return pd.DataFrame(rows)


def ranking(light: pd.DataFrame, mig: pd.DataFrame) -> pd.DataFrame:
    """Exposure index: artificial light × passage intensity, normalised to 100 in the most exposed city.

    It is given per season, because the spring and the autumn passage are not the same in the same place, and
    with both versions of the intensity (the seasonal mean and that of the peak nights).
    """
    d = mig.merge(light, on="city", how="inner")
    for base, label in (("vid_mean", "exposure_mean"), ("vid_peaks", "exposure_peaks")):
        raw = d["light_mean"] * d[base]
        d[label] = 100 * raw / raw.max()
    return d.sort_values(["season", "exposure_peaks"], ascending=[True, False]).reset_index(drop=True)
