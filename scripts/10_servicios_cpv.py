"""Paso 10 · ¿Qué se contrata en el cierre? Defensa frente al resto de la AGE por código CPV.

Uso (desde la carpeta del proyecto, después del paso 3):
    python scripts/10_servicios_cpv.py registros scripts/intermedios/codigos_codice.json .

Mismas licitaciones y reglas que la línea base (paso 7): versión más reciente de cada licitación, sin anuladas ni
retiradas, resultados adjudicados o formalizados en el mes de su fecha de adjudicación, sin establecimiento de acuerdos
marco ni de sistemas dinámicos, sin contratos menores, y programa especial = expediente de 100 M€ o más (con IVA, euros
de 2025) en un año. Solo Defensa (serie del proyecto, sección 14) y el resto de la Administración General del Estado.

CPV: el código principal de cada licitación (Vocabulario Común de Contratos Públicos, Reglamento (CE) 213/2008), agregado
a división (2 dígitos) y grupo (3 dígitos). Solo agregados: ni órganos, ni expedientes, ni adjudicatarios.

Salidas:
  servicios_cpv.csv                por año, periodo (ene-oct / nov-dic), bloque, tipo de contrato y grupo CPV: adjudicaciones,
                                   importe total, de programas especiales y ordinario, y sumas para medir la competencia
  servicios_cpv_division.csv       servicios 2017-2025 por división CPV (las que pesan al menos un 1 % en Defensa, el resto
                                   agrupado): peso del cierre en Defensa y en el resto de la AGE, aportación a la diferencia,
                                   años en que Defensa queda por encima y salto de la oferta única en el cierre
  servicios_cpv_mantenimiento.csv  lo mismo para los grupos de la división 50 (reparación y mantenimiento)
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

_aqui = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("lb", _aqui / "07_linea_base_sector_publico.py")
lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lb)
u = lb.u

DIVISIONES = {
    "03": "Productos de la agricultura, ganadería, pesca y silvicultura",
    "09": "Derivados del petróleo, combustibles, electricidad y otras fuentes de energía",
    "14": "Productos de la minería y metales de base",
    "15": "Alimentos, bebidas y tabaco",
    "16": "Maquinaria agrícola",
    "18": "Prendas de vestir, calzado, artículos de viaje y accesorios",
    "19": "Piel, textiles, plástico y caucho",
    "22": "Impresos y productos relacionados",
    "24": "Productos químicos",
    "30": "Máquinas, equipo y artículos de oficina y de informática",
    "31": "Máquinas, aparatos y material eléctrico; iluminación",
    "32": "Equipos de radio, televisión, comunicaciones y telecomunicaciones",
    "33": "Equipamiento y artículos médicos, farmacéuticos y de higiene personal",
    "34": "Equipos de transporte y productos auxiliares",
    "35": "Equipo de seguridad, extinción de incendios, policía y defensa",
    "37": "Instrumentos musicales, artículos deportivos, juegos y juguetes",
    "38": "Equipo de laboratorio, óptico y de precisión",
    "39": "Mobiliario, electrodomésticos y productos de limpieza",
    "41": "Agua recogida y depurada",
    "42": "Maquinaria industrial",
    "43": "Maquinaria para la minería y equipo de construcción",
    "44": "Estructuras y materiales de construcción",
    "45": "Trabajos de construcción",
    "48": "Paquetes de software y sistemas de información",
    "50": "Servicios de reparación y mantenimiento",
    "51": "Servicios de instalación (excepto software)",
    "55": "Servicios de hostelería y restauración",
    "60": "Servicios de transporte (excepto residuos)",
    "63": "Servicios auxiliares del transporte; agencias de viajes",
    "64": "Servicios de correos y telecomunicaciones",
    "65": "Servicios públicos (agua, gas, electricidad)",
    "66": "Servicios financieros y de seguros",
    "70": "Servicios inmobiliarios",
    "71": "Servicios de arquitectura, construcción, ingeniería e inspección",
    "72": "Servicios de tecnologías de la información",
    "73": "Servicios de investigación y desarrollo",
    "75": "Servicios de administración pública, defensa y seguridad social",
    "76": "Servicios relacionados con la industria del gas y del petróleo",
    "77": "Servicios agrícolas, forestales y de jardinería",
    "79": "Servicios a empresas (asesoría, selección de personal, imprenta, seguridad…)",
    "80": "Servicios de enseñanza y formación",
    "85": "Servicios de salud y asistencia social",
    "90": "Servicios de alcantarillado, basura, limpieza y medio ambiente",
    "92": "Servicios de esparcimiento, culturales y deportivos",
    "98": "Otros servicios comunitarios, sociales o personales",
}
SIN_CPV = "Sin CPV"
GRUPOS_50 = {
    "500": "Reparación y mantenimiento (sin especificar)",
    "501": "Vehículos y equipo conexo",
    "502": "Aeronaves, ferrocarriles, carreteras y equipo marino",
    "503": "Ordenadores, equipo de oficina, telecomunicaciones y audiovisual",
    "504": "Equipo médico y de precisión",
    "505": "Bombas, válvulas, grifos, contenedores de metal y maquinaria",
    "506": "Equipo de seguridad y defensa",
    "507": "Instalaciones de edificios",
    "508": "Otros servicios de reparación y mantenimiento",
}
HASTA = 2025          # años completos que entran en los resúmenes
PESO_MINIMO = 0.01    # divisiones con menos peso en los servicios de Defensa se agrupan en «Resto de servicios»


def resumen(cubo, clave, filtro):
    """Servicios 2017-HASTA agregados por `clave(grupo)`: importes, cierre, oferta única y años por encima."""
    t = collections.defaultdict(lambda: collections.defaultdict(float))
    for (anio, periodo, bloque, tipo, grupo), v in cubo.items():
        if tipo != "Servicios" or anio > HASTA or not filtro(grupo):
            continue
        for k in (clave(grupo), "Total"):
            d = t[k]
            d[(bloque, periodo, "imp")] += v[1] - v[3]
            d[(bloque, periodo, "n")] += v[0] - v[2]
            d[(bloque, periodo, "nof")] += v[4]
            d[(bloque, periodo, "ou")] += v[5]
            d[(bloque, anio, periodo, "imp")] += v[1] - v[3]
    out = {}
    for k, d in t.items():
        r = {}
        for b, x in (("Defensa", "def"), ("Resto de la AGE", "age")):
            tot = d[(b, "Ene-oct", "imp")] + d[(b, "Nov-dic", "imp")]
            r[f"imp_{x}"] = tot
            r[f"n_{x}"] = d[(b, "Ene-oct", "n")] + d[(b, "Nov-dic", "n")]
            r[f"cuota_{x}"] = d[(b, "Nov-dic", "imp")] / tot if tot else None
            ou = [d[(b, p, "ou")] / d[(b, p, "nof")] if d[(b, p, "nof")] else None for p in ("Nov-dic", "Ene-oct")]
            r[f"ou_{x}"] = ou[0] - ou[1] if None not in ou else None
        encima = validos = 0
        for a in range(u.SERIE_DESDE, HASTA + 1):
            c = []
            for b in ("Defensa", "Resto de la AGE"):
                tot = d[(b, a, "Ene-oct", "imp")] + d[(b, a, "Nov-dic", "imp")]
                c.append(d[(b, a, "Nov-dic", "imp")] / tot if tot else None)
            if None not in c:
                validos += 1
                encima += c[0] > c[1]
        r["encima"] = f"{encima} de {validos}"
        out[k] = r
    tot_def, tot_age = out["Total"]["imp_def"], out["Total"]["imp_age"]
    for r in out.values():
        r["peso_def"] = r["imp_def"] / tot_def if tot_def else 0
        r["peso_age"] = r["imp_age"] / tot_age if tot_age else 0
    return out


def escribir_resumen(ruta, filas, campo_codigo, campo_nombre):
    campos = ["orden", campo_codigo, campo_nombre, "importe_defensa_meur", "peso_en_servicios_defensa", "adjudicaciones_defensa",
              "cuota_nov_dic_defensa", "cuota_nov_dic_resto_age", "diferencia_puntos", "aportacion_a_la_diferencia_puntos",
              "anios_defensa_por_encima", "salto_oferta_unica_defensa_puntos", "salto_oferta_unica_resto_age_puntos"]
    f4 = lambda x: "" if x is None else f"{x:.6f}".replace(".", ",")
    pt = lambda x: "" if x is None else f"{x * 100:.1f}".replace(".", ",")
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(campos)
        for i, (codigo, nombre, r) in enumerate(filas):
            dif = None if None in (r["cuota_def"], r["cuota_age"]) else r["cuota_def"] - r["cuota_age"]
            apor = None if dif is None else r["peso_def"] * dif
            w.writerow([i, codigo, nombre, f"{r['imp_def'] / 1e6:.1f}".replace(".", ","), f4(r["peso_def"]), int(r["n_def"]),
                        f4(r["cuota_def"]), f4(r["cuota_age"]), pt(dif), pt(apor), r["encima"],
                        pt(r["ou_def"]), pt(r["ou_age"])])


def main():
    registros, salida = Path(sys.argv[1]), Path(sys.argv[3])
    sys.stdout.reconfigure(errors="replace")
    carpeta = registros / "sector_publico"
    factores = u.cargar_factores(salida)
    s14, otros_def = lb.ids_defensa(registros)
    cat = lb.catalogo(carpeta)
    procesados = sorted({int(m.group(1)) for f in carpeta.glob("placsp_sector_publico_2*.jsonl.gz")
                         if (m := re.search(r"_(\d{4})\.jsonl", f.name))})
    ultimo = max(procesados)

    ultimos, bajas = {}, {}
    for f in sorted(carpeta.glob("placsp_sector_publico_2*.jsonl.gz")):
        inv = {}
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            fh.readline()
            for linea in fh:
                o = json.loads(linea)
                t = o["t"]
                if t == "o":
                    inv[o["k"]] = lb.clasificar(o, cat)[0]
                elif t == "l":
                    prev = ultimos.get(o["id"])
                    if prev is None or prev[0] < o["upd"]:
                        ultimos[o["id"]] = (o["upd"], inv[o["o"]], o.get("est"), o.get("proc"), o.get("urg"), o.get("sist"),
                                            o.get("res") or [], lb.TIPO.get(o.get("tipo"), "Otros"), o.get("cpv") or "")
                elif t == "b":
                    if o["id"] not in bajas or bajas[o["id"]] < o["when"]:
                        bajas[o["id"]] = o["when"]

    filas, tot_exp = [], collections.defaultdict(float)
    for rid, (upd, c, est, proc, urg, sist, res, tipo, cpv) in ultimos.items():
        if (False, rid) in s14:
            bloque = "Defensa"
        elif (False, rid) in otros_def or c == lb.DEFENSA or c[0] != "Resto de la AGE":
            continue
        else:
            bloque = "Resto de la AGE"
        if est == "ANUL" or sist in ("1", "2"):
            continue
        b = bajas.get(rid)
        if b and b > upd and (date.fromisoformat(b[:10]) - date.fromisoformat(upd[:10])).days <= u.MAX_DIAS_RETIRADA:
            continue
        grupo = cpv[:3] if re.fullmatch(r"\d{8}", cpv) else SIN_CPV
        for r in res:
            cod, f, sin, con, nof = (r + [None] * 5)[:5]
            if cod not in u.OK or not f or (sin is None and con is None):
                continue
            if not (f[:4].isdigit() and u.SERIE_DESDE <= int(f[:4]) <= ultimo):
                continue
            imp = con if con is not None else (sin or 0) * 1.21
            anio = int(f[:4])
            tot_exp[(rid, anio)] += imp
            filas.append((rid, anio, "Nov-dic" if int(f[5:7]) >= 11 else "Ene-oct", bloque, tipo, grupo, imp, nof, proc, urg))
    del ultimos, bajas

    cubo = collections.defaultdict(lambda: [0, 0.0, 0, 0.0, 0, 0, 0, 0])
    for rid, anio, periodo, bloque, tipo, grupo, imp, nof, proc, urg in filas:
        v = cubo[(anio, periodo, bloque, tipo, grupo)]
        v[0] += 1
        v[1] += imp
        if tot_exp[(rid, anio)] * factores.get(anio, 1.0) >= u.UMBRAL_PROGRAMA_ESPECIAL:
            v[2] += 1
            v[3] += imp
            continue
        if nof:
            v[4] += 1
            v[5] += nof == 1
        v[6] += proc == "3"
        v[7] += urg in ("2", "3")

    campos = ["anio", "periodo", "bloque", "tipo_contrato", "cpv_division", "division", "cpv_grupo", "n_adjudicaciones",
              "importe_con_iva_eur", "n_programa_especial", "importe_programa_especial_eur", "n_ordinario", "importe_ordinario_eur",
              "n_con_ofertas", "n_oferta_unica", "n_negociado_sin_publicidad", "n_urgente_o_emergencia"]
    orden_b = {"Defensa": 0, "Resto de la AGE": 1}
    with (salida / "servicios_cpv.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(campos)
        for (anio, periodo, bloque, tipo, grupo), v in sorted(cubo.items(), key=lambda x: (x[0][0], x[0][1], orden_b[x[0][2]], lb.TIPOS.index(x[0][3]), x[0][4])):
            div = grupo[:2] if grupo != SIN_CPV else SIN_CPV
            nombre = DIVISIONES.get(div, SIN_CPV if div == SIN_CPV else "Otra división")
            fila = [anio, periodo, bloque, tipo, div, nombre, grupo, v[0], v[1], v[2], v[3], v[0] - v[2], v[1] - v[3], v[4], v[5], v[6], v[7]]
            w.writerow([f"{x:.2f}".replace(".", ",") if isinstance(x, float) else x for x in fila])

    # Resumen por división (servicios) y descomposición de la diferencia con el resto de la AGE
    division = lambda g: g[:2] if g != SIN_CPV else SIN_CPV
    base = resumen(cubo, division, lambda g: True)
    principales = sorted((k for k in base if k != "Total" and base[k]["peso_def"] >= PESO_MINIMO), key=lambda k: -base[k]["imp_def"])
    resto = [k for k in base if k not in principales and k != "Total"]
    agrupado = resumen(cubo, lambda g: division(g) if division(g) in principales else "Resto", lambda g: True)
    filas = [("Total", "Todos los servicios", base["Total"])]
    filas += [(k, DIVISIONES.get(k, SIN_CPV), base[k]) for k in principales]
    if resto:
        filas.append(("Resto", "Resto de servicios", agrupado["Resto"]))
    escribir_resumen(salida / "servicios_cpv_division.csv", filas, "cpv_division", "division")
    dentro = sum(r["peso_def"] * (r["cuota_def"] - r["cuota_age"]) for k, r in base.items()
                 if k != "Total" and r["cuota_def"] is not None and r["cuota_age"] is not None)
    composicion = sum((r["peso_def"] - r["peso_age"]) * r["cuota_age"] for k, r in base.items()
                      if k != "Total" and r["cuota_age"] is not None)
    print(f"Servicios {u.SERIE_DESDE}-{HASTA}: cierre Defensa {base['Total']['cuota_def']:.1%}, resto de la AGE {base['Total']['cuota_age']:.1%}; "
          f"de la diferencia, {dentro * 100:.1f} puntos salen de concentrar más dentro de cada división y "
          f"{composicion * 100:.1f} de comprar otra mezcla de servicios")
    mant = resumen(cubo, lambda g: g, lambda g: g.startswith("50"))
    filas = [("50", "Toda la reparación y mantenimiento", mant["Total"])]
    filas += [(k, GRUPOS_50.get(k, k), mant[k]) for k in sorted((k for k in mant if k != "Total"), key=lambda k: -mant[k]["imp_def"])]
    escribir_resumen(salida / "servicios_cpv_mantenimiento.csv", filas, "cpv_grupo", "grupo")

    control = collections.defaultdict(float)
    for (anio, periodo, bloque, tipo, grupo), v in cubo.items():
        control[(bloque, anio)] += v[1] - v[3]
    for (bloque, anio), imp in sorted(control.items()):
        print(f"{bloque:16} {anio}  importe ordinario {imp / 1e6:10.1f} M€")


if __name__ == "__main__":
    main()
