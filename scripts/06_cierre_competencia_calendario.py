"""Paso 6 · ¿Cómo se adjudica en el cierre? Competencia, calendario y presupuesto.

Uso (desde la carpeta del proyecto, después del paso 3):
    python scripts/06_cierre_competencia_calendario.py registros scripts/intermedios/codigos_codice.json .

Alcance: licitaciones de la sección 14 sin establecimiento de acuerdos marco, sin contratos menores y sin programas
especiales (importe ordinario). Solo agregados; no usa adjudicatarios.

Salidas:
  cierre_competencia.csv    por año y periodo (enero-octubre / noviembre-diciembre): adjudicaciones, ofertas medias,
                            oferta única, negociado sin publicidad, tramitación urgente o de emergencia, baja media
                            (1 - adjudicado / presupuesto, sin IVA, en licitaciones de un solo resultado), parte
                            adjudicada sin baja (al precio de licitación) y desiertos
  calendario_cierre.csv     por año y quincena: número e importe ordinario y su peso en el año
  presupuesto_y_cierre.csv  por año: situación del presupuesto, créditos y obligaciones de la IGAE (caps. 2 y 6),
                            ejecución, crédito sin ejecutar y peso del cierre
"""
import collections, csv, importlib.util, statistics, sys
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location("unir", Path(__file__).with_name("03_unir_registros.py"))
u = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(u)
REGISTROS, CODIGOS, SALIDA = sys.argv[1], sys.argv[2], Path(sys.argv[3])
DESIERTO = {"3", "6", "7"}
SITUACION = {2017: "Publicado tarde (junio)", 2018: "Publicado tarde (julio)", 2019: "Prorrogado", 2020: "Prorrogado",
             2021: "Aprobado en plazo", 2022: "Aprobado en plazo", 2023: "Aprobado en plazo",
             2024: "Prorrogado", 2025: "Prorrogado", 2026: "Prorrogado"}
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

ultimos, bajas, cab, org = u.leer(REGISTROS)
cat = u.construir_catalogo(org, ultimos)
factores = u.cargar_factores(SALIDA)
tot_exp = collections.defaultdict(float)
filas, desiertos = [], collections.Counter()
for rec in ultimos.values():
    rama, _ = u.asignar_rama(rec, cat)
    if rama not in u.SECCION_14 or rec.get("menor") or rec.get("sist") in ("1", "2") or rec.get("est") == "ANUL":
        continue
    b = bajas.get(rec["id"])
    if b and b > rec["upd"] and (date.fromisoformat(b[:10]) - date.fromisoformat(rec["upd"][:10])).days <= u.MAX_DIAS_RETIRADA:
        continue
    res = rec.get("res") or []
    for r in res:
        f = r.get("fAdj") or ""
        if not (f[:4].isdigit() and 2017 <= int(f[:4]) <= 2026):
            continue
        if r.get("cod") in DESIERTO:
            desiertos[(int(f[:4]), "Nov-dic" if int(f[5:7]) >= 11 else "Ene-oct")] += 1
            continue
        if r.get("cod") not in u.OK or (r.get("sin") is None and r.get("con") is None):
            continue
        imp = r["con"] if r.get("con") is not None else (r.get("sin") or 0) * 1.21
        tot_exp[(rec["id"], f[:4])] += imp
        baja = None
        if len(res) == 1 and rec.get("pres") and r.get("sin") and 0 < r["sin"] <= 1.5 * rec["pres"]:
            baja = 1 - r["sin"] / rec["pres"]
        filas.append(dict(id=rec["id"], anio=int(f[:4]), mes=int(f[5:7]), dia=int(f[8:10]) if f[8:10].isdigit() else 1, imp=imp,
                          nOf=r.get("nOf"), proc=rec.get("proc"), urg=rec.get("urg"), baja=baja))
filas = [x for x in filas if tot_exp[(x["id"], str(x["anio"]))] * factores.get(x["anio"], 1.0) < u.UMBRAL_PROGRAMA_ESPECIAL]


def fmt(v):
    return f"{v:.4f}".replace(".", ",") if isinstance(v, float) else ("" if v is None else v)


def escribir(nombre, filas_out):
    with (SALIDA / nombre).open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas_out[0]), delimiter=";"); w.writeheader()
        for r in filas_out: w.writerow({k: fmt(v) for k, v in r.items()})


