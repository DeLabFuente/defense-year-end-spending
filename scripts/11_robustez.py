"""Paso 11 · Robustez: ¿se sostienen las conclusiones si cambian las reglas?

Uso (desde la carpeta del proyecto, después de los pasos 3, 7 y 8):
    python scripts/11_robustez.py registros scripts/intermedios/codigos_codice.json .

Repite, con las licitaciones de Defensa (serie del proyecto) y del resto de la Administración General del Estado, las
cifras del resumen cambiando una regla cada vez: el umbral de programa especial, los años que entran, la tramitación
urgente o de emergencia, los contratos basados en acuerdos marco, las mayores adjudicaciones de cada año y la forma de
agregar los años. El calendario de la orden de cierre se repite con ventanas de 3, 5, 7 y 10 días hábiles y en importe,
a partir de ordenes_cierre_dias.csv (paso 8). Solo agregados; no usa adjudicatarios.

Salidas:
  robustez.csv             una fila por variante: peso de noviembre-diciembre en Defensa y en el resto de la AGE, años en
                           que Defensa queda por encima, salto de la oferta única y del negociado sin publicidad en el
                           cierre y peso del cierre en los servicios
  robustez_calendario.csv  caída tras el plazo de fiscalización del compromiso con distintas ventanas, en número e importe
"""
import collections
import csv
import gzip
import importlib.util
import json
import statistics
import sys
from datetime import date
from pathlib import Path

_aqui = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("lb", _aqui / "07_linea_base_sector_publico.py")
lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lb)
u = lb.u

ANIOS = list(range(u.SERIE_DESDE, 2026))
BLOQUES = ("Defensa", "Resto de la AGE")
INF = float("inf")


def filas_base(registros):
    """Una fila por resultado adjudicado de las licitaciones de Defensa (sección 14) y del resto de la AGE, 2017-2025."""
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
                    inv[o["k"]] = lb.clasificar(o, cat)[0]
                elif t == "l":
                    prev = ultimos.get(o["id"])
                    if prev is None or prev[0] < o["upd"]:
                        ultimos[o["id"]] = (o["upd"], inv[o["o"]], o.get("est"), o.get("proc"), o.get("urg"), o.get("sist"),
                                            o.get("res") or [], lb.TIPO.get(o.get("tipo"), "Otros"))
                elif t == "b":
                    if o["id"] not in bajas or bajas[o["id"]] < o["when"]:
                        bajas[o["id"]] = o["when"]
    filas, tot_exp = [], collections.defaultdict(float)
    for rid, (upd, c, est, proc, urg, sist, res, tipo) in ultimos.items():
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
        for r in res:
            cod, f, sin, con, nof = (r + [None] * 5)[:5]
            if cod not in u.OK or not f or (sin is None and con is None) or not f[:4].isdigit() or int(f[:4]) not in ANIOS:
                continue
            imp = con if con is not None else (sin or 0) * 1.21
            anio = int(f[:4])
            tot_exp[(rid, anio)] += imp
            filas.append({"id": rid, "anio": anio, "nd": int(f[5:7]) >= 11, "bloque": bloque, "imp": imp, "nof": nof,
                          "nsp": proc == "3", "urg": urg in ("2", "3"), "basado": proc == "7" or sist in ("3", "4"), "tipo": tipo})
    for x in filas:
        x["exp"] = tot_exp[(x["id"], x["anio"])]
    return filas


