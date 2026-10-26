"""Paso 7 · Línea base: el cierre de Defensa frente al resto del sector público.

Uso (desde la carpeta del proyecto, después del paso 3):
    python scripts/07_linea_base_sector_publico.py registros scripts/intermedios/codigos_codice.json .

Entradas:
  registros/sector_publico/placsp_sector_publico_AAAA.jsonl.gz           todas las licitaciones de la PLACSP (sindicación 643)
  registros/sector_publico/placsp_sector_publico_menores_AAAA.jsonl.gz   todos los contratos menores (sindicación 1143)
  registros/placsp_defensa_*.jsonl.gz                                    para identificar exactamente la serie de Defensa
  macro_2017_2026.csv                                                    factores a euros de 2025 (umbral de programa especial)

Mismas reglas que el paso 3: versión más reciente de cada licitación, sin anuladas ni retiradas (salvo bajas por purga),
resultados adjudicados o formalizados (1, 2, 8, 9) en el mes de su fecha de adjudicación, sin establecimiento de acuerdos
marco ni de sistemas dinámicos, y programa especial = expediente de 100 M€ o más (con IVA, euros de 2025) en un año.

Clasificación del órgano de contratación (solo a nivel de ministerio o tipo de administración; ningún órgano concreto):
  1. Defensa = exactamente las licitaciones de la serie del proyecto (sección 14, paso 3). ISDEFE, SAES y lo que el paso 3
     no asigna a la sección 14 quedan fuera de la comparación.
  2. Jerarquía del órgano: Administración General del Estado (por ministerio, con la estructura ministerial actual),
     comunidades autónomas, entidades locales y otras entidades (sociedades y fundaciones, universidades, mutuas,
     instituciones independientes).
  3. Sin jerarquía (habitual en 2017-2021): catálogo con la observación más reciente del mismo órgano en cualquier año
     (identificador de plataforma, DIR3 o nombre inequívoco); si no, el prefijo del código DIR3 (E = Estado, A = autonómico,
     L = local, U = universidad).

Salidas:
  linea_base_cierre.csv          por año, mes, comparador, grupo, licitación o contrato menor y tipo de contrato (suministros,
                                 servicios, obras, otros): adjudicaciones,
                                 importes (total, programas especiales, menores con importe imposible, ordinario) y sumas
                                 para medir la competencia del importe ordinario de las licitaciones
  scripts/intermedios/resumen_linea_base.json   controles: cobertura de la clasificación y cuadre de Defensa con el paso 3
"""
import collections
import csv
import gzip
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location("unir", Path(__file__).with_name("03_unir_registros.py"))
u = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(u)

AGE = "ADMINISTRACIÓN GENERAL DEL ESTADO"
TOPES = {AGE: "AGE", "COMUNIDADES Y CIUDADES AUTÓNOMAS": "Comunidades autónomas", "ENTIDADES LOCALES": "Entidades locales",
         "OTRAS ENTIDADES DEL SECTOR PÚBLICO": "Otras"}
