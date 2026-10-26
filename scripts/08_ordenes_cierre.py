"""Paso 8 · ¿Explican las órdenes de cierre del ejercicio el pico de la segunda quincena de noviembre?

Uso (desde la carpeta del proyecto, después del paso 3):
    python scripts/08_ordenes_cierre.py registros scripts/intermedios/codigos_codice.json .

Entradas:
  ordenes_cierre.csv                          fechas límite de cada orden anual de cierre (Ministerio de Hacienda, BOE)
  registros/placsp_defensa_registros_*.jsonl.gz
  registros/sector_publico/placsp_sector_publico_AAAA.jsonl.gz   (para el resto de la AGE, con las reglas del paso 7)

Alcance: licitaciones con importe ordinario (sin establecimiento de acuerdos marco ni sistemas dinámicos, sin contratos
menores y sin programas especiales), 2017-2025. Defensa = serie del proyecto (sección 14); resto de la AGE = paso 7.
Solo agregados por día; no usa adjudicatarios.

Las órdenes de cierre se aplican a toda la Administración General del Estado. Si el pico de Defensa se debiera a ellas,
(1) el resto de la AGE tendría el mismo pico y (2) el pico se movería con las fechas límite de cada año.

Salidas:
  ordenes_cierre_dias.csv      por año, bloque y día de octubre a diciembre: adjudicaciones e importe ordinario y su peso
                               en el año, con la fase de la orden en la que cae el día
  ordenes_cierre_tramos.csv    por año y bloque: peso de cada tramo de la orden (antes de publicarse, hasta el envío a
                               fiscalización de la aprobación, hasta el del compromiso, hasta los documentos D y después) y
                               adjudicaciones por día hábil en cada tramo frente a octubre
  ordenes_cierre_corte.csv     por año y bloque: adjudicaciones en los 5 días hábiles antes y después del plazo de envío a
                               fiscalización del compromiso y, como control, antes y después de una fecha fija (7 de diciembre)
"""
import collections
import csv
import gzip
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

AQUI = Path(__file__).parent


def _cargar(nombre, fichero):
    spec = importlib.util.spec_from_file_location(nombre, AQUI / fichero)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


u = _cargar("unir", "03_unir_registros.py")
lb = _cargar("linea_base", "07_linea_base_sector_publico.py")

