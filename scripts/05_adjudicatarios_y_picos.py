"""Paso 5 · Adjudicatarios (huellas anónimas) y picos de cierre clasificados.

Uso (desde la carpeta del proyecto, después del paso 3):
    python scripts/05_adjudicatarios_y_picos.py registros scripts/intermedios/codigos_codice.json sucesos_2017_2026.csv .

Salidas:
  adjudicatarios_anual.csv   rotación (repiten, nuevos, vuelven, se van), concentración (HHI y top 10) y peso de los habituales,
                             noviembre-diciembre frente a enero-octubre, sobre el importe ordinario (sin programas especiales)
  adjudicatarios_perfil.csv  especialización por divisiones CPV, SOLO AGREGADA: perfil x tramo de importe, con medianas y
                             supresión de las celdas con menos de 5 adjudicatarios (no lleva huellas)
  privado/adjudicatarios_perfil_detalle.csv
                             el mismo perfil adjudicatario a adjudicatario, con huella. Es de uso interno: con la huella, el
                             importe y los expedientes públicos se puede reidentificar a una empresa. No se publica ni lo lee Power BI.
  picos_cierre.csv           picos de cierre por rama y órgano, clasificados con las reglas de abajo

Alcance: sección 14 sin establecimiento de acuerdos marco ni contratos menores. Nunca se guardan ni muestran nombres de adjudicatarios.

Reglas de los picos:

Pico: cuota de noviembre-diciembre en el importe del año >= 2 veces la línea base (33,3 %) y al menos 1 M€ en nov-dic.
Clasificación (en este orden):
  Explicable · programas especiales  si sin los expedientes de >= 100 M€ la cuota baja de 33,3 %.
  Explicable · emergencia            si >= 50 % del importe ordinario de nov-dic es tramitación de emergencia.
  Explicable · renovación anual      si >= 50 % del importe ordinario de nov-dic son contratos periódicos (servicios o consumos
                                      corrientes: combustible, alimentación, energía, seguros, limpieza, hostelería) de 12 meses o más
                                      que el mismo órgano adjudica en nov-dic con la misma clase CPV (5 dígitos) en 3 años o más.
                                      Comprar material en diciembre todos los años NO cuenta como renovación: es el patrón que se estudia.
  Crédito tardío                      si el crédito del año llegó a mitad de año (presupuesto publicado en julio en 2017 y 2018;
                                      Plan Industrial y Tecnológico de abril de 2025 para la Secretaría de Estado de Defensa):
                                      Explicable con cuota ordinaria < 50 %, A vigilar con 50 % o más.
  Sin explicar                        si la cuota ordinaria >= 50 %.
  A vigilar                           el resto (cuota ordinaria entre 33,3 % y 50 %).
Un solo expediente con >= 50 % del importe ordinario de nov-dic o >= 50 % por negociado sin publicidad se anota en «notas»; no cambia la clase.
"""
import collections, csv, importlib.util, re, sys
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location("unir", Path(__file__).with_name("03_unir_registros.py"))
u = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(u)
REGISTROS, CODIGOS, SUCESOS, SALIDA = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])

CPV2 = {'03':'Agricultura','09':'Combustibles','14':'Minería','15':'Alimentos','16':'Maquinaria agrícola','18':'Ropa y equipo personal','19':'Cuero y textil','22':'Impresos','24':'Química','30':'Equipo de oficina e informático','31':'Material eléctrico','32':'Radio, TV y telecomunicaciones','33':'Material médico','34':'Transporte (vehículos, aeronaves, buques)','35':'Seguridad, defensa y policía','37':'Ocio y deporte','38':'Instrumental y laboratorio','39':'Mobiliario y limpieza','41':'Agua','42':'Maquinaria industrial','43':'Minería y construcción (maquinaria)','44':'Materiales de construcción','45':'Obras','48':'Software','50':'Reparación y mantenimiento','51':'Instalación','55':'Hostelería','60':'Transporte (servicios)','63':'Servicios de transporte auxiliares','64':'Correos y telecomunicaciones','65':'Suministros públicos','66':'Finanzas y seguros','70':'Inmobiliarios','71':'Arquitectura e ingeniería','72':'Servicios TI','73':'I+D','75':'Administración y defensa','76':'Petróleo y gas','77':'Agricultura y jardinería','79':'Servicios a empresas','80':'Formación','85':'Sanidad y social','90':'Limpieza y medio ambiente','92':'Cultura y deporte','98':'Otros servicios'}

