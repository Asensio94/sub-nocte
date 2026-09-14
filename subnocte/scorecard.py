"""Verification of the forecasts that were actually published.

The daily routine commits the forecast in force, so the history of the repository is an archive of
forecasts stamped with the moment they were issued: `git show <commit>:data/phase3_forecast.csv` gives
back what was predicted *before* each night happened. That is what makes an honest check possible.
Running the model again today, over weather that is already known, would flatter it.

Against that archive goes what the radars measured, downloaded again from the public archive. Three
things are measured, in order of how much they can be trusted:

1. **Order.** Rank correlation between the prediction and the density measured at the nearest radar,
   within each place. It does not depend on how long that radar's record is, so it survives everywhere.
2. **Level.** Whether the nights called high or very high really landed in the top quarter of that
   radar's own record. Only where the record is long enough to say so.
3. **Size.** The predicted birds/km² against the measured ones, which is where the model is known to
   fall short.

Nothing here writes into data/nightly: those tables are the archive the thresholds lean on, and they are
read, never rebuilt. Both the forecast archive and the measured nights accumulate in their own files, so
a shallow clone or a re-downloaded window never loses what was already verified.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wilcoxon

from . import aloft
from .nightly import build_nightly

FORECAST_REL = "data/phase3_forecast.csv"
ARCHIVE_COLS = ["city", "night", "season", "country", "doy", "pred", "p_alert", "level", "percentile"]
MIN_COVERAGE = 0.6     # same coverage filter used everywhere else in the project
MIN_REF = 100          # nights a radar needs in its own record before its percentiles mean anything
WINDOW = 21            # half-width, in days, of the window the observed percentile is taken over
LEAD_OP = (-1, 1)      # the operational alert: last night, tonight and tomorrow
LAG_DAYS = 3           # the public archive publishes each day's file with about two days of delay


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True, encoding="utf-8").stdout


def forecast_archive(root: Path, log=print) -> pd.DataFrame:
    """Every forecast the daily routine has committed, with the date it was issued."""
    out = root / "data" / "forecast_archive.parquet"
    old = pd.read_parquet(out) if out.exists() else None
    seen = set(old["sha"].unique()) if old is not None else set()
    frames = [old] if old is not None else []
    fresh = 0
    for line in _git(root, "log", "--format=%H%x09%cI", "--", FORECAST_REL).splitlines():
        sha, when = line.split("\t", 1)
        if sha in seen:
            continue
        try:
            raw = _git(root, "show", f"{sha}:{FORECAST_REL}")
        except subprocess.CalledProcessError:      # the file did not exist yet at that commit
            continue
        d = pd.read_csv(io.StringIO(raw))
        if "city" not in d.columns:                # forecasts issued before the rename to English
            continue
        d = d[[c for c in ARCHIVE_COLS if c in d.columns]].copy()
        d["issued"] = pd.Timestamp(when[:10])
        d["sha"] = sha
        frames.append(d)
        fresh += 1
    fc = pd.concat(frames, ignore_index=True)
    fc["night"] = pd.to_datetime(fc["night"])
    # one forecast per city and night: the most recent issue wins for the archive's own bookkeeping,
    # but every issue is kept so the lead time can be measured
    fc = fc.drop_duplicates(["issued", "city", "night"], keep="last")
    fc["lead"] = (fc["night"] - fc["issued"]).dt.days
    fc.to_parquet(out, index=False)
    log(f"forecast archive: {len(fc):,} rows, {fc['issued'].nunique()} issues "
        f"({fresh} new), nights {fc['night'].min():%Y-%m-%d} to {fc['night'].max():%Y-%m-%d}")
    return fc


def observations(radars: list[str], start: dt.date, end: dt.date, root: Path, log=print) -> pd.DataFrame:
    """Radar x night densities for the window, built in memory from the public profiles.

    Accumulates in data/verification_nights.parquet, so each run only downloads the days it lacks.
    """
    out = root / "data" / "verification_nights.parquet"
    cache = root / "data" / "cache"
    old = pd.read_parquet(out) if out.exists() else None
    keep = ["radar", "night", "vid_night", "mtr_night", "coverage"]
    frames = [old] if old is not None else []
    for r in radars:
        first = start
        if old is not None and (old["radar"] == r).any():
            last = old.loc[old["radar"] == r, "night"].max().date()
            first = max(start, last)               # the last saved night may have been cut short
        if first > end:
            continue
        try:
            df = aloft.fetch_radar(r, first, end, cache, log=lambda m: None)
        except Exception as e:                     # a radar missing from the bucket must not stop the rest
            log(f"  {r}: {type(e).__name__} {e}")
            continue
        if df.empty:
            continue
        _, n = build_nightly(df, r)
        frames.append(n.assign(radar=r)[keep])
    if not frames:
        return pd.DataFrame(columns=keep)
    obs = pd.concat(frames, ignore_index=True)
    obs["night"] = pd.to_datetime(obs["night"])
    obs = obs.sort_values("coverage").drop_duplicates(["radar", "night"], keep="last")
    obs.to_parquet(out, index=False)
    log(f"observations: {len(obs):,} radar-nights from {obs['radar'].nunique()} radars")
    return obs


def _season(night: pd.Series) -> pd.Series:
    m = night.dt.month
    return np.where(m.isin([2, 3, 4, 5, 6]), "spring", np.where(m.isin([8, 9, 10, 11]), "autumn", "off season"))


def reference(nightly_dir: Path) -> pd.DataFrame:
    """Each radar's own record: the nights the observed percentile is measured against."""
    frames = []
    for f in sorted(nightly_dir.glob("*.parquet")):
        if "_profiles" in f.name:
            continue
        d = pd.read_parquet(f, columns=["radar", "night", "vid_night", "coverage"])
        frames.append(d[d["coverage"] >= MIN_COVERAGE])
    ref = pd.concat(frames, ignore_index=True)
    ref["night"] = pd.to_datetime(ref["night"])
    ref["doy"] = ref["night"].dt.dayofyear
    ref["season"] = _season(ref["night"])
    return ref[ref["season"] != "off season"]