ANIOS = range(2017, 2026)
BLOQUES = ["Defensa", "Resto de la AGE"]
# Fiestas nacionales de octubre a diciembre (no hay que afinar más: es para contar días hábiles comparables)
FIESTAS = {(10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}
TRAMOS = ["1. Octubre", "2. Noviembre, antes de publicarse la orden", "3. Hasta el envío a fiscalización de la aprobación",
          "4. Hasta el envío a fiscalización del compromiso", "5. Hasta los documentos D y AD", "6. Después de los documentos D y AD"]


def fecha(s):
    return date.fromisoformat(s)


def leer_ordenes(salida):
    with (salida / "ordenes_cierre.csv").open(encoding="utf-8-sig") as fh:
        return {int(r["anio"]): {k: (fecha(v) if k.startswith(("limite_", "fecha_", "ultimo_")) else v) for k, v in r.items()}
                for r in csv.DictReader(fh, delimiter=";")}


def tramo(d, o):
    if d.month == 10:
        return TRAMOS[0]
    if d < o["fecha_publicacion"]:
        return TRAMOS[1]
    if d <= o["limite_fiscalizacion_aprobacion"]:
        return TRAMOS[2]
    if d <= o["limite_fiscalizacion_compromiso"]:
        return TRAMOS[3]
    if d <= o["limite_documentos_d_ad"]:
        return TRAMOS[4]
    return TRAMOS[5]


def habil(d):
    return d.weekday() < 5 and (d.month, d.day) not in FIESTAS


def filas_defensa(registros, factores):
    """(fecha, importe) de las licitaciones ordinarias de Defensa, con las reglas del paso 6."""
    ultimos, bajas, _, org = u.leer(registros)
    cat = u.construir_catalogo(org, ultimos)
    filas, tot_exp = [], collections.defaultdict(float)
    for rec in ultimos.values():
        rama, _ = u.asignar_rama(rec, cat)
        if rama not in u.SECCION_14 or rec.get("menor") or rec.get("sist") in ("1", "2") or rec.get("est") == "ANUL":
            continue
        b = bajas.get(rec["id"])
        if b and b > rec["upd"] and (date.fromisoformat(b[:10]) - date.fromisoformat(rec["upd"][:10])).days <= u.MAX_DIAS_RETIRADA:
            continue
        for r in rec.get("res") or []:
            f = r.get("fAdj") or ""
            if r.get("cod") not in u.OK or (r.get("sin") is None and r.get("con") is None):
                continue
            try:
                d = fecha(f[:10])
            except ValueError:
                continue
            if d.year not in ANIOS:
                continue
            imp = r["con"] if r.get("con") is not None else (r.get("sin") or 0) * 1.21
            tot_exp[(rec["id"], d.year)] += imp
            filas.append((rec["id"], d, imp))
    return [(d, imp) for rid, d, imp in filas if tot_exp[(rid, d.year)] * factores.get(d.year, 1.0) < u.UMBRAL_PROGRAMA_ESPECIAL]


def filas_resto_age(registros, factores):
    """(fecha, importe) de las licitaciones ordinarias del resto de la AGE, con la clasificación del paso 7."""
    carpeta = registros / "sector_publico"
    s14, otros_def = lb.ids_defensa(registros)
    cat = lb.catalogo(carpeta)
    ultimos, bajas = {}, {}
    for f in sorted(carpeta.glob("placsp_sector_publico_2*.jsonl.gz")):
        inv = {}
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            fh.readline()
            for linea in fh:
                o = json.loads(linea)
                t = o["t"]
                if t == "o":
                    inv[o["k"]] = lb.clasificar(o, cat)[0][0]
                elif t == "l":
                    prev = ultimos.get(o["id"])
                    if prev is None or prev[0] < o["upd"]:
                        ultimos[o["id"]] = (o["upd"], inv[o["o"]], o.get("est"), o.get("sist"), o.get("res") or [])
                elif t == "b":
                    if o["id"] not in bajas or bajas[o["id"]] < o["when"]:
                        bajas[o["id"]] = o["when"]
    filas, tot_exp = [], collections.defaultdict(float)
    for rid, (upd, comp, est, sist, res) in ultimos.items():
        if comp != "Resto de la AGE" or (False, rid) in s14 or (False, rid) in otros_def or est == "ANUL" or sist in ("1", "2"):
            continue
        b = bajas.get(rid)
        if b and b > upd and (date.fromisoformat(b[:10]) - date.fromisoformat(upd[:10])).days <= u.MAX_DIAS_RETIRADA:
            continue
        for r in res:
            cod, f, sin, con, _ = (r + [None] * 5)[:5]
            if cod not in u.OK or not f or (sin is None and con is None):
                continue
            try:
                d = fecha(f[:10])
            except ValueError:
                continue
            if d.year not in ANIOS:
                continue
            imp = con if con is not None else (sin or 0) * 1.21
            tot_exp[(rid, d.year)] += imp
            filas.append((rid, d, imp))
    return [(d, imp) for rid, d, imp in filas if tot_exp[(rid, d.year)] * factores.get(d.year, 1.0) < u.UMBRAL_PROGRAMA_ESPECIAL]


def fmt(v):
    return f"{v:.4f}".replace(".", ",") if isinstance(v, float) else v


def escribir(ruta, filas):
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]), delimiter=";")
        w.writeheader()
        for r in filas:
            w.writerow({k: fmt(v) for k, v in r.items()})