# ---- Adjudicaciones a nivel de lote (en memoria; no se escriben)
ultimos, bajas, cab, org = u.leer(REGISTROS)
cat = u.construir_catalogo(org, ultimos)
canon = u.nombres_canonicos([r for r in ultimos.values() if u.asignar_rama(r, cat)[0] not in (None, u.NO_DEFENSA)])
FILAS = []; _tot_exp = collections.defaultdict(float)
for rec in ultimos.values():
    rama, _ = u.asignar_rama(rec, cat)
    if rama in (None, u.NO_DEFENSA) or rec.get('est') == 'ANUL': continue
    b = bajas.get(rec['id'])
    if b and b > rec['upd'] and (date.fromisoformat(b[:10]) - date.fromisoformat(rec['upd'][:10])).days <= u.MAX_DIAS_RETIRADA: continue
    nm = re.sub(r"\s+", " ", (rec.get('cad') or [''])[0] or "").strip()
    for r in rec.get('res') or []:
        if r.get('cod') not in u.OK or not r.get('fAdj') or (r.get('sin') is None and r.get('con') is None): continue
        f = r['fAdj']
        if not (f[:4].isdigit() and u.SERIE_DESDE <= int(f[:4]) <= 2026): continue
        imp = r['con'] if r.get('con') is not None else (r.get('sin') or 0) * 1.21
        _tot_exp[(rec['id'], f[:4])] += imp
        FILAS.append(dict(id=rec['id'], anio=int(f[:4]), mes=int(f[5:7]), rama=rama, s14=rama in u.SECCION_14, marco=rec.get('sist') in ('1', '2'), menor=bool(rec.get('menor')),
                          organo=u.ALIAS_ORGANO.get(canon.get(nm, nm), canon.get(nm, nm)), cpv=rec.get('cpv') or '', tipo=rec.get('tipo'), proc=rec.get('proc'),
                          urg=rec.get('urg'), adj=r.get('adj'), nOf=r.get('nOf'), dur=rec.get('dur'), durU=rec.get('durU'), imp=imp))
_factores = u.cargar_factores(SALIDA)
for x in FILAS: x['esp'] = _tot_exp[(x['id'], str(x['anio']))] * _factores.get(x['anio'], 1.0) >= u.UMBRAL_PROGRAMA_ESPECIAL

# ---- Perfil de especialización (adjudicatarios con adjudicaciones en 3 años o más, 2017-2025)
_por=collections.defaultdict(list)
for x in FILAS:
    if x['s14'] and not x['marco'] and not x['menor'] and x['anio']<=2025 and x['adj']: _por[x['adj']].append(x)
TODOS=[]
for h,xs in _por.items():
    yrs={x['anio'] for x in xs}
    if len(yrs)<3: continue
    c=collections.Counter(x['cpv'][:2] for x in xs if x['cpv'])
    n=sum(c.values()) or 1; imp=sum(x['imp'] for x in xs)
    TODOS.append(dict(h=h,anios=len(yrs),n=len(xs),div=len(c),top=(c.most_common(1)[0][1]/n if c else 0.0),imp=imp,
        nd=sum(1 for x in xs if x['mes']>=11)/len(xs), nd_imp=sum(x['imp'] for x in xs if x['mes']>=11)/imp if imp else 0.0,
        nsp=sum(1 for x in xs if x['proc']=='3')/len(xs), emer=sum(1 for x in xs if x['urg']=='3')/len(xs),
        ofertas1=sum(1 for x in xs if x['nOf']==1)/len(xs), organos=len({x['organo'] for x in xs}), ramas=len({x['rama'] for x in xs}), divs=c))

# ---- Rotación, concentración y perfil

F=[x for x in FILAS if x['s14'] and not x['marco'] and not x['menor'] and x['adj']]
anios_por=collections.defaultdict(set)
for x in F: anios_por[x['adj']].add(x['anio'])
def fmt(v): return f"{v:.4f}".replace('.',',') if isinstance(v,float) else v
def hhi(imps):
    t=sum(imps.values()); return sum((v/t)**2 for v in imps.values())*10000 if t else 0.0
def top_share(imps,k):
    t=sum(imps.values()); return sum(sorted(imps.values(),reverse=True)[:k])/t if t else 0.0
