"""Command line.

  python -m subnocte.cli ingest estjv esgld --start 2025-11-01 --end 2026-08-31
  python -m subnocte.cli nightly estjv esgld
  python -m subnocte.cli phase0
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import typer
from rich import print as rprint

from . import aloft
from .nightly import build_nightly, radar_position

app = typer.Typer(add_completion=False,
                  help="Sub Nocte: nocturnal bird migration in Europe, from the radar profiles to the city alert")

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "aloft"
VPTS = ROOT / "data" / "vpts"
NIGHTLY = ROOT / "data" / "nightly"
OUTPUT = ROOT / "output"

# Phase 0 set: renewed Spanish network + Portugal as a control + one old Spanish radar
PHASE0 = {
    "estjv": "Madrid (Torrejón de Velasco)",
    "esgld": "Barcelona (Gelida)",
    "esahr": "Málaga (Alhaurín)",
    "essft": "Cáceres (Sierra de Fuentes)",
    "ptlis": "Lisbon (control, IPMA)",
    "ptprt": "Porto (control, IPMA)",
}
PHASE0_START = dt.date(2025, 11, 1)
PHASE0_END = dt.date(2026, 8, 31)


def _parse(d: str) -> dt.date:
    return dt.date.fromisoformat(d)


@app.command()
def radars():
    """List the radars in the bucket and their years with data."""
    for r in aloft.list_radars():
        rprint(f"{r}: {aloft.radar_years(r)}")


@app.command()
def ingest(radars: list[str], start: str = typer.Option(...), end: str = typer.Option(...)):
    """Download profiles from Aloft and save them as parquet (data/vpts/{radar}.parquet)."""
    VPTS.mkdir(parents=True, exist_ok=True)
    for r in radars:
        rprint(f"[bold]{r}[/bold]")
        df = aloft.fetch_radar(r, _parse(start), _parse(end), CACHE, log=rprint)
        if df.empty:
            rprint("  [red]no data[/red]")
            continue
        df.to_parquet(VPTS / f"{r}.parquet", index=False)
        rprint(f"  {len(df):,} rows, {df['datetime'].min():%Y-%m-%d} → {df['datetime'].max():%Y-%m-%d}")


@app.command()
def nightly(radars: list[str]):
    """Compute the radar × night table (data/nightly/{radar}.parquet)."""
    NIGHTLY.mkdir(parents=True, exist_ok=True)
    for r in radars:
        df = pd.read_parquet(VPTS / f"{r}.parquet")
        p, n = build_nightly(df, r)
        p.to_parquet(NIGHTLY / f"{r}_profiles.parquet", index=False)
        n.to_parquet(NIGHTLY / f"{r}.parquet", index=False)
        ok = n[n["coverage"] >= 0.6]
        rprint(f"{r}: {len(n)} nights ({len(ok)} with coverage ≥60 %), median MTR "
               f"{ok['mtr_night'].median():,.0f} birds/km/night, max {ok['mtr_night'].max():,.0f}, "
               f"step {n['step_min'].iloc[0]:.0f} min")


@app.command()
def phase0(skip_download: bool = False):
    """Run the full phase 0 validation and write output/phase0.html."""
    from . import validate as V

    OUTPUT.mkdir(parents=True, exist_ok=True)
    rads = list(PHASE0)
    if not skip_download:
        ingest(rads, start=PHASE0_START.isoformat(), end=PHASE0_END.isoformat())
    nightly(rads)
    raw, profiles, nights, positions = {}, {}, [], {}
    for r in rads:
        raw[r] = pd.read_parquet(VPTS / f"{r}.parquet")
        profiles[r] = pd.read_parquet(NIGHTLY / f"{r}_profiles.parquet")
        nights.append(pd.read_parquet(NIGHTLY / f"{r}.parquet"))
        positions[r] = radar_position(raw[r])
    allnights = pd.concat(nights, ignore_index=True)
    allnights.to_csv(OUTPUT / "phase0_nights.csv", index=False)
    summary = V.summary_table(allnights)
    corr = V.correlation_table(allnights)
    figs = [OUTPUT / "phase0_series.png", OUTPUT / "phase0_daycycle.png",
            OUTPUT / "phase0_nightcourse.png", OUTPUT / "phase0_profile.png"]
    V.fig_timeseries(allnights, figs[0])
    V.fig_daycycle(profiles, figs[1])
    V.fig_nightcourse(profiles, figs[2])
    V.fig_vertical(raw, positions, figs[3])
    notes = [
        "Radars: " + "; ".join(f"{k} = {v}" for k, v in PHASE0.items()),
        "Criterion: a radar 'sees birds' if in spring the night density clearly exceeds the daytime one "
        "(ratio > 2), the spring night MTR is of the order of thousands of birds/km/night, the night traffic is "
        "concentrated towards the N-NE (concentration > 0.4) at more than 8 m/s, and there is night-to-night "
        "coherence between neighbouring radars.",
    ]
    directions = V.direction_table(raw, positions)
    directions.to_csv(OUTPUT / "phase0_directions.csv", index=False)
    V.write_report(summary, corr, figs, OUTPUT / "phase0.html", notes, directions)
    rprint(summary.to_string(index=False))
    rprint("\n[bold]Direction and speed (spring):[/bold]")
    rprint(directions.round(2).to_string(index=False))
    rprint("\n[bold]Spring correlation (log MTR):[/bold]")
    rprint(corr.to_string())
    rprint(f"\nReport: {OUTPUT / 'phase0.html'}")


# Phase 1: radars of interest for the Iberian pilot and its surroundings (old and new Spain, Portugal, France)
PHASE1_COUNTRIES = ("es", "pt", "fr")


@app.command()
def history(radars: list[str] = typer.Argument(None), countries: str = ",".join(PHASE1_COUNTRIES),
            start_year: int = 2016, end_year: int = dt.date.today().year, purge: bool = True):
    """Build data/nightly/{radar}.parquet for the whole archive. With no explicit radars it uses the given countries."""
    from .history import build_history

    if not radars:
        prefixes = tuple(countries.split(","))
        radars = [r for r in aloft.list_radars() if r.startswith(prefixes)]
    rprint(f"{len(radars)} radars, {start_year}-{end_year}")
    for r in radars:
        years = [y for y in aloft.radar_years(r) if start_year <= y <= end_year]
        if not years:
            rprint(f"[dim]{r}: no years in range[/dim]")
            continue
        rprint(f"[bold]{r}[/bold] {years[0]}-{years[-1]}")
        build_history(r, years, CACHE, NIGHTLY, purge=purge, log=rprint)


@app.command()
def climatology():
    """Climatology by day of year and P70/P90 thresholds per radar and season → data/climatology_doy.csv, data/thresholds.csv."""
    from .history import climatology_doy, load_all_nightly, thresholds

    n = load_all_nightly(NIGHTLY)
    if n.empty:
        rprint("[red]There are no nightly tables in data/nightly[/red]")
        raise typer.Exit(1)
    n.to_parquet(ROOT / "data" / "nights.parquet", index=False)
    # two metrics: night MTR (birds/km/night, needs speed) and night VID (birds/km², density only).
    # Many French radars have not published speed since 2023, so VID is the only homogeneous series.
    doy = pd.concat([climatology_doy(n, metric=m) for m in ("mtr_night", "vid_night")], ignore_index=True)
    doy.to_csv(ROOT / "data" / "climatology_doy.csv", index=False, float_format="%.1f")
    th = pd.concat([thresholds(n, metric=m) for m in ("mtr_night", "vid_night")], ignore_index=True)
    th.to_csv(ROOT / "data" / "thresholds.csv", index=False, float_format="%.1f")
    doy_mtr, th_mtr = doy[doy["metric"] == "mtr_night"], th[th["metric"] == "mtr_night"]
    rprint(f"{n['radar'].nunique()} radars, {len(n):,} nights ({n['night'].min():%Y-%m-%d} → {n['night'].max():%Y-%m-%d})")
    rprint(th_mtr.round(1).to_string(index=False))
    from . import phase1 as F

    OUTPUT.mkdir(parents=True, exist_ok=True)
    pilot = [r for r in ("estjv", "esgld", "essft", "esahr", "ptprt", "ptlis") if r in set(doy["radar"])]
    others = sorted(set(doy["radar"]) - set(pilot))
    figs = [OUTPUT / "phase1_climate_pilot.png", OUTPUT / "phase1_climate_rest.png",
            OUTPUT / "phase1_climate_pilot_mtr.png",
            OUTPUT / "phase1_map_spring.png", OUTPUT / "phase1_map_autumn.png"]
    F.fig_climatology(doy, pilot, figs[0])
    F.fig_climatology(doy, others, figs[1], ncols=4)
    F.fig_climatology(doy_mtr, pilot, figs[2], metric="mtr_night")
    F.fig_thresholds_map(th, figs[3], "spring")
    F.fig_thresholds_map(th, figs[4], "autumn")
    F.write_report(th, doy, n[n["coverage"] >= 0.6], figs, OUTPUT / "phase1.html")
    rprint(f"Report: {OUTPUT / 'phase1.html'}")


@app.command()
def cities():
    """Assign each pilot city to its nearest usable radar (5-100 km) → data/cities.csv."""
    from .cities import assign
    from .history import load_all_nightly

    n = load_all_nightly(NIGHTLY)
    if n.empty:
        rprint("[red]There are no nightly tables in data/nightly[/red]")
        raise typer.Exit(1)
    pos = n.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"),
                                 last_year=("night", lambda x: x.dt.year.max())).reset_index()
    table = assign(pos)
    table.to_csv(ROOT / "data" / "cities.csv", index=False)
    rprint(table.to_string(index=False))
    rprint(f"\n{(table['radar'].notna()).sum()} of {len(table)} cities have a radar between 5 and 100 km")


@app.command()
def verify(countries: str = ",".join(PHASE1_COUNTRIES), start_year: int = 2016, retry: bool = False):
    """Compare the years available in Aloft with those present in data/nightly and, on request, reprocess the missing ones."""
    from .history import build_history, without_nights

    empty = without_nights(NIGHTLY)
    prefixes = tuple(countries.split(","))
    missing: dict[str, list[int]] = {}
    for r in [x for x in aloft.list_radars() if x.startswith(prefixes)]:
        available = [y for y in aloft.radar_years(r) if y >= start_year]
        dest = NIGHTLY / f"{r}.parquet"
        have = set()
        if dest.exists():
            have = set(pd.to_datetime(pd.read_parquet(dest, columns=["night"])["night"]).dt.year)
        # radar-years with no usable nights (e.g. esgrm, daytime scans only) are recorded and not retried
        pending = [y for y in available if y not in have and (r, y) not in empty]
        if pending:
            missing[r] = pending
            rprint(f"[yellow]{r}[/yellow]: missing {pending}")
    if not missing:
        rprint("[green]Every available radar-year is processed[/green]")
        return
    rprint(f"{sum(len(v) for v in missing.values())} radar-years pending in {len(missing)} radars")
    if retry:
        for r, years in missing.items():
            rprint(f"[bold]{r}[/bold] {years}")
            build_history(r, years, CACHE, NIGHTLY, purge=True, log=rprint)


WEATHER = ROOT / "data" / "weather"
WEATHER_LEVELS = ROOT / "data" / "weather_levels"


@app.command()
def weather(radars: list[str] = typer.Argument(None), start_year: int = 2016):
    """Download hourly ERA5 (Open-Meteo) for every radar with a nightly table → data/weather/{radar}.parquet."""
    from .history import load_all_nightly
    from .weather import fetch_radar_weather

    n = load_all_nightly(NIGHTLY)
    pos = n.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"),
                                 y0=("night", lambda x: x.dt.year.min()), y1=("night", lambda x: x.dt.year.max()))
    if radars:
        pos = pos.loc[[r for r in radars if r in pos.index]]
    rprint(f"{len(pos)} radars")
    for r, p in pos.iterrows():
        years = list(range(max(start_year, int(p.y0)), int(p.y1) + 1))
        rprint(f"[bold]{r}[/bold] {years[0]}-{years[-1]}")
        fetch_radar_weather(r, float(p.lat), float(p.lon), years, WEATHER, log=rprint)


@app.command()
def weather_levels(radars: list[str] = typer.Argument(None), start_year: int = 2021):
    """Download wind and temperature on pressure levels (925/850/700 hPa, flight altitude) from 2021."""
    from .history import load_all_nightly
    from .weather import fetch_radar_levels

    n = load_all_nightly(NIGHTLY)
    pos = n.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"),
                                 y0=("night", lambda x: x.dt.year.min()), y1=("night", lambda x: x.dt.year.max()))
    if radars:
        pos = pos.loc[[r for r in radars if r in pos.index]]
    rprint(f"{len(pos)} radars")
    for r, pp in pos.iterrows():
        years = list(range(max(start_year, int(pp.y0)), int(pp.y1) + 1))
        if not years:
            continue
        rprint(f"[bold]{r}[/bold] {years[0]}-{years[-1]}")
        fetch_radar_levels(r, float(pp.lat), float(pp.lon), years, WEATHER_LEVELS, log=rprint)


def _phase2_dataset(cache: bool, levels: bool):
    """Load (or build) the radar × night set and return (dataset, features)."""
    from . import model as M
    from .history import load_all_nightly

    dsf = ROOT / "data" / "phase2_dataset.parquet"
    if cache and dsf.exists():
        ds = pd.read_parquet(dsf)
        rprint(f"dataset reused from {dsf}")
    else:
        n = load_all_nightly(NIGHTLY)
        clim = pd.read_csv(ROOT / "data" / "climatology_doy.csv")
        ds = M.build_dataset(n, WEATHER, clim, log=rprint, levels_dir=WEATHER_LEVELS)
        ds.to_parquet(dsf, index=False)
    if levels and "ws_850hPa" in ds:
        ds = ds[ds["ws_850hPa"].notna()].reset_index(drop=True)
        rprint("[bold]with wind at flight altitude[/bold] (925/850/700 hPa, from 2021)")
    ds = M.mark_alerts(ds)  # the heavy-passage threshold is recomputed over the nights that enter the model
    cols = M.feature_columns(ds, levels=levels)
    rprint(f"{len(ds):,} radar-nights inside the migration window, {ds['radar'].nunique()} radars, {len(cols)} features, "
           f"{ds['alert_obs'].mean():.1%} heavy-passage nights")
    return ds, cols


REF_CSV = ROOT / "data" / "phase2_validation_surface.csv"


@app.command()
def phase2_reference(cache: bool = True):
    """Phase 2 reference: the same nights with wind aloft, but using surface weather only."""
    from . import model as M

    ds, _ = _phase2_dataset(cache, levels=True)
    ref, _p = M.evaluate(ds, M.feature_columns(ds, levels=False), log=rprint)
    ref.to_csv(REF_CSV, index=False, float_format="%.3f")
    rprint(f"Reference saved in {REF_CSV}")


@app.command()
def phase2(cache: bool = False, levels: bool = True, reference_from_file: bool = False):
    """Weather model of the night VID: radar × night set, validation by year and by radar, report."""
    from . import model as M
    from . import phase2 as F

    ds, cols = _phase2_dataset(cache, levels)
    met, preds = M.evaluate(ds, cols, log=rprint)
    met.to_csv(ROOT / "data" / "phase2_validation.csv", index=False, float_format="%.3f")
    preds.to_parquet(ROOT / "data" / "phase2_predictions.parquet", index=False)  # to redo figures without revalidating
    imp = M.importance(ds, cols)
    imp.to_csv(ROOT / "data" / "phase2_importance.csv", float_format="%.2f")
    M.fit_final(ds, cols, ROOT / "data")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # reference: same nights, surface weather only, to measure what flight altitude adds
    ref = None
    if levels and any("hPa" in c for c in cols):
        if reference_from_file and REF_CSV.exists():
            ref = pd.read_csv(REF_CSV)
            rprint(f"reference without altitude read from {REF_CSV}")
        else:
            rprint("[bold]reference without wind aloft[/bold]")
            ref, _ = M.evaluate(ds, M.feature_columns(ds, levels=False), log=rprint)
            ref.to_csv(REF_CSV, index=False, float_format="%.3f")
    figs = F.figures(ds, met, preds, imp, OUTPUT)
    F.write_report(ds, met, imp, cols, figs, OUTPUT / "phase2.html", ref=ref)
    ra = met[met["split"].str.startswith("radar")]
    rprint(ra.round(2).to_string(index=False))
    rprint(f"[bold]radar left out[/bold]: median area under the curve {ra['auc'].median():.2f}, "
           f"heavy passage captured {ra['hit_rate'].mean():.0%} (chance 10 %)")
    rprint(f"Report: {OUTPUT / 'phase2.html'}")


CITY_WEATHER = ROOT / "data" / "weather_cities"
CITY_CLIMATE = ROOT / "data" / "phase3_city_climate.parquet"
THRESHOLDS_CSV = ROOT / "data" / "phase3_thresholds.csv"
FORECAST_CSV = ROOT / "data" / "phase3_forecast.csv"


@app.command()
def phase3_archive(wanted: list[str] = typer.Argument(None), start_year: int = 2021):
    """Weather archive at each city's point, over the migration windows, to calibrate its thresholds."""
    from .cities import CITIES
    from .forecast import fetch_archive

    years = list(range(start_year, dt.date.today().year + 1))
    wanted_cities = [c for c in CITIES if not wanted or c[0] in wanted]
    rprint(f"{len(wanted_cities)} cities, {years[0]}-{years[-1]}")
    for name, country, lat, lon in wanted_cities:
        rprint(f"[bold]{name}[/bold] ({country})")
        fetch_archive(name, lat, lon, years, CITY_WEATHER, log=rprint)


