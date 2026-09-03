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


def figures(ds: pd.DataFrame, met: pd.DataFrame, preds: pd.DataFrame, imp: pd.DataFrame, out_dir: Path) -> list[Path]:
    figs = []
    # 1) importancia de los rasgos en los dos modelos
    p = out_dir / "fase2_importancia.png"
    top = imp.head(15)[::-1]
    y = np.arange(len(top)); h = 0.4
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.barh(y + h / 2, top["alerta"], h, color="#2c3e50", label="modelo de alerta")
    ax.barh(y - h / 2, top["intensidad"], h, color="#95a5a6", label="modelo de intensidad")
    ax.set_yticks(y, [NOMBRE.get(k, k) for k in top.index])
    ax.set_xlabel("% de la ganancia del modelo"); ax.legend(fontsize=9)
    ax.set_title("Qué usan los modelos para anticipar la migración")
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
    axes[1].bar(x - w / 2, r["acierto"], w, color="#2c3e50", label="noches de paso fuerte capturadas por las alertas")
    axes[1].bar(x + w / 2, r["falsa_alarma"], w, color="#e67e22", label="alertas emitidas que no eran paso fuerte")
    axes[1].axhline(0.1, color="#c0392b", ls="--", lw=0.9, label="lo que capturaría el azar (10 %)")
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
            temporada = s["season"].mode().iat[0]
            # reindexar a días naturales: las noches sin dato quedan como hueco y la línea se corta
            s = (s.set_index("night").reindex(pd.date_range(s["night"].min(), s["night"].max(), freq="D"))
                 .rename_axis("night").reset_index())
            ax.plot(s["night"], s["y"] ** 3, color="#333", lw=1, label="observado (radar)")
            ax.plot(s["night"], s["pred"].clip(lower=0) ** 3, color="#e67e22", lw=1.2, label="predicho (solo meteorología, radar no visto)")
            # el umbral es por radar y temporada: hay que tomar el de la temporada que se dibuja, no el primero
            thr = ds.loc[(ds["radar"] == r) & (ds["season"] == temporada), "p90_temporada"].iloc[0]
            ax.axhline(thr, color="#c0392b", ls=":", lw=0.8, label="paso fuerte: P90 local observado")
            # noches en las que el modelo de alerta habría avisado
            corte = q[q["radar"] == r].groupby("season")["p_alerta"].quantile(0.9)
            av = s[s["p_alerta"] >= s["season"].map(corte).fillna(np.inf)]
            for x in av["night"]:
                ax.axvline(x, color="#f39c12", alpha=0.35, lw=3, zorder=0)
            ax.plot([], [], color="#f39c12", alpha=0.5, lw=3, label="noche con alerta emitida")
            ax.set_title(f"{r} · {yr}", fontsize=10); ax.set_ylabel("VID (aves/km²)")
        axes.flat[0].legend(fontsize=8, ncol=4)
        fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def write_report(ds: pd.DataFrame, met: pd.DataFrame, imp: pd.DataFrame, cols: list[str], figs: list[Path], out: Path,
                 ref: pd.DataFrame | None = None) -> None:
    con_altura = any("hPa" in c for c in cols)
    fuente = ("viento y temperatura en los niveles de presión de 925, 850 y 700 hectopascales, es decir a unos 750, "
              "1.500 y 3.000 m sobre el nivel del mar, que es donde vuelan las aves, más el viento de 10 y 100 m, "
              "temperatura, humedad, presión, precipitación y nubosidad en superficie; archivo de análisis y pronósticos "
              "operativos de Open-Meteo, disponible desde 2021") if con_altura else (
              "viento a 10 y 100 m, temperatura, humedad, presión, precipitación y nubosidad; reanálisis ERA5 vía "
              "Open-Meteo, disponible desde 1940")
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
        "Área bajo la curva mediana (radar fuera)": f"{ra['auc'].median():.2f}",
        "Noches de paso fuerte capturadas (radar fuera)": f"{ra['acierto'].mean():.0%}",
        "Alertas erróneas (radar fuera)": f"{ra['falsa_alarma'].mean():.0%}",
    }
    fmt = met.copy()
    for c in ("spearman", "r2", "r2_clim", "auc", "auc_intensidad"):
        fmt[c] = fmt[c].map("{:.2f}".format)
    for c in ("acierto", "falsa_alarma"):
        fmt[c] = fmt[c].map("{:.0%}".format)
    fmt = fmt.rename(columns={"split": "validación", "r2": "R²", "r2_clim": "R² climatología", "auc": "área bajo la curva",
                              "auc_intensidad": "área bajo la curva (intensidad)",
                              "acierto": "paso fuerte capturado", "falsa_alarma": "alertas erróneas",
                              "alertas_obs": "noches de paso fuerte", "alertas_pred": "alertas emitidas"})
    from .modelo import MIN_NOCHES_RADAR as min_noches
    n_folds = len(ra)
    imp_t = imp.reset_index().rename(columns={"index": "rasgo", "intensidad": "intensidad %", "alerta": "alerta %"})
    imp_t["rasgo"] = imp_t["rasgo"].map(lambda k: NOMBRE.get(k, k))
    for c in ("intensidad %", "alerta %"):
        imp_t[c] = imp_t[c].map("{:.1f}".format)
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Fase 2 · modelo meteorológico</title>",
        "<style>body{font:15px/1.5 system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
        "table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:3px 8px;text-align:right}"
        "th{background:#f4f4f4}td:first-child,th:first-child{text-align:left}img{max-width:100%}"
        ".k{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}"
        ".k div{background:#f7f7f7;padding:8px 12px;border-radius:6px}.k b{display:block;font-size:20px}</style>",
        "<h1>Fase 2 · ¿predice la meteorología la migración nocturna?</h1>",
        "<p>Modelo de árboles potenciados (LightGBM) que estima la <b>densidad nocturna de aves</b> (VID, aves/km²) de "
        f"cada radar a partir de la meteorología de la noche ({fuente}), el día del año, la climatología local del radar y "
        "su posición. El viento se descompone en componente a favor y componente lateral respecto al rumbo migratorio de la "
        "temporada, y se añaden los cambios de presión y temperatura en 24 h, que marcan el paso de frentes. Objetivo "
        "transformado con la raíz cúbica. Solo noches con cobertura ≥ 60 % dentro de las ventanas migratorias "
        "(15 feb-31 may, 15 ago-30 nov).</p>",
        "<p><b>Dos validaciones honestas:</b> (1) dejar fuera un año completo y predecirlo con el resto (¿funciona en un año "
        "nuevo?); (2) dejar fuera un radar completo (¿funciona en un lugar donde no se entrenó? — es el caso de los radares "
        "españoles nuevos, que tienen pocos años).</p>",
        "<p><b>Cómo se decide una alerta.</b> Se llama <i>noche de paso fuerte</i> a la que supera el percentil 90 histórico "
        "local de su temporada, es decir una noche de cada diez. Un modelo de media encoge las predicciones hacia el centro "
        "y casi nunca cruza ese valor absoluto, así que la alerta la decide un <b>segundo modelo</b>, entrenado para "
        "clasificar directamente ese suceso, y el umbral se calibra sobre la distribución de sus "
        "predicciones: se alerta en el decil superior de las noches previstas de ese radar y temporada. En operación esa "
        "distribución se obtiene corriendo el modelo sobre diez años de reanálisis en el punto de interés, sin necesidad de "
        "un radar en la ciudad. Como se emiten tantas alertas como noches de paso fuerte hay, el porcentaje capturado es "
        "directamente comparable con el 10 % que daría el azar. El área bajo la curva resume la capacidad de separar esas "
        "noches sin depender de ningún umbral (0,5 = azar).</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in resumen.items()) + "</div>",
        f"<h2>Qué usa el modelo</h2><img src='{figs[0].name}'>",
        f"<h2>Validación radar a radar</h2><img src='{figs[1].name}'>",
        f"<h2>Observado frente a predicho</h2><img src='{figs[2].name}'>",
    ]
    if len(figs) > 3:
        parts.append(f"<h2>Ejemplos: radares españoles nuevos y Oporto</h2><img src='{figs[3].name}'>")
    if ref is not None and not ref.empty:
        rr = ref[ref["split"].str.startswith("año")]
        aa = met[met["split"].str.startswith("año")]
        comp = pd.DataFrame({
            "con viento en altura de vuelo": [f"{aa['spearman'].median():.2f}", f"{aa['auc'].median():.2f}",
                                              f"{aa['acierto'].mean():.0%}"],
            "solo meteorología de superficie": [f"{rr['spearman'].median():.2f}", f"{rr['auc'].median():.2f}",
                                                f"{rr['acierto'].mean():.0%}"],
        }, index=["Spearman mediano", "área bajo la curva mediana", "paso fuerte capturado"])
        parts += [
            "<h2>¿Cuánto aporta el viento a la altura a la que vuelan?</h2>",
            "<p>Las mismas noches y los mismos pliegues por año, cambiando solo el conjunto de rasgos: con el viento en "
            "925, 850 y 700 hectopascales (unos 750, 1.500 y 3.000 m) frente a solo el de 10 y 100 m.</p>",
            comp.to_html(),
        ]
    parts += [
        "<h2>Tablas</h2><h3>Validación</h3>", fmt.to_html(index=False),
        "<h3>Importancia de los rasgos</h3>", imp_t.to_html(index=False),
        "<h2>Limitaciones</h2><ul>"
        + ("<li>El viento en la capa de vuelo procede del archivo de pronósticos operativos, que solo llega hasta 2021. "
           "Eso reduce el histórico utilizable y deja fuera los primeros años de las series francesas, que son las "
           "largas. La comparación con el modelo de superficie mide cuánto se gana a cambio.</li>" if con_altura else
           "<li>El viento en la capa de vuelo (925, 850 y 700 hectopascales) no entra en esta versión: el reanálisis "
           "ERA5 de Open-Meteo solo sirve superficie y 100 m. Con los niveles de presión el modelo debería mejorar.</li>")
        + "<li>Sin la velocidad de vol2bird no se pueden separar insectos de aves por velocidad aérea; en otoño y en el sur "
        "parte del VID es insecto. La climatología local absorbe parte del sesgo, no todo.</li>"
        f"<li>Solo los {n_folds} radares con al menos {min_noches} noches tienen validación propia; los demás aportan al "
        "entrenamiento pero no se validan por separado. Seis radares tienen menos de 20 noches en total.</li>"
        "<li>Los años con pocos radares dan R² muy negativo (el modelo acierta el orden de las noches pero no el nivel "
        "absoluto de un radar que apenas ha visto). El Spearman y el área bajo la curva son las métricas de fiar; el R² "
        "solo tiene sentido comparado con el de la climatología, en la misma columna.</li>"
        "<li>La predicción usa el análisis de la propia noche, no un pronóstico a varios días: es la cota superior de lo "
        "que se conseguirá en operación.</li></ul>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
