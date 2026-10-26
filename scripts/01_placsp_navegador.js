// Paso 1 · Extraer de la PLACSP las licitaciones del Ministerio de Defensa, un fichero anual cada vez
//
// Se ejecuta en la consola del navegador con una pestaña abierta en
// https://contrataciondelsectorpublico.gob.es (mismo origen que los ficheros, que no se guardan en disco).
// Ficheros: licitacionesPerfilesContratanteCompleto3_AAAA.zip (sindicación 643, licitaciones de los
// perfiles del contratante, sin contratos menores). El fichero del año AAAA contiene las entradas
// publicadas o actualizadas durante ese año.
//
// Uso:
//   __gd.procesar(2019); __gd.procesar(2020)   // descarga en paralelo, análisis de uno en uno
//   __gd.resumen()                              // progreso de todos los años
//   __gd.guardar(2019)                          // «Guardar como» placsp_defensa_registros_2019.jsonl.gz
//
// Qué guarda: cada licitación de órganos del Ministerio de Defensa (los que tienen «Ministerio de Defensa»
// en su jerarquía) con su última versión dentro del fichero, y las bajas del feed. En los ficheros antiguos
// (2017, 2018) la mayoría de las entradas no trae la jerarquía del órgano, así que se guardan también las
// entradas sin jerarquía de órganos de la Administración General del Estado (DIR3 que empieza por E, o sin
// DIR3 pero con nombre militar) y un inventario de todos los órganos con su DIR3. La rama se asigna después
// en 03_unir_registros.py, y la unión entre años (versión más reciente de cada licitación) también: así
// diciembre de un año se completa con lo publicado en enero del siguiente.
//
// Privacidad: no se guardan nombres de adjudicatarios. El NIF del adjudicatario se convierte en una huella
// SHA-256 con una clave aleatoria que solo vive en el almacenamiento local de este navegador.
//
// Resultado de las ejecuciones (23/10/2026): 2017 · 93.068 entradas, 19.540 licitaciones guardadas;
// 2018 · 156.186 entradas, 21.202 licitaciones guardadas. Sin errores de lectura.

window.__gd = window.__gd || {};
__gd.jobs = __gd.jobs || {};
__gd.PREFIJO = 'https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/';
__gd.corto = (s) => (s && s.startsWith(__gd.PREFIJO)) ? s.slice(__gd.PREFIJO.length) : s;
__gd.RX = /defensa|ej[eé]rcito|armada|militar|fuerzas armadas|arsenal|intendencia|intendente|mando de|cuartel general|guardia real|isfas|invied|unidad militar de emergencias|estado mayor|aeródromo|base aérea|ala \d|aérea/i;

__gd.sal = function () {
  let s = localStorage.getItem('gd_sal_v1');
  if (!s) { const b = crypto.getRandomValues(new Uint8Array(32)); s = Array.from(b, x => x.toString(16).padStart(2, '0')).join(''); localStorage.setItem('gd_sal_v1', s); }
  return s;
};
__gd.huella = async function (nif) {
  if (!nif) return null;
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(__gd.sal() + '|' + nif.trim().toUpperCase()));
  return Array.from(new Uint8Array(d).slice(0, 6), x => x.toString(16).padStart(2, '0')).join('');
};

// Turno de análisis: las descargas van en paralelo, pero se analiza un fichero cada vez.
__gd.cola = __gd.cola || Promise.resolve();
__gd.turno = function () { const prev = __gd.cola; let release; __gd.cola = new Promise(r => release = r); return prev.then(() => release); };

__gd.resumen = function () {
  const o = {};
  for (const [a, J] of Object.entries(__gd.jobs)) o[a] = { phase: J.phase, MB: Math.round(J.bytes / 1048576), files: J.filesDone + '/' + J.filesTotal, errores: J.errors.length, salidaMB: J.out ? +(J.out.size / 1048576).toFixed(1) : null };
  return o;
};