filas=[]
for y in range(2017,2027):
    act={h for h,v in anios_por.items() if y in v}; prev={h for h,v in anios_por.items() if y-1 in v}
    nuevos={h for h in act if min(anios_por[h])==y}; vuelven={h for h in act-prev if min(anios_por[h])<y}
    xs=[x for x in F if x['anio']==y and not x['esp']]
    per={'año':collections.Counter(),'nov-dic':collections.Counter(),'ene-oct':collections.Counter()}
    for x in xs:
        per['año'][x['adj']]+=x['imp']; per['nov-dic' if x['mes']>=11 else 'ene-oct'][x['adj']]+=x['imp']
    # habituales = adjudicatario con adjudicación en alguno de los dos años anteriores
    hab=lambda h: bool(anios_por[h] & {y-1,y-2})
    def cuota_hab(sel):
        t=sum(x['imp'] for x in sel); n=len(sel)
        return (sum(x['imp'] for x in sel if hab(x['adj']))/t if t else 0.0, sum(1 for x in sel if hab(x['adj']))/n if n else 0.0)
    nd=[x for x in xs if x['mes']>=11]; eo=[x for x in xs if x['mes']<11]
    hn,hnn=cuota_hab(nd); he,hen=cuota_hab(eo)
    if y==2026: hn=hnn=''
    filas.append({'anio':y,'adjudicatarios_activos':len(act),'repiten_del_anio_anterior':len(act&prev),'nuevos':len(nuevos),
        'vuelven_tras_hueco':len(vuelven),'se_van':len(prev-act) if 2017<y<2026 else '',
        'hhi_ordinario_anio':hhi(per['año']),'hhi_ordinario_nov_dic':hhi(per['nov-dic']) if y<2026 else '','hhi_ordinario_ene_oct':hhi(per['ene-oct']),
        'cuota_top10_ordinario_anio':top_share(per['año'],10),'cuota_top10_ordinario_nov_dic':top_share(per['nov-dic'],10) if y<2026 else '','cuota_top10_ordinario_ene_oct':top_share(per['ene-oct'],10),
        'cuota_habituales_importe_nov_dic':hn if y>=2019 else '','cuota_habituales_importe_ene_oct':he if y>=2019 else '',
        'cuota_habituales_n_nov_dic':hnn if y>=2019 else '','cuota_habituales_n_ene_oct':hen if y>=2019 else '',
        'nota':'Año en curso (a 23/10/2026)' if y==2026 else ('Sin año anterior: no hay repetidores ni salidas' if y==2017 else ('Habituales sin calcular: faltan dos años previos' if y==2018 else ''))})