def medir(filas, umbral, factores, anios, agregar="conjunto"):
    """Cifras del resumen con un umbral de programa especial (M€ de 2025) y unos años dados."""
    ordinarias = [x for x in filas if x["anio"] in anios and x["exp"] * factores.get(x["anio"], 1.0) < umbral]
    acc = collections.defaultdict(float)
    for x in ordinarias:
        k = (x["bloque"], x["anio"])
        p = "nd" if x["nd"] else "eo"
        acc[k + ("imp", p)] += x["imp"]
        if x["tipo"] == "Servicios":
            acc[k + ("serv", p)] += x["imp"]
        acc[k + ("n", p)] += 1
        acc[k + ("nsp", p)] += x["nsp"]
        if x["nof"]:
            acc[k + ("nof", p)] += 1
            acc[k + ("ou", p)] += x["nof"] == 1

    def cuota(b, a_s, campo):
        nd = sum(acc[(b, a, campo, "nd")] for a in a_s)
        eo = sum(acc[(b, a, campo, "eo")] for a in a_s)
        return nd / (nd + eo) if nd + eo else None

    def salto(b, a_s, num, den):
        v = []
        for p in ("nd", "eo"):
            d = sum(acc[(b, a, den, p)] for a in a_s)
            if not d:
                return None
            v.append(sum(acc[(b, a, num, p)] for a in a_s) / d)
        return (v[0] - v[1]) * 100

    def valor(f):
        if agregar == "conjunto":
            return f(anios)
        vs = [f([a]) for a in anios]
        vs = [v for v in vs if v is not None]
        return statistics.median(vs) if vs else None

    r = {}
    for b, x in zip(BLOQUES, ("def", "age")):
        r[f"cuota_{x}"] = valor(lambda a_s: cuota(b, a_s, "imp"))
        r[f"ou_{x}"] = valor(lambda a_s: salto(b, a_s, "ou", "nof"))
        r[f"nsp_{x}"] = valor(lambda a_s: salto(b, a_s, "nsp", "n"))
        r[f"serv_{x}"] = valor(lambda a_s: cuota(b, a_s, "serv"))
    encima = [a for a in anios if (cuota("Defensa", [a], "imp") or 0) > (cuota("Resto de la AGE", [a], "imp") or 0)]
    r["encima"] = f"{len(encima)} de {len(anios)}"
    r["n_def"] = sum(1 for x in ordinarias if x["bloque"] == "Defensa")
    return r


def sin_mayores(filas, k):
    """Quita las k mayores adjudicaciones ordinarias de cada bloque y año (por debajo de 100 M€)."""
    fuera = set()
    grupos = collections.defaultdict(list)
    for i, x in enumerate(filas):
        grupos[(x["bloque"], x["anio"])].append((x["imp"], i))
    for g in grupos.values():
        fuera.update(i for _, i in sorted(g, reverse=True)[:k])
    return [x for i, x in enumerate(filas) if i not in fuera]


def calendario(salida):
    serie, habiles, plazos = collections.defaultdict(lambda: [0, 0.0]), collections.defaultdict(list), {}
    with (salida / "ordenes_cierre_dias.csv").open(encoding="utf-8-sig") as fh:
        for x in csv.DictReader(fh, delimiter=";"):
            a = int(x["anio"])
            serie[(x["bloque"], x["fecha"])] = [int(x["adjudicaciones"]), float(x["importe_ordinario_eur"].replace(",", "."))]
            if x["bloque"] == "Defensa" and x["dia_habil"] == "Sí":
                habiles[a].append(x["fecha"])
            if x["dias_hasta_fiscalizacion_compromiso"] == "0":
                plazos[a] = x["fecha"]
    out = []
    for v in (3, 5, 7, 10):
        for medida, i in (("adjudicaciones", 0), ("importe", 1)):
            fila = {"orden": len(out), "ventana_dias_habiles": v, "medida": medida}
            for b in BLOQUES:
                cocientes, caen = [], 0
                for a in sorted(plazos):
                    h = sorted(habiles[a])
                    pos = max(j for j, d in enumerate(h) if d <= plazos[a])
                    antes = sum(serie[(b, d)][i] for d in h[max(0, pos - v + 1):pos + 1])
                    despues = sum(serie[(b, d)][i] for d in h[pos + 1:pos + 1 + v])
                    if antes:
                        cocientes.append(despues / antes)
                        caen += despues < antes
                x = "defensa" if b == "Defensa" else "resto_age"
                fila[f"cambio_mediano_{x}"] = statistics.median(cocientes) - 1
                fila[f"anios_que_cae_{x}"] = f"{caen} de {len(cocientes)}"
            out.append(fila)
    return out


def fmt(v, dec=4):
    if v is None:
        return ""
    return f"{v:.{dec}f}".replace(".", ",") if isinstance(v, float) else v