OTRAS = {
    "SOCIEDADES, FUNDACIONES y CONSORCIOS ESTATALES": ("Sociedades y fundaciones públicas", "Sociedades, fundaciones y consorcios estatales"),
    "SOCIEDADES, FUNDACIONES Y CONSORCIOS COMUNIDADES AUTÓNOMAS": ("Sociedades y fundaciones públicas", "Sociedades, fundaciones y consorcios autonómicos"),
    "SOCIEDADES, FUNDACIONES Y CONSORCIOS ENTIDADES LOCALES": ("Sociedades y fundaciones públicas", "Sociedades, fundaciones y consorcios locales"),
    "UNIVERSIDADES": ("Universidades", "Universidades"),
    "MUTUAS DE ACCIDENTES DE TRABAJO COLABORADORAS DE LA SEGURIDAD SOCIAL": ("Mutuas e instituciones independientes", "Mutuas colaboradoras de la Seguridad Social"),
    "INSTITUCIONES INDEPENDIENTES": ("Mutuas e instituciones independientes", "Instituciones independientes"),
}
# Departamentos de legislaturas anteriores → departamento actual que asumió el grueso de sus competencias
MINISTERIO_ACTUAL = {
    "Ministerio de Asuntos Económicos y Transformación Digital": "Ministerio de Economía, Comercio y Empresa",
    "Ministerio de Economía y Competitividad": "Ministerio de Economía, Comercio y Empresa",
    "Ministerio de Economía y Empresa": "Ministerio de Economía, Comercio y Empresa",
    "Ministerio de Economía, Industria y Competitividad": "Ministerio de Economía, Comercio y Empresa",
    "Ministerio de Ciencia e Innovación": "Ministerio de Ciencia, Innovación y Universidades",
    "Ministerio de Universidades": "Ministerio de Ciencia, Innovación y Universidades",
    "Ministerio de Consumo": "Ministerio de Derechos Sociales, Consumo y Agenda 2030",
    "Ministerio de Derechos Sociales y Agenda 2030": "Ministerio de Derechos Sociales, Consumo y Agenda 2030",
    "Ministerio de Cultura y Deporte": "Ministerio de Cultura",
    "Ministerio de Educación y Formación Profesional": "Ministerio de Educación, Formación Profesional y Deportes",
    "Ministerio de Educación, Cultura y Deporte": "Ministerio de Educación, Formación Profesional y Deportes",
    "Ministerio de Hacienda y Función Pública": "Ministerio de Hacienda",
    "Ministerio de Hacienda y Administraciones Públicas": "Ministerio de Hacienda",
    "Ministerio de Industria, Comercio y Turismo": "Ministerio de Industria y Turismo",
    "Ministerio de Justicia": "Ministerio de la Presidencia, Justicia y Relaciones con las Cortes",
    "Ministerio de la Presidencia, Relaciones con las Cortes e Igualdad": "Ministerio de la Presidencia, Justicia y Relaciones con las Cortes",
    "Ministerio de la Presidencia, Relaciones con las Cortes y Memoria Democrática": "Ministerio de la Presidencia, Justicia y Relaciones con las Cortes",
    "Ministerio de Política Territorial": "Ministerio de Política Territorial y Memoria Democrática",
    "Ministerio de Política Territorial y Función Pública": "Ministerio de Política Territorial y Memoria Democrática",
    "Ministerio de Sanidad, Consumo y Bienestar Social": "Ministerio de Sanidad",
    "Ministerio de Trabajo, Migraciones y Seguridad Social": "Ministerio de Trabajo y Economía Social",
    "Ministerio de Transportes, Movilidad y Agenda Urbana": "Ministerio de Transportes y Movilidad Sostenible",
    "Ministerio para la Transición Ecológica": "Ministerio para la Transición Ecológica y el Reto Demográfico",
}
DEFENSA = ("Ministerio de Defensa", "Ministerio de Defensa")
FUERA = ("(fuera)", "(fuera)")
# Un contrato menor no puede superar 40.000 € (obras) sin IVA; por encima de 50.000 € sin IVA (60.500 € con IVA) es un error
# de importe en la publicación y no cuenta en el importe ordinario (sí en el número de adjudicaciones).
MAX_MENOR_CON_IVA = 60500
SIN_MINISTERIO = "AGE · ministerio sin identificar"
PREFIJO_DIR3 = {"E": ("Resto de la AGE", SIN_MINISTERIO), "A": ("Comunidades autónomas", "Comunidades autónomas"),
                "L": ("Entidades locales", "Entidades locales"), "U": ("Universidades", "Universidades")}
