"""Línea de comandos.

  python -m subnocte.cli ingest estjv esgld --start 2025-11-01 --end 2026-08-31
  python -m subnocte.cli nightly estjv esgld
  python -m subnocte.cli fase0
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import typer
from rich import print as rprint

from . import aloft
from .nightly import build_nightly, radar_position

app = typer.Typer(add_completion=False, help="Sub Nocte: migración nocturna de aves en Europa, de los perfiles de radar al aviso por ciudad")

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
METEO_NIVELES = ROOT / "data" / "meteo_niveles"


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


@app.command()
def meteo_niveles(radares: list[str] = typer.Argument(None), start_year: int = 2021):
    """Descarga viento y temperatura en niveles de presión (925/850/700 hPa, altura de vuelo) desde 2021."""
    from .historico import load_all_nightly
    from .meteo import fetch_radar_niveles

    n = load_all_nightly(NIGHTLY)
    pos = n.groupby("radar").agg(lat=("lat", "first"), lon=("lon", "first"),
                                 y0=("night", lambda x: x.dt.year.min()), y1=("night", lambda x: x.dt.year.max()))
    if radares:
        pos = pos.loc[[r for r in radares if r in pos.index]]
    rprint(f"{len(pos)} radares")
    for r, pp in pos.iterrows():
        years = list(range(max(start_year, int(pp.y0)), int(pp.y1) + 1))
        if not years:
            continue
        rprint(f"[bold]{r}[/bold] {years[0]}-{years[-1]}")
        fetch_radar_niveles(r, float(pp.lat), float(pp.lon), years, METEO_NIVELES, log=rprint)


def _conjunto_fase2(cache: bool, niveles: bool):
    """Carga (o construye) el conjunto radar x noche y devuelve (conjunto, rasgos)."""
    from . import modelo as M
    from .historico import load_all_nightly

    dsf = ROOT / "data" / "fase2_dataset.parquet"
    if cache and dsf.exists():
        ds = pd.read_parquet(dsf)
        rprint(f"conjunto reutilizado de {dsf}")
    else:
        n = load_all_nightly(NIGHTLY)
        clim = pd.read_csv(ROOT / "data" / "climatologia_doy.csv")
        ds = M.build_dataset(n, METEO, clim, log=rprint, niveles_dir=METEO_NIVELES)
        ds.to_parquet(dsf, index=False)
    if niveles and "ws_850hPa" in ds:
        ds = ds[ds["ws_850hPa"].notna()].reset_index(drop=True)
        rprint("[bold]con viento en altura de vuelo[/bold] (925/850/700 hPa, desde 2021)")
    ds = M.marcar_alertas(ds)  # el umbral de paso fuerte se recalcula sobre las noches que entran al modelo
    cols = M.feature_columns(ds, niveles=niveles)
    rprint(f"{len(ds):,} radar-noches en ventana migratoria, {ds['radar'].nunique()} radares, {len(cols)} rasgos, "
           f"{ds['alerta_obs'].mean():.1%} de noches de paso fuerte")
    return ds, cols


REF_CSV = ROOT / "data" / "fase2_validacion_superficie.csv"


@app.command()
def fase2_referencia(cache: bool = True):
    """Referencia de la fase 2: las mismas noches con viento en altura, pero usando solo superficie."""
    from . import modelo as M

    ds, _ = _conjunto_fase2(cache, niveles=True)
    ref, _p = M.evaluate(ds, M.feature_columns(ds, niveles=False), log=rprint)
    ref.to_csv(REF_CSV, index=False, float_format="%.3f")
    rprint(f"Referencia guardada en {REF_CSV}")


@app.command()
def fase2(cache: bool = False, niveles: bool = True, referencia_en_fichero: bool = False):
    """Modelo meteorológico del VID nocturno: conjunto radar × noche, validación por año y por radar, informe."""
    from . import fase2 as F
    from . import modelo as M

    ds, cols = _conjunto_fase2(cache, niveles)
    met, preds = M.evaluate(ds, cols, log=rprint)
    met.to_csv(ROOT / "data" / "fase2_validacion.csv", index=False, float_format="%.3f")
    preds.to_parquet(ROOT / "data" / "fase2_predicciones.parquet", index=False)  # para rehacer figuras sin revalidar
    imp = M.importance(ds, cols)
    imp.to_csv(ROOT / "data" / "fase2_importancia.csv", float_format="%.2f")
    M.fit_final(ds, cols, ROOT / "data")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # referencia: mismas noches, solo meteorología de superficie, para medir lo que aporta la altura de vuelo
    ref = None
    if niveles and any("hPa" in c for c in cols):
        if referencia_en_fichero and REF_CSV.exists():
            ref = pd.read_csv(REF_CSV)
            rprint(f"referencia sin altura leída de {REF_CSV}")
        else:
            rprint("[bold]referencia sin viento en altura[/bold]")
            ref, _ = M.evaluate(ds, M.feature_columns(ds, niveles=False), log=rprint)
            ref.to_csv(REF_CSV, index=False, float_format="%.3f")
    figs = F.figures(ds, met, preds, imp, OUTPUT)
    F.write_report(ds, met, imp, cols, figs, OUTPUT / "fase2.html", ref=ref)
    ra = met[met["split"].str.startswith("radar")]
    rprint(ra.round(2).to_string(index=False))
    rprint(f"[bold]radar fuera[/bold]: área bajo la curva mediana {ra['auc'].median():.2f}, "
           f"paso fuerte capturado {ra['acierto'].mean():.0%} (azar 10 %)")
    rprint(f"Informe: {OUTPUT / 'fase2.html'}")


CIUDADES_METEO = ROOT / "data" / "meteo_ciudades"
CLIMA_CIUDADES = ROOT / "data" / "fase3_clima_ciudades.parquet"
UMBRALES_CSV = ROOT / "data" / "fase3_umbrales.csv"
PREVISION_CSV = ROOT / "data" / "fase3_prevision.csv"


@app.command()
def fase3_archivo(ciudades_pedidas: list[str] = typer.Argument(None), start_year: int = 2021):
    """Archivo meteorológico en el punto de cada ciudad, en ventanas migratorias, para calibrar sus umbrales."""
    from .ciudades import CIUDADES
    from .prevision import descargar_archivo

    anos = list(range(start_year, dt.date.today().year + 1))
    lista = [c for c in CIUDADES if not ciudades_pedidas or c[0] in ciudades_pedidas]
    rprint(f"{len(lista)} ciudades, {anos[0]}-{anos[-1]}")
    for nombre, pais, lat, lon in lista:
        rprint(f"[bold]{nombre}[/bold] ({pais})")
        descargar_archivo(nombre, lat, lon, anos, CIUDADES_METEO, log=rprint)


@app.command()
def fase3_entrenar(cache: bool = True):
    """Modelos operativos: los de la fase 2 sin climatología local, la configuración validada dejando radares fuera."""
    from . import modelo as M

    ds, cols = _conjunto_fase2(cache, niveles=True)
    cols = [c for c in cols if not c.startswith("clim_")]
    paths = M.fit_final(ds, cols, ROOT / "data", prefijo="modelo_op")
    rprint(f"{len(cols)} rasgos sin climatologia local -> " + ", ".join(p.name for p in paths))


def _rasgos_ciudades(modelos, log=rprint) -> pd.DataFrame:
    """Rasgos y predicciones del archivo meteorológico de todas las ciudades con descarga hecha."""
    from . import prevision as P
    from .ciudades import CIUDADES

    partes = []
    for nombre, pais, lat, lon in CIUDADES:
        f = CIUDADES_METEO / f"{nombre}.parquet"
        if not f.exists():
            log(f"  {nombre}: sin archivo meteorológico")
            continue
        r = P.rasgos(nombre, lat, lon, pd.read_parquet(f))
        if r.empty:
            continue
        partes.append(P.predecir(r, modelos).assign(pais=pais))
        log(f"  {nombre}: {len(r)} noches")
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


@app.command()
def fase3_umbrales():
    """Corre el modelo sobre el archivo de cada ciudad y guarda los percentiles que definen los niveles de aviso."""
    from . import prevision as P

    modelos = P.cargar_modelos(ROOT / "data")
    pred = _rasgos_ciudades(modelos)
    if pred.empty:
        rprint("[red]ninguna ciudad tiene archivo meteorológico: corre antes fase3-archivo[/red]")
        raise typer.Exit(1)
    pred.to_parquet(CLIMA_CIUDADES, index=False)
    u = P.calcular_umbrales(pred)
    u.to_csv(UMBRALES_CSV, index=False, float_format="%.4f")
    rprint(u[["ciudad", "season", "noches", "alerta_q75", "alerta_q90"]].round(3).to_string(index=False))
    rprint(f"Umbrales de {u['ciudad'].nunique()} ciudades en {UMBRALES_CSV}")


@app.command()
def fase3(dias: int = 7, cache: bool = False):
    """Previsión de las próximas noches por ciudad, con el nivel de aviso propio de cada sitio."""
    from . import fase3 as F3
    from . import prevision as P
    from .ciudades import CIUDADES

    modelos = P.cargar_modelos(ROOT / "data")
    umbrales = pd.read_csv(UMBRALES_CSV)
    con_umbral = set(umbrales["ciudad"])
    bruto = ROOT / "data" / "fase3_prevision_bruta.parquet"
    if cache and bruto.exists():
        prev = pd.read_parquet(bruto)
        rprint(f"previsión reutilizada de {bruto}")
    else:
        partes = []
        for nombre, pais, lat, lon in CIUDADES:
            if nombre not in con_umbral:
                continue
            h = P.descargar_prevision(lat, lon, dias, log=rprint)
            r = P.rasgos(nombre, lat, lon, h)
            if r.empty:
                rprint(f"  {nombre}: el pronóstico no cubre ninguna noche completa")
                continue
            partes.append(P.predecir(r, modelos).assign(pais=pais))
            rprint(f"  {nombre}: {len(r)} noches previstas")
        prev = pd.concat(partes, ignore_index=True)
        prev.to_parquet(bruto, index=False)
    prev = P.aplicar_umbrales(prev, umbrales)
    prev.to_csv(PREVISION_CSV, index=False, float_format="%.4f")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figs = F3.figures(prev, umbrales, OUTPUT)
    F3.write_report(prev, umbrales, figs, OUTPUT / "fase3.html")
    aviso = prev[prev["nivel"].isin(["alto", "muy alto"])]
    rprint(f"[bold]{len(prev)} noches-ciudad previstas, {len(aviso)} con aviso alto o muy alto[/bold]")
    if not aviso.empty:
        rprint(aviso.assign(noche=aviso["night"].dt.strftime("%d/%m"))
               [["ciudad", "noche", "nivel", "p_alerta"]].round(2).to_string(index=False))
    rprint(f"Informe: {OUTPUT / 'fase3.html'}")


LUCES = ROOT / "data" / "luces"


@app.command()
def ranking(radio_km: float = 10.0):
    """Ranking de exposición: luz artificial de cada ciudad × densidad de aves prevista sobre ella."""
    from . import fase3 as F3
    from . import luces as L
    from .ciudades import CIUDADES

    tif = L.asegurar_atlas(LUCES, log=rprint)
    luz = L.muestrear(tif, CIUDADES, radio_km=radio_km, log=rprint)
    luz.to_csv(ROOT / "data" / "luces_ciudades.csv", index=False, float_format="%.3f")
    if not CLIMA_CIUDADES.exists():
        rprint("[red]falta el archivo de predicciones por ciudad: corre antes fase3-umbrales[/red]")
        raise typer.Exit(1)
    mig = L.indice_migracion(pd.read_parquet(CLIMA_CIUDADES))
    rk = L.ranking(luz, mig)
    rk.to_csv(ROOT / "data" / "ranking_exposicion.csv", index=False, float_format="%.3f")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figs = F3.figura_ranking(rk, OUTPUT)
    F3.write_ranking(rk, figs, OUTPUT / "ranking.html")
    for temporada, g in rk.groupby("season"):
        rprint(f"[bold]{temporada}[/bold]")
        rprint(g.nlargest(10, "exposicion_picos")[["ciudad", "luz_media", "vid_picos", "exposicion_picos"]]
               .round(1).to_string(index=False))
    rprint(f"Informe: {OUTPUT / 'ranking.html'}")


if __name__ == "__main__":
    app()
