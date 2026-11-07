// O leitor em JavaScript devolve o mesmo que o motor? Compara linha a linha, por tabela e município,
// nos dois modos, e repete em Firefox e WebKit. Depois testa em Parquet real no GitHub Pages direto.
import { chromium, firefox, webkit } from 'playwright-core'; import fs from 'node:fs'; import zlib from 'node:zlib';
const saida = process.argv[2];
const P = 'http://127.0.0.1:8931';
const TABELAS = [
  { arq: 'BR_res_mes.parquet', uf: 'uf35_res_mes.parquet', coluna: 'mun_res', chaves: ['mes'] },
  { arq: 'BR_res_tri_capitulo.parquet', uf: 'uf35_res_tri_capitulo.parquet', coluna: 'mun_res', chaves: ['tri', 'capitulo'] },
  { arq: 'BR_res_ano_faixa12_sexo.parquet', uf: 'uf35_res_ano_faixa12_sexo.parquet', coluna: 'mun_res', chaves: ['faixa12', 'sexo'] },
  { arq: 'BR_hosp_tri_capitulo.parquet', uf: 'uf35_hosp_tri_capitulo.parquet', coluna: 'mun_hosp', chaves: ['tri', 'capitulo'] },
];
const MUNICIPIOS = ['354850', '355030', '350635', '350010', '350730', '353760'];
const ordena = (l, chaves) => [...l].sort((a, b) => chaves.map(k => String(a[k])).join('|').localeCompare(chaves.map(k => String(b[k])).join('|')));
const normal = v => (v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v)) ? null : (typeof v === 'number' ? Math.round(v * 100) / 100 : v));
const compara = (a, b, chaves) => {
  if (a.length !== b.length) return `linhas ${a.length} x ${b.length}`;
  const x = ordena(a, chaves), y = ordena(b, chaves);
  for (let i = 0; i < x.length; i++) for (const k of Object.keys(y[i])) {
    if (normal(x[i][k]) !== normal(y[i][k])) return `linha ${i} coluna ${k}: ${x[i][k]} x ${y[i][k]}`;
  }
  return null;
};
const res = { comparacoes: 0, iguais: 0, diferencas: [], navegadores: {}, host_real: {} };

// Referência: o motor
const b = await chromium.launch({ channel: 'chrome', headless: true });
const page = await (await b.newContext()).newPage();
await page.goto(P + '/index.html');
await page.addScriptTag({ url: '/app.js', type: 'module' });
await page.addScriptTag({ url: '/hyp.js', type: 'module' });
await page.waitForFunction(() => window.iniciar && window.__leitorPronto);
await page.evaluate(() => window.iniciar({ forceFullHTTPReads: false }));
const referencia = {};
for (const t of TABELAS) for (const m of MUNICIPIOS) {
  const url = `${P}/dados/${t.arq}`;
  const tam = fs.statSync('site/dados/' + t.arq).size;
  const motor = await page.evaluate(async ({ url, coluna, m }) => {
    const r = await window.__con.query(`SELECT * FROM read_parquet('${url}') WHERE ${coluna}='${m}'`);
    return JSON.parse(JSON.stringify(r.toArray().map(x => x.toJSON()), (k, v) => (typeof v === 'bigint' ? Number(v) : v)));
  }, { url, coluna: t.coluna, m });
  referencia[t.arq + m] = motor;
  const parcial = await page.evaluate(a => window.lerParcial(a), { url, byteLength: tam, coluna: t.coluna, valor: m });
  const inteiroBR = await page.evaluate(a => window.lerInteiro(a), { url, coluna: t.coluna, valor: m });
  const inteiroUF = await page.evaluate(a => window.lerInteiro(a), { url: `${P}/dados/${t.uf}`, coluna: t.coluna, valor: m });
  for (const [modo, r] of [['parcial', parcial], ['inteiro BR', inteiroBR], ['inteiro UF', inteiroUF]]) {
    res.comparacoes++;
    const dif = compara(motor, r.linhas, t.chaves);
    if (dif) res.diferencas.push({ tabela: t.arq, municipio: m, modo, dif }); else res.iguais++;
  }
}
// Oculto continua oculto: conta os nulos no arquivo inteiro
const nulos = await page.evaluate(async url => {
  const r = await window.lerInteiro({ url });
  const motor = await window.__con.query(`SELECT count(*) c, count(*) FILTER (internacoes IS NULL) n, count(*) FILTER (oculto) o FROM read_parquet('${url}')`);
  const m = motor.toArray()[0].toJSON();
  return { linhas_leitor: r.total, nulos_leitor: r.linhas.filter(l => l.internacoes === null).length, ocultas_leitor: r.linhas.filter(l => l.oculto === true).length, linhas_motor: Number(m.c), nulos_motor: Number(m.n), ocultas_motor: Number(m.o) };
}, `${P}/dados/BR_res_tri_capitulo.parquet`);
res.nulos = nulos;
console.log('comparações', res.comparacoes, 'iguais', res.iguais, JSON.stringify(res.diferencas.slice(0, 5)));
console.log('nulos', JSON.stringify(nulos));
await b.close();