# 1. Competencia por año y periodo
grupos = collections.defaultdict(list)
for x in filas:
    grupos[(x["anio"], "Nov-dic" if x["mes"] >= 11 else "Ene-oct")].append(x)
comp = []
for (a, p), xs in sorted(grupos.items()):
    of = [x["nOf"] for x in xs if x["nOf"]]
    bj = [x["baja"] for x in xs if x["baja"] is not None]
    d = desiertos[(a, p)]
    comp.append({"anio": a, "periodo": p, "orden_periodo": 2 if p == "Nov-dic" else 1, "adjudicaciones": len(xs),
                 "ofertas_media": statistics.mean(of) if of else None,
                 "cuota_oferta_unica": sum(1 for o in of if o == 1) / len(of) if of else None,
                 "cuota_negociado_sin_publicidad": sum(1 for x in xs if x["proc"] == "3") / len(xs),
                 "cuota_urgente_o_emergencia": sum(1 for x in xs if x["urg"] in ("2", "3")) / len(xs),
                 "baja_media": statistics.mean(bj) if bj else None,
                 "cuota_sin_baja": sum(1 for v in bj if v < 0.001) / len(bj) if bj else None, "licitaciones_con_baja": len(bj),
                 "desiertos": d, "cuota_desiertos": d / (d + len(xs)) if (d + len(xs)) else None})
escribir("cierre_competencia.csv", comp)

# 2. Calendario por quincenas
cal = collections.defaultdict(lambda: [0, 0.0]); tot = collections.defaultdict(lambda: [0, 0.0])
for x in filas:
    q = (x["mes"] - 1) * 2 + (2 if x["dia"] >= 16 else 1)
    cal[(x["anio"], q)][0] += 1; cal[(x["anio"], q)][1] += x["imp"]
    tot[x["anio"]][0] += 1; tot[x["anio"]][1] += x["imp"]
calendario = []
for a in sorted(tot):
    for q in range(1, 25):
        n, imp = cal.get((a, q), [0, 0.0])
        calendario.append({"anio": a, "quincena": q, "etiqueta": f"{MESES[(q - 1) // 2]} {'1-15' if q % 2 else '16-fin'}",
                           "adjudicaciones": n, "importe_eur": imp, "cuota_n": n / tot[a][0], "cuota_importe": imp / tot[a][1] if tot[a][1] else 0.0})
escribir("calendario_cierre.csv", calendario)

# 3. Presupuesto y cierre
igae = collections.defaultdict(float)
for r in csv.DictReader((SALIDA / "igae_defensa.csv").open(encoding="utf-8-sig"), delimiter=";"):
    if r["programa"] == "Total sección" and r["medida"] in ("creditos_definitivos", "obligaciones_reconocidas_netas"):
        igae[(int(r["anio"]), r["medida"])] += float(r["importe_eur"])
pres = []
for a in sorted(tot):
    cr, ob = igae.get((a, "creditos_definitivos")), igae.get((a, "obligaciones_reconocidas_netas"))
    nd = [x for x in filas if x["anio"] == a and x["mes"] >= 11]
    ult = [x for x in filas if x["anio"] == a and x["mes"] == 12 and x["dia"] >= 16]
    pres.append({"anio": a, "situacion_presupuesto": SITUACION.get(a, ""),
                 "creditos_caps26_meur": cr / 1e6 if cr else None, "obligaciones_caps26_meur": ob / 1e6 if ob else None,
                 "ejecucion": ob / cr if cr and ob else None, "credito_sin_ejecutar_meur": (cr - ob) / 1e6 if cr and ob else None,
                 "cuota_nov_dic_importe": sum(x["imp"] for x in nd) / tot[a][1], "cuota_nov_dic_n": len(nd) / tot[a][0],
                 "cuota_ultima_quincena_importe": sum(x["imp"] for x in ult) / tot[a][1], "cuota_ultima_quincena_n": len(ult) / tot[a][0],
                 "nota": "Año en curso: sin noviembre ni diciembre" if a == 2026 else ""})
escribir("presupuesto_y_cierre.csv", pres)
print("cierre_competencia.csv, calendario_cierre.csv y presupuesto_y_cierre.csv escritos")