@app.command()
def phase3_train(cache: bool = True):
    """Operational models: the phase 2 ones without local climatology, the configuration validated leaving radars out."""
    from . import model as M

    ds, cols = _phase2_dataset(cache, levels=True)
    cols = [c for c in cols if not c.startswith("clim_")]
    paths = M.fit_final(ds, cols, ROOT / "data", prefix="model_op")
    rprint(f"{len(cols)} features without local climatology -> " + ", ".join(p.name for p in paths))


def _city_features(models, log=rprint) -> pd.DataFrame:
    """Features and predictions from the weather archive of every city already downloaded."""
    from . import forecast as P
    from .cities import CITIES

    parts = []
    for name, country, lat, lon in CITIES:
        f = CITY_WEATHER / f"{name}.parquet"
        if not f.exists():
            log(f"  {name}: no weather archive")
            continue
        r = P.features(name, lat, lon, pd.read_parquet(f))
        if r.empty:
            continue
        parts.append(P.predict(r, models).assign(country=country))
        log(f"  {name}: {len(r)} nights")
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


@app.command()
def phase3_thresholds():
    """Run the model over each city's archive and save the percentiles that define the alert levels."""
    from . import forecast as P

    models = P.load_models(ROOT / "data")
    pred = _city_features(models)
    if pred.empty:
        rprint("[red]no city has a weather archive: run phase3-archive first[/red]")
        raise typer.Exit(1)
    pred.to_parquet(CITY_CLIMATE, index=False)
    u = P.compute_thresholds(pred)
    u.to_csv(THRESHOLDS_CSV, index=False, float_format="%.4f")
    rprint(u[["city", "season", "nights", "alert_q75", "alert_q90"]].round(3).to_string(index=False))
    rprint(f"Thresholds for {u['city'].nunique()} cities in {THRESHOLDS_CSV}")