// Formatos: arquivo sem compressão com o leitor sem descompressor
const tamanhoLeve = ['hyp.js', 'hyp_leve.js'];
res.bundles = {};
for (const f of tamanhoLeve) {
  // Direto do arquivo: o fetch do Node descomprime, e o tamanho lido dele seria o bruto
  const bruto = fs.readFileSync('site/' + f);
  res.bundles[f] = { gzip_bytes: zlib.gzipSync(bruto, { level: 6 }).length, bruto_bytes: bruto.length };
}
console.log('bundles', JSON.stringify(res.bundles));

// Outros navegadores: mesmo teste, no modo arquivo inteiro e no parcial
for (const [nome, tipo, opcoes] of [['chromium', chromium, { channel: 'chrome', headless: true }], ['firefox', firefox, { headless: true }], ['webkit', webkit, { headless: true }]]) {
  let br;
  try { br = await tipo.launch(opcoes); } catch (e) { res.navegadores[nome] = { erro: String(e).slice(0, 160) }; continue; }
  const pg = await (await br.newContext()).newPage();
  await pg.goto(P + '/index.html');
  await pg.addScriptTag({ url: '/hyp.js', type: 'module' });
  await pg.waitForFunction(() => window.__leitorPronto);
  let ok = 0, total = 0; const erros = [];
  for (const t of TABELAS) for (const m of MUNICIPIOS.slice(0, 3)) {
    const tam = fs.statSync('site/dados/' + t.arq).size;
    for (const [modo, chamada] of [['parcial', { fn: 'lerParcial', a: { url: `${P}/dados/${t.arq}`, byteLength: tam, coluna: t.coluna, valor: m } }], ['inteiro', { fn: 'lerInteiro', a: { url: `${P}/dados/${t.uf}`, coluna: t.coluna, valor: m } }]]) {
      total++;
      try {
        const r = await pg.evaluate(({ fn, a }) => window[fn](a), chamada);
        const dif = compara(referencia[t.arq + m], r.linhas, t.chaves);
        if (dif) erros.push(`${t.arq} ${m} ${modo}: ${dif}`); else ok++;
      } catch (e) { erros.push(`${t.arq} ${m} ${modo}: ${String(e).slice(0, 120)}`); }
    }
  }
  res.navegadores[nome] = { versao: br.version(), iguais: ok, total, erros: erros.slice(0, 3) };
  console.log(nome, JSON.stringify(res.navegadores[nome]));
  await br.close();
}

// Host real: GitHub Pages direto, sem Cloudflare, em navegador real
{
  const U = 'https://idl.uw.edu/mosaic-datasets/data/flights-200k.parquet'; const TAM = 1129931; const LINHAS = 231083;
  const br = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await br.newContext(); const pg = await ctx.newPage();
  const reqs = []; ctx.on('request', r => { if (r.url().endsWith('.parquet')) reqs.push(r); });
  await pg.goto(P + '/index.html'); await pg.addScriptTag({ url: '/hyp.js', type: 'module' });
  await pg.waitForFunction(() => window.__leitorPronto);
  const inteiro = await pg.evaluate(u => window.lerInteiro({ url: u }).then(r => ({ ms: r.ms, total: r.total, status: r.status })), U);
  await pg.addScriptTag({ url: '/hyp_meta.js', type: 'module' });
  await pg.waitForFunction(() => window.lerFaixaReal);
  // Só a primeira linha do erro: as seguintes trazem o endereço do script que o antivírus injeta
  const parcialMeta = await pg.evaluate(({ u, tam }) => window.lerFaixaReal(u, tam), { u: U, tam: TAM }).catch(e => ({ erro: String(e).split('\n')[0].slice(0, 160) }));
  res.host_real = { url: U, linhas_esperadas: LINHAS, origem_da_pagina: 'servidor local, fora da origem do arquivo', inteiro, parcial: parcialMeta };
  const det = [];
  for (const q of reqs) { const resp = await q.response().catch(() => null); const h = await q.allHeaders(); det.push(`${q.method()} ${resp && resp.status()} [${h.range || ''}]`); }
  res.host_real.requisicoes = det;
  console.log('host real', JSON.stringify(res.host_real).slice(0, 700));
  await br.close();
}
fs.writeFileSync(saida, JSON.stringify(res, null, 1));
console.log('FIM');
