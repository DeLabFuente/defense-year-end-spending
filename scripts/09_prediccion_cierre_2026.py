"""Paso 9 · Predicción del cierre de 2026, escrita antes de noviembre y comprobable en enero de 2027.

Uso (desde la carpeta del proyecto):
    python scripts/09_prediccion_cierre_2026.py .

Lee solo los CSV publicados (linea_base_cierre.csv, calendario_cierre.csv, ordenes_cierre_corte.csv,
placsp_defensa_adjudicaciones.csv y placsp_anios.csv); no necesita registros/ ni usa adjudicatarios.

Las predicciones están fijadas abajo (PREDICCIONES) desde el 29/10/2026, con datos a 23/10/2026: no se recalculan
con datos nuevos. El script calcula, para cada una, el valor de 2017-2025 que la respalda y, cuando 2026 esté
completo (placsp_anios.csv con 2026 en estado «Completo», tras el paso 1 de «Enero de 2027» del README), el valor
de 2026 y si se cumple. Mientras 2026 siga en curso, las columnas de 2026 salen vacías.

Salida:
  prediccion_cierre_2026.csv  una fila por predicción: qué se mide, qué se predice, cuántos años de 2017-2025 lo
                              cumplieron, valores por año, valor de 2026 y resultado
"""
import collections, csv, statistics, sys
from pathlib import Path

sys.stdout.reconfigure(errors="replace")
CARPETA = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
HISTORICO = range(2017, 2026)
OBJETIVO = 2026
DEF, AGE = "Defensa", "Resto de la AGE"