@app.command()
def phase3(days: int = 7, cache: bool = False):
    """Forecast of the coming nights per city, with each place's own alert level."""
    from . import forecast as P
    from . import phase3 as F3
    from .cities import CITIES

    models = P.load_models(ROOT / "data")
    th = pd.read_csv(THRESHOLDS_CSV)
    with_threshold = set(th["city"])
    raw = ROOT / "data" / "phase3_forecast_raw.parquet"
    if cache and raw.exists():
        fc = pd.read_parquet(raw)
        rprint(f"forecast reused from {raw}")
    else:
        parts = []
        for name, country, lat, lon in CITIES:
            if name not in with_threshold:
                continue
            h = P.fetch_forecast(lat, lon, days, log=rprint)
            r = P.features(name, lat, lon, h)
            if r.empty:
                rprint(f"  {name}: the forecast covers no complete night")
                continue
            parts.append(P.predict(r, models).assign(country=country))
            rprint(f"  {name}: {len(r)} nights forecast")
        fc = pd.concat(parts, ignore_index=True)
        fc.to_parquet(raw, index=False)
    fc = P.apply_thresholds(fc, th)
    fc.to_csv(FORECAST_CSV, index=False, float_format="%.4f")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figs = F3.figures(fc, th, OUTPUT)
    F3.write_report(fc, th, figs, OUTPUT / "phase3.html")
    alerts = fc[fc["level"].isin(["high", "very high"])]
    rprint(f"[bold]{len(fc)} city-nights forecast, {len(alerts)} with a high or very high alert[/bold]")
    if not alerts.empty:
        rprint(alerts.assign(date=alerts["night"].dt.strftime("%d/%m"))
               [["city", "date", "level", "p_alert"]].round(2).to_string(index=False))
    rprint(f"Report: {OUTPUT / 'phase3.html'}")