# Tipo de contrato: los tres grandes y el resto (concesiones, administrativos especiales, privados, patrimoniales…)
TIPO = {"1": "Suministros", "2": "Servicios", "3": "Obras"}
TIPOS = ["Suministros", "Servicios", "Obras", "Otros"]
BLOQUE = {"Ministerio de Defensa": "Defensa", "Resto de la AGE": "Resto de la AGE"}
ORDEN = ["Ministerio de Defensa", "Resto de la AGE", "Sociedades y fundaciones públicas", "Comunidades autónomas",
         "Entidades locales", "Universidades", "Mutuas e instituciones independientes", "Sin clasificar"]


def por_cadena(cad):
    """(comparador, grupo) a partir de la jerarquía, o None si no la hay."""
    if not cad or len(cad) < 2:
        return None
    for i, n in enumerate(cad):
        tope = TOPES.get((n or "").strip())
        if not tope:
            continue
        sub = (cad[i - 1] or "").strip() if i >= 1 else ""
        if tope == "AGE":
            m = re.sub(r"\s+", " ", sub) or SIN_MINISTERIO
            m = MINISTERIO_ACTUAL.get(m, m)
            return DEFENSA if m == "Ministerio de Defensa" else ("Resto de la AGE", m)
        if tope == "Otras":
            return OTRAS.get(sub, ("Mutuas e instituciones independientes", "Otras entidades"))
        return (tope, tope)
    return None


