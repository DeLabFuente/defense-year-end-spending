"""Paso 3 · Unir los registros anuales de la PLACSP y generar el CSV de adjudicaciones para Power BI.

Uso (desde la carpeta del proyecto):
    python scripts/03_unir_registros.py registros scripts/intermedios/codigos_codice.json .

Entradas:
  registros/placsp_defensa_registros_AAAA.jsonl.gz   uno por fichero anual de licitaciones (sindicación 643)
  registros/placsp_defensa_menores_AAAA.jsonl.gz     opcional: uno por fichero anual de contratos menores (sindicación 1143),
                                                     marcados con es_contrato_menor = Sí y fuera del «importe analizado»
  codigos_codice.json                                listas oficiales de códigos CODICE

Reglas:
  1. Una licitación puede aparecer en varios ficheros anuales: se toma la versión más reciente
     (campo «updated» de la entrada Atom).
  2. Se descartan las licitaciones anuladas (estado ANUL) y las retiradas del feed después de
     su última versión, salvo las bajas por purga (más de 5 años después de la última versión).
  3. Rama: el órgano que cuelga directamente de «Ministerio de Defensa» en la jerarquía del órgano
     de contratación. En los ficheros antiguos muchas entradas no traen jerarquía; a esas se les
     asigna la rama con un catálogo construido con los órganos que sí la traen, por código DIR3,
     después por identificador de la plataforma y por último por nombre exacto. Las que no se
     pueden asignar quedan fuera y se listan para revisión.
  4. Cuentan los resultados adjudicados o formalizados (códigos 1, 2, 8 y 9) con fecha de
     adjudicación e importe. Cada adjudicación cuenta en el mes de su fecha de adjudicación,
     no en el año del fichero: así diciembre se completa con lo publicado en enero siguiente.
  5. Solo se conservan adjudicaciones desde el primer año de la serie (SERIE_DESDE).

Salidas:
  placsp_defensa_adjudicaciones.csv   agregado mensual (mismo formato que la prueba de 2023)
  placsp_anios.csv                    estado de cada año: completo, diciembre incompleto, prueba 2023 o pendiente
  resumen_registros.json             controles por fichero y por año, órganos sin asignar
  catalogo_organos_defensa.csv       órganos de Defensa con su rama y cómo se asignó
"""
import csv
import gzip
import json
import re
import sys
from datetime import date
from collections import Counter, defaultdict
from pathlib import Path

SERIE_DESDE = 2017
SERIE_DESDE_MENORES = 2018  # el primer fichero de contratos menores es el de 2018
# La plataforma purga del feed las entradas con más de ~6 años (bajas con desfase de 6-8 años sobre la última versión).
# Eso no es una retirada: solo cuenta como retirada una baja en los 5 años siguientes a la última versión.
MAX_DIAS_RETIRADA = 5 * 365
# Programa especial: expediente con adjudicaciones de al menos este importe (con IVA) en un mismo año,
# medido en euros constantes de 2025 (deflactor del PIB de macro_2017_2026.csv; sin ese fichero, euros corrientes).
UMBRAL_PROGRAMA_ESPECIAL = 100e6


def cargar_factores(carpeta):
    """anio -> factor para pasar euros corrientes a euros de 2025 (deflactor del PIB)."""
    f = Path(carpeta) / "macro_2017_2026.csv"
    if not f.exists():
        return {}
    with f.open(encoding="utf-8-sig") as fh:
        return {int(r["anio"]): float(r["factor_euros_2025"].replace(",", ".")) for r in csv.DictReader(fh, delimiter=";")}
OK = {"1", "2", "8", "9"}
SECCION_14 = {"Armada", "Ejército de Tierra", "Ejército del Aire", "Estado Mayor de la Defensa",
              "Secretaría de Estado de Defensa", "Subsecretaría de Defensa"}
ALIAS_RAMA = {"Ejército del Aire y del Espacio": "Ejército del Aire"}
NO_DEFENSA = "(otro departamento)"
RX_MILITAR = re.compile(r"defensa|ej[eé]rcito|armada|militar|fuerzas armadas|arsenal|intendencia|intendente|armamento|"
                        r"aeroespacial|mando de|cuartel general|guardia real|isfas|invied|unidad militar de emergencias|estado mayor", re.I)