LIGHTS = ROOT / "data" / "lights"


@app.command()
def ranking(radius_km: float = 10.0):
    """Exposure ranking: artificial light of each city × bird density forecast above it."""
    from . import lights as L
    from . import phase3 as F3
    from .cities import CITIES

    tif = L.ensure_atlas(LIGHTS, log=rprint)
    light = L.sample(tif, CITIES, radius_km=radius_km, log=rprint)
    light.to_csv(ROOT / "data" / "city_lights.csv", index=False, float_format="%.3f")
    if not CITY_CLIMATE.exists():
        rprint("[red]the per-city prediction archive is missing: run phase3-thresholds first[/red]")
        raise typer.Exit(1)
    mig = L.migration_index(pd.read_parquet(CITY_CLIMATE))
    rk = L.ranking(light, mig)
    rk.to_csv(ROOT / "data" / "exposure_ranking.csv", index=False, float_format="%.3f")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figs = F3.ranking_figures(rk, OUTPUT)
    F3.write_ranking(rk, figs, OUTPUT / "ranking.html")
    for season, g in rk.groupby("season"):
        rprint(f"[bold]{season}[/bold]")
        rprint(g.nlargest(10, "exposure_peaks")[["city", "light_mean", "vid_peaks", "exposure_peaks"]]
               .round(1).to_string(index=False))
    rprint(f"Report: {OUTPUT / 'ranking.html'}")


REPORTS = ["output/phase0.html", "output/phase1.html", "output/phase2.html", "output/phase3.html",
           "output/ranking.html", "docs/design.html"]


@app.command()
def web():
    """Regenerate the public site (repository root) from the latest forecast and the latest ranking."""
    from . import web as W

    fc = pd.read_csv(FORECAST_CSV, parse_dates=["night"]) if FORECAST_CSV.exists() else None
    rk_csv = ROOT / "data" / "exposure_ranking.csv"
    rk = pd.read_csv(rk_csv) if rk_csv.exists() else None
    if fc is None:
        rprint("[yellow]no forecast: the site comes out without the coming-nights section[/yellow]")
    W.build(fc, rk, [ROOT / n for n in REPORTS], ROOT, log=rprint)


if __name__ == "__main__":
    app()