__gd.procesar = async function (anio) {
  const J = __gd.jobs[anio] = { anio, version: 3, phase: 'downloading', bytes: 0, filesTotal: 0, filesDone: 0, entries: 0, defEntries: 0, candEntries: 0, deleted: 0, errors: [], startedAt: Date.now() };
  try {
    // 1. Descarga en memoria
    const r = await fetch(location.origin + '/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3_' + anio + '.zip', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    J.lastModified = r.headers.get('last-modified');
    const reader = r.body.getReader(); const parts = []; let batch = [], bb = 0;
    for (;;) { const { done, value } = await reader.read(); if (done) break; batch.push(value); bb += value.byteLength; J.bytes += value.byteLength; if (bb >= 64 * 1048576) { parts.push(new Blob(batch)); batch = []; bb = 0; } }
    if (batch.length) parts.push(new Blob(batch));
    const blob = new Blob(parts, { type: 'application/zip' });
    J.phase = 'esperando-turno';
    const liberar = await __gd.turno();
    try {
      // 2. Directorio central del zip (ZIP64)
      J.phase = 'reading-zip'; J.zipBytes = blob.size;
      const ab = async (s, e) => new DataView(await blob.slice(s, e).arrayBuffer());
      const u64 = (dv, o) => dv.getUint32(o, true) + dv.getUint32(o + 4, true) * 4294967296;
      const tailLen = Math.min(blob.size, 70000);
      const tail = await ab(blob.size - tailLen, blob.size);
      let eocd = -1;
      for (let i = tailLen - 22; i >= 0; i--) { if (tail.getUint32(i, true) === 0x06054b50) { eocd = i; break; } }
      if (eocd < 0) throw new Error('EOCD not found');
      let nEntries = tail.getUint16(eocd + 10, true), cdSize = tail.getUint32(eocd + 12, true), cdOff = tail.getUint32(eocd + 16, true);
      if (nEntries === 0xFFFF || cdSize === 0xFFFFFFFF || cdOff === 0xFFFFFFFF) {
        const loc = eocd - 20;
        if (tail.getUint32(loc, true) !== 0x07064b50) throw new Error('ZIP64 locator missing');
        const z64off = u64(tail, loc + 8); const z = await ab(z64off, z64off + 56);
        nEntries = u64(z, 32); cdSize = u64(z, 40); cdOff = u64(z, 48);
      }
      const cd = await ab(cdOff, cdOff + cdSize);
      const files = []; let p = 0; const dec = new TextDecoder();
      for (let k = 0; k < nEntries; k++) {
        if (cd.getUint32(p, true) !== 0x02014b50) throw new Error('bad CD at ' + k);
        const method = cd.getUint16(p + 10, true);
        let comp = cd.getUint32(p + 20, true), unc = cd.getUint32(p + 24, true);
        const nl = cd.getUint16(p + 28, true), el = cd.getUint16(p + 30, true), cl = cd.getUint16(p + 32, true);
        let lho = cd.getUint32(p + 42, true);
        const name = dec.decode(new Uint8Array(cd.buffer, cd.byteOffset + p + 46, nl));
        let q = p + 46 + nl; const qe = q + el;
        while (q + 4 <= qe) {
          const hid = cd.getUint16(q, true), hs = cd.getUint16(q + 2, true); let r2 = q + 4;
          if (hid === 1) { if (unc === 0xFFFFFFFF) { unc = u64(cd, r2); r2 += 8; } if (comp === 0xFFFFFFFF) { comp = u64(cd, r2); r2 += 8; } if (lho === 0xFFFFFFFF) { lho = u64(cd, r2); r2 += 8; } }
          q += 4 + hs;
        }
        files.push({ name, method, comp, unc, lho }); p += 46 + nl + el + cl;
      }
      const atoms = files.filter(f => /\.atom$/i.test(f.name));
      J.filesTotal = atoms.length; J.zipEntries = files.length; J.uncompressedBytes = atoms.reduce((s, f) => s + f.unc, 0);

      // 3. Análisis de cada fichero Atom
      J.phase = 'parsing';
      const kid = (e, n) => { if (!e) return null; for (const c of e.children) if (c.localName === n) return c; return null; };
      const kids = (e, n) => e ? Array.from(e.children).filter(c => c.localName === n) : [];
      const tx = e => e ? e.textContent.trim() : null;
      const num = s => { if (s == null || s === '') return null; const v = Number(s); return Number.isFinite(v) ? v : null; };
      const recs = new Map(), dels = new Map(), inv = new Map();
      for (const f of atoms) {
        try {
          const lh = await ab(f.lho, f.lho + 30);
          if (lh.getUint32(0, true) !== 0x04034b50) throw new Error('bad LH');
          const start = f.lho + 30 + lh.getUint16(26, true) + lh.getUint16(28, true);
          let stream = blob.slice(start, start + f.comp).stream();
          if (f.method === 8) stream = stream.pipeThrough(new DecompressionStream('deflate-raw')); else if (f.method !== 0) throw new Error('method ' + f.method);
          const doc = new DOMParser().parseFromString(await new Response(stream).text(), 'application/xml');
          for (const e of doc.documentElement.children) {
            if (e.localName === 'deleted-entry') { J.deleted++; const ref = __gd.corto(e.getAttribute('ref')), w = e.getAttribute('when'); if (!dels.has(ref) || dels.get(ref) < w) dels.set(ref, w); continue; }
            if (e.localName !== 'entry') continue;
            J.entries++;
            const cfs = kid(e, 'ContractFolderStatus'); if (!cfs) continue;
            const lcp = kid(cfs, 'LocatedContractingParty'); if (!lcp) continue;
            const party = kid(lcp, 'Party');
            const chain = [tx(kid(kid(party, 'PartyName'), 'Name'))];
            let pp = kid(lcp, 'ParentLocatedParty');
            while (pp) { chain.push(tx(kid(kid(pp, 'PartyName'), 'Name'))); pp = kid(pp, 'ParentLocatedParty'); }
            let dir3 = null, idp = null;
            for (const pi of kids(party, 'PartyIdentification')) { const idEl = kid(pi, 'ID'); const sch = idEl && idEl.getAttribute('schemeName'); if (sch === 'DIR3') dir3 = tx(idEl); if (sch === 'ID_PLATAFORMA') idp = tx(idEl); }
            const ik = chain.join(' < ') + '|' + (dir3 || '') + '|' + (idp || '');
            const io = inv.get(ik); if (io) io.n++; else inv.set(ik, { cad: chain, dir3, idp, n: 1 });
            const esDef = chain.some(n => n && /^ministerio de defensa$/i.test(n));
            if (esDef) J.defEntries++;
            else {
              if (chain.length > 1) continue;
              if (!((!dir3 || dir3.startsWith('E')) || __gd.RX.test(chain[0] || ''))) continue;
              J.candEntries++;
            }
            const id = __gd.corto(tx(kid(e, 'id'))), upd = tx(kid(e, 'updated'));
            const prev = recs.get(id); if (prev && prev.upd >= upd) continue;   // última versión dentro del fichero
            const proj = kid(cfs, 'ProcurementProject'), ba = kid(proj, 'BudgetAmount'), tp = kid(cfs, 'TenderingProcess'), per = kid(proj, 'PlannedPeriod');
            const dm = kid(per, 'DurationMeasure');
            const res = [];
            for (const t of kids(cfs, 'TenderResult')) {
              const atp = kid(t, 'AwardedTenderedProject'), lmt = kid(atp, 'LegalMonetaryTotal'), c = kid(t, 'Contract'), wp = kid(t, 'WinningParty');
              let nif = null;
              for (const pi of kids(wp, 'PartyIdentification')) { const v = tx(kid(pi, 'ID')); if (v) { nif = v; break; } }
              res.push({ cod: tx(kid(t, 'ResultCode')), fAdj: tx(kid(t, 'AwardDate')), fForm: tx(kid(c, 'IssueDate')), lote: tx(kid(atp, 'ProcurementProjectLotID')),
                sin: num(tx(kid(lmt, 'TaxExclusiveAmount'))), con: num(tx(kid(lmt, 'PayableAmount'))), nOf: num(tx(kid(t, 'ReceivedTenderQuantity'))),
                pyme: tx(kid(t, 'SMEAwardedIndicator')), adj: nif });   // el NIF se sustituye por su huella antes de exportar
            }
            recs.set(id, {
              t: 'l', h: esDef ? 1 : 0, id, upd, exp: tx(kid(cfs, 'ContractFolderID')), est: tx(kid(cfs, 'ContractFolderStatusCode')),
              cad: chain, dir3, idp,
              tipo: tx(kid(proj, 'TypeCode')), sub: tx(kid(proj, 'SubTypeCode')), cpv: tx(kid(kid(proj, 'RequiredCommodityClassification'), 'ItemClassificationCode')),
              obj: tx(kid(proj, 'Name')) || tx(kid(e, 'title')),
              pres: num(tx(kid(ba, 'TaxExclusiveAmount'))), presIva: num(tx(kid(ba, 'TotalAmount'))), vest: num(tx(kid(ba, 'EstimatedOverallContractAmount'))),
              dur: num(tx(dm)), durU: dm ? dm.getAttribute('unitCode') : null, ini: tx(kid(per, 'StartDate')), fin: tx(kid(per, 'EndDate')),
              proc: tx(kid(tp, 'ProcedureCode')), urg: tx(kid(tp, 'UrgencyCode')), sist: tx(kid(tp, 'ContractingSystemCode')),
              res
            });
          }
        } catch (err) { J.errors.push(f.name + ': ' + String(err)); }
        J.filesDone++; J.uniqueRecs = recs.size;
      }

      // 4. Huellas de adjudicatarios y fichero de salida (JSON Lines comprimido)
      J.phase = 'exporting';
      const cache = new Map(); const lines = []; let nDef = 0;
      for (const rec of recs.values()) {
        if (rec.h) nDef++;
        for (const x of rec.res) { if (x.adj) { if (!cache.has(x.adj)) cache.set(x.adj, await __gd.huella(x.adj)); x.adj = cache.get(x.adj); } }
        lines.push(JSON.stringify(rec));
      }
      for (const [r2, w] of dels) lines.push(JSON.stringify({ t: 'b', id: r2, when: w }));
      for (const o of inv.values()) lines.push(JSON.stringify({ t: 'o', ...o }));
      const cab = { t: 'cabecera', version: 3, anio, fichero: 'licitacionesPerfilesContratanteCompleto3_' + anio + '.zip', lastModified: J.lastModified,
        zipBytes: J.zipBytes, ficherosAtom: J.filesTotal, entradas: J.entries, entradasDefensaJerarquia: J.defEntries, entradasCandidatasSinJerarquia: J.candEntries,
        licitacionesDefensaJerarquia: nDef, licitacionesGuardadas: recs.size, organos: inv.size, errores: J.errors.length, generado: new Date().toISOString() };
      const texto = JSON.stringify(cab) + '\n' + lines.join('\n') + '\n';
      J.out = await new Response(new Blob([texto]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
      J.cabecera = cab;
      J.phase = 'ready';
    } finally { liberar(); }
  } catch (err) { J.phase = 'error'; J.errors.push(String(err && err.stack || err)); }
};

__gd.guardar = function (anio) {
  const J = __gd.jobs[anio]; if (!J || !J.out) return 'sin resultado';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(J.out);
  a.download = 'placsp_defensa_registros_' + anio + '.jsonl.gz';
  document.body.appendChild(a); a.click(); a.remove();
  return a.download;
};