# Reglas provisionales para órganos sin jerarquía que el catálogo aún no cubre (ficheros de 2017-2018).
# Se aplican después del catálogo, que siempre tiene prioridad, y quedan marcadas como «regla».
# Códigos DIR3 de nivel de rama que se repiten en varios órganos del mismo Ejército u organismo.
REGLA_DIR3 = {
    "E00117001": "Ejército de Tierra",
    "E00117101": "Armada",
    "E00117201": "Ejército del Aire",
    "E04973401": "Secretaría de Estado de Defensa",   # Subdirección General de Adquisiciones de Armamento y Material (DGAM)
    "E00116302": "Secretaría de Estado de Defensa",   # Dirección General de Infraestructura
    "E00116401": "Secretaría de Estado de Defensa",   # INTA
    "E04905001": "Secretaría de Estado de Defensa",   # INVIED
    "E00116901": "Subsecretaría de Defensa",          # ISFAS
    "E00116602": "Subsecretaría de Defensa",          # Secretaría General Técnica
    "E02932501": "Subsecretaría de Defensa",          # Inspección General de Sanidad
}
REGLA_NOMBRE = [
    (r"ingenier[ií]a de sistemas para la defensa", "ISDEFE"),
    (r"electr[oó]nica submarina", "Sociedad Anónima de Electrónica Submarina (SAES)"),
    (r"ej[ée]rcito del aire|secci[oó]n econ[oó]mico[ -]?administrativ|base a[ée]rea|aer[oó]dromo militar|mando a[ée]reo|"
     r"acuartelamiento a[ée]reo|academia general del aire", "Ejército del Aire"),
    (r"\barmada\b|^intendente de |^intendencia de madrid$|arsenal|escuela naval|infanter[ií]a de marina", "Armada"),
    (r"estado mayor de la defensa|unidad militar de emergencias|mando de operaciones|centro de inteligencia de las fuerzas armadas", "Estado Mayor de la Defensa"),
    (r"ej[ée]rcito|mando de apoyo log[ií]stico|intendencia de asuntos econ[oó]micos|mando de canarias|mando de personal|"
     r"mando de adiestramiento|academia general militar|cuartel general terrestre|fuerza terrestre|fuerza log[ií]stica|"
     r"fuerzas (pesadas|ligeras)|divisi[oó]n (san marcial|castillejos)|parque y centro|comandancia gral|comandancia general|"
     r"secci[oó]n de asuntos econ[oó]micos de la direcci[oó]n de infraestructura$|sistemas de informaci[oó]n, telecomunicaciones", "Ejército de Tierra"),
    (r"sanidad de la defensa|instituto social de las fuerzas armadas|centro universitario de la defensa|"
     r"hospital (central|general) de la defensa|reclutamiento y ense[ñn]anza|subsecretar[ií]a de defensa", "Subsecretaría de Defensa"),
    (r"armamento y material|\binta\b|t[ée]cnica aeroespacial|infraestructura y equipamiento de la defensa|invied|"
     r"direcci[oó]n general de infraestructura|junta de contrataci[oó]n del ministerio de defensa|secretar[ií]a de estado de defensa|"
     r"experiencias hidrodin", "Secretaría de Estado de Defensa"),
]
REGLA_NOMBRE = [(re.compile(rx, re.I), rama) for rx, rama in REGLA_NOMBRE]


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def rama_por_jerarquia(cadena):
    for i, n in enumerate(cadena or []):
        if norm(n) == "ministerio de defensa":
            r = cadena[i - 1] if i >= 1 else "(Ministerio)"
            return ALIAS_RAMA.get(r, r)
    return None


