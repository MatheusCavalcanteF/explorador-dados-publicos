// Motor contra Parquet em host real, com e sem leitura parcial, olhando o tráfego do worker.
// Uso: node teste_real3.mjs <saida.json> <url> [<url> ...]. Precisa de servidor.mjs na porta 8931 e de site/app_teste.js.
import { chromium } from 'playwright-core';
import { writeFileSync } from 'node:fs';
const P = 'http://127.0.0.1:8931';
const [SAIDA, ...ALVOS] = process.argv.slice(2);
const res = [];
for (const U of ALVOS) for (const [nome, op, modo] of [['padrão', {}, 'url'], ['forceFull=false', { forceFullHTTPReads: false }, 'url'], ['forceFull=false + registro', { forceFullHTTPReads: false }, 'reg'], ['forceFull=false + reliable=false + registro', { forceFullHTTPReads: false, reliableHeadRequests: false }, 'reg']]) {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await b.newContext(); const page = await ctx.newPage();
  const reqs = []; ctx.on('request', r => { if (r.url().endsWith('.parquet')) reqs.push(r); });
  await page.goto(P + '/index.html'); await page.addScriptTag({ url: '/app_teste.js', type: 'module' });
  await page.waitForFunction(() => window.iniciar && window.registrar);
  await page.evaluate(o => window.iniciar(o), op);
  let fonte = U;
  if (modo === 'reg') { await page.evaluate(([u]) => window.registrar('a.parquet', u, false), [U]); fonte = 'a.parquet'; }
  let resultado;
  try { const r = await page.evaluate(q => window.consultar(q), `SELECT count(*) c FROM read_parquet('${fonte}')`); resultado = { ok: true, linhas: r.amostra[0].c, ms: Math.round(r.ms) }; }
  catch (e) { resultado = { ok: false, erro: String(e).replace(/\s+/g, ' ').slice(0, 160) }; }
  await page.waitForTimeout(500);
  let total = 0; const det = [];
  for (const q of reqs) { const resp = await q.response().catch(() => null); let t = 0; try { t = (await q.sizes()).responseBodySize; } catch {} total += Math.max(t, 0); const h = await q.allHeaders(); const rh = resp ? await resp.allHeaders() : {}; det.push(`${q.method()} ${resp && resp.status()} [${h.range || ''}] ae=${(h['accept-encoding'] || '-').slice(0, 8)} enc=${rh['content-encoding'] || '-'} cl=${rh['content-length'] || '-'} cr=${rh['content-range'] || '-'}`); }
  res.push({ url: U, host: U.split('/')[2], cenario: nome, resultado, requisicoes: reqs.length, bytes_no_corpo: total, detalhe: det.slice(0, 5) });
  console.log(`${U.split('/')[2]} | ${nome}: ${JSON.stringify(resultado)} | ${reqs.length} req, ${total} b`);
  for (const d of det.slice(0, 5)) console.log('     ' + d);
  await b.close();
}
writeFileSync(SAIDA, JSON.stringify({ navegador: 'Chrome', origem_da_pagina: 'servidor local, fora da origem do arquivo', consulta: 'count(*)', cenarios: res }, null, 1));
