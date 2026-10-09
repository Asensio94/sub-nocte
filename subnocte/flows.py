"""Replay of a night: where the birds were, every 20 minutes, from the radar profiles.

BirdCast's live maps show the night as it happens, built on the US NEXRAD volumes. In Europe the open profiles
(Aloft) arrive about two days late, so this is the same picture after the fact: a replay of the night as the
radars saw it, the evening the files are out.

Per radar and instant the profile gives the bird density of each 200 m layer and the flight vector (u, v). The
night is cut into 20-minute frames and, for each frame:

- **Density** (VID, birds/km²) is spread over a grid with a Gaussian kernel in log space (`SIGMA_KM`). Far from
  every radar the map fades out (`FADE_KM`): what is not seen is not drawn, rather than invented.
- **Flight** is drawn as an arrow at each radar: the density-weighted mean of the layers' vectors, i.e. where the
  bulk of the birds over that radar was heading and how fast (ground speed).

Rain and clutter are filtered with the same rules as the nightly table (`nightly.clean`). Radars that do not
publish the flight vector (several French ones since 2023) show density only.

The kernel is a plain smoother, not a model. The next step is to use the weather model as the background and to
interpolate only the radars' departure from it (regression kriging), so that the areas without radar get the
model instead of a blank.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import aloft as A
from .nightly import LAYER_KM, NIGHT_ELEV, clean
from .solar import sun_elevation

COUNTRIES = ("es", "pt", "fr")
FRAME_MIN = 20
SIGMA_KM = 110         # width of the kernel that spreads each radar's density
FADE_KM = (150, 260)   # fully drawn up to the first distance from the nearest radar, gone beyond the second
EXTENT = (-10.0, 8.5, 35.5, 51.5)  # lon_min, lon_max, lat_min, lat_max: Iberia and France
GRID_DEG = 0.1
BORDERS = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"


# The radar nearest town or the city it serves, as a reader would place it: (Spanish, English).
RADAR_NAMES = {
    "esahr": ("Málaga", "Málaga"), "esatn": ("Gran Canaria", "Gran Canaria"), "esbnv": ("Tenerife", "Tenerife"),
    "esclg": ("Sevilla", "Seville"), "esgld": ("Barcelona", "Barcelona"), "esnjr": ("Almería", "Almería"),
    "espdg": ("Zaragoza", "Zaragoza"), "essft": ("Cáceres", "Cáceres"), "estjv": ("Madrid", "Madrid"),
    "frabb": ("Abbeville", "Abbeville"), "fraja": ("Ajaccio", "Ajaccio"), "frale": ("Aléria", "Aléria"),
    "frave": ("Avesnes", "Avesnes"), "frbla": ("Dijon", "Dijon"), "frbol": ("Bollène", "Bollène"),
    "frbor": ("Burdeos", "Bordeaux"), "frbou": ("Bourges", "Bourges"), "frcol": ("Tolón", "Toulon"),
    "frgre": ("Brive", "Brive"), "frlep": ("Le Puy", "Le Puy"), "frmcl": ("Albi", "Albi"), "frmom": ("Pau", "Pau"),
    "frmtc": ("Belfort", "Belfort"), "frnan": ("Nancy", "Nancy"), "frnim": ("Nimes", "Nîmes"),
    "frniz": ("Mâcon", "Mâcon"), "fropo": ("Perpiñán", "Perpignan"), "frpla": ("Brest", "Brest"),
    "frtou": ("Toulouse", "Toulouse"), "frtra": ("París", "Paris"), "frtre": ("Nantes", "Nantes"),
    "frtro": ("Troyes", "Troyes"), "ptfar": ("Faro", "Faro"), "ptflr": ("Flores (Azores)", "Flores (Azores)"),
    "ptlis": ("Lisboa", "Lisbon"), "ptprt": ("Oporto", "Porto"), "ptsmg": ("São Miguel (Azores)", "São Miguel (Azores)"),
    "pttrc": ("Terceira (Azores)", "Terceira (Azores)"),
}
DAYS = {"es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"], "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
MONTHS = {"es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
          "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]}
DENSITY_LABEL = {"es": "aves en vuelo por km²", "en": "birds in flight per km²"}
LANGS = ("es", "en")


def radar_name(code: str, lang: str = "en") -> str:
    names = RADAR_NAMES.get(code)
    return names[LANGS.index(lang)] if names else code


def _stamp(local: pd.Timestamp, lang: str) -> str:
    """Frame title in local time, without relying on the system locale."""
    when = f"{DAYS[lang][local.weekday()]} {local.day} {MONTHS[lang][local.month - 1]} {local.year} · {local:%H:%M}"
    return f"{when} ({'hora de Madrid' if lang == 'es' else 'Madrid time'})"


def radars(countries=COUNTRIES) -> list[str]:
    return [r for r in A.list_radars() if r[:2] in countries]


def night_profiles(radar: str, night: dt.date, cache_dir: Path) -> pd.DataFrame:
    """Profiles of one radar over one night (the night is labelled with the date of its sunset).

    The night crosses midnight UTC, so it needs the daily file of the night and the one of the next day.
    """
    frames = []
    for d in (night, night + dt.timedelta(days=1)):
        p = A.download(A.daily_key(radar, d), cache_dir)
        if p is not None:
            frames.append(A.read_vpts(p))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    lat, lon = float(df["radar_latitude"].dropna().iat[0]), float(df["radar_longitude"].dropna().iat[0])
    d = clean(df)
    d["dens0"] = d["dens_clean"].fillna(0.0)
    ok = np.isfinite(d["u"]) & np.isfinite(d["v"])
    d["wu"] = np.where(ok, d["dens0"] * d["u"], 0.0)
    d["wv"] = np.where(ok, d["dens0"] * d["v"], 0.0)
    d["wok"] = np.where(ok, d["dens0"], 0.0)
    d["wh"] = d["dens0"] * d["height"]
    g = d.groupby("datetime")
    p = pd.DataFrame({"vid": g["dens0"].sum() * LAYER_KM, "valid": g["dens_clean"].count(),
                      "wu": g["wu"].sum(), "wv": g["wv"].sum(), "wok": g["wok"].sum(),
                      "wh": g["wh"].sum(), "dsum": g["dens0"].sum()}).reset_index()
    p = p[p["valid"] > 0]
    p["u"] = np.where(p["wok"] > 0, p["wu"] / p["wok"], np.nan)
    p["v"] = np.where(p["wok"] > 0, p["wv"] / p["wok"], np.nan)
    p["alt"] = np.where(p["dsum"] > 0, p["wh"] / p["dsum"], np.nan)
    p["sun"] = sun_elevation(lat, lon, p["datetime"])
    label = (p["datetime"] - pd.Timedelta(hours=12)).dt.date
    p = p[(p["sun"] < NIGHT_ELEV) & (label == night)]
    return p[["datetime", "vid", "u", "v", "alt"]].assign(radar=radar, lat=lat, lon=lon)


def frames(profiles: pd.DataFrame) -> pd.DataFrame:
    """Radar × 20-minute frame: mean density and flight vector."""
    p = profiles.assign(frame=profiles["datetime"].dt.floor(f"{FRAME_MIN}min"))
    return (p.groupby(["frame", "radar"])
            .agg(vid=("vid", "mean"), u=("u", "mean"), v=("v", "mean"), alt=("alt", "mean"),
                 lat=("lat", "first"), lon=("lon", "first"))
            .reset_index())


def _km(lat0: float) -> tuple[float, float]:
    return 111.32 * np.cos(np.radians(lat0)), 110.57


def grid():
    lon = np.arange(EXTENT[0], EXTENT[1] + GRID_DEG / 2, GRID_DEG)
    lat = np.arange(EXTENT[2], EXTENT[3] + GRID_DEG / 2, GRID_DEG)
    return np.meshgrid(lon, lat)


def field(points: pd.DataFrame, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Density over the grid (birds/km²) and its opacity, from the radars of one frame."""
    kx, ky = _km(float(np.mean(EXTENT[2:])))
    dx = (lon[..., None] - points["lon"].to_numpy()) * kx
    dy = (lat[..., None] - points["lat"].to_numpy()) * ky
    d = np.hypot(dx, dy)
    w = np.exp(-0.5 * (d / SIGMA_KM) ** 2) + 1e-12
    z = (w * np.log1p(points["vid"].to_numpy())).sum(-1) / w.sum(-1)
    near = d.min(-1)
    alpha = np.clip((FADE_KM[1] - near) / (FADE_KM[1] - FADE_KM[0]), 0, 1)
    return np.expm1(z), alpha