with open(SALIDA / 'adjudicatarios_anual.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(filas[0]),delimiter=';'); w.writeheader()
    for r in filas: w.writerow({k:fmt(v) for k,v in r.items()})
# perfil por adjudicatario con 3 años o más
perfil=[]
for r in TODOS:
    tipo='Dispersa' if (r['top']<.4 and r['div']>=6) else 'Especialista' if r['top']>=.8 else 'Intermedia'
    senales=[]
    if r['nd']>=.4: senales.append('≥40 % de sus adjudicaciones en nov-dic')
    if r['nsp']>=.5: senales.append('≥50 % negociado sin publicidad')
    if r['emer']>.1: senales.append('>10 % por emergencia')
    perfil.append({'huella':r['h'],'perfil':tipo,'anios_con_adjudicacion':r['anios'],'adjudicaciones':r['n'],'divisiones_cpv':r['div'],
        'cuota_division_principal':r['top'],'divisiones_principales':' · '.join(CPV2.get(d,d) for d,_ in r['divs'].most_common(3)),
        'importe_con_iva_eur':r['imp'],'cuota_nov_dic_n':r['nd'],'cuota_nov_dic_importe':r['nd_imp'],'cuota_negociado_sin_publicidad':r['nsp'],
        'cuota_emergencia':r['emer'],'cuota_oferta_unica':r['ofertas1'],'organos':r['organos'],'ramas':r['ramas'],
        'senales':' · '.join(senales),'n_senales':len(senales)})
(SALIDA / 'privado').mkdir(exist_ok=True)
with open(SALIDA / 'privado' / 'adjudicatarios_perfil_detalle.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(perfil[0]),delimiter=';'); w.writeheader()
    for r in perfil: w.writerow({k:(f"{v:.2f}".replace('.',',') if k=='importe_con_iva_eur' else fmt(v)) for k,v in r.items()})

# Agregado publicable: perfil x tramo de importe; las celdas con menos de K_MIN adjudicatarios se suprimen.
K_MIN = 5
TRAMOS = [(0, 1e6, '1. Menos de 1 M€'), (1e6, 1e7, '2. De 1 a 10 M€'), (1e7, 1e8, '3. De 10 a 100 M€'), (1e8, float('inf'), '4. 100 M€ o más')]
def tramo(v):
    for a, b, t in TRAMOS:
        if a <= v < b: return t
import statistics
grupos = collections.defaultdict(list)
for r in perfil:
    grupos[(r['perfil'], tramo(r['importe_con_iva_eur']))].append(r)
    grupos[(r['perfil'], '0. Todos')].append(r)
agregado = []
ORDEN = {'Especialista': 1, 'Intermedia': 2, 'Dispersa': 3}
for (pf, tr), rs in sorted(grupos.items(), key=lambda x: (ORDEN[x[0][0]], x[0][1])):
    n = len(rs); ok = n >= K_MIN
    med = lambda k: statistics.median(r[k] for r in rs) if ok else ''
    agregado.append({'perfil': pf, 'orden_perfil': ORDEN[pf], 'tramo_importe': tr, 'adjudicatarios': n if ok else '',
        'suprimido': 'No' if ok else f'Sí (menos de {K_MIN})',
        'mediana_anios': med('anios_con_adjudicacion'), 'mediana_adjudicaciones': med('adjudicaciones'), 'mediana_divisiones_cpv': med('divisiones_cpv'),
        'mediana_cuota_division_principal': med('cuota_division_principal'), 'mediana_cuota_nov_dic_n': med('cuota_nov_dic_n'),
        'mediana_cuota_oferta_unica': med('cuota_oferta_unica'), 'mediana_cuota_negociado_sin_publicidad': med('cuota_negociado_sin_publicidad'),
        'mediana_organos': med('organos'), 'con_alguna_senal': sum(1 for r in rs if r['n_senales']) if ok else ''})
with open(SALIDA / 'adjudicatarios_perfil.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(agregado[0]),delimiter=';'); w.writeheader()
    for r in agregado: w.writerow({k:(f"{v:.4f}".replace('.',',') if isinstance(v,float) else v) for k,v in r.items()})

# ---- Picos de cierre

F=[x for x in FILAS if x['s14'] and not x['marco'] and not x['menor'] and x['anio']<=2025]
SUC=list(csv.DictReader(open(SUCESOS,encoding='utf-8-sig'),delimiter=';'))
LB=2/12
CREDITO_TARDIO={(2017,None):'P01 (PGE 2017 publicados el 28 de junio)',(2018,None):'P02 (PGE 2018 publicados el 4 de julio)',
                (2025,'Secretaría de Estado de Defensa'):'P08 (Plan Industrial y Tecnológico, abril de 2025)'}
def credito_tardio(anio,rama):
    return CREDITO_TARDIO.get((anio,None)) or CREDITO_TARDIO.get((anio,rama))
# Renovaciones anuales: (órgano, CPV a 5 dígitos) con adjudicación en nov-dic en 3 años o más
CPV_PERIODICOS={'09','15','55','65','66','90'}
def periodico(x):
    meses=(x['dur'] or 0)*(12 if x['durU']=='ANN' else 1 if x['durU']=='MON' else 0)
    return (x['tipo']=='2' or x['cpv'][:2] in CPV_PERIODICOS) and meses>=12
_anios_nd=collections.defaultdict(set)
for x in F:
    if x['mes']>=11 and not x['esp'] and x['cpv'] and periodico(x): _anios_nd[(x['organo'],x['cpv'][:5])].add(x['anio'])
RECURRENTE={k for k,v in _anios_nd.items() if len(v)>=3}
def sucesos_del(anio, rama):
    ids=[]
    for s in SUC:
        ini=s['fecha_inicio']; fin=s['fecha_fin'] or ini
        if ini[:4]<=str(anio)<=fin[:4] and (ini<=f'{anio}-12-31' and fin>=f'{anio}-09-01'):
            ids.append(s['id'])
    return ids
def evaluar(xs, nivel, anio, rama, organo):
    tot=sum(x['imp'] for x in xs); nd=[x for x in xs if x['mes']>=11]; tnd=sum(x['imp'] for x in nd)
    if tot<=0 or tnd<1e6 or tnd/tot<2*LB: return None
    ordx=[x for x in xs if not x['esp']]; tord=sum(x['imp'] for x in ordx); ndo=[x for x in ordx if x['mes']>=11]; tndo=sum(x['imp'] for x in ndo)
    cuota_ord=tndo/tord if tord else 0.0
    emer=sum(x['imp'] for x in ndo if x['urg']=='3')/tndo if tndo else 0.0
    porexp=collections.Counter()
    for x in ndo: porexp[x['id']]+=x['imp']
    mayor=porexp.most_common(1)[0][1]/tndo if tndo else 0.0
    nsp=sum(x['imp'] for x in ndo if x['proc']=='3')/tndo if tndo else 0.0
    ids=sucesos_del(anio,rama)
    recur=sum(x['imp'] for x in ndo if periodico(x) and (x['organo'],x['cpv'][:5]) in RECURRENTE)/tndo if tndo else 0.0
    ct=credito_tardio(anio,rama)
    if cuota_ord<2*LB: cl,mot='Explicable','Programas especiales: sin los expedientes de 100 M€ o más la cuota de nov-dic baja de 33,3 %'
    elif emer>=.5: cl,mot='Explicable','Emergencia: la mitad o más del importe ordinario de nov-dic se tramitó por emergencia'
    elif recur>=.5: cl,mot='Explicable',f'Renovación anual: el {100*recur:.0f} % del importe ordinario de nov-dic se adjudica en esas fechas cada año (misma clase CPV y órgano en 3 años o más)'
    elif ct and cuota_ord<.5: cl,mot='Explicable',f'Crédito tardío: {ct}'
    elif ct: cl,mot='A vigilar',f'Crédito tardío ({ct}), pero la cuota ordinaria de nov-dic es del 50 % o más'
    elif cuota_ord>=.5: cl,mot='Sin explicar','La cuota ordinaria de nov-dic es del 50 % o más y ninguna regla la explica'
    else: cl,mot='A vigilar','Cuota ordinaria de nov-dic entre 33,3 % y 50 %'
    notas=[]
    if mayor>=.5 and cl!='Explicable': notas.append(f'un solo expediente supone el {100*mayor:.0f} % del importe ordinario de nov-dic')
    if nsp>=.5: notas.append(f'{100*nsp:.0f} % del importe ordinario de nov-dic por negociado sin publicidad')
    return {'nivel':nivel,'anio':anio,'rama':rama,'organo':organo,'importe_anio_eur':tot,'importe_nov_dic_eur':tnd,'cuota_nov_dic':tnd/tot,
            'importe_ordinario_anio_eur':tord,'importe_ordinario_nov_dic_eur':tndo,'cuota_nov_dic_ordinaria':cuota_ord,
            'cuota_emergencia_nov_dic':emer,'cuota_mayor_expediente_nov_dic':mayor,'cuota_negociado_sp_nov_dic':nsp,'cuota_renovacion_anual_nov_dic':recur,
            'clasificacion':cl,'motivo':mot,'notas':' · '.join(notas),'sucesos_del_ultimo_cuatrimestre':' '.join(ids)}
g_r=collections.defaultdict(list); g_o=collections.defaultdict(list)
for x in F: g_r[(x['anio'],x['rama'])].append(x); g_o[(x['anio'],x['rama'],x['organo'])].append(x)
out=[]
for (a,r),xs in sorted(g_r.items()):
    e=evaluar(xs,'Rama',a,r,'(toda la rama)')
    if e: out.append(e)
for (a,r,o),xs in sorted(g_o.items()):
    e=evaluar(xs,'Órgano',a,r,o)
    if e: out.append(e)
def fmt(k,v):
    if isinstance(v,float): return (f"{v:.2f}" if k.endswith('_eur') else f"{v:.4f}").replace('.',',')
    return v
with open(SALIDA / 'picos_cierre.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(out[0]),delimiter=';'); w.writeheader()
    for r in out: w.writerow({k:fmt(k,v) for k,v in r.items()})
print('adjudicatarios_anual.csv, adjudicatarios_perfil.csv (agregado), privado/adjudicatarios_perfil_detalle.csv y picos_cierre.csv escritos')
