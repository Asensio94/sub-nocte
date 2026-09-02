"""Línea de comandos.

  python -m birdcast_eu.cli ingest estjv esgld --start 2025-11-01 --end 2026-08-31
  python -m birdcast_eu.cli nightly estjv esgld
  python -m birdcast_eu.cli fase0
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import typer
from rich import print as rprint

from . import aloft
from .nightly import build_nightly, radar_position

app = typer.Typer(add_completion=False, help="BirdCast Europa: perfiles de radar → noches → validación")

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "aloft"
VPTS = ROOT / "data" / "vpts"
NIGHTLY = ROOT / "data" / "nightly"
OUTPUT = ROOT / "output"

# Conjunto de la fase 0: red española renovada + Portugal como control + un radar español antiguo
FASE0 = {
    "estjv": "Madrid (Torrejón de Velasco)",
    "esgld": "Barcelona (Gelida)",
    "esahr": "Málaga (Alhaurín)",
    "essft": "Cáceres (Sierra de Fuentes)",
    "ptlis": "Lisboa (control, IPMA)",
    "ptprt": "Oporto (control, IPMA)",
}
FASE0_START = dt.date(2025, 11, 1)
FASE0_END = dt.date(2026, 8, 31)


def _parse(d: str) -> dt.date:
    return dt.date.fromisoformat(d)


@app.command()
def radars():
    """Lista los radares del bucket y sus años con datos."""
    for r in aloft.list_radars():
        rprint(f"{r}: {aloft.radar_years(r)}")


@app.command()
def ingest(radares: list[str], start: str = typer.Option(...), end: str = typer.Option(...)):
    """Descarga perfiles de Aloft y los guarda en parquet (data/vpts/{radar}.parquet)."""
    VPTS.mkdir(parents=True, exist_ok=True)
    for r in radares:
        rprint(f"[bold]{r}[/bold]")
        df = aloft.fetch_radar(r, _parse(start), _parse(end), CACHE, log=rprint)
        if df.empty:
            rprint(f"  [red]sin datos[/red]")
            continue
        df.to_parquet(VPTS / f"{r}.parquet", index=False)
        rprint(f"  {len(df):,} filas, {df['datetime'].min():%Y-%m-%d} → {df['datetime'].max():%Y-%m-%d}")


@app.command()
def nightly(radares: list[str]):
    """Calcula la tabla radar × noche (data/nightly/{radar}.parquet)."""
    NIGHTLY.mkdir(parents=True, exist_ok=True)
    for r in radares:
        df = pd.read_parquet(VPTS / f"{r}.parquet")
        p, n = build_nightly(df, r)
        p.to_parquet(NIGHTLY / f"{r}_profiles.parquet", index=False)
        n.to_parquet(NIGHTLY / f"{r}.parquet", index=False)
        ok = n[n["coverage"] >= 0.6]
        rprint(f"{r}: {len(n)} noches ({len(ok)} con cobertura ≥60 %), MTR mediana {ok['mtr_night'].median():,.0f} aves/km/noche, "
               f"máx {ok['mtr_night'].max():,.0f}, paso {n['step_min'].iloc[0]:.0f} min")


@app.command()
def fase0(skip_download: bool = False):
    """Ejecuta la validación completa de la fase 0 y escribe output/fase0.html."""
    from . import validate as V

    OUTPUT.mkdir(parents=True, exist_ok=True)
    radares = list(FASE0)
    if not skip_download:
        ingest(radares, start=FASE0_START.isoformat(), end=FASE0_END.isoformat())
    nightly(radares)
    raw, profiles, nights, positions = {}, {}, [], {}
    for r in radares:
        raw[r] = pd.read_parquet(VPTS / f"{r}.parquet")
        profiles[r] = pd.read_parquet(NIGHTLY / f"{r}_profiles.parquet")
        nights.append(pd.read_parquet(NIGHTLY / f"{r}.parquet"))
        positions[r] = radar_position(raw[r])
    allnights = pd.concat(nights, ignore_index=True)
    allnights.to_csv(OUTPUT / "fase0_noches.csv", index=False)
    summary = V.summary_table(allnights)
    corr = V.correlation_table(allnights)
    figs = [OUTPUT / "fase0_series.png", OUTPUT / "fase0_ciclo_diario.png", OUTPUT / "fase0_curso_nocturno.png", OUTPUT / "fase0_perfil.png"]
    V.fig_timeseries(allnights, figs[0])
    V.fig_daycycle(profiles, figs[1])
    V.fig_nightcourse(profiles, figs[2])
    V.fig_vertical(raw, positions, figs[3])
    notes = [
        "Radares: " + "; ".join(f"{k} = {v}" for k, v in FASE0.items()),
        "Criterio: un radar 've aves' si en primavera la densidad nocturna supera claramente a la diurna (ratio > 2), "
        "el MTR nocturno de primavera es del orden de miles de aves/km/noche, el tráfico nocturno va concentrado hacia el N-NE "
        "(concentración > 0,4) a más de 8 m/s, y hay coherencia noche a noche entre radares vecinos.",
    ]
    directions = V.direction_table(raw, positions)
    directions.to_csv(OUTPUT / "fase0_direcciones.csv", index=False)
    V.write_report(summary, corr, figs, OUTPUT / "fase0.html", notes, directions)
    rprint(summary.to_string(index=False))
    rprint("\n[bold]Dirección y velocidad (primavera):[/bold]")
    rprint(directions.round(2).to_string(index=False))
    rprint("\n[bold]Correlación primavera (log MTR):[/bold]")
    rprint(corr.to_string())
    rprint(f"\nInforme: {OUTPUT / 'fase0.html'}")


# Fase 1: radares con interés para el piloto ibérico y su entorno (España antigua y nueva, Portugal, Francia)
FASE1_PAISES = ("es", "pt", "fr")


@app.command()
def historico(radares: list[str] = typer.Argument(None), paises: str = ",".join(FASE1_PAISES),
              start_year: int = 2016, end_year: int = dt.date.today().year, purge: bool = True):
    """Construye data/nightly/{radar}.parquet para todo el histórico. Sin radares explícitos usa los países indicados."""
    from .historico import build_history

    if not radares:
        prefijos = tuple(paises.split(","))
        radares = [r for r in aloft.list_radars() if r.startswith(prefijos)]
    rprint(f"{len(radares)} radares, {start_year}-{end_year}")
    for r in radares:
        years = [y for y in aloft.radar_years(r) if start_year <= y <= end_year]
        if not years:
            rprint(f"[dim]{r}: sin años en rango[/dim]")
            continue
        rprint(f"[bold]{r}[/bold] {years[0]}-{years[-1]}")
        build_history(r, years, CACHE, NIGHTLY, purge=purge, log=rprint)


@app.command()
def climatologia():
    """Climatología por día del año y umbrales P70/P90 por radar y temporada → data/climatologia_doy.csv, data/umbrales.csv."""
    from .historico import climatology_doy, load_all_nightly, thresholds

    n = load_all_nightly(NIGHTLY)
    if n.empty:
        rprint("[red]No hay tablas nocturnas en data/nightly[/red]")
        raise typer.Exit(1)
    n.to_parquet(ROOT / "data" / "noches.parquet", index=False)
    # dos métricas: MTR nocturno (aves/km/noche, exige velocidad) y VID nocturno (aves/km2, solo densidad).
    # Muchos radares franceses no publican velocidad desde 2023, así que el VID es la única serie homogénea.
    doy = pd.concat([climatology_doy(n, metric=m) for m in ("mtr_night", "vid_night")], ignore_index=True)
    doy.to_csv(ROOT / "data" / "climatologia_doy.csv", index=False, float_format="%.1f")
    th = pd.concat([thresholds(n, metric=m) for m in ("mtr_night", "vid_night")], ignore_index=True)
    th.to_csv(ROOT / "data" / "umbrales.csv", index=False, float_format="%.1f")
    doy_mtr, th_mtr = doy[doy["metrica"] == "mtr_night"], th[th["metrica"] == "mtr_night"]
    rprint(f"{n['radar'].nunique()} radares, {len(n):,} noches ({n['night'].min():%Y-%m-%d} → {n['night'].max():%Y-%m-%d})")
    rprint(th[th["metrica"] == "mtr_night"].round(1).to_string(index=False))
    from . import fase1 as F

    OUTPUT.mkdir(parents=True, exist_ok=True)
    piloto = [r for r in ("estjv", "esgld", "essft", "esahr", "ptprt", "ptlis") if r in set(doy["radar"])]
    otros = sorted(set(doy["radar"]) - set(piloto))
    figs = [OUTPUT / "fase1_clima_piloto.png", OUTPUT / "fase1_clima_resto.png",
            OUTPUT / "fase1_clima_piloto_mtr.png",
            OUTPUT / "fase1_mapa_primavera.png", OUTPUT / "fase1_mapa_otoño.png"]
    F.fig_climatology(doy, piloto, figs[0])
    F.fig_climatology(doy, otros, figs[1], ncols=4)
    F.fig_climatology(doy_mtr, piloto, figs[2], metric="mtr_night")
    F.fig_thresholds_map(th, figs[3], "primavera")
    F.fig_thresholds_map(th, figs[4], "otoño")
    F.write_report(th, doy, n[n["coverage"] >= 0.6], figs, OUTPUT / "fase1.html")
    rprint(f"Informe: {OUTPUT / 'fase1.html'}")


@app.command()
def ciudades():
    """Asigna cada ciudad del piloto al radar útil más cercano (5-100 km) → data/ciudades.csv."""
    from .ciudades import asignar
    from .historico import load_all_nightly

    n = load_all_nightly(NIGHTLY)
    if n.empty:
        rprint("[red]No hay tablas nocturnas en data/nightly[/red]")
        raise typer.Exit(1)
    pos = n.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"),
                                 ultimo_anio=("night", lambda x: x.dt.year.max())).reset_index()
    tabla = asignar(pos)
    tabla.to_csv(ROOT / "data" / "ciudades.csv", index=False)
    rprint(tabla.to_string(index=False))
    rprint(f"\n{(tabla['radar'].notna()).sum()} de {len(tabla)} ciudades con radar entre 5 y 100 km")


@app.command()
def verificar(paises: str = ",".join(FASE1_PAISES), start_year: int = 2016, reintentar: bool = False):
    """Compara los años disponibles en Aloft con los presentes en data/nightly y, si se pide, reprocesa los que falten."""
    from .historico import build_history, sin_noches

    vacios = sin_noches(NIGHTLY)
    prefijos = tuple(paises.split(","))
    faltan: dict[str, list[int]] = {}
    for r in [x for x in aloft.list_radars() if x.startswith(prefijos)]:
        disp = [y for y in aloft.radar_years(r) if y >= start_year]
        dest = NIGHTLY / f"{r}.parquet"
        hay = set()
        if dest.exists():
            hay = set(pd.to_datetime(pd.read_parquet(dest, columns=["night"])["night"]).dt.year)
        # los radar-años sin noches utilizables (p. ej. esgrm, solo barridos diurnos) están anotados y no se reintentan
        pend = [y for y in disp if y not in hay and (r, y) not in vacios]
        if pend:
            faltan[r] = pend
            rprint(f"[yellow]{r}[/yellow]: faltan {pend}")
    if not faltan:
        rprint("[green]Todos los radar-años disponibles están procesados[/green]")
        return
    rprint(f"{sum(len(v) for v in faltan.values())} radar-años pendientes en {len(faltan)} radares")
    if reintentar:
        for r, years in faltan.items():
            rprint(f"[bold]{r}[/bold] {years}")
            build_history(r, years, CACHE, NIGHTLY, purge=True, log=rprint)


METEO = ROOT / "data" / "meteo"


@app.command()
def meteo(radares: list[str] = typer.Argument(None), start_year: int = 2016):
    """Descarga ERA5 horario (Open-Meteo) para cada radar con tabla nocturna → data/meteo/{radar}.parquet."""
    from .historico import load_all_nightly
    from .meteo import fetch_radar_meteo

    n = load_all_nightly(NIGHTLY)
    pos = n.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"),
                                 y0=("night", lambda x: x.dt.year.min()), y1=("night", lambda x: x.dt.year.max()))
    if radares:
        pos = pos.loc[[r for r in radares if r in pos.index]]
    rprint(f"{len(pos)} radares")
    for r, p in pos.iterrows():
        years = list(range(max(start_year, int(p.y0)), int(p.y1) + 1))
        rprint(f"[bold]{r}[/bold] {years[0]}-{years[-1]}")
        fetch_radar_meteo(r, float(p.lat), float(p.lon), years, METEO, log=rprint)


if __name__ == "__main__":
    app()