def main():
    registros, salida = Path(sys.argv[1]), Path(sys.argv[3])
    ordenes = leer_ordenes(salida)
    factores = u.cargar_factores(salida)
    datos = {"Defensa": filas_defensa(registros, factores), "Resto de la AGE": filas_resto_age(registros, factores)}

    dias, tramos = [], []
    for bloque in BLOQUES:
        por_dia = collections.defaultdict(lambda: [0, 0.0])
        tot = collections.defaultdict(lambda: [0, 0.0])
        for d, imp in datos[bloque]:
            por_dia[d][0] += 1
            por_dia[d][1] += imp
            tot[d.year][0] += 1
            tot[d.year][1] += imp
        for a in ANIOS:
            o = ordenes[a]
            acum = collections.defaultdict(lambda: [0, 0.0, 0])
            d = date(a, 10, 1)
            while d.year == a:
                n, imp = por_dia.get(d, [0, 0.0])
                t = tramo(d, o)
                acum[t][0] += n
                acum[t][1] += imp
                acum[t][2] += habil(d)
                dias.append({"anio": a, "bloque": bloque, "fecha": d.isoformat(), "dia_habil": "Sí" if habil(d) else "No", "tramo": t,
                             "dias_hasta_fiscalizacion_compromiso": (o["limite_fiscalizacion_compromiso"] - d).days,
                             "adjudicaciones": n, "importe_ordinario_eur": imp, "cuota_n": n / tot[a][0] if tot[a][0] else 0.0,
                             "cuota_importe": imp / tot[a][1] if tot[a][1] else 0.0})
                d += timedelta(days=1)
            oct_dia = acum[TRAMOS[0]][0] / acum[TRAMOS[0]][2]
            for t in TRAMOS:
                n, imp, h = acum[t]
                tramos.append({"anio": a, "bloque": bloque, "tramo": t, "orden_tramo": TRAMOS.index(t) + 1, "dias_habiles": h,
                               "adjudicaciones": n, "cuota_n": n / tot[a][0], "cuota_importe": imp / tot[a][1],
                               "adjudicaciones_por_dia_habil": n / h if h else None,
                               "ritmo_frente_a_octubre": (n / h) / oct_dia if h and oct_dia else None})
    # Corte: 5 días hábiles antes (incluido el del plazo) y 5 después, con el plazo de la orden y con una fecha fija de control
    serie = {(x["bloque"], x["fecha"]): x["adjudicaciones"] for x in dias}
    cortes = []
    for a in ANIOS:
        habiles = sorted(x["fecha"] for x in dias if x["anio"] == a and x["bloque"] == BLOQUES[0] and x["dia_habil"] == "Sí")
        for bloque in BLOQUES:
            fila = {"anio": a, "bloque": bloque, "plazo_fiscalizacion_compromiso": ordenes[a]["limite_fiscalizacion_compromiso"].isoformat()}
            for clave, ref in (("plazo", ordenes[a]["limite_fiscalizacion_compromiso"]), ("control_7_dic", date(a, 12, 7))):
                pos = max(i for i, d in enumerate(habiles) if d <= ref.isoformat())
                antes = sum(serie[(bloque, d)] for d in habiles[pos - 4:pos + 1])
                despues = sum(serie[(bloque, d)] for d in habiles[pos + 1:pos + 6])
                fila.update({f"antes_{clave}": antes, f"despues_{clave}": despues, f"despues_entre_antes_{clave}": despues / antes if antes else None})
            cortes.append(fila)
    escribir(salida / "ordenes_cierre_corte.csv", cortes)
    escribir(salida / "ordenes_cierre_dias.csv", dias)
    escribir(salida / "ordenes_cierre_tramos.csv", tramos)

    # Resumen en pantalla: ritmo por tramo (media 2017-2025) y semana pico de cada año
    print("Ritmo por día hábil frente a octubre, media 2017-2025")
    for bloque in BLOQUES:
        fila = [f"{bloque:16}"]
        for t in TRAMOS[1:]:
            v = [x["ritmo_frente_a_octubre"] for x in tramos if x["bloque"] == bloque and x["tramo"] == t and x["ritmo_frente_a_octubre"]]
            fila.append(f"{t[:2]} {sum(v) / len(v):.2f}")
        print("  ".join(fila))
    print("\nDespués / antes del plazo de envío a fiscalización del compromiso (5 días hábiles), mediana 2017-2025")
    for bloque in BLOQUES:
        xs = [x for x in cortes if x["bloque"] == bloque]
        med = lambda k: sorted(x[k] for x in xs)[len(xs) // 2]
        cae = sum(1 for x in xs if x["despues_entre_antes_plazo"] < 1)
        print(f"  {bloque:16} plazo de la orden {med('despues_entre_antes_plazo'):.2f} (cae en {cae} de {len(xs)} años) · fecha fija 7 dic {med('despues_entre_antes_control_7_dic'):.2f}")
    print("\nSemana (7 días) con más adjudicaciones entre el 1 de noviembre y el 31 de diciembre")
    for a in ANIOS:
        o = ordenes[a]
        linea = [str(a)]
        for bloque in BLOQUES:
            serie = {x["fecha"]: x["adjudicaciones"] for x in dias if x["anio"] == a and x["bloque"] == bloque}
            mejor = max((sum(serie.get((date(a, 11, 1) + timedelta(days=i + k)).isoformat(), 0) for k in range(7)), i) for i in range(55))
            ini = date(a, 11, 1) + timedelta(days=mejor[1])
            linea.append(f"{bloque}: {ini:%d/%m}-{ini + timedelta(days=6):%d/%m}")
        linea.append(f"orden {o['fecha_publicacion']:%d/%m}, aprob. {o['limite_fiscalizacion_aprobacion']:%d/%m}, "
                     f"compr. {o['limite_fiscalizacion_compromiso']:%d/%m}, D {o['limite_documentos_d_ad']:%d/%m}")
        print("  ".join(linea))


if __name__ == "__main__":
    main()
