"""Paso 2 · Prueba de cobertura 2023: CSV para Power BI, CSV de la IGAE y resumen.

Uso (desde la carpeta del proyecto): python scripts/02_construir_salidas.py scripts/intermedios .


Entradas (en la carpeta pasada como argumento):
  cube_2023.txt          agregado calculado en el navegador a partir de
                         licitacionesPerfilesContratanteCompleto3_2023.zip (PLACSP)
  codigos_codice.json    listas oficiales de códigos CODICE
  igae_defensa_2023.json obligaciones reconocidas de Defensa 2023 (IGAE)
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

base = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else base
cod = json.loads((base / "codigos_codice.json").read_text(encoding="utf-8"))
igae = json.loads((base / "igae_defensa_2023.json").read_text(encoding="utf-8"))
lines = (base / "cube_2023.txt").read_text(encoding="utf-8").strip().split("\n")
ramas = lines[0].split("=", 1)[1].split(";")

SECCION_14 = {"Armada", "Ejército de Tierra", "Ejército del Aire", "Estado Mayor de la Defensa",
              "Secretaría de Estado de Defensa", "Subsecretaría de Defensa"}
lab = lambda t, k: cod[t].get(k, f"Código {k}") if k else "Sin dato"

rows = []
for ln in lines[1:]:
    mes, ri, tipo, proc, urg, sist, n, nexp, sin, con = ln.split("|")
    rama = ramas[int(ri)]
    rows.append({
        "fecha_mes": f"{mes}-01",
        "anio": int(mes[:4]),
        "mes": int(mes[5:7]),
        "rama": rama,
        "en_seccion_14": "Sí" if rama in SECCION_14 else "No",
        "tipo_contrato": lab("tipo", tipo),
        "procedimiento": lab("proc", proc),
        "tramitacion": lab("urg", urg),
        "sistema_contratacion": lab("sist", sist),
        "es_establecimiento_marco": "Sí" if sist in ("1", "2") else "No",
        "n_adjudicaciones": int(n),
        "n_expedientes": int(nexp),
        "importe_sin_iva_eur": float(sin),
        "importe_con_iva_eur": float(con),
    })

csv_path = out / "placsp_defensa_adjudicaciones_2023.csv"
with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
    w.writeheader()
    for r in rows:
        w.writerow({k: (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v) for k, v in r.items()})

M = 1e6
den = {k: v * 1000 for k, v in igae["denominadores"].items()}
sel = lambda **f: [r for r in rows if all(r[k] == v for k, v in f.items())]
tot = lambda rs: sum(r["importe_con_iva_eur"] for r in rs)
cnt = lambda rs: sum(r["n_adjudicaciones"] for r in rs)

s14 = sel(en_seccion_14="Sí")
s14_nm = [r for r in s14 if r["es_establecimiento_marco"] == "No"]
ejercitos = [r for r in s14_nm if r["rama"] != "Secretaría de Estado de Defensa"]

def mensual(rs):
    m = defaultdict(lambda: [0.0, 0])
    for r in rs:
        m[r["mes"]][0] += r["importe_con_iva_eur"]; m[r["mes"]][1] += r["n_adjudicaciones"]
    return {k: (round(v[0] / M, 1), v[1]) for k, v in sorted(m.items())}

def cuota_nd(rs):
    t, c = tot(rs), cnt(rs)
    nd = [r for r in rs if r["mes"] in (11, 12)]
    return {"importe": round(tot(nd) / t, 3), "numero": round(cnt(nd) / c, 3)}

def por(rs, key):
    d = defaultdict(float)
    for r in rs:
        d[r[key]] += r["importe_con_iva_eur"]
    return sorted(((k, round(v / M, 1)) for k, v in d.items()), key=lambda x: -x[1])

summary = {
    "total_todo_MEUR": round(tot(rows) / M, 1),
    "fuera_seccion_14_MEUR": round(tot(sel(en_seccion_14="No")) / M, 1),
    "s14_MEUR": round(tot(s14) / M, 1),
    "s14_establecimiento_marco_MEUR": round(tot([r for r in s14 if r["es_establecimiento_marco"] == "Sí"]) / M, 1),
    "s14_sin_marco_MEUR": round(tot(s14_nm) / M, 1),
    "s14_sin_marco_adjudicaciones": cnt(s14_nm),
    "denominador_cap2_6_MEUR": den["cap2_mas_cap6"] / M,
    "denominador_cap2_6_sin_122B_MEUR": den["cap2_mas_cap6_sin_122B"] / M,
    "ratio_s14_sin_marco_vs_cap2_6": round(tot(s14_nm) / den["cap2_mas_cap6"], 3),
    "ratio_s14_sin_marco_vs_cap2_6_sin_122B": round(tot(s14_nm) / den["cap2_mas_cap6_sin_122B"], 3),
    "ejercitos_EMAD_SUBDEF_sin_marco_MEUR": round(tot(ejercitos) / M, 1),
    "ratio_ejercitos_vs_cap2_6_sin_122B": round(tot(ejercitos) / den["cap2_mas_cap6_sin_122B"], 3),
    "cuota_nov_dic_s14_sin_marco": cuota_nd(s14_nm),
    "cuota_nov_dic_sin_SEDEF": cuota_nd(ejercitos),
    "mensual_s14_sin_marco_MEUR_y_n": mensual(s14_nm),
    "mensual_sin_SEDEF_MEUR_y_n": mensual(ejercitos),
    "s14_sin_marco_por_rama": por(s14_nm, "rama"),
    "s14_sin_marco_por_procedimiento": por(s14_nm, "procedimiento"),
    "s14_sin_marco_por_tipo": por(s14_nm, "tipo_contrato"),
    "s14_sin_marco_por_tramitacion": por(s14_nm, "tramitacion"),
    "filas_csv": len(rows),
}
(base / "resumen_cobertura_2023.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))

# CSV de la IGAE (denominador de la cobertura) ------------------------------
c2, c6 = igae["capitulo_2_secciones_p125"], igae["capitulo_6_secciones_p144"]
igae_rows = []
for anio in (2023, 2022):
    for cap, d in (("2 Gastos corrientes en bienes y servicios", c2), ("6 Inversiones reales", c6)):
        for med in ("creditos_definitivos", "obligaciones_reconocidas_netas", "pagos"):
            igae_rows.append(["14 Defensa", "Total sección", cap, anio, med, d[f"{med}_{anio}"] * 1000,
                              "IGAE MENSUAL 12-23, p. " + ("125" if cap.startswith("2") else "144")])
for prog, d in igae["orn_por_programas_y_capitulos_p97"].items():
    if prog == "DEFENSA_total":
        continue
    for k, capname in (("cap2", "2 Gastos corrientes en bienes y servicios"), ("cap6", "6 Inversiones reales")):
        if k in d:
            igae_rows.append(["14 Defensa", prog, capname, 2023, "obligaciones_reconocidas_netas", d[k] * 1000, "IGAE MENSUAL 12-23, p. 97"])
with (out / "igae_defensa_2023.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["seccion", "programa", "capitulo", "anio", "medida", "importe_eur", "fuente"])
    w.writerows(igae_rows)