def borders(cache_dir: Path) -> list[np.ndarray]:
    """Country outlines (Natural Earth, public domain) as lon/lat rings inside the map extent."""
    f = cache_dir / "ne_50m_admin_0_countries.geojson"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(requests.get(BORDERS, timeout=120).content)
    rings = []
    for feat in json.loads(f.read_text(encoding="utf-8"))["features"]:
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            r = np.asarray(poly[0])
            if ((r[:, 0] > EXTENT[0] - 5) & (r[:, 0] < EXTENT[1] + 5)
                    & (r[:, 1] > EXTENT[2] - 5) & (r[:, 1] < EXTENT[3] + 5)).any():
                rings.append(r)
    return rings


# ---------------------------------------------------------------- drawing

VMIN, VMAX = 0.5, 60.0   # birds/km², log colour scale


def _ax(ax, rings):
    for r in rings:
        ax.plot(r[:, 0], r[:, 1], color="#8a8f98", lw=0.5)
    ax.set_xlim(EXTENT[0], EXTENT[1]); ax.set_ylim(EXTENT[2], EXTENT[3])
    ax.set_aspect(1 / np.cos(np.radians(np.mean(EXTENT[2:]))))
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor("#0d1b2a")


def draw(fr: pd.DataFrame, rings, title: str, out: Path, lon=None, lat=None, lang: str = "en") -> Path:
    """One map: density field, radars, and flight arrows (ground speed, 1° of arrow = 7 m/s)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    if lon is None:
        lon, lat = grid()
    z, alpha = field(fr, lon, lat)
    cmap = plt.get_cmap("inferno")
    rgba = cmap(LogNorm(VMIN, VMAX, clip=True)(np.clip(z, VMIN, VMAX)))
    rgba[..., 3] = alpha
    fig, ax = plt.subplots(figsize=(7.2, 6.6), facecolor="#0d1b2a")
    _ax(ax, rings)
    ax.imshow(rgba, origin="lower", extent=(lon.min(), lon.max(), lat.min(), lat.max()), interpolation="bilinear",
              aspect=ax.get_aspect())
    for r in rings:
        ax.plot(r[:, 0], r[:, 1], color="#cfd4dc", lw=0.5, alpha=0.6)
    ax.scatter(fr["lon"], fr["lat"], s=9, c="#7fdbff", edgecolors="none", zorder=3)
    a = fr.dropna(subset=["u", "v"])
    a = a[a["vid"] > VMIN]
    ax.quiver(a["lon"], a["lat"], a["u"], a["v"], color="#e8f6ff", scale=7, scale_units="xy", angles="xy",
              width=0.005, headwidth=3.5, zorder=4)
    ax.set_xlim(EXTENT[0], EXTENT[1]); ax.set_ylim(EXTENT[2], EXTENT[3])
    ax.set_title(title, color="w", fontsize=11)
    sm = plt.cm.ScalarMappable(norm=LogNorm(VMIN, VMAX), cmap=cmap)
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(DENSITY_LABEL[lang], color="w"); cb.ax.tick_params(colors="w")
    fig.savefig(out, dpi=100, bbox_inches="tight", facecolor=fig.get_facecolor()); plt.close(fig)
    return out


def animate(fr: pd.DataFrame, rings, out: Path, work: Path, tz: str = "Europe/Madrid", lang: str = "en") -> Path:
    """Animated GIF of the night, one frame every FRAME_MIN minutes."""
    from PIL import Image

    lon, lat = grid()
    work.mkdir(parents=True, exist_ok=True)
    imgs = []
    for t, g in fr.groupby("frame"):
        if len(g) < 5:  # the edges of the night, with only a few radars already dark
            continue
        local = pd.Timestamp(t).tz_convert(tz)
        p = draw(g, rings, _stamp(local, lang), work / f"{local:%Y%m%d_%H%M}_{lang}.png", lon, lat, lang)
        imgs.append(Image.open(p).convert("P", palette=Image.ADAPTIVE))
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=350, loop=0, optimize=True)
    return out


def night_summary(fr: pd.DataFrame) -> pd.DataFrame:
    """Per radar over the whole night: mean density, mean flight vector, speed, heading and altitude."""
    s = fr.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"), vid=("vid", "mean"),
                                peak=("vid", "max"), u=("u", "mean"), v=("v", "mean"), alt=("alt", "mean"),
                                frames=("vid", "size")).reset_index()
    s["speed"] = np.hypot(s["u"], s["v"])
    s["heading"] = (np.degrees(np.arctan2(s["u"], s["v"])) + 360) % 360  # direction of flight, 0 = north
    return s


COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def overall_flight(summary: pd.DataFrame) -> tuple[str, float]:
    """Compass point and speed (m/s) of the night's flight over every radar, weighted by its density."""
    d = summary.dropna(subset=["u", "v"])
    w = d["vid"]
    u, v = (np.average(d["u"], weights=w), np.average(d["v"], weights=w)) if w.sum() > 0 else (0.0, 0.0)
    return COMPASS[int(((np.degrees(np.arctan2(u, v)) + 360) % 360 + 11.25) // 22.5) % 16], float(np.hypot(u, v))


def write_report(night: dt.date, fr: pd.DataFrame, summary: pd.DataFrame, rings, out: Path) -> None:
    from .phase3 import STYLE
    from .report import embed_images

    work = out.parent / "flows_frames"
    gif = animate(fr, rings, out.parent / "flows_night.gif", work)
    animate(fr, rings, out.parent / "flows_night_es.gif", work, lang="es")  # the Spanish page of the site
    whole = draw(summary.assign(frame=None), rings, f"Night of {night:%d %b %Y}: mean density and mean flight",
                 out.parent / "flows_mean.png")
    s = summary.sort_values("vid", ascending=False)
    with_dir = s.dropna(subset=["u", "v"])
    heading, speed = overall_flight(summary)
    kpi = {"radars with data": len(s), "with flight direction": len(with_dir),
           "mean density": f"{s['vid'].mean():.1f} birds/km²",
           "busiest radar": f"{radar_name(s['radar'].iat[0])} ({s['vid'].iat[0]:.0f} birds/km²)",
           "overall heading": f"{heading} at {speed:.1f} m/s"}
    rows = "".join(
        f"<tr><td>{radar_name(r.radar)} <small>{r.radar}</small></td><td>{r.vid:.1f}</td><td>{r.peak:.1f}</td>"
        f"<td>{'' if np.isnan(r.heading) else COMPASS[int((r.heading + 11.25) // 22.5) % 16]}</td>"
        f"<td>{'' if np.isnan(r.speed) else f'{r.speed:.1f}'}</td><td>{r.alt:.0f}</td></tr>" for r in s.itertuples())
    parts = [
        f"<!doctype html><meta charset='utf-8'><title>Night replay · {night:%d/%m/%Y}</title>", STYLE,
        f"<h1>Night replay · {night:%A %d %B %Y}</h1>",
        "<p>Where the migrating birds were over Iberia and France that night, every 20 minutes, as the weather radars "
        "saw it. It is the European counterpart of BirdCast's live maps, but after the fact: the open radar profiles "
        "(Aloft) are published about two days late, so the replay of a night is out on the third morning.</p>",
        "<p><b>How to read it.</b> The colour is the density of birds in flight (birds per km², all altitudes "
        "together), spread around each radar and faded out where no radar sees. The arrows are the mean flight of "
        "the birds over each radar: where they head and how fast over the ground. Radars that do not publish the "
        "flight vector (several French ones) show density only.</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in kpi.items()) + "</div>",
        f"<p><img src='{gif.name}'></p>", f"<p><img src='{whole.name}'></p>",
        "<h2>Per radar</h2><table><tr><th>Radar</th><th>Mean birds/km²</th><th>Peak birds/km²</th>"
        "<th>Heading</th><th>Speed (m/s)</th><th>Mean altitude (m a.s.l.)</th></tr>" + rows + "</table>",
        "<h2>Limitations</h2><ul>"
        "<li>The map between radars is a smoother, not a measurement: with radars 150-250 km apart, a front of "
        "migration narrower than that is blurred. The next version fills the gaps with the weather model.</li>"
        "<li>The profiles carry no quality control. Rain is mostly removed by vol2bird and by the same filter as the "
        "nightly table, but insects and residual clutter can remain, especially in the south.</li>"
        "<li>The lowest 200 m are not used (ground clutter) and radars on mountains do not see below their antenna.</li>"
        "</ul><p><small>Radar profiles: Aloft / ENRAM / OPERA (CC0). Borders: Natural Earth.</small></p>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    embed_images(out)
