"""Fase 2: informe del modelo meteorológico (output/fase2.html)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

NOMBRE = {
    "tail_100m": "viento a favor 100 m", "tail_10m": "viento a favor 10 m", "tail0_100m": "viento a favor al inicio 100 m",
    "tail0_10m": "viento a favor al inicio 10 m", "cross_100m": "viento lateral 100 m", "cross_10m": "viento lateral 10 m",
    "ws_100m": "velocidad viento 100 m", "ws_10m": "velocidad viento 10 m", "t2m": "temperatura 2 m", "rh2m": "humedad relativa",
    "pmsl": "presión al nivel del mar", "precip": "precipitación acumulada", "precip_h": "fracción horas con lluvia",
    "cloud": "nubosidad", "dp24": "cambio presión 24 h", "dt24": "cambio temperatura 24 h", "doy_sin": "día del año (sen)",
    "doy_cos": "día del año (cos)", "clim_p50": "climatología local P50", "clim_p90": "climatología local P90",
    "lat": "latitud", "lon": "longitud",
}
PAIS = {"es": "España", "pt": "Portugal", "fr": "Francia"}
COLOR = {"es": "#c0392b", "pt": "#27ae60", "fr": "#2980b9"}


def figures(ds: pd.DataFrame, met: pd.DataFrame, preds: pd.DataFrame, imp: pd.Series, out_dir: Path) -> list[Path]:
    figs = []
    # 1) importancia de los rasgos
    p = out_dir / "fase2_importancia.png"
    top = (imp / imp.sum() * 100).head(15)[::-1]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh([NOMBRE.get(k, k) for k in top.index], top.values, color="#555")
    ax.set_xlabel("% de la ganancia del modelo"); ax.set_title("Qué usa el modelo para predecir el VID nocturno")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 2) validación radar a radar (cada radar predicho por un modelo que no lo vio)
    p = out_dir / "fase2_radares.png"
    r = met[met["split"].str.startswith("radar")].copy()
    r["radar"] = r["split"].str.split().str[1]
    r = r.sort_values("spearman", ascending=False)
    col = [COLOR.get(x[:2], "#888") for x in r["radar"]]
    fig, axes = plt.subplots(2, 1, figsize=(max(8, 0.32 * len(r)), 6.5), sharex=True)
    axes[0].bar(r["radar"], r["spearman"], color=col); axes[0].set_ylabel("Spearman obs-pred"); axes[0].set_ylim(0, 1)
    axes[0].axhline(r["spearman"].median(), color="k", ls="--", lw=0.8)
    axes[0].set_title("Validación dejando fuera cada radar (rojo España, verde Portugal, azul Francia)")
    w = 0.4; x = np.arange(len(r))
    axes[1].bar(x - w / 2, r["acierto"], w, color="#2c3e50", label="aciertos en noches ≥ P90 observadas")
    axes[1].bar(x + w / 2, r["falsa_alarma"], w, color="#e67e22", label="falsas alarmas entre las alertas emitidas")
    axes[1].set_xticks(x, r["radar"], rotation=90); axes[1].set_ylim(0, 1); axes[1].legend(loc="upper right", fontsize=8)
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 3) dispersión observado-predicho fuera de muestra (por radar)
    p = out_dir / "fase2_dispersion.png"
    q = preds[preds["split"] == "radar"]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    hb = ax.hexbin(q["pred"], q["y"], gridsize=45, bins="log", cmap="Greys", mincnt=1)
    lim = [0, max(q["y"].quantile(0.999), q["pred"].quantile(0.999))]
    ax.plot(lim, lim, color="#c0392b", lw=1); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("predicho (raíz cúbica del VID)"); ax.set_ylabel("observado (raíz cúbica del VID)")
    ax.set_title(f"Radares no vistos en el entrenamiento (n={len(q):,})"); fig.colorbar(hb, label="noches")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 4) series de ejemplo: radares españoles nuevos y Oporto, última primavera con datos
    p = out_dir / "fase2_series.png"
    ej = [r for r in ("estjv", "esgld", "essft", "ptprt") if r in set(q["radar"])]
    if ej:
        fig, axes = plt.subplots(len(ej), 1, figsize=(10, 2.4 * len(ej)), squeeze=False)
        for ax, r in zip(axes.flat, ej):
            s = q[q["radar"] == r].sort_values("night")
            yr = s["night"].dt.year.max()
            s = s[(s["night"].dt.year == yr) & (s["night"].dt.month.between(2, 5))]
            if s.empty:
                s = q[q["radar"] == r].sort_values("night"); s = s[s["night"].dt.year == yr]
            ax.plot(s["night"], s["y"] ** 3, color="#333", lw=1, label="observado (radar)")
            ax.plot(s["night"], s["pred"].clip(lower=0) ** 3, color="#e67e22", lw=1.2, label="predicho (solo meteorología)")
            thr = ds.loc[ds["radar"] == r, "p90_temporada"].iloc[0]
            ax.axhline(thr, color="#c0392b", ls=":", lw=0.8, label="P90 local (alerta alta)")
            ax.set_title(f"{r} · {yr}", fontsize=10); ax.set_ylabel("VID (aves/km²)")
        axes.flat[0].legend(fontsize=8, ncol=3)
        fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def write_report(ds: pd.DataFrame, met: pd.DataFrame, imp: pd.Series, cols: list[str], figs: list[Path], out: Path) -> None:
    an = met[met["split"].str.startswith("año")]
    ra = met[met["split"].str.startswith("radar")].copy()
    ra["pais"] = ra["split"].str.split().str[1].str[:2].map(PAIS)
    es = ra[ra["pais"] == "España"]
    resumen = {
        "radar-noches": f"{len(ds):,}", "radares": ds["radar"].nunique(),
        "años": f"{ds['year'].min()}-{ds['year'].max()}", "rasgos": len(cols),
        "Spearman mediano (año fuera)": f"{an['spearman'].median():.2f}",
        "R² mediano (año fuera) / solo climatología": f"{an['r2'].median():.2f} / {an['r2_clim'].median():.2f}",
        "Spearman mediano (radar fuera)": f"{ra['spearman'].median():.2f}",
        "Spearman mediano radares españoles (fuera)": f"{es['spearman'].median():.2f}" if len(es) else "—",
        "Aciertos noches ≥ P90 (radar fuera, media)": f"{ra['acierto'].mean():.0%}",
        "Falsas alarmas (radar fuera, media)": f"{ra['falsa_alarma'].mean():.0%}",
    }
    fmt = met.copy()
    for c in ("spearman", "r2", "r2_clim"):
        fmt[c] = fmt[c].map("{:.2f}".format)
    for c in ("acierto", "falsa_alarma"):
        fmt[c] = fmt[c].map("{:.0%}".format)
    fmt = fmt.rename(columns={"split": "validación", "r2": "R²", "r2_clim": "R² climatología", "acierto": "aciertos P90",
                              "falsa_alarma": "falsas alarmas", "alertas_obs": "noches ≥ P90", "alertas_pred": "alertas emitidas"})
    imp_t = (imp / imp.sum() * 100).rename("ganancia %").reset_index().rename(columns={"index": "rasgo"})
    imp_t["rasgo"] = imp_t["rasgo"].map(lambda k: NOMBRE.get(k, k)); imp_t["ganancia %"] = imp_t["ganancia %"].map("{:.1f}".format)
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Fase 2 · modelo meteorológico</title>",
        "<style>body{font:15px/1.5 system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
        "table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:3px 8px;text-align:right}"
        "th{background:#f4f4f4}td:first-child,th:first-child{text-align:left}img{max-width:100%}"
        ".k{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}"
        ".k div{background:#f7f7f7;padding:8px 12px;border-radius:6px}.k b{display:block;font-size:20px}</style>",
        "<h1>Fase 2 · ¿predice la meteorología la migración nocturna?</h1>",
        "<p>Modelo de árboles potenciados (LightGBM) que estima la <b>densidad nocturna de aves</b> (VID, aves/km²) de "
        "cada radar a partir de la meteorología de la noche (reanálisis ERA5 vía Open-Meteo: viento a 10 y 100 m "
        "descompuesto en componente a favor y lateral respecto al rumbo migratorio, temperatura, humedad, presión y sus "
        "cambios en 24 h, precipitación y nubosidad), el día del año y la climatología local. Objetivo transformado con "
        "la raíz cúbica. Solo noches con cobertura ≥ 60 % dentro de las ventanas migratorias (15 feb-31 may, 15 ago-30 nov).</p>",
        "<p><b>Dos validaciones honestas:</b> (1) dejar fuera un año completo y predecirlo con el resto (¿funciona en un año "
        "nuevo?); (2) dejar fuera un radar completo (¿funciona en un lugar donde no se entrenó? — es el caso de los radares "
        "españoles nuevos, que tienen pocos años). Una alerta se considera acertada cuando la predicción supera el P90 "
        "histórico local de la temporada y la observación también.</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in resumen.items()) + "</div>",
        f"<h2>Qué usa el modelo</h2><img src='{figs[0].name}'>",
        f"<h2>Validación radar a radar</h2><img src='{figs[1].name}'>",
        f"<h2>Observado frente a predicho</h2><img src='{figs[2].name}'>",
    ]
    if len(figs) > 3:
        parts.append(f"<h2>Ejemplos: radares españoles nuevos y Oporto</h2><img src='{figs[3].name}'>")
    parts += [
        "<h2>Tablas</h2><h3>Validación</h3>", fmt.to_html(index=False),
        "<h3>Importancia de los rasgos</h3>", imp_t.to_html(index=False),
        "<h2>Limitaciones</h2><ul>"
        "<li>Open-Meteo no sirve los niveles de presión (925/850/700 hPa) en su archivo; el viento en la capa de vuelo se "
        "aproxima con el de 100 m. El modelo definitivo debe usar ERA5 completo (Copernicus CDS).</li>"
        "<li>Sin la velocidad de vol2bird no se pueden separar insectos de aves por velocidad aérea; en otoño y en el sur "
        "parte del VID es insecto. La climatología local absorbe parte del sesgo, no todo.</li>"
        "<li>La predicción usa el reanálisis de la propia noche, no un pronóstico: es la cota superior de lo que se "
        "conseguirá en operación con pronósticos a 24-72 h.</li></ul>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
