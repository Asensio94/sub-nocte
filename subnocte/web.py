"""Web pública de Sub Nocte: una página estática generada desde los datos, servida por GitHub Pages.

No hay servidor ni base de datos. La rutina diaria vuelve a correr la previsión, regenera `index.html` y hace
un commit; Pages publica la raíz del repositorio. Todo lo que la página afirma sale de ficheros versionados, así
que cualquiera puede rehacerlo.

La página tiene una regla de honestidad: **el nivel de aviso es relativo a cada ciudad**, no una cifra absoluta
de aves, y eso se dice en el propio sitio donde se muestra el aviso, no en una nota al pie.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

COLOR = {"bajo": "#e9edf2", "moderado": "#ffd98e", "alto": "#f08c1e", "muy alto": "#b32d1f",
         "sin umbral": "#f6f6f6"}
TEXTO = {"muy alto": "#fff", "alto": "#3a2100"}
PAIS = {"ES": "España", "PT": "Portugal", "FR": "Francia"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

CSS = """
:root{--tinta:#1b1f24;--suave:#5b646e;--linea:#dde3ea;--fondo:#fff;--caja:#f7f9fb;--acento:#1d4e6f}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;color:var(--tinta);background:var(--fondo)}
.env{max-width:900px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(180deg,#0d1b26,#16303f);color:#eaf1f6;padding:44px 0 34px}
header h1{margin:0;font-size:44px;letter-spacing:-.5px;font-weight:600}
header .verso{margin:6px 0 0;font-style:italic;color:#9fb6c6;font-size:15px}
header p.claim{margin:16px 0 0;font-size:18px;color:#cddbe5;max-width:640px}
.aviso-beta{background:#fff6e0;border:1px solid #f0d79a;border-radius:8px;padding:12px 16px;margin:22px 0;font-size:14.5px}
h2{margin:38px 0 6px;font-size:24px;letter-spacing:-.2px}
h2+p.sub{margin:0 0 16px;color:var(--suave);font-size:15px}
h3{margin:26px 0 8px;font-size:18px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--linea);padding:6px 8px;text-align:right}
th{color:var(--suave);font-weight:600;text-align:right}
td:first-child,th:first-child{text-align:left}
.cal{overflow-x:auto;margin:8px 0 6px}
.cal table{width:auto;min-width:100%}
.cal td.n{text-align:center;font-size:12px;white-space:nowrap;border:2px solid #fff;border-radius:4px}
.cal th{font-size:12px;text-align:center;line-height:1.25}
.leyenda{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--suave);margin:6px 0 0}
.leyenda span i{display:inline-block;width:13px;height:13px;border-radius:3px;vertical-align:-2px;margin-right:5px}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
.tarjetas div{background:var(--caja);border:1px solid var(--linea);border-radius:8px;padding:14px 16px}
.tarjetas b{display:block;font-size:15px;margin-bottom:4px}
.tarjetas p{margin:0;font-size:14px;color:var(--suave)}
ul{padding-left:20px}li{margin:5px 0}
a{color:var(--acento)}
footer{margin:56px 0 0;padding:26px 0 40px;border-top:1px solid var(--linea);color:var(--suave);font-size:13.5px}
.pill{display:inline-block;background:var(--caja);border:1px solid var(--linea);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--suave)}
@media (max-width:620px){header h1{font-size:34px}h2{font-size:21px}}
"""


def _fecha(d: dt.date) -> str:
    return f"{d.day} de {['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'][d.month - 1]} de {d.year}"


def _celda(nivel: str) -> str:
    return (f"<td class='n' style='background:{COLOR.get(nivel, '#f6f6f6')};"
            f"color:{TEXTO.get(nivel, '#3a3f45')}'>{nivel}</td>")


def calendario(prev: pd.DataFrame) -> str:
    """Tabla ciudad × noche con el nivel de aviso, ordenada por ciudades con más aviso arriba."""
    peso = {"bajo": 0, "moderado": 1, "alto": 2, "muy alto": 3}
    prev = prev.copy()
    prev["w"] = prev["nivel"].map(peso).fillna(0)
    orden = prev.groupby("ciudad")["w"].max().sort_values(ascending=False).index
    noches = sorted(prev["night"].unique())
    cab = "".join(f"<th>{DIAS[pd.Timestamp(n).weekday()]}<br>{pd.Timestamp(n).day} {MESES[pd.Timestamp(n).month - 1]}</th>"
                  for n in noches)
    filas = []
    for c in orden:
        g = prev[prev["ciudad"] == c].set_index("night")
        pais = PAIS.get(g["pais"].iat[0], g["pais"].iat[0])
        celdas = "".join(_celda(g.loc[n, "nivel"]) if n in g.index else "<td class='n'></td>" for n in noches)
        filas.append(f"<tr><td><b>{c}</b> <span class='pill'>{pais}</span></td>{celdas}</tr>")
    leyenda = "".join(f"<span><i style='background:{COLOR[n]}'></i>{n}</span>"
                      for n in ("bajo", "moderado", "alto", "muy alto"))
    return (f"<div class='cal'><table><tr><th>ciudad</th>{cab}</tr>{''.join(filas)}</table></div>"
            f"<div class='leyenda'>{leyenda}</div>")


def tabla_ranking(rk: pd.DataFrame, temporada: str, n: int = 12) -> str:
    g = rk[rk["season"] == temporada].nlargest(n, "exposicion_picos")
    filas = "".join(
        f"<tr><td>{i}. <b>{r.ciudad}</b> <span class='pill'>{PAIS.get(r.pais, r.pais)}</span></td>"
        f"<td>{r.veces_natural:.0f}×</td><td>{r.vid_picos:.0f}</td><td>{r.exposicion_picos:.0f}</td></tr>"
        for i, r in enumerate(g.itertuples(index=False), 1))
    return ("<table><tr><th>ciudad</th><th>cielo vs natural</th><th>aves/km² en noches punta</th>"
            f"<th>exposición</th></tr>{filas}</table>")


def construir(prev: pd.DataFrame | None, rk: pd.DataFrame | None, informes: list[Path], out_dir: Path,
              log=print) -> Path:
    """Escribe `out_dir/index.html`. Pages sirve la raíz del repositorio, así que los informes se enlazan
    donde ya están (`output/`) en lugar de duplicarlos."""
    out_dir.mkdir(parents=True, exist_ok=True)
    enlaces = [f.relative_to(out_dir).as_posix() for f in informes if f.exists()]
    (out_dir / ".nojekyll").touch()  # que Pages sirva los ficheros tal cual, sin pasarlos por Jekyll
    hoy = dt.datetime.now(dt.timezone.utc).date()

    p = ["<!doctype html><html lang='es'><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width,initial-scale=1'>",
         "<title>Sub Nocte · migración nocturna de aves en Europa</title>",
         "<meta name='description' content='Previsión por ciudad de la intensidad de migración nocturna de aves "
         "en Europa, con avisos de luces fuera, sobre los perfiles de radar abiertos de Aloft.'>",
         f"<style>{CSS}</style>",
         "<header><div class='env'><h1>Sub Nocte</h1>",
         "<p class='verso'>ibant obscuri sola sub nocte per umbram — Virgilio, <i>Eneida</i> VI</p>",
         "<p class='claim'>Cada noche de primavera y de otoño, millones de aves cruzan Europa en la oscuridad. "
         "Unas pocas noches concentran la mitad del paso. Esta página intenta decir <b>cuáles</b>, ciudad por "
         "ciudad, para que se puedan apagar las luces justo esas noches.</p></div></header>",
         "<div class='env'>",
         "<div class='aviso-beta'><b>Versión técnica, no un servicio en producción.</b> El modelo está validado "
         "(ver más abajo) pero ninguna de estas ciudades tiene un radar cerca con el que comprobar la previsión al "
         "día siguiente. Úsese como indicación, no como dato cerrado.</div>"]

    if prev is not None and not prev.empty:
        # la descarga arranca el día anterior para poder calcular tendencias de 24 h: esa noche ya ha pasado
        prev = prev[pd.to_datetime(prev["night"]).dt.date >= hoy]
    if prev is not None and not prev.empty:
        noches = sorted(prev["night"].unique())
        alto = prev[prev["nivel"].isin(["alto", "muy alto"])]
        p += [f"<h2>Próximas noches</h2><p class='sub'>Actualizado el {_fecha(hoy)}. "
              f"{len(noches)} noches, {prev['ciudad'].nunique()} ciudades.</p>",
              "<p><b>El nivel es relativo a cada ciudad</b>, no una cantidad absoluta de aves: «muy alto» significa "
              "que esa noche entra en el 10 % más intenso del historial <i>de esa misma ciudad</i>. Así el aviso "
              "quiere decir lo mismo en Sevilla y en Bilbao, aunque por Sevilla pase mucha más ave.</p>",
              "<p class='sub'>En pleno pico de la temporada es normal que muchas ciudades salgan altas a la vez: "
              "el percentil se mide sobre la temporada entera, que incluye sus semanas flojas.</p>",
              calendario(prev)]
        if not alto.empty:
            lista = ", ".join(f"{r.ciudad} ({DIAS[pd.Timestamp(r.night).weekday()]} "
                              f"{pd.Timestamp(r.night).day} {MESES[pd.Timestamp(r.night).month - 1]})"
                              for r in alto.sort_values("night").itertuples(index=False))
            p.append(f"<p><b>Noches para apagar:</b> {lista}.</p>")
        else:
            p.append("<p>Ninguna ciudad supera su percentil 75 en este periodo: no hay motivo para un aviso.</p>")
    else:
        p.append("<h2>Próximas noches</h2><p class='sub'>Previsión no disponible todavía.</p>")

    p += ["<h2>Qué hacer una noche de aviso</h2>",
          "<p class='sub'>Lo que reduce las colisiones y la desorientación, por orden de eficacia y de facilidad.</p>",
          "<div class='tarjetas'>"
          "<div><b>Apagar la iluminación ornamental</b><p>Fachadas, monumentos, cañones de luz al cielo y rótulos "
          "no esenciales, de la puesta de sol al amanecer.</p></div>"
          "<div><b>Apagar plantas y oficinas vacías</b><p>Las plantas altas iluminadas de edificios acristalados "
          "son las que más atraen y las que más matan.</p></div>"
          "<div><b>Bajar persianas y cortinas</b><p>Si la luz interior tiene que quedarse encendida, que no salga "
          "por la ventana.</p></div>"
          "<div><b>Apuntar la luz al suelo</b><p>Luminarias con el flujo por debajo de la horizontal y temperatura "
          "de color cálida (≤ 2.700 K); el azul desorienta más.</p></div></div>"]

    if rk is not None and not rk.empty:
        temporada = "otoño" if hoy.month >= 7 else "primavera"
        temporada = temporada if temporada in set(rk["season"]) else rk["season"].iat[0]
        p += [f"<h2>Dónde coinciden más aves y más luz</h2>"
              f"<p class='sub'>Ranking de exposición en {temporada}: el brillo artificial del cielo de cada ciudad "
              "multiplicado por la densidad de aves prevista en sus diez noches más intensas, normalizado a 100 en "
              "la ciudad más expuesta del conjunto. Sigue el método de Horton y col. (2019).</p>",
              tabla_ranking(rk, temporada),
              "<p class='sub'>La columna «cielo vs natural» dice cuántas veces más brillante es el cielo de esa "
              "ciudad que uno sin luz artificial. Aviso: entre la ciudad más y la menos iluminada hay un factor 3-4, "
              "mientras que en aves apenas hay un factor 2, así que el orden lo marca sobre todo la luz.</p>"]

    p += ["<h2>Cómo se calcula</h2>",
          "<p class='sub'>Sin acrónimos, en cuatro pasos.</p>",
          "<ol>"
          "<li><b>Los radares meteorológicos ven aves.</b> Además de la lluvia, un radar mide el eco de los animales "
          "que cruzan su haz. La red europea publica en abierto un perfil vertical cada 5-15 minutos con cuántas aves "
          "hay por kilómetro cúbico a cada altura. Nosotros resumimos cada noche en una cifra: la densidad media de "
          "aves en la columna de aire, en aves por kilómetro cuadrado.</li>"
          "<li><b>La meteorología explica buena parte de esa cifra.</b> Con once años de noches de 55 radares de "
          "España, Portugal y Francia entrenamos dos modelos: uno estima cuánta ave habrá y otro decide si la noche "
          "va a ser de paso fuerte. Las variables son el viento a la altura a la que vuelan (750, 1.500 y 3.000 "
          "metros), descompuesto en lo que empuja hacia el rumbo migratorio y lo que desvía; la temperatura y su "
          "cambio en 24 horas; la humedad, la nubosidad, la lluvia y la presión; y el día del año.</li>"
          "<li><b>La validación se hace quitando radares enteros</b>, no noches al azar. Es la única prueba honesta "
          "para una ciudad sin radar: se entrena sin ese radar y se le pide predecirlo a ciegas. Así el modelo "
          "captura un <b>34 % de las noches de paso fuerte</b> frente al 10 % que daría el azar, con un 66 % de "
          "falsas alarmas. Es decir: acierta tres veces más que tirar una moneda, y se equivoca a menudo.</li>"
          "<li><b>El aviso se calibra ciudad a ciudad.</b> Se corre el modelo sobre cinco años de meteorología en el "
          "punto exacto de la ciudad y los niveles se cortan por los percentiles de esa distribución. Por eso el "
          "aviso no necesita radar en la ciudad y significa lo mismo en todas.</li></ol>"]

    if enlaces:
        p += ["<h2>Informes técnicos</h2><p class='sub'>Cada fase con sus figuras, sus tablas y sus limitaciones.</p><ul>"]
        nombres = {"fase0.html": "Fase 0 — ¿ven aves los radares españoles renovados?",
                   "fase1.html": "Fase 1 — histórico 2016-2026 y climatologías por radar",
                   "fase2.html": "Fase 2 — el modelo meteorológico y su validación",
                   "fase3.html": "Fase 3 — previsión por ciudad",
                   "ranking.html": "Ranking de exposición a la luz artificial",
                   "diseno.html": "Documento de diseño del proyecto"}
        for e in enlaces:
            p.append(f"<li><a href='{e}'>{nombres.get(e.rsplit('/', 1)[-1], e)}</a></li>")
        p.append("</ul>")

    p += ["<h2>Lo que esto no es</h2><ul>"
          "<li>No es un recuento de aves sobre tu tejado: es la densidad media en toda la columna de aire, la mayor "
          "parte de ella entre 200 y 3.000 metros de altura.</li>"
          "<li>No distingue especies. Un radar meteorológico no sabe si el eco es un zorzal o un mosquitero.</li>"
          "<li>En otoño y en el sur, parte de la señal puede ser insecto. Hace falta la velocidad de vuelo para "
          "separarlos y el archivo europeo dejó de publicarla en Francia en 2021 y casi siempre en España.</li>"
          "<li>El pronóstico se degrada con los días: la primera noche es fiable, la séptima mucho menos.</li>"
          "<li>Las cuatro ciudades españolas con radar nuevo son el caso difícil del modelo (mide bien el orden de "
          "las noches, pero el perfil llega truncado a seis capas). No conviene tomar decisiones firmes ahí hasta "
          "la temporada de 2027.</li></ul>",
          "<h2>Datos, método y crédito</h2>",
          "<p>Perfiles verticales de aves: <a href='https://aloftdata.eu'>Aloft</a> (Desmet y col. 2025), red "
          "europea de radares meteorológicos, licencia CC0. Meteorología: <a href='https://open-meteo.com'>"
          "Open-Meteo</a> (CC BY 4.0). Luz artificial: Falchi y col. (2016), <i>The new world atlas of artificial "
          "night sky brightness</i>, Science Advances 2(6):e1600377, y GFZ Data Services "
          "doi:10.5880/GFZ.1.4.2016.001 — los ficheros originales no se redistribuyen aquí, solo resultados "
          "derivados. Método: Van Doren y Horton (2018) para el modelo, Horton y col. (2019) para la exposición a "
          "la luz, Horton y col. (2021) para la concentración del paso en pocas noches.</p>",
          "<p>Sub Nocte sigue el planteamiento de <a href='https://birdcast.org'>BirdCast</a>, el servicio de la "
          "Universidad de Cornell para Estados Unidos, y no tiene ninguna relación con él.</p>",
          "<footer><p>Proyecto abierto y sin ánimo de lucro. Todo el código y los datos derivados están en "
          "<a href='https://github.com/Asensio94/sub-nocte'>github.com/Asensio94/sub-nocte</a> (licencia MIT); la "
          "página se regenera desde esos mismos ficheros, así que cualquiera puede reproducir lo que dice.</p>"
          f"<p>Generado el {_fecha(hoy)}.</p></footer>",
          "</div></html>"]

    idx = out_dir / "index.html"
    idx.write_text("\n".join(p), encoding="utf-8", newline="\n")
    log(f"{idx} ({idx.stat().st_size / 1000:.0f} kB), {len(enlaces)} informes enlazados")
    return idx
