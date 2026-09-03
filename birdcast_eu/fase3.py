"""Fase 3: informes de la previsión por ciudad y del ranking de exposición a la luz."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .informe import incrustar_imagenes

COLOR_NIVEL = {"bajo": "#e8eaed", "moderado": "#ffd98e", "alto": "#f08c1e", "muy alto": "#b32d1f",
               "sin umbral": "#ffffff"}
ORDEN_NIVEL = ["bajo", "moderado", "alto", "muy alto"]
PAIS = {"ES": "España", "PT": "Portugal", "FR": "Francia"}
ESTILO = ("<style>body{font:15px/1.55 system-ui;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}"
          "table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ddd;padding:3px 8px;text-align:right}"
          "th{background:#f4f4f4}td:first-child,th:first-child{text-align:left}img{max-width:100%}"
          ".k{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin:1em 0}"
          ".k div{background:#f7f7f7;padding:8px 12px;border-radius:6px}.k b{display:block;font-size:20px}"
          ".n{display:inline-block;padding:1px 7px;border-radius:4px;font-size:12px}</style>")


def _orden_ciudades(prev: pd.DataFrame) -> list[str]:
    """Ciudades de más a menos aviso, para que el calendario se lea de arriba abajo."""
    peso = {n: i for i, n in enumerate(ORDEN_NIVEL)}
    s = prev.assign(w=prev["nivel"].map(peso).fillna(0)).groupby("ciudad")["w"].mean()
    return list(s.sort_values(ascending=False).index)


def figures(prev: pd.DataFrame, umbrales: pd.DataFrame, out_dir: Path) -> list[Path]:
    figs = []
    ciudades = _orden_ciudades(prev)
    noches = sorted(prev["night"].unique())

    # 1) calendario de avisos: una fila por ciudad, una columna por noche
    p = out_dir / "fase3_calendario.png"
    m = np.full((len(ciudades), len(noches)), -1)
    for i, c in enumerate(ciudades):
        g = prev[prev["ciudad"] == c].set_index("night")
        for j, n in enumerate(noches):
            if n in g.index:
                m[i, j] = ORDEN_NIVEL.index(g.loc[n, "nivel"]) if g.loc[n, "nivel"] in ORDEN_NIVEL else -1
    from matplotlib.colors import BoundaryNorm, ListedColormap
    cmap = ListedColormap(["#ffffff"] + [COLOR_NIVEL[n] for n in ORDEN_NIVEL])
    fig, ax = plt.subplots(figsize=(1.1 * len(noches) + 3.5, 0.34 * len(ciudades) + 1.6))
    ax.pcolormesh(m, cmap=cmap, norm=BoundaryNorm(range(-1, 5), cmap.N), edgecolors="w", linewidth=1.2)
    ax.set_yticks(np.arange(len(ciudades)) + 0.5, ciudades, fontsize=9)
    ax.set_xticks(np.arange(len(noches)) + 0.5, [pd.Timestamp(n).strftime("%a %d/%m") for n in noches], fontsize=9)
    ax.invert_yaxis(); ax.set_title("Aviso por ciudad y noche (nivel relativo al historial de cada ciudad)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=COLOR_NIVEL[n], edgecolor="#bbb", label=n) for n in ORDEN_NIVEL],
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(p, dpi=130, bbox_inches="tight"); plt.close(fig); figs.append(p)

    # 2) intensidad prevista noche a noche en las ciudades con más aviso, con sus propios umbrales
    p = out_dir / "fase3_series.png"
    ej = ciudades[:6]
    fig, axes = plt.subplots(len(ej), 1, figsize=(9, 1.7 * len(ej)), squeeze=False, sharex=True)
    u = umbrales.set_index(["ciudad", "season"])
    for ax, c in zip(axes.flat, ej):
        g = prev[prev["ciudad"] == c].sort_values("night")
        ax.plot(g["night"], g["pred"].clip(lower=0) ** 3, color="#333", marker="o", ms=4, lw=1.4)
        clave = (c, g["season"].mode().iat[0])
        if clave in u.index:
            for q, col, txt in ((75, "#f08c1e", "alto"), (90, "#b32d1f", "muy alto")):
                ax.axhline(max(u.loc[clave, f"pred_q{q}"], 0) ** 3, color=col, ls=":", lw=1, label=txt)
            ax.legend(fontsize=7, loc="upper right", ncol=2)
        ax.set_ylabel("aves/km²", fontsize=8); ax.set_title(c, fontsize=10, loc="left")
        ax.tick_params(labelsize=8)
    fig.autofmt_xdate()
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)

    # 3) mapa sencillo: cada ciudad en su posición, coloreada por el aviso más alto de los próximos días
    p = out_dir / "fase3_mapa.png"
    peor = (prev.assign(w=prev["nivel"].map({n: i for i, n in enumerate(ORDEN_NIVEL)}).fillna(0))
            .sort_values("w").groupby("ciudad").last().reset_index())
    fig, ax = plt.subplots(figsize=(7, 6.4))
    ax.scatter(peor["lon"], peor["lat"], s=170, c=[COLOR_NIVEL.get(n, "#eee") for n in peor["nivel"]],
               edgecolors="#555", linewidths=0.8, zorder=3)
    for r in peor.itertuples(index=False):
        ax.annotate(r.ciudad, (r.lon, r.lat), fontsize=7.5, xytext=(0, 9), textcoords="offset points", ha="center")
    ax.set_xlabel("longitud"); ax.set_ylabel("latitud"); ax.grid(alpha=0.25)
    ax.set_title("Aviso máximo previsto en el periodo")
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig); figs.append(p)
    return figs


def _tabla_prevision(prev: pd.DataFrame) -> str:
    t = prev.copy()
    t["noche"] = t["night"].dt.strftime("%a %d/%m")
    t["aves/km² previstas"] = (t["pred"].clip(lower=0) ** 3).map("{:.0f}".format)
    t["probabilidad de paso fuerte"] = t["p_alerta"].map("{:.2f}".format)
    t["aviso"] = [f"<span class='n' style='background:{COLOR_NIVEL.get(n, '#eee')}'>{n}</span>" for n in t["nivel"]]
    t["país"] = t["pais"].map(PAIS).fillna(t["pais"])
    cols = ["ciudad", "país", "noche", "aves/km² previstas", "probabilidad de paso fuerte", "aviso"]
    return t[cols].to_html(index=False, escape=False)


def write_report(prev: pd.DataFrame, umbrales: pd.DataFrame, figs: list[Path], out: Path) -> None:
    noches = sorted(prev["night"].unique())
    aviso = prev[prev["nivel"].isin(["alto", "muy alto"])]
    resumen = {
        "ciudades": prev["ciudad"].nunique(),
        "noches previstas": len(noches),
        "primera noche": pd.Timestamp(noches[0]).strftime("%d/%m/%Y"),
        "última noche": pd.Timestamp(noches[-1]).strftime("%d/%m/%Y"),
        "avisos altos o muy altos": len(aviso),
        "ciudades con algún aviso": aviso["ciudad"].nunique(),
    }
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Fase 3 · previsión por ciudad</title>", ESTILO,
        "<h1>Fase 3 · previsión de migración nocturna por ciudad</h1>",
        "<p>Previsión de la <b>densidad de aves en vuelo nocturno</b> sobre cada ciudad para las próximas noches, "
        "hecha solo con el pronóstico meteorológico: no hay radar en ninguna de estas ciudades. Los dos modelos son "
        "los de la fase 2 reentrenados <b>sin la climatología local</b>, que es la configuración que se validó "
        "dejando radares enteros fuera del entrenamiento: en ese escenario capturaban un 34 % de las noches de paso "
        "fuerte frente al 10 % que daría el azar, con un área bajo la curva mediana de 0,77.</p>",
        "<p><b>Qué significa el nivel de aviso.</b> El modelo da un número continuo, y lo que es mucho en Sevilla no "
        "es lo mismo que en Bilbao. Para cada ciudad se ha corrido el modelo sobre el archivo meteorológico de 2021 "
        "en adelante en sus propias coordenadas, y los niveles se cortan por los percentiles de <i>su</i> "
        "distribución: <b>moderado</b> por encima de la mediana, <b>alto</b> por encima del percentil 75 y "
        "<b>muy alto</b> por encima del percentil 90, es decir la noche más intensa de cada diez. Así el aviso "
        "significa lo mismo en todas partes: «hoy pasa mucho más de lo normal aquí».</p>",
        "<div class='k'>" + "".join(f"<div>{k}<b>{v}</b></div>" for k, v in resumen.items()) + "</div>",
    ]
    for f in figs:
        parts.append(f"<p><img src='{f.name}'></p>")
    parts += [
        "<h2>Noches con aviso alto o muy alto</h2>",
        _tabla_prevision(aviso.sort_values(["night", "ciudad"])) if len(aviso) else
        "<p>Ninguna ciudad supera el percentil 75 de su propio historial en este periodo.</p>",
        "<h2>Previsión completa</h2>", _tabla_prevision(prev.sort_values(["ciudad", "night"])),
        "<h2>Umbrales de cada ciudad</h2>",
        "<p>Calculados sobre las predicciones del archivo meteorológico 2021-hoy en el punto de cada ciudad. "
        "«aves/km²» son los cortes del modelo de intensidad; la probabilidad es el corte del clasificador de paso "
        "fuerte, que es el que decide el aviso.</p>",
        (umbrales.assign(**{"aves/km² alto": (umbrales["pred_q75"].clip(lower=0) ** 3).map("{:.0f}".format),
                            "aves/km² muy alto": (umbrales["pred_q90"].clip(lower=0) ** 3).map("{:.0f}".format),
                            "prob. alto": umbrales["alerta_q75"].map("{:.2f}".format),
                            "prob. muy alto": umbrales["alerta_q90"].map("{:.2f}".format)})
         .rename(columns={"season": "temporada"})
         [["ciudad", "temporada", "noches", "aves/km² alto", "aves/km² muy alto", "prob. alto", "prob. muy alto"]]
         .to_html(index=False)),
        "<h2>Limitaciones</h2><ul>"
        "<li>El pronóstico se degrada con los días: la primera noche va con el análisis casi cerrado y la séptima "
        "con un pronóstico a seis días. El modelo se entrenó sobre análisis y pronósticos a corto plazo, así que "
        "las noches lejanas son peores de lo que sugieren las cifras de validación.</li>"
        "<li>Ninguna de estas ciudades tiene radar dentro del alcance útil, así que <b>no hay nada con lo que "
        "comparar la previsión el día siguiente</b>. La validación de la fase 2 es la única garantía, y se hizo "
        "justamente dejando fuera radares enteros para imitar esta situación.</li>"
        "<li>La densidad prevista es la del volumen de aire sobre la ciudad, no el número de aves que se acercan a "
        "las luces. Falta la pieza de exposición, que es el ranking de luz artificial.</li>"
        "<li>Sin la velocidad de vuelo del procesador de radar, parte de la densidad de otoño en el sur puede ser "
        "insecto y no ave. Es la misma limitación de la fase 2.</li></ul>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    incrustar_imagenes(out)


# ---------------------------------------------------------------- ranking de exposición a la luz

def figura_ranking(rk: pd.DataFrame, out_dir: Path) -> list[Path]:
    p = out_dir / "ranking_exposicion.png"
    temporadas = list(rk["season"].unique())
    fig, axes = plt.subplots(1, len(temporadas), figsize=(6.2 * len(temporadas), 6.4), squeeze=False)
    col = {"ES": "#c0392b", "PT": "#27ae60", "FR": "#2980b9"}
    for ax, t in zip(axes.flat, temporadas):
        g = rk[rk["season"] == t].nlargest(20, "exposicion_picos")[::-1]
        ax.barh(g["ciudad"], g["exposicion_picos"], color=[col.get(p_, "#888") for p_ in g["pais"]])
        ax.set_xlabel("índice de exposición (100 = máximo)"); ax.set_title(f"{t}", fontsize=11)
        ax.tick_params(labelsize=9)
    fig.suptitle("Exposición del paso nocturno a la luz artificial: luz de la ciudad × aves previstas en las noches punta",
                 fontsize=11)
    fig.tight_layout(); fig.savefig(p, dpi=130); plt.close(fig)

    p2 = out_dir / "ranking_dispersion.png"
    fig, ax = plt.subplots(figsize=(7, 6))
    g = rk[rk["season"] == temporadas[0]]
    ax.scatter(g["luz_media"], g["vid_picos"], s=60, c=[col.get(p_, "#888") for p_ in g["pais"]], edgecolors="#444")
    for r in g.itertuples(index=False):
        ax.annotate(r.ciudad, (r.luz_media, r.vid_picos), fontsize=7.5, xytext=(0, 7),
                    textcoords="offset points", ha="center")
    ax.set_xscale("log"); ax.set_xlabel("brillo artificial del cielo (mcd/m², escala logarítmica)")
    ax.set_ylabel("aves/km² previstas en las diez noches más intensas")
    ax.set_title(f"Las dos piezas del riesgo ({temporadas[0]})"); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(p2, dpi=130); plt.close(fig)
    return [p, p2]


def write_ranking(rk: pd.DataFrame, figs: list[Path], out: Path) -> None:
    from .luces import BRILLO_NATURAL, RADIO_KM

    t = rk.copy()
    t["país"] = t["pais"].map(PAIS).fillna(t["pais"])
    t["brillo artificial (mcd/m²)"] = t["luz_media"].map("{:.2f}".format)
    t["veces el cielo natural"] = t["veces_natural"].map("{:.0f}".format)
    t["aves/km² en noches punta"] = t["vid_picos"].map("{:.0f}".format)
    t["aves/km² medias"] = t["vid_medio"].map("{:.0f}".format)
    t["exposición (picos)"] = t["exposicion_picos"].map("{:.1f}".format)
    t["exposición (media)"] = t["exposicion_media"].map("{:.1f}".format)
    cols = ["ciudad", "país", "season", "brillo artificial (mcd/m²)", "veces el cielo natural",
            "aves/km² medias", "aves/km² en noches punta", "exposición (media)", "exposición (picos)"]
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Ranking de exposición a la luz</title>", ESTILO,
        "<h1>Ranking de exposición: dónde coinciden muchas aves y mucha luz</h1>",
        "<p>Un aviso de «luces fuera» solo sirve donde pasan muchas aves <i>y</i> hay mucha luz encendida. Este "
        "ranking multiplica las dos cosas, siguiendo el método con el que Horton y col. (2019) ordenaron las "
        "ciudades de Estados Unidos.</p>",
        "<p><b>La luz</b> es el componente artificial del brillo del cielo nocturno en el cenit según el Nuevo Atlas "
        f"Mundial (Falchi y col., 2016), promediado en un disco de {RADIO_KM:.0f} km alrededor del centro urbano. "
        f"El cielo natural está en {BRILLO_NATURAL} mcd/m²: la columna «veces el cielo natural» dice cuántas veces "
        "más brillante es el cielo de esa ciudad que uno sin luz artificial.</p>",
        "<p><b>Las aves</b> salen del modelo de la fase 3 corrido sobre el archivo meteorológico de 2021 en adelante "
        "en las coordenadas de cada ciudad: la densidad media de la temporada y la media de sus diez noches más "
        "intensas, que es cuando el aviso importa. El índice se normaliza a 100 en la ciudad más expuesta.</p>",
    ]
    for f in figs:
        parts.append(f"<p><img src='{f.name}'></p>")
    for temporada in t["season"].unique():
        g = t[t["season"] == temporada].sort_values("exposicion_picos", ascending=False)
        parts += [f"<h2>{temporada.capitalize()}</h2>", g[cols].rename(columns={"season": "temporada"}).to_html(index=False)]
    parts += [
        "<h2>Cómo leerlo y qué no es</h2><ul>"
        "<li>El atlas mide el brillo del cielo <b>visto desde el suelo</b>, que incluye la luz dispersada por la "
        "atmósfera y la que llega de poblaciones vecinas. Lo que interpela a un ave que vuela a mil metros es la "
        "radiancia que la ciudad emite <b>hacia arriba</b>, que miden los satélites VIIRS. Para ordenar ciudades "
        "las dos medidas van casi de la mano, pero no son la misma magnitud.</li>"
        "<li>Los datos de luz son de <b>2015</b>. En diez años el cambio a iluminación de diodos ha subido el "
        "componente azul, al que las aves son más sensibles, y ha cambiado la intensidad en muchas ciudades.</li>"
        "<li>El disco de 10 km es una regla igual para todas, no el término municipal: en un área metropolitana "
        "grande recorta y en una ciudad pequeña incluye campo oscuro.</li>"
        "<li>Las densidades previstas están <b>comprimidas en la cola</b>: el modelo de intensidad es una regresión "
        "de media, así que sus noches punta se quedan cortas frente a las observadas por radar (predicho: percentil 99 "
        "de unas 8 aves/km²; observado en los radares: unas 30). Para <i>ordenar</i> ciudades da igual, porque el sesgo "
        "es el mismo en todas, pero no hay que leer las cifras como densidades absolutas.</li>"
        "<li><b>La luz manda en el orden.</b> Entre la ciudad más y la menos iluminada del piloto hay un factor 3-4, "
        "mientras que en aves previstas apenas hay un factor 2. El ranking está diciendo sobre todo dónde hay más luz "
        "encendida, matizado por el paso; no son dos factores de peso parecido.</li>"
        "<li>El índice no es una medida de mortalidad. Dice dónde coinciden el paso y la luz, que es la condición "
        "necesaria; lo que ocurre depende además de la altura de vuelo, la niebla, el tipo de luminaria y la "
        "presencia de edificios altos acristalados.</li>"
        "<li>La licencia del atlas <b>prohíbe redistribuir los ficheros</b>. Este informe publica resultados "
        "derivados citando las dos referencias obligatorias; el raster no se sube a ningún sitio. Para una versión "
        "pública conviene sustituirlo por la radiancia VIIRS, que es de dominio público y anual.</li></ul>",
        "<h2>Citas</h2><p>Falchi F. y col. (2016). <i>The new world atlas of artificial night sky brightness</i>. "
        "Science Advances 2(6):e1600377. — Falchi F. y col. (2016). <i>Supplement to: The New World Atlas of "
        "Artificial Night Sky Brightness</i>. GFZ Data Services, doi:10.5880/GFZ.1.4.2016.001. — Horton K. G. y col. "
        "(2019). <i>Bright lights in the big cities: migratory birds' exposure to artificial light</i>. Frontiers in "
        "Ecology and the Environment 17(4):209-214.</p>",
    ]
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    incrustar_imagenes(out)