def main():
    registros, salida = Path(sys.argv[1]), Path(sys.argv[3])
    sys.stdout.reconfigure(errors="replace")
    factores = u.cargar_factores(salida)
    filas = filas_base(registros)
    base = u.UMBRAL_PROGRAMA_ESPECIAL
    variantes = [
        ("Base", "Umbral de programa especial de 100 M€, 2017-2025, años sumados", filas, base, ANIOS, "conjunto"),
        ("Umbral 50 M€", "Programa especial desde 50 M€ por expediente y año", filas, 50e6, ANIOS, "conjunto"),
        ("Umbral 200 M€", "Programa especial desde 200 M€", filas, 200e6, ANIOS, "conjunto"),
        ("Umbral 500 M€", "Programa especial desde 500 M€", filas, 500e6, ANIOS, "conjunto"),
        ("Sin excluir programas", "Todo el importe, también los expedientes de 100 M€ o más", filas, INF, ANIOS, "conjunto"),
        ("Sin 2025", "2017-2024", filas, base, ANIOS[:-1], "conjunto"),
        ("Sin 2018 ni 2025", "Los dos años con más programas especiales en el cierre", filas, base,
         [a for a in ANIOS if a not in (2018, 2025)], "conjunto"),
        ("Desde 2019", "Solo los años con la ley de contratos de 2017 plenamente aplicada", filas, base, ANIOS[2:], "conjunto"),
        ("Sin urgencia ni emergencia", "Sin tramitación urgente o de emergencia (covid, DANA, misiones)",
         [x for x in filas if not x["urg"]], base, ANIOS, "conjunto"),
        ("Sin contratos basados en acuerdos marco", "Sin derivados de acuerdo marco ni de sistema dinámico",
         [x for x in filas if not x["basado"]], base, ANIOS, "conjunto"),
        ("Sin las 10 mayores de cada año", "Quitando las 10 mayores adjudicaciones ordinarias de cada bloque y año",
         sin_mayores([x for x in filas if x["exp"] * factores.get(x["anio"], 1.0) < base], 10), base, ANIOS, "conjunto"),
        ("Mediana de los años", "Cada cifra, calculada año a año y resumida con la mediana", filas, base, ANIOS, "mediana"),
    ]
    filas_out = []
    for nombre, desc, datos, umbral, anios, agregar in variantes:
        r = medir(datos, umbral, factores, anios, agregar)
        filas_out.append({
            "orden": len(filas_out), "variante": nombre, "descripcion": desc, "adjudicaciones_defensa": r["n_def"],
            "cuota_nov_dic_defensa": r["cuota_def"], "cuota_nov_dic_resto_age": r["cuota_age"],
            "diferencia_puntos": None if None in (r["cuota_def"], r["cuota_age"]) else (r["cuota_def"] - r["cuota_age"]) * 100,
            "anios_defensa_por_encima": r["encima"],
            "salto_oferta_unica_defensa_puntos": r["ou_def"], "salto_oferta_unica_resto_age_puntos": r["ou_age"],
            "salto_negociado_defensa_puntos": r["nsp_def"], "salto_negociado_resto_age_puntos": r["nsp_age"],
            "cuota_servicios_defensa": r["serv_def"], "cuota_servicios_resto_age": r["serv_age"],
        })
    with (salida / "robustez.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas_out[0]), delimiter=";")
        w.writeheader()
        for x in filas_out:
            w.writerow({k: fmt(v, 2 if k.endswith("_puntos") else 6) for k, v in x.items()})
    cal = calendario(salida)
    with (salida / "robustez_calendario.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cal[0]), delimiter=";")
        w.writeheader()
        for x in cal:
            w.writerow({k: fmt(v) for k, v in x.items()})
    for x in filas_out:
        print(f'{x["variante"]:42} Def {x["cuota_nov_dic_defensa"]:.3f} AGE {x["cuota_nov_dic_resto_age"]:.3f} '
              f'({x["anios_defensa_por_encima"]})  OU {x["salto_oferta_unica_defensa_puntos"]:+.1f}/{x["salto_oferta_unica_resto_age_puntos"]:+.1f}  '
              f'NSP {x["salto_negociado_defensa_puntos"]:+.1f}/{x["salto_negociado_resto_age_puntos"]:+.1f}  '
              f'serv {x["cuota_servicios_defensa"]:.3f}/{x["cuota_servicios_resto_age"]:.3f}')
    for x in cal:
        print(f'{x["ventana_dias_habiles"]:>2} días, {x["medida"]:14} Defensa {x["cambio_mediano_defensa"]:+.0%} ({x["anios_que_cae_defensa"]})  '
              f'resto de la AGE {x["cambio_mediano_resto_age"]:+.0%} ({x["anios_que_cae_resto_age"]})')


if __name__ == "__main__":
    main()
