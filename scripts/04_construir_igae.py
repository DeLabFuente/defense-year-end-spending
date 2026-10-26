"""Paso 4 · CSV de la IGAE para Power BI (denominador de la cobertura), con todos los años disponibles.

Uso (desde la carpeta del proyecto): python scripts/04_construir_igae.py scripts/intermedios .

Lee scripts/intermedios/igae_defensa_AAAA.json (uno por informe de diciembre de la IGAE; cada informe
trae su año y el anterior para los cuadros por secciones) y escribe igae_defensa.csv.
"""
import csv
import json
import re
import sys
from pathlib import Path

base, out = Path(sys.argv[1]), Path(sys.argv[2])
CAPS = {"2": "2 Gastos corrientes en bienes y servicios", "6": "6 Inversiones reales"}
filas, vistos = [], set()
for f in sorted(base.glob("igae_defensa_*.json"), reverse=True):      # el informe más reciente manda
    d = json.loads(f.read_text(encoding="utf-8"))
    informe = re.search(r"MENSUAL[^)]*?(\d{2}-\d{2})", d["fuente"]).group(1)
    for clave, bloque in d.items():
        m = re.match(r"capitulo_(\d)_secciones_p(\d+)", clave)
        if m:
            cap, pag = m.groups()
            for k, v in bloque.items():
                mm = re.match(r"(creditos_definitivos|obligaciones_reconocidas_netas|pagos)_(\d{4})", k)
                if not mm:
                    continue
                medida, anio = mm.group(1), int(mm.group(2))
                if anio < 2017:
                    continue
                key = ("Total sección", cap, anio, medida)
                if key in vistos:
                    continue
                vistos.add(key)
                filas.append(["14 Defensa", "Total sección", CAPS[cap], anio, medida, v * 1000, f"IGAE MENSUAL {informe}, p. {pag}"])
        m = re.match(r"orn_.*programas.*_p(\d+)", clave)
        if m:
            pag = m.group(1)
            anio = 2000 + int(informe[-2:])
            for prog, caps in bloque.items():
                if prog.startswith("DEFENSA"):
                    continue
                for c in ("2", "6"):
                    if f"cap{c}" in caps:
                        key = (prog, c, anio, "obligaciones_reconocidas_netas")
                        if key in vistos:
                            continue
                        vistos.add(key)
                        filas.append(["14 Defensa", prog, CAPS[c], anio, "obligaciones_reconocidas_netas", caps[f"cap{c}"] * 1000, f"IGAE MENSUAL {informe}, p. {pag}"])
filas.sort(key=lambda r: (r[3], r[1] != "Total sección", r[1], r[2], r[4]))
with (out / "igae_defensa.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["seccion", "programa", "capitulo", "anio", "medida", "importe_eur", "fuente"])
    w.writerows(filas)
tot = {}
for r in filas:
    if r[1] == "Total sección" and r[4] == "obligaciones_reconocidas_netas":
        tot[r[3]] = tot.get(r[3], 0) + r[5]
print(len(filas), "filas; obligaciones caps. 2 y 6 (M€):", {a: round(v / 1e6, 1) for a, v in sorted(tot.items())})