def add_percentile(obs: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Where each measured night sits in its own radar's record, for the season and for the date.

    The seasonal figure is the one the published level claims to match; the one taken over the three
    weeks either side is the fairer question, «was this night busy for the time of year?».
    """
    o = obs[obs["coverage"] >= MIN_COVERAGE].copy()
    o["doy"] = o["night"].dt.dayofyear
    o["season"] = _season(o["night"])
    o = o[o["season"] != "off season"]
    pct, pct_win, n_ref = [], [], []
    for r in o.itertuples(index=False):
        g = ref[(ref["radar"] == r.radar) & (ref["season"] == r.season)]
        v = g["vid_night"].dropna().to_numpy()
        w = g.loc[(g["doy"] - r.doy).abs() <= WINDOW, "vid_night"].dropna().to_numpy()
        n_ref.append(len(v))
        pct.append(float((v < r.vid_night).mean()) if len(v) >= 30 else np.nan)
        pct_win.append(float((w < r.vid_night).mean()) if len(w) >= 30 else np.nan)
    return o.assign(obs_pct=pct, obs_pct_win=pct_win, ref_n=n_ref)


def match(fc: pd.DataFrame, obs: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    """Join each issued forecast with what its city's nearest radar went on to measure.

    Where two cities share a radar only the closest one is kept, so a single radar-night does not
    count twice in the totals.
    """
    c = cities[["city", "country", "nearest_radar", "dist_km", "confidence"]]
    m = fc.drop(columns=[x for x in ("country",) if x in fc.columns]).merge(c, on="city", how="inner")
    m = m.merge(obs, left_on=["nearest_radar", "night"], right_on=["radar", "night"], how="inner")
    closest = m.sort_values("dist_km").groupby("nearest_radar")["city"].first().to_dict()
    m = m[[closest[r] == c for r, c in zip(m["nearest_radar"], m["city"])]]
    return m.assign(pred_vid=m["pred"].clip(lower=0) ** 3)


def metrics(m: pd.DataFrame) -> dict:
    """The headline numbers of the verification."""
    op = m[m["lead"].between(*LEAD_OP)]
    rho = (op.groupby("nearest_radar")
             .apply(lambda x: spearmanr(x["pred"], x["vid_night"]).correlation if len(x) > 5 else np.nan)
             .dropna())
    ok = op[op["ref_n"] >= MIN_REF]
    a = ok["level"].isin(["high", "very high"])
    o = ok["obs_pct"] >= 0.75
    out = {
        "nights": int(m["night"].nunique()), "places": int(m["nearest_radar"].nunique()),
        "cases": len(op), "radars_scored": len(rho),
        "rho_median": float(rho.median()) if len(rho) else np.nan,
        "rho_positive": int((rho > 0).sum()),
        "rho_p": float(wilcoxon(rho).pvalue) if len(rho) >= 6 else np.nan,
        "alert_rate": float(a.mean()) if len(ok) else np.nan,
        "busy_rate": float(o.mean()) if len(ok) else np.nan,
        "precision": float((a & o).sum() / a.sum()) if a.sum() else np.nan,
        "recall": float((a & o).sum() / o.sum()) if o.sum() else np.nan,
        "scored_cases": len(ok),
        "pred_mean": float(op["pred_vid"].mean()), "obs_mean": float(op["vid_night"].mean()),
    }
    out["under"] = out["obs_mean"] / out["pred_mean"] if out["pred_mean"] else np.nan
    return out


def by_place(m: pd.DataFrame) -> pd.DataFrame:
    """One row per place: how well its nights were ordered and how far the size fell short."""
    op = m[m["lead"].between(*LEAD_OP)]
    t = (op.groupby(["city", "nearest_radar"])
           .apply(lambda x: pd.Series({
               "nights": x["night"].nunique(),
               "km to radar": x["dist_km"].iloc[0],
               "rank correlation": spearmanr(x["pred"], x["vid_night"]).correlation,
               "forecast birds/km²": x["pred_vid"].mean(),
               "measured birds/km²": x["vid_night"].mean(),
               "busiest night": x.loc[x["vid_night"].idxmax(), "night"].strftime("%d %b"),
               "level that night": x.loc[x["vid_night"].idxmax(), "level"],
               "record nights": x["ref_n"].max()}))
           .reset_index())
    return t.sort_values("measured birds/km²", ascending=False)


def by_lead(m: pd.DataFrame) -> pd.DataFrame:
    """How the skill decays as the forecast reaches further ahead."""
    rows = []
    for lead, g in m.groupby("lead"):
        rho = (g.groupby("nearest_radar")
                 .apply(lambda x: spearmanr(x["pred"], x["vid_night"]).correlation if len(x) > 5 else np.nan)
                 .dropna())
        if len(rho) < 3:
            continue
        rows.append({"days ahead": int(lead), "cases": len(g), "places": len(rho),
                     "median rank correlation": rho.median()})
    return pd.DataFrame(rows)


def figures(m: pd.DataFrame, out_dir: Path, nights_shown: int = 21) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    from .phase3 import LEVEL_COLOR, LEVEL_ORDER

    figs = []
    op = m[m["lead"].between(*LEAD_OP)].sort_values("lead")
    last = op.drop_duplicates(["city", "night"], keep="first")   # the closest forecast to each night

    # 1) what was said against what flew, night by night
    p = out_dir / "scorecard_grid.png"
    nights = sorted(last["night"].unique())[-nights_shown:]
    g = last[last["night"].isin(nights)]
    order = g.groupby("city")["vid_night"].mean().sort_values(ascending=False).index.tolist()
    fig, ax = plt.subplots(figsize=(max(7, 0.55 * len(nights) + 2.5), 0.42 * len(order) + 1.6))
    for i, c in enumerate(order):
        for j, n in enumerate(nights):
            row = g[(g["city"] == c) & (g["night"] == n)]
            if row.empty:
                continue
            lv, v = row["level"].iat[0], row["vid_night"].iat[0]
            ax.add_patch(plt.Rectangle((j, i), 1, 1, facecolor=LEVEL_COLOR.get(lv, "#fff"), edgecolor="white"))
            ax.text(j + 0.5, i + 0.5, f"{v:.0f}" if v >= 10 else f"{v:.1f}", ha="center", va="center",
                    fontsize=7, color="white" if lv == "very high" else "#2c2c2a")
    ax.set_xlim(0, len(nights)); ax.set_ylim(0, len(order)); ax.invert_yaxis()
    ax.set_xticks(np.arange(len(nights)) + 0.5)
    ax.set_xticklabels([pd.Timestamp(n).strftime("%d/%m") for n in nights], rotation=90, fontsize=7)
    ax.set_yticks(np.arange(len(order)) + 0.5); ax.set_yticklabels(order, fontsize=8)
    ax.set_title("Colour: the alert that was published. Number: the birds/km² the radar then measured", fontsize=10)
    ax.legend(handles=[Patch(facecolor=LEVEL_COLOR[n], edgecolor="#bbb", label=n) for n in LEVEL_ORDER],
              loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4, frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(p, dpi=130, bbox_inches="tight"); plt.close(fig); figs.append(p)

    # 2) size: the forecast against the measurement, on the same scale
    p = out_dir / "scorecard_scatter.png"
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    ax.scatter(op["pred_vid"].clip(lower=0.05), op["vid_night"].clip(lower=0.05), s=16, alpha=0.45,
               color="#1d6fa5", edgecolors="none")
    lim = [0.05, max(op["vid_night"].max(), op["pred_vid"].max()) * 1.3]
    ax.plot(lim, lim, color="#b32d1f", lw=1, ls="--", label="perfect agreement")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("forecast birds/km²"); ax.set_ylabel("measured birds/km²")
    ax.set_title("Every night ranked and measured", fontsize=10)
    ax.grid(alpha=0.25); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 3) how far ahead the skill survives
    t = by_lead(m)
    if len(t) > 1:
        p = out_dir / "scorecard_lead.png"
        fig, ax = plt.subplots(figsize=(6.4, 3.2))
        ax.axhline(0, color="#999", lw=0.8)
        ax.plot(t["days ahead"], t["median rank correlation"], marker="o", color="#333", lw=1.5)
        ax.set_xlabel("days between the forecast and the night"); ax.set_ylabel("median rank correlation")
        ax.set_title("How far ahead the ordering survives", fontsize=10); ax.grid(alpha=0.25)
        fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def write_report(m: pd.DataFrame, k: dict, figs: list[Path], out: Path) -> None:
    from .phase3 import STYLE

    pct = lambda x: "—" if pd.isna(x) else f"{x:.0%}"
    num = lambda x, d=2: "—" if pd.isna(x) else f"{x:.{d}f}"
    summary = {
        "nights verified": f"{k['nights']}",
        "places with a radar": f"{k['places']}",
        "forecast-nights checked": f"{k['cases']:,}",
        "median rank correlation": num(k["rho_median"]),
        "places where it is positive": f"{k['rho_positive']} of {k['radars_scored']}",
        "alerts that landed on a busy night": pct(k["precision"]),
        "busy nights that were flagged": pct(k["recall"]),
        "size falls short by": f"×{num(k['under'], 1)}",
    }
    parts = [
        "<h1>Did the published forecasts hold up?</h1>",
        f"<p><i>Generated on {dt.date.today():%d %B %Y}. Every number here comes from forecasts that were "
        "published before the night happened.</i></p>",
        "<p><b>Where the forecasts come from.</b> The daily routine commits the forecast in force, so the "
        "history of this repository is an archive of forecasts stamped with the day they were issued. "
        "Nothing is re-run: the model is judged on what it actually said. Against it goes the density each "
        "city's nearest radar went on to measure, taken again from the public archive, which publishes each "
        "day with about two days of delay.</p>",
        "<div class='k'>" + "".join(f"<div>{a}<b>{b}</b></div>" for a, b in summary.items()) + "</div>",
        f"<p><b>How to read it.</b> The rank correlation asks whether the busier nights of a place were "
        f"forecast as the busier ones: it needs no long radar record, so it is the number that holds "
        f"everywhere. The alert figures only use the {k['scored_cases']} cases where the radar has at least "
        f"{MIN_REF} nights in its own record, because without that there is nothing to call a busy night "
        f"against; chance alone would land on one {pct(k['busy_rate'])} of the time. The size is the honest "
        "weak point: the model orders nights better than it measures them.</p>",
    ]
    for f in figs:
        parts.append(f"<p><img src='{f.name}'></p>")
    parts += [
        "<h2>Place by place</h2>",
        by_place(m).round(2).to_html(index=False),
        "<h2>By how far ahead</h2>",
        by_lead(m).round(3).to_html(index=False),
        "<h2>What this cannot tell you</h2><ul>"
        "<li>The radar is not in the city: it is the nearest one, tens of kilometres away, and it sees a "
        "circle of its own. A forecast can be right about the city and still miss the radar.</li>"
        "<li>The Spanish radars renewed in 2025 have no full autumn in the archive yet, so what counts as a "
        "busy night there is not settled and their alert figures are left out of the totals.</li>"
        "<li>The French radars changed scale in 2019, by a factor of tens: their nights are comparable with "
        "each other from that year on, but not with the ones before.</li>"
        "<li>Only cities whose nearest radar still publishes can be checked at all.</li></ul>",
    ]
    out.write_text(STYLE + "\n".join(parts), encoding="utf-8")