def leer(carpeta):
    ultimos, bajas, cabeceras, organos = {}, {}, [], []
    ficheros = sorted(Path(carpeta).glob("placsp_defensa_registros_*.jsonl.gz")) + sorted(Path(carpeta).glob("placsp_defensa_menores_*.jsonl.gz"))
    for f in ficheros:
        menor = "_menores_" in f.name
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for linea in fh:
                o = json.loads(linea)
                t = o.get("t")
                if t == "cabecera":
                    o["fichero_local"] = f.name
                    o["menores"] = menor
                    cabeceras.append(o)
                elif t == "l":
                    o["menor"] = menor
                    prev = ultimos.get(o["id"])
                    if prev is None or prev["upd"] < o["upd"]:
                        ultimos[o["id"]] = o
                elif t == "b":
                    if o["id"] not in bajas or bajas[o["id"]] < o["when"]:
                        bajas[o["id"]] = o["when"]
                elif t == "o":
                    o["anio"] = cabeceras[-1]["anio"] if cabeceras else None
                    organos.append(o)
    return ultimos, bajas, cabeceras, organos


def construir_catalogo(organos, ultimos):
    """DIR3 / id de plataforma / nombre → rama, a partir de órganos que traen jerarquía."""
    votos = {"dir3": defaultdict(Counter), "idp": defaultdict(Counter), "nombre": defaultdict(Counter)}
    fuentes = [(o.get("cad"), o.get("dir3"), o.get("idp"), o.get("n", 1)) for o in organos]
    if not organos:  # ficheros v2 sin inventario: usar los propios registros
        fuentes = [(r.get("cad"), r.get("dir3"), r.get("idp"), 1) for r in ultimos.values()]
    for cad, dir3, idp, n in fuentes:
        if not cad or len(cad) < 2:
            continue
        rama = rama_por_jerarquia(cad) or NO_DEFENSA
        if dir3:
            votos["dir3"][dir3][rama] += n
        if idp:
            votos["idp"][idp][rama] += n
        votos["nombre"][norm(cad[0])][rama] += n
    return {k: {clave: c.most_common(1)[0][0] for clave, c in v.items()} for k, v in votos.items()}


def asignar_rama(rec, cat):
    rama = rama_por_jerarquia(rec.get("cad"))
    if rama:
        return rama, "jerarquía"
    if rec.get("dir3") and rec["dir3"] in cat["dir3"]:
        return cat["dir3"][rec["dir3"]], "DIR3"
    if rec.get("idp") and rec["idp"] in cat["idp"]:
        return cat["idp"][rec["idp"]], "id plataforma"
    nombre = norm((rec.get("cad") or [None])[0])
    if nombre in cat["nombre"]:
        return cat["nombre"][nombre], "nombre"
    if len(rec.get("cad") or []) <= 1:
        if rec.get("dir3") in REGLA_DIR3:
            return REGLA_DIR3[rec["dir3"]], "regla DIR3"
        for rx, rama in REGLA_NOMBRE:
            if rx.search(nombre):
                return rama, "regla de nombre"
    return None, None


# Códigos DIR3 de nivel de rama o de junta: los comparten órganos distintos y no sirven para unificar nombres.
# Variantes de nombre sin id ni DIR3 propio que las una.
ALIAS_ORGANO = {
    "Director de Abastecimiento y Transportes de la Jefatura de Apoyo Logístico de la Armada": "Dirección de Abastecimiento y Transportes de la Armada",
}
DIR3_COMPARTIDOS = {"E00117001", "E00117101", "E00117201", "E00116001", "E00116202", "E00116501"}


def nombres_canonicos(registros):
    """Une las variantes de nombre de un mismo órgano (mismo id de plataforma o mismo DIR3 propio)
    y devuelve nombre -> nombre más reciente del grupo."""
    padre = {}

    def raiz(x):
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    ultimo = {}
    por_clave = {}
    for rec in registros:
        nm = re.sub(r"\s+", " ", (rec.get("cad") or [""])[0] or "").strip()
        if not nm:
            continue
        raiz(nm)
        if nm not in ultimo or ultimo[nm] < rec["upd"]:
            ultimo[nm] = rec["upd"]
        claves = []
        if rec.get("idp"):
            claves.append(("idp", rec["idp"]))
        if rec.get("dir3") and rec["dir3"] not in DIR3_COMPARTIDOS:
            claves.append(("dir3", rec["dir3"]))
        for c in claves:
            if c in por_clave:
                a, b = raiz(nm), raiz(por_clave[c])
                if a != b:
                    padre[a] = b
            else:
                por_clave[c] = nm
    grupos = defaultdict(list)
    for nm in list(padre):
        grupos[raiz(nm)].append(nm)
    canon = {}
    for miembros in grupos.values():
        elegido = max(miembros, key=lambda n: ultimo.get(n, ""))
        elegido = ALIAS_ORGANO.get(elegido, elegido).replace("Nª", "Nº")
        for n in miembros:
            canon[n] = elegido
    return canon