def catalogo(carpeta):
    """Observación más reciente de cada órgano con jerarquía, por id de plataforma, DIR3 y nombre."""
    obs = {"idp": {}, "dir3": {}}
    nombres = collections.defaultdict(collections.Counter)
    for f in sorted(carpeta.glob("placsp_sector_publico_*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            anio = json.loads(fh.readline())["anio"]
            for linea in fh:
                if not linea.startswith('{"t":"o"'):
                    break
                o = json.loads(linea)
                c = por_cadena(o.get("cad"))
                if not c:
                    continue
                for k in ("idp", "dir3"):
                    v = o.get(k)
                    if v and (v not in obs[k] or obs[k][v][0] < (anio, o["n"])):
                        obs[k][v] = ((anio, o["n"]), c)
                nombres[u.norm(o["cad"][0])][c] += o["n"]
    cat = {k: {v: c for v, (_, c) in d.items()} for k, d in obs.items()}
    cat["nombre"] = {}
    for nm, cnt in nombres.items():
        c, n = cnt.most_common(1)[0]
        if n >= 0.9 * sum(cnt.values()):
            cat["nombre"][nm] = c
    return cat


def clasificar(o, cat):
    c = por_cadena(o.get("cad"))
    if c:
        return c, "jerarquía"
    for k in ("idp", "dir3"):
        v = o.get(k)
        if v and v in cat[k]:
            return cat[k][v], "catálogo"
    nm = u.norm((o.get("cad") or [""])[0])
    if nm in cat["nombre"]:
        return cat["nombre"][nm], "catálogo"
    d = (o.get("dir3") or "")[:1].upper()
    if d in PREFIJO_DIR3:
        return PREFIJO_DIR3[d], "prefijo DIR3"
    return ("Sin clasificar", "Sin clasificar"), "sin clasificar"


def ids_defensa(registros):
    """Ids de la serie de Defensa (sección 14) y de lo que el paso 3 asigna a Defensa fuera de ella, por tipo de fichero."""
    ultimos, bajas, cab, org = u.leer(registros)
    cat = u.construir_catalogo(org, ultimos)
    s14, otros = set(), set()
    for rid, rec in ultimos.items():
        rama, _ = u.asignar_rama(rec, cat)
        if rama is None or rama == u.NO_DEFENSA:
            continue
        (s14 if rama in u.SECCION_14 else otros).add((bool(rec.get("menor")), rid))
    return s14, otros


def main():
    registros, salida = Path(sys.argv[1]), Path(sys.argv[3])
    carpeta = registros / "sector_publico"
    factores = u.cargar_factores(salida)
    s14, otros_def = ids_defensa(registros)
    cat = catalogo(carpeta)
    grupos, gidx = [], {}

    def g_id(c):
        if c not in gidx:
            gidx[c] = len(grupos)
            grupos.append(c)
        return gidx[c]

    control = collections.Counter()
    via_anio = collections.defaultdict(collections.Counter)
    cubo = collections.defaultdict(lambda: [0] * 14)
    procesados = sorted({int(m.group(1)) for f in carpeta.glob("placsp_sector_publico_2*.jsonl.gz")
                         if (m := re.search(r"_(\d{4})\.jsonl", f.name))})
    ultimo = max(procesados)

    for menor in (False, True):
        patron = "placsp_sector_publico_menores_*.jsonl.gz" if menor else "placsp_sector_publico_2*.jsonl.gz"
        ultimos, bajas = {}, {}
        for f in sorted(carpeta.glob(patron)):
            inv = {}
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                fh.readline()
                for linea in fh:
                    o = json.loads(linea)
                    t = o["t"]
                    if t == "o":
                        c, como = clasificar(o, cat)
                        inv[o["k"]] = (g_id(c), como)
                    elif t == "l":
                        prev = ultimos.get(o["id"])
                        if prev is None or prev[0] < o["upd"]:
                            g, como = inv[o["o"]]
                            ultimos[o["id"]] = (o["upd"], g, como, o.get("est"), o.get("proc"), o.get("urg"), o.get("sist"),
                                                o.get("presIva"), o.get("res") or [], TIPO.get(o.get("tipo"), "Otros"))
                    elif t == "b":
                        if o["id"] not in bajas or bajas[o["id"]] < o["when"]:
                            bajas[o["id"]] = o["when"]
        control[f"{'menores' if menor else 'licitaciones'}_unicas"] = len(ultimos)
        desde = u.SERIE_DESDE_MENORES if menor else u.SERIE_DESDE
        filas = []
        tot_exp = collections.defaultdict(float)
        def_vistos = set()
        for rid, (upd, g, como, est, proc, urg, sist, pres, res, tipo) in ultimos.items():
            clave = (menor, rid)
            if clave in s14:
                c = DEFENSA
                def_vistos.add(rid)
            elif clave in otros_def:
                c = FUERA
                control["defensa_fuera_de_la_seccion_14"] += 1
            else:
                c = grupos[g]
                if c == DEFENSA:  # jerarquía de Defensa que el paso 3 no asigna a la sección 14
                    c = FUERA
                    control["defensa_sin_rama_en_paso_3"] += 1
            if c == FUERA or est == "ANUL" or sist in ("1", "2"):
                continue
            b = bajas.get(rid)
            if b and b > upd and (date.fromisoformat(b[:10]) - date.fromisoformat(upd[:10])).days <= u.MAX_DIAS_RETIRADA:
                control["retiradas"] += 1
                continue
            for r in res:
                cod, f, sin, con, nof = (r + [None] * 5)[:5]
                if cod not in u.OK or not f or (sin is None and con is None):
                    continue
                if not (f[:4].isdigit() and desde <= int(f[:4]) <= ultimo):
                    continue
                imp = con if con is not None else (sin or 0) * 1.21
                anio = int(f[:4])
                tot_exp[(rid, anio)] += imp
                baja = None
                if len(res) == 1 and pres and con and 0 < con <= 1.5 * pres:
                    baja = 1 - con / pres
                filas.append((rid, anio, int(f[5:7]), c, imp, nof, proc, urg, baja, tipo))
                via_anio[anio]["defensa (paso 3)" if c == DEFENSA else como] += 1
        control[f"defensa_{'menores' if menor else 'licitaciones'}_en_sector_publico"] = len(def_vistos)
        control[f"defensa_{'menores' if menor else 'licitaciones'}_en_serie"] = sum(1 for m, _ in s14 if m == menor)
        del ultimos, bajas
        for rid, anio, mes, c, imp, nof, proc, urg, baja, tipo in filas:
            v = cubo[(anio, mes, c, menor, tipo)]
            v[0] += 1
            v[1] += imp
            if menor and imp > MAX_MENOR_CON_IVA:
                v[12] += 1
                v[13] += imp
                continue
            if tot_exp[(rid, anio)] * factores.get(anio, 1.0) >= u.UMBRAL_PROGRAMA_ESPECIAL:
                v[2] += 1
                v[3] += imp
                continue
            if menor:
                continue
            if nof:
                v[4] += 1
                v[5] += nof
                v[6] += nof == 1
            v[7] += proc == "3"
            v[8] += urg in ("2", "3")
            if baja is not None:
                v[9] += 1
                v[10] += baja
                v[11] += baja < 0.001
        del filas, tot_exp

    campos = ["anio", "mes", "fecha_mes", "periodo", "bloque", "comparador", "orden_comparador", "grupo", "es_contrato_menor",
              "tipo_contrato", "orden_tipo", "n_adjudicaciones", "importe_con_iva_eur", "n_programa_especial", "importe_programa_especial_eur",
              "n_menor_importe_atipico", "importe_menor_atipico_eur", "n_ordinario", "importe_ordinario_eur", "n_con_ofertas", "suma_ofertas", "n_oferta_unica",
              "n_negociado_sin_publicidad", "n_urgente_o_emergencia", "n_con_baja", "suma_baja", "n_sin_baja"]
    with (salida / "linea_base_cierre.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(campos)
        for (anio, mes, (comp, grupo), menor, tipo), v in sorted(cubo.items(), key=lambda x: (x[0][0], x[0][1], ORDEN.index(x[0][2][0]), x[0][2][1], x[0][3], TIPOS.index(x[0][4]))):
            fila = [anio, mes, f"{anio}-{mes:02d}-01", "Nov-dic" if mes >= 11 else "Ene-oct", BLOQUE.get(comp, "Resto del sector público"), comp, ORDEN.index(comp) + 1, grupo,
                    "Sí" if menor else "No", tipo, TIPOS.index(tipo) + 1, v[0], v[1], v[2], v[3], v[12], v[13], v[0] - v[2] - v[12], v[1] - v[3] - v[13], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[11]]
            w.writerow([f"{x:.{4 if k == 'suma_baja' else 2}f}".replace(".", ",") if isinstance(x, float) else x for k, x in zip(campos, fila)])

    # Controles: cuota de noviembre-diciembre por comparador y año (licitaciones, importe ordinario) y cobertura
    agg = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])
    for (anio, mes, (comp, grupo), menor, _), v in cubo.items():
        if menor:
            continue
        a = agg[(anio, comp)]
        a[0] += v[1] - v[3]
        a[2] += v[0] - v[2]
        if mes >= 11:
            a[1] += v[1] - v[3]
            a[3] += v[0] - v[2]
    cuotas = {}
    for (anio, comp), (imp, imp_nd, n, n_nd) in sorted(agg.items()):
        cuotas.setdefault(comp, {})[anio] = {"ordinario_MEUR": round(imp / 1e6, 1), "cuota_nd_importe": round(imp_nd / imp, 3) if imp else None,
                                             "n": n, "cuota_nd_n": round(n_nd / n, 3) if n else None}
    sin_min = collections.Counter()
    age = collections.Counter()
    for (anio, mes, (comp, grupo), menor, _), v in cubo.items():
        if comp == "Resto de la AGE" and not menor:
            age[anio] += v[0]
            if grupo == SIN_MINISTERIO:
                sin_min[anio] += v[0]
    resumen = {
        "control": dict(control),
        "clasificacion_por_anio": {a: dict(c) for a, c in sorted(via_anio.items())},
        "resto_age_sin_ministerio_cuota": {a: round(sin_min[a] / age[a], 3) for a in sorted(age)},
        "catalogo": {k: len(v) for k, v in cat.items()},
        "cuotas_licitaciones_ordinario": cuotas,
    }
    destino = salida / "scripts" / "intermedios"
    destino = destino if destino.exists() else salida
    (destino / "resumen_linea_base.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