def leer(nombre):
    with open(CARPETA / nombre, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def num(x):
    return float(x.replace(",", ".")) if x not in ("", None) else 0.0


def fmt(x, dec=4):
    if x is None:
        return ""
    if isinstance(x, int):
        return str(x)
    return f"{x:.{dec}f}".replace(".", ",")


# ── Datos ───────────────────────────────────────────────────────────────────────────────────────────────
estado = {int(r["anio"]): r["estado"] for r in leer("placsp_anios.csv")}
completo_2026 = estado.get(OBJETIVO) == "Completo"

# Línea base: licitaciones sin contratos menores; importe ordinario (sin programas especiales ni menores atípicos)
lb = collections.defaultdict(float)
for r in leer("linea_base_cierre.csv"):
    if r["es_contrato_menor"] != "No" or r["bloque"] not in (DEF, AGE):
        continue
    for tipo in ("Todos", r["tipo_contrato"]):
        k = (int(r["anio"]), r["bloque"], tipo, r["periodo"])
        for campo in ("importe_ordinario_eur", "n_ordinario", "n_con_ofertas", "n_oferta_unica",
                      "n_negociado_sin_publicidad", "n_adjudicaciones"):
            lb[k + (campo,)] += num(r[campo])


def cuota_nov_dic(anio, bloque, tipo="Todos", campo="importe_ordinario_eur"):
    nd, eo = lb[(anio, bloque, tipo, "Nov-dic", campo)], lb[(anio, bloque, tipo, "Ene-oct", campo)]
    return nd / (nd + eo) if nd + eo else None


def salto(anio, bloque, num_, den):
    """Puntos de diferencia nov-dic menos ene-oct de una proporción (en tanto por uno)."""
    v = {}
    for p in ("Nov-dic", "Ene-oct"):
        d = lb[(anio, bloque, "Todos", p, den)]
        if not d:
            return None
        v[p] = lb[(anio, bloque, "Todos", p, num_)] / d
    return v["Nov-dic"] - v["Ene-oct"]


calendario = collections.defaultdict(list)
for r in leer("calendario_cierre.csv"):
    calendario[int(r["anio"])].append((num(r["cuota_n"]), r["etiqueta"]))

corte = {(int(r["anio"]), r["bloque"]): num(r["despues_entre_antes_plazo"]) for r in leer("ordenes_cierre_corte.csv")}

programas_nd = collections.Counter()
for r in leer("placsp_defensa_adjudicaciones.csv"):
    if r["es_programa_especial"] == "Sí" and int(r["mes"]) >= 11:
        programas_nd[int(r["anio"])] += int(num(r["n_expedientes"]))


# ── Indicadores (valor de un año) ───────────────────────────────────────────────────────────────────────
def ind(clave, a):
    if clave == "cuota_importe_def":
        return cuota_nov_dic(a, DEF)
    if clave == "dif_cuota_importe":
        x, y = cuota_nov_dic(a, DEF), cuota_nov_dic(a, AGE)
        return None if None in (x, y) else x - y
    if clave == "dif_cuota_n":
        x, y = cuota_nov_dic(a, DEF, campo="n_ordinario"), cuota_nov_dic(a, AGE, campo="n_ordinario")
        return None if None in (x, y) else x - y
    if clave == "dif_cuota_servicios":
        x, y = cuota_nov_dic(a, DEF, "Servicios"), cuota_nov_dic(a, AGE, "Servicios")
        return None if None in (x, y) else x - y
    if clave == "salto_oferta_unica_def":
        return salto(a, DEF, "n_oferta_unica", "n_con_ofertas")
    if clave == "salto_oferta_unica_dif":
        x, y = salto(a, DEF, "n_oferta_unica", "n_con_ofertas"), salto(a, AGE, "n_oferta_unica", "n_con_ofertas")
        return None if None in (x, y) else x - y
    if clave == "salto_negociado_def":
        return salto(a, DEF, "n_negociado_sin_publicidad", "n_adjudicaciones")
    if clave == "quincena_pico":
        return max(calendario[a])[1] if calendario.get(a) else None
    if clave == "corte_def":
        return corte.get((a, DEF))
    if clave == "corte_dif":
        x, y = corte.get((a, DEF)), corte.get((a, AGE))
        return None if None in (x, y) else x - y
    if clave == "programas_nov_dic":
        return programas_nd.get(a, 0)
    raise KeyError(clave)


# ── Predicciones fijadas el 29/10/2026 (no tocar: es lo que se contrasta en enero de 2027) ─────────────────
# (id, bloque temático, clave, qué se mide, predicción en palabras, prueba)
PREDICCIONES = [
    ("P1", "Peso del cierre", "cuota_importe_def",
     "Peso de noviembre-diciembre en el importe ordinario de Defensa",
     "Entre el 22 % y el 33 % (valor central, 26 %)",
     lambda v: 0.22 <= v <= 0.33),
    ("P2", "Peso del cierre", "dif_cuota_importe",
     "Peso de noviembre-diciembre en el importe ordinario: Defensa menos resto de la AGE",
     "Defensa por encima del resto de la AGE (diferencia mayor que 0)",
     lambda v: v > 0),
    ("P3", "Peso del cierre", "dif_cuota_n",
     "Peso de noviembre-diciembre en el número de adjudicaciones: Defensa menos resto de la AGE",
     "Sin diferencia clara: entre -3 y +3 puntos",
     lambda v: -0.03 <= v <= 0.03),
    ("P4", "Tipos de contrato", "dif_cuota_servicios",
     "Peso de noviembre-diciembre en el importe de servicios: Defensa menos resto de la AGE",
     "Defensa por encima del resto de la AGE (diferencia mayor que 0)",
     lambda v: v > 0),
    ("P5", "Competencia", "salto_oferta_unica_def",
     "Oferta única en Defensa: noviembre-diciembre menos enero-octubre",
     "Sube en el cierre (más de 0 puntos)",
     lambda v: v > 0),
    ("P6", "Competencia", "salto_oferta_unica_dif",
     "Salto de la oferta única en el cierre: Defensa menos resto de la AGE",
     "El salto de Defensa es mayor que el del resto de la AGE",
     lambda v: v > 0),
    ("P7", "Competencia", "salto_negociado_def",
     "Negociado sin publicidad en Defensa: noviembre-diciembre menos enero-octubre",
     "Sube en el cierre (más de 0 puntos)",
     lambda v: v > 0),
    ("P8", "Calendario", "quincena_pico",
     "Quincena con más adjudicaciones de Defensa en el año",
     "Del 16 al 30 de noviembre",
     lambda v: v == "Nov 16-fin"),
    ("P9", "Calendario", "corte_def",
     "Defensa: adjudicaciones después del plazo de fiscalización del compromiso entre las de antes (mismos días hábiles)",
     "Caen tras el plazo (cociente menor que 1)",
     lambda v: v < 1),
    ("P10", "Calendario", "corte_dif",
     "Ese mismo cociente: Defensa menos resto de la AGE",
     "Defensa cae más que el resto de la AGE (diferencia menor que 0)",
     lambda v: v < 0),
    ("P11", "Programas especiales", "programas_nov_dic",
     "Expedientes de 100 M€ o más (programas especiales) adjudicados en noviembre-diciembre",
     "Al menos uno (sin predecir el importe)",
     lambda v: v >= 1),
]


def texto(v):
    if v is None:
        return ""
    return v if isinstance(v, str) else fmt(v)


filas = []
for pid, bloque, clave, mide, pred, prueba in PREDICCIONES:
    hist = {a: ind(clave, a) for a in HISTORICO}
    validos = {a: v for a, v in hist.items() if v is not None}
    cumplen = sum(1 for v in validos.values() if prueba(v))
    numeros = [v for v in validos.values() if not isinstance(v, str)]
    v26 = ind(clave, OBJETIVO) if completo_2026 else None
    filas.append({
        "id": pid, "bloque": bloque, "indicador": mide, "prediccion_2026": pred,
        "anios_que_cumplen_2017_2025": f"{cumplen} de {len(validos)}",
        "mediana_2017_2025": fmt(statistics.median(numeros), 4 if any(isinstance(v, float) for v in numeros) else 1) if numeros else "",
        "minimo_2017_2025": fmt(min(numeros)) if numeros else "",
        "maximo_2017_2025": fmt(max(numeros)) if numeros else "",
        "valores_2017_2025": " | ".join(f"{a}: {texto(v)}" for a, v in hist.items()),
        "valor_2026": texto(v26),
        "resultado_2026": "" if v26 is None else ("Se cumple" if prueba(v26) else "No se cumple"),
        "fijada": "2026-10-29 (datos a 2026-10-23)",
    })

with open(CARPETA / "prediccion_cierre_2026.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(filas[0]), delimiter=";")
    w.writeheader(); w.writerows(filas)

for x in filas:
    print(f'{x["id"]:>4}  {x["anios_que_cumplen_2017_2025"]:>8}  mediana {x["mediana_2017_2025"]:>8}  '
          f'2026: {x["resultado_2026"] or "pendiente"}  · {x["prediccion_2026"]}')
if not completo_2026:
    print("2026 sigue en curso: las columnas de 2026 se rellenarán cuando placsp_anios.csv lo marque como «Completo».")