def main():
    carpeta, codigos, salida = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    cod = json.loads(Path(codigos).read_text(encoding="utf-8"))
    lab = lambda t, k: cod[t].get(k, f"Código {k}") if k else "Sin dato"
    ultimos, bajas, cabeceras, organos = leer(carpeta)
    cat = construir_catalogo(organos, ultimos)

    procesados = sorted({c["anio"] for c in cabeceras if not c.get("menores")})
    ultimo = max(procesados)
    control = Counter()
    via = Counter()
    via_anio = defaultdict(Counter)
    sin_asignar = Counter()
    organos_def = {}
    cubo = {}
    factores = cargar_factores(salida)
    canon = nombres_canonicos([r for r in ultimos.values() if asignar_rama(r, cat)[0] not in (None, NO_DEFENSA)])
    items = []
    tot_exp = defaultdict(float)
    for rec in ultimos.values():
        rama, como = asignar_rama(rec, cat)
        nombre = (rec.get("cad") or [""])[0]
        if rama is None:
            if RX_MILITAR.search(nombre or ""):
                sin_asignar[f"{nombre} | DIR3 {rec.get('dir3')}"] += 1
            continue
        if rama == NO_DEFENSA:
            continue
        control["licitaciones_defensa"] += 1
        via[como] += 1
        organos_def.setdefault((nombre, rec.get("dir3")), [rama, como, 0])[2] += 1
        if rec.get("est") == "ANUL":
            control["anuladas"] += 1
            continue
        b = bajas.get(rec["id"])
        if b and b > rec["upd"]:
            lag = (date.fromisoformat(b[:10]) - date.fromisoformat(rec["upd"][:10])).days
            if lag <= MAX_DIAS_RETIRADA:
                control["retiradas"] += 1
                continue
            control["bajas_por_purga_ignoradas"] += 1
        for r in rec.get("res") or []:
            if r.get("cod") not in OK or not r.get("fAdj"):
                continue
            if r.get("sin") is None and r.get("con") is None:
                continue
            mes = r["fAdj"][:7]
            desde = SERIE_DESDE_MENORES if rec.get("menor") else SERIE_DESDE
            if not (mes[:4].isdigit() and desde <= int(mes[:4]) <= ultimo):
                control["adjudicaciones_fuera_de_serie"] += 1
                continue
            imp_con = r["con"] if r.get("con") is not None else (r.get("sin") or 0) * 1.21
            items.append((mes, rama, rec.get("tipo") or "", rec.get("proc") or "", rec.get("urg") or "", rec.get("sist") or "", bool(rec.get("menor")),
                          rec["id"], r.get("sin") or 0, imp_con, canon.get(re.sub(r"\s+", " ", nombre or "").strip(), (nombre or "").strip())))
            tot_exp[(rec["id"], mes[:4])] += imp_con
            control["adjudicaciones"] += 1
            via_anio[int(mes[:4])]["jerarquía" if como == "jerarquía" else "regla" if como.startswith("regla") else "catálogo"] += 1

    for mes, rama, tipo, proc, urg, sist, menor, rid, sin, con, organo in items:
        esp = "Sí" if tot_exp[(rid, mes[:4])] * factores.get(int(mes[:4]), 1.0) >= UMBRAL_PROGRAMA_ESPECIAL else "No"
        k = (mes, rama, organo, tipo, proc, urg, sist, esp, menor)
        c = cubo.setdefault(k, {"n": 0, "ids": set(), "sin": 0.0, "con": 0.0})
        c["n"] += 1
        c["ids"].add(rid)
        c["sin"] += sin
        c["con"] += con

    filas = []
    for (mes, rama, organo, tipo, proc, urg, sist, esp, menor), c in sorted(cubo.items()):
        filas.append({
            "fecha_mes": f"{mes}-01", "anio": int(mes[:4]), "mes": int(mes[5:7]), "rama": rama, "organo": organo,
            "en_seccion_14": "Sí" if rama in SECCION_14 else "No",
            "tipo_contrato": lab("tipo", tipo), "procedimiento": lab("proc", proc),
            "tramitacion": lab("urg", urg), "sistema_contratacion": lab("sist", sist),
            "es_establecimiento_marco": "Sí" if sist in ("1", "2") else "No",
            "es_programa_especial": esp,
            "es_contrato_menor": "Sí" if menor else "No",
            "n_adjudicaciones": c["n"], "n_expedientes": len(c["ids"]),
            "importe_sin_iva_eur": round(c["sin"], 2), "importe_con_iva_eur": round(c["con"], 2),
        })
    with (salida / "placsp_defensa_adjudicaciones.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]), delimiter=";")
        w.writeheader()
        for r in filas:
            w.writerow({k: (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v) for k, v in r.items()})

    with (salida / "catalogo_organos_defensa.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["organo", "dir3", "rama", "asignada_por", "licitaciones"])
        for (nombre, dir3), (rama, como, n) in sorted(organos_def.items(), key=lambda x: (x[1][0], -x[1][2])):
            w.writerow([nombre, dir3 or "", rama, como, n])

    with (salida / "placsp_anios.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["anio", "estado", "nota"])
        for a in range(SERIE_DESDE, 2027):
            if a in procesados and a == 2026:
                estado = "Año en curso"
            elif a in procesados and a + 1 in procesados:
                estado = "Completo"
            elif a in procesados:
                estado = "Diciembre incompleto"
            elif a == 2023:
                estado = "Prueba 2023 (método anterior)"
            else:
                estado = "Pendiente"
            v = via_anio.get(a)
            if v:
                tot = sum(v.values())
                nota = (f"Rama por jerarquía {100 * v['jerarquía'] / tot:.0f} %, por catálogo de otros años {100 * v['catálogo'] / tot:.0f} %, "
                        f"por regla provisional {100 * v['regla'] / tot:.0f} %")
            elif a == 2023:
                nota = "Datos de la prueba de cobertura: un solo fichero anual"
            else:
                nota = ""
            w.writerow([a, estado, nota])

    por_anio = defaultdict(lambda: Counter())
    for r in filas:
        a = por_anio[r["anio"]]
        a["adjudicaciones"] += r["n_adjudicaciones"]
        a["importe_con_iva_MEUR"] += r["importe_con_iva_eur"] / 1e6
        if r["en_seccion_14"] == "Sí" and r["es_establecimiento_marco"] == "No":
            a["s14_sin_marco_MEUR"] += r["importe_con_iva_eur"] / 1e6
            a["s14_sin_marco_n"] += r["n_adjudicaciones"]
            if r["mes"] >= 11:
                a["nov_dic_s14_sin_marco_MEUR"] += r["importe_con_iva_eur"] / 1e6
                a["nov_dic_s14_sin_marco_n"] += r["n_adjudicaciones"]
    resumen = {
        "ficheros": [{k: c.get(k) for k in ("fichero_local", "anio", "version", "lastModified", "entradas",
                                            "entradasDefensaJerarquia", "entradasCandidatasSinJerarquia",
                                            "licitacionesGuardadas", "organos", "errores")} for c in cabeceras],
        "control": dict(control),
        "rama_asignada_por": dict(via),
        "catalogo": {k: len(v) for k, v in cat.items()},
        "por_anio": {a: {k: (round(v, 1) if isinstance(v, float) else v) for k, v in d.items()} for a, d in sorted(por_anio.items())},
        "organos_militares_sin_asignar": sin_asignar.most_common(40),
    }
    for a, d in resumen["por_anio"].items():
        if d.get("s14_sin_marco_MEUR"):
            d["cuota_nov_dic_importe"] = round(d.get("nov_dic_s14_sin_marco_MEUR", 0) / d["s14_sin_marco_MEUR"], 3)
            d["cuota_nov_dic_numero"] = round(d.get("nov_dic_s14_sin_marco_n", 0) / d["s14_sin_marco_n"], 3)
    (salida / "resumen_registros.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
