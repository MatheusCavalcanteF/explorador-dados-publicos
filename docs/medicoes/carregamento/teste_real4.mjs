// Consulta filtrada: lê só parte do arquivo no GitHub Pages direto?
// Uso: node teste_real4.mjs <saida.json>. Precisa de servidor.mjs na porta 8931 e de site/app_teste.js.
import { chromium } from 'playwright-core';
import { writeFileSync } from 'node:fs';
const P = 'http://127.0.0.1:8931'; const U = 'https://idl.uw.edu/mosaic-datasets/data/flights-200k.parquet';
const SAIDA = process.argv[2];
const b = await chromium.launch({ channel: 'chrome', headless: true });
const ctx = await b.newContext(); const page = await ctx.newPage();
const reqs = []; ctx.on('request', r => { if (r.url().endsWith('.parquet')) reqs.push(r); });
await page.goto(P + '/index.html'); await page.addScriptTag({ url: '/app_teste.js', type: 'module' });
await page.waitForFunction(() => window.iniciar);
await page.evaluate(o => window.iniciar(o), { forceFullHTTPReads: false });
const consultas = [`SELECT count(*) c FROM read_parquet('${U}')`, `SELECT avg(delay) d FROM read_parquet('${U}')`, `SELECT row_group_id, count(*) n FROM parquet_metadata('${U}') GROUP BY 1 LIMIT 3`];
const res = [];
for (const sql of consultas) {
  const n = reqs.length; const r = await page.evaluate(q => window.consultar(q), sql); await page.waitForTimeout(300);
  let total = 0; const det = [];
  for (const q of reqs.slice(n)) { const resp = await q.response().catch(() => null); let t = 0; try { t = (await q.sizes()).responseBodySize; } catch {} total += Math.max(t, 0); const h = await q.allHeaders(); det.push(`${q.method()} ${resp && resp.status()} [${h.range || ''}]`); }
  res.push({ consulta: sql.replace(U, '<url>'), primeira_linha: r.amostra[0], ms: Math.round(r.ms), requisicoes: reqs.length - n, bytes_no_corpo: total, detalhe: det.slice(0, 6) });
  console.log(sql.slice(0, 44), '->', JSON.stringify(r.amostra[0]), Math.round(r.ms), 'ms |', reqs.length - n, 'req,', total, 'b :: ', det.slice(0, 6).join(' ; '));
}
writeFileSync(SAIDA, JSON.stringify({ url: U, navegador: 'Chrome', opcao: 'forceFullHTTPReads: false', consultas: res }, null, 1));
await b.close();
