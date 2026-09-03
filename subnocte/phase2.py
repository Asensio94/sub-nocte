"""Phase 2: report of the weather model (output/phase2.html)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .report import embed_images

NAME = {
    "tail_100m": "tailwind 100 m", "tail_10m": "tailwind 10 m", "tail0_100m": "tailwind at dusk 100 m",
    "tail0_10m": "tailwind at dusk 10 m", "cross_100m": "crosswind 100 m", "cross_10m": "crosswind 10 m",
    "ws_100m": "wind speed 100 m", "ws_10m": "wind speed 10 m", "t2m": "temperature 2 m", "rh2m": "relative humidity",
    "pmsl": "pressure at sea level", "precip": "accumulated precipitation", "precip_h": "share of hours with rain",
    "cloud": "cloud cover", "dp24": "pressure change 24 h", "dt24": "temperature change 24 h",
    "doy_sin": "day of the year (sin)", "doy_cos": "day of the year (cos)",
    "clim_p50": "local climatology P50", "clim_p90": "local climatology P90",
    "lat": "latitude", "lon": "longitude",
}
# approximate height of each pressure level, to name the features without jargon
LEVEL_HEIGHT = {"925hPa": "750 m", "850hPa": "1,500 m", "700hPa": "3,000 m"}
for _n, _h in LEVEL_HEIGHT.items():
    NAME[f"ws_{_n}"] = f"wind speed at {_h}"
    NAME[f"tail_{_n}"] = f"tailwind at {_h}"
    NAME[f"cross_{_n}"] = f"crosswind at {_h}"
    NAME[f"tail0_{_n}"] = f"tailwind at dusk, {_h}"
NAME.update({"t850": "temperature at 1,500 m", "dt850_24": "temperature change at 1,500 m in 24 h",
             "gh850": "height of the 1,500 m level (high or low pressure)"})

COUNTRY = {"es": "Spain", "pt": "Portugal", "fr": "France"}
COLOR = {"es": "#c0392b", "pt": "#27ae60", "fr": "#2980b9"}


def figures(ds: pd.DataFrame, met: pd.DataFrame, preds: pd.DataFrame, imp: pd.DataFrame, out_dir: Path) -> list[Path]:
    figs = []
    # 1) feature importance in both models
    p = out_dir / "phase2_importance.png"
    top = imp.head(15)[::-1]
    y = np.arange(len(top)); h = 0.4
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.barh(y + h / 2, top["alert"], h, color="#2c3e50", label="alert model")
    ax.barh(y - h / 2, top["intensity"], h, color="#95a5a6", label="intensity model")
    ax.set_yticks(y, [NAME.get(k, k) for k in top.index])
    ax.set_xlabel("% of the model gain"); ax.legend(fontsize=9)
    ax.set_title("What the models use to anticipate migration")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 2) radar-by-radar validation (each radar predicted by a model that never saw it)
    p = out_dir / "phase2_radars.png"
    r = met[met["split"].str.startswith("radar")].copy()
    r["radar"] = r["split"].str.split().str[1]
    r = r.sort_values("spearman", ascending=False)
    col = [COLOR.get(x[:2], "#888") for x in r["radar"]]
    fig, axes = plt.subplots(2, 1, figsize=(max(8, 0.32 * len(r)), 6.5), sharex=True)
    axes[0].bar(r["radar"], r["spearman"], color=col); axes[0].set_ylabel("Spearman obs-pred"); axes[0].set_ylim(0, 1)
    axes[0].axhline(r["spearman"].median(), color="k", ls="--", lw=0.8)
    axes[0].set_title("Validation leaving each radar out (red Spain, green Portugal, blue France)")
    w = 0.4; x = np.arange(len(r))
    axes[1].bar(x - w / 2, r["hit_rate"], w, color="#2c3e50", label="heavy-passage nights captured by the alerts")
    axes[1].bar(x + w / 2, r["false_alarm"], w, color="#e67e22", label="alerts issued that were not heavy passage")
    axes[1].axhline(0.1, color="#c0392b", ls="--", lw=0.9, label="what chance would capture (10 %)")
    axes[1].set_xticks(x, r["radar"], rotation=90); axes[1].set_ylim(0, 1); axes[1].legend(loc="upper right", fontsize=8)
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 3) out-of-sample observed-predicted scatter (by radar)
    p = out_dir / "phase2_scatter.png"
    q = preds[preds["split"] == "radar"]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    hb = ax.hexbin(q["pred"], q["y"], gridsize=45, bins="log", cmap="Greys", mincnt=1)
    lim = [0, max(q["y"].quantile(0.999), q["pred"].quantile(0.999))]
    ax.plot(lim, lim, color="#c0392b", lw=1); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("predicted (cube root of the VID)"); ax.set_ylabel("observed (cube root of the VID)")
    ax.set_title(f"Radars unseen in training (n={len(q):,})"); fig.colorbar(hb, label="nights")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 4) example series: the new Spanish radars and Porto, last spring with data
    p = out_dir / "phase2_series.png"
    ex = [r for r in ("estjv", "esgld", "essft", "ptprt") if r in set(q["radar"])]
    if ex:
        fig, axes = plt.subplots(len(ex), 1, figsize=(10, 2.4 * len(ex)), squeeze=False)
        for ax, r in zip(axes.flat, ex):
            s = q[q["radar"] == r].sort_values("night")
            yr = s["night"].dt.year.max()
            s = s[(s["night"].dt.year == yr) & (s["night"].dt.month.between(2, 5))]
            if s.empty:
                s = q[q["radar"] == r].sort_values("night"); s = s[s["night"].dt.year == yr]
            season = s["season"].mode().iat[0]
            # reindex to calendar days: nights without data stay a gap and the line breaks
            s = (s.set_index("night").reindex(pd.date_range(s["night"].min(), s["night"].max(), freq="D"))
                 .rename_axis("night").reset_index())
            ax.plot(s["night"], s["y"] ** 3, color="#333", lw=1, label="observed (radar)")
            ax.plot(s["night"], s["pred"].clip(lower=0) ** 3, color="#e67e22", lw=1.2,
                    label="predicted (weather only, radar unseen)")
            # the threshold is per radar and season: take the one of the season being drawn, not the first
            thr = ds.loc[(ds["radar"] == r) & (ds["season"] == season), "p90_season"].iloc[0]
            ax.axhline(thr, color="#c0392b", ls=":", lw=0.8, label="heavy passage: observed local P90")
            # nights on which the alert model would have warned
            cut = q[q["radar"] == r].groupby("season")["p_alert"].quantile(0.9)
            al = s[s["p_alert"] >= s["season"].map(cut).fillna(np.inf)]
            for x in al["night"]:
                ax.axvline(x, color="#f39c12", alpha=0.35, lw=3, zorder=0)
            ax.plot([], [], color="#f39c12", alpha=0.5, lw=3, label="night with an alert issued")
            ax.set_title(f"{r} · {yr}", fontsize=10); ax.set_ylabel("VID (birds/km²)")
        axes.flat[0].legend(fontsize=8, ncol=4)
        fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def write_report(ds: pd.DataFrame, met: pd.DataFrame, imp: pd.DataFrame, cols: list[str], figs: list[Path], out: Path,
                 ref: pd.DataFrame | None = None) -> None:
    with_levels = any("hPa" in c for c in cols)
    source = ("wind and temperature on the 925, 850 and 700 hectopascal pressure levels, that is at roughly 750, "
              "1,500 and 3,000 m above sea level, which is where the birds fly, plus the 10 and 100 m wind, "
              "temperature, humidity, pressure, precipitation and cloud cover at the surface; archive of "
              "operational analyses and forecasts from Open-Meteo, available from 2021") if with_levels else (
              "wind at 10 and 100 m, temperature, humidity, pressure, precipitation and cloud cover; ERA5 "
              "reanalysis via Open-Meteo, available from 1940")
    an = met[met["split"].str.startswith("year")]
    ra = met[met["split"].str.startswith("radar")].copy()
    ra["country"] = ra["split"].str.split().str[1].str[:2].map(COUNTRY)
    es = ra[ra["country"] == "Spain"]
    summary = {
        "radar-nights": f"{len(ds):,}", "radars": ds["radar"].nunique(),
        "years": f"{ds['year'].min()}-{ds['year'].max()}", "features": len(cols),
        "Median Spearman (year out)": f"{an['spearman'].median():.2f}",
        "Median R² (year out) / climatology only": f"{an['r2'].median():.2f} / {an['r2_clim'].median():.2f}",
        "Median Spearman (radar out)": f"{ra['spearman'].median():.2f}",
        "Median Spearman Spanish radars (out)": f"{es['spearman'].median():.2f}" if len(es) else "—",
        "Median area under the curve (radar out)": f"{ra['auc'].median():.2f}",
        "Heavy-passage nights captured (radar out)": f"{ra['hit_rate'].mean():.0%}",
        "Wrong alerts (radar out)": f"{ra['false_alarm'].mean():.0%}",
    }
    fmt = met.copy()
    for c in ("spearman", "r2", "r2_clim", "auc", "auc_intensity"):
        fmt[c] = fmt[c].map("{:.2f}".format)
    for c in ("hit_rate", "false_alarm"):
        fmt[c] = fmt[c].map("{:.0%}".format)
    fmt = fmt.rename(columns={"split": "validation", "r2": "R²", "r2_clim": "R² climatology",
                              "auc": "area under the curve", "auc_intensity": "area under the curve (intensity)",
                              "hit_rate": "heavy passage captured", "false_alarm": "wrong alerts",
                              "alerts_obs": "heavy-passage nights", "alerts_pred": "alerts issued"})
    from .model import MIN_NIGHTS_RADAR as min_nights
    n_folds = len(ra)
    n_small = int((ds.groupby("radar").size() < 20).sum())
    imp_t = imp.reset_index().rename(columns={"index": "feature", "intensity": "intensity %", "alert": "alert %"})
    imp_t["feature"] = imp_t["feature"].map(lambda k: NAME.get(k, k))
    for c in ("intensity %", "alert %"):
        imp_t[c] = imp_t[c].map("{:.1f}".format)
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Phase 2 · weather model</title>",
        "<style>body{font:15px/1.5 system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
        "table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:3px 8px;text-align:right}"
        "th{background:#f4f4f4}td:first-child,th:first-child{text-align:left}img{max-width:100%}"
        ".k{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}"
        ".k div{background:#f7f7f7;padding:8px 12px;border-radius:6px}.k b{display:block;font-size:20px}</style>",
        "<h1>Phase 2 · does the weather predict nocturnal migration?</h1>",
        "<p>A boosted-tree model (LightGBM) estimating the <b>nightly bird density</b> (VID, birds/km²) of each radar "
        f"from the weather of the night ({source}), the day of the year, the radar's local climatology and its "
        "position. The wind is split into a tailwind and a crosswind component relative to the season's migratory "
        "heading, and the 24 h changes of pressure and temperature, which mark frontal passages, are added. The "
        "target is cube-root transformed. Only nights with coverage &ge; 60 % inside the migration windows "
        "(15 Feb-31 May, 15 Aug-30 Nov).</p>",
        "<p><b>Two honest validations:</b> (1) leave a whole year out and predict it with the rest (does it work in a "
        "new year?); (2) leave a whole radar out (does it work in a place it was not trained on? — that is the case of "
        "a city with no radar nearby, and also that of the new Spanish radars, which only have one season).</p>",
        "<p><b>Every fold only sees what would have been available.</b> The radar's local climatology is computed from "
        "its own observations, so handing it to the model as is would leak the answer. Leaving a year out, it is "
        "recomputed with the remaining years (moving window of ±7 days); leaving a radar out it <b>disappears from the "
        "features</b>, because in a city without a radar it does not exist. That is why the per-radar figures are lower "
        "than the annual ones: the model is left with the weather, the calendar and the geographic position alone.</p>",
        "<p><b>How an alert is decided.</b> A <i>heavy-passage night</i> is one above the local historical 90th "
        "percentile of its season, that is one night in ten. A mean model shrinks the predictions towards the centre "
        "and almost never crosses that absolute value, so the alert is decided by a <b>second model</b>, trained to "
        "classify that event directly, and the threshold is calibrated on the distribution of its predictions: the "
        "alert fires in the top decile of the forecast nights of that radar and season. In operation that distribution "
        "comes from running the model over ten years of reanalysis at the point of interest, with no need for a radar "
        "in the city. Since as many alerts are issued as there are heavy-passage nights, the captured percentage is "
        "directly comparable with the 10 % that chance would give. The area under the curve summarises the ability to "
        "separate those nights without depending on any threshold (0.5 = chance).</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in summary.items()) + "</div>",
        "<h2>What the model uses</h2><p>Relative gain of each feature training on everything, that is in the scenario "
        f"with the local climatology available.</p><img src='{figs[0].name}'>",
        f"<h2>Radar-by-radar validation</h2><img src='{figs[1].name}'>",
        f"<h2>Observed against predicted</h2><img src='{figs[2].name}'>",
    ]
    if len(figs) > 3:
        parts.append(f"<h2>Examples: the new Spanish radars and Porto</h2><img src='{figs[3].name}'>")
    if ref is not None and not ref.empty:
        rows, idx = [], []
        for axis, label in (("year", "year out"), ("radar", "radar out")):
            a = met[met["split"].str.startswith(axis)]
            b = ref[ref["split"].str.startswith(axis)]
            if a.empty or b.empty:
                continue
            for key, name, f in (("spearman", "Median Spearman", "{:.2f}".format),
                                 ("auc", "Median area under the curve", "{:.2f}".format),
                                 ("hit_rate", "Heavy passage captured", "{:.0%}".format)):
                v = (lambda d: d[key].mean() if key == "hit_rate" else d[key].median())
                rows.append((f(v(a)), f(v(b))))
                idx.append(f"{name} ({label})")
        comp = pd.DataFrame(rows, columns=["with wind at flight altitude", "surface weather only"], index=idx)
        parts += [
            "<h2>How much does the wind at flight altitude add?</h2>",
            "<p>The same nights and the same folds, changing only the feature set: with the wind at 925, 850 and 700 "
            "hectopascals (roughly 750, 1,500 and 3,000 m above sea level) against only the 10 and 100 m wind. The row "
            "that matters for the service is «radar out»: a city where there is no radar to train with.</p>",
            comp.to_html(),
        ]
    AZORES = {"ptflr", "ptsmg", "pttrc"}
    ra2 = ra.copy(); ra2["radar"] = ra2["split"].str.split().str[1]
    new_es = ra2[ra2["radar"].isin(["estjv", "esgld", "essft", "esahr"])]
    islands = ra2[ra2["radar"].isin(AZORES)]
    cont = ra2[~ra2["radar"].isin(AZORES)]

    def rng(d, c, pct=False):
        f = "{:.0%}".format if pct else "{:.2f}".format
        return f(d[c].min()) + "-" + f(d[c].max())

    parts += [
        "<h2>What this means for the pilot</h2><ul>",
        f"<li><b>The four renewed Spanish radars are the hard case.</b> Madrid, Barcelona, Cáceres and Málaga give an "
        f"area under the curve of {rng(new_es, 'auc')} and capture {rng(new_es, 'hit_rate', True)} of the "
        "heavy-passage nights. They beat chance (10 %) by little more than a factor of two, and with a single season "
        "of data every alert rests on very few nights. That is not yet enough for a reliable alert in those cities.</li>"
        f"<li><b>The best results are from the Azores</b> (area under the curve {rng(islands, 'auc')}, "
        f"{rng(islands, 'hit_rate', True)} captured): oceanic islands where the passage is very episodic and depends "
        "almost only on the weather. They must be read with caution, because they are few nights and do not represent "
        "the continent.</li>"
        f"<li>On the continent the median area under the curve is {cont['auc'].median():.2f} and the best radars reach "
        f"{cont['auc'].max():.2f} with {cont.loc[cont['auc'].idxmax(), 'hit_rate']:.0%} captured. There the service "
        "does work: they are almost all French, plus Porto.</li>"
        "<li>The operational conclusion is that the alert works where the radar sees well and there are several "
        "seasons of archive. In Spain it is better to wait for the 2027 season and, above all, to resolve the profile "
        "truncated at six layers and the insect contamination before publishing alerts.</li></ul>",
        "<h2>Tables</h2><h3>Validation</h3>", fmt.to_html(index=False),
        "<h3>Feature importance</h3>", imp_t.to_html(index=False),
        "<h2>Limitations</h2><ul>"
        + ("<li>The wind in the flight layer comes from the archive of operational forecasts, which only goes back to "
           "2021. That shortens the usable archive and leaves out the first years of the French series, which are the "
           "long ones. The comparison with the surface model measures what is gained in exchange.</li>" if with_levels else
           "<li>The wind in the flight layer (925, 850 and 700 hectopascals) is not in this version: the ERA5 "
           "reanalysis of Open-Meteo only serves surface and 100 m. With the pressure levels the model should "
           "improve.</li>")
        + "<li>Without the speed from vol2bird, insects cannot be separated from birds by airspeed; in autumn and in "
        "the south part of the VID is insect. The local climatology absorbs part of the bias, not all of it.</li>"
        f"<li>Only the {n_folds} radars with at least {min_nights} nights get their own validation; the rest "
        f"contribute to the training but are not validated separately ({n_small} radars do not reach 20 nights).</li>"
        "<li>The «R² climatology» column of the per-radar folds compares against the observed climatology of that same "
        "radar, which the model could not use: it is a deliberately generous benchmark.</li>"
        "<li>Years with few radars give a very negative R² (the model gets the ranking of the nights right but not the "
        "absolute level of a radar it has barely seen). Spearman and the area under the curve are the metrics to trust; "
        "the R² only makes sense next to the climatology one, in the same column.</li>"
        "<li>The prediction uses the analysis of the night itself, not a forecast several days ahead: it is the upper "
        "bound of what will be achieved in operation.</li></ul>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    embed_images(out)  # self-contained: the report can be emailed or opened from any folder
