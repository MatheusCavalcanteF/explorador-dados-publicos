// Leitor em GitHub Pages real, na mesma origem do arquivo, como será no site. Registra o que o navegador recebe,
// e se há código de terceiro injetado na página.
import { chromium, firefox, webkit } from 'playwright-core'; import fs from 'node:fs';
const saida = process.argv[2];
const U = 'https://idl.uw.edu/mosaic-datasets/data/flights-200k.parquet'; const TAM = 1129931;
const ORIGEM = 'https://idl.uw.edu/mosaic-datasets/data/flights-200k.parquet.html';
const codigo = fs.readFileSync('site/hyp_meta.js', 'utf-8');
const res = { url: U, navegadores: {} };
for (const [nome, tipo, opcoes] of [['chromium', chromium, { channel: 'chrome', headless: true }], ['firefox', firefox, { headless: true }], ['webkit', webkit, { headless: true }]]) {
  const b = await tipo.launch(opcoes);
  const ctx = await b.newContext(); const page = await ctx.newPage();
  const reqs = []; const injetados = [];
  ctx.on('request', r => { if (r.url().endsWith('.parquet')) reqs.push(r); if (/kaspersky/i.test(r.url())) injetados.push(r.url().split('/').slice(0, 3).join('/')); });
  // Página em branco na mesma origem do arquivo: só o documento é local, o Parquet vem do host real
  await page.route(ORIGEM, r => r.fulfill({ status: 200, contentType: 'text/html', body: '<!doctype html><title>teste</title>' }));
  await page.goto(ORIGEM, { waitUntil: 'domcontentloaded' });
  await page.addScriptTag({ content: codigo, type: 'module' });
  await page.waitForFunction(() => window.lerFaixaReal, null, { timeout: 20000 });
  let r;
  try { r = await page.evaluate(([u, t]) => window.lerFaixaReal(u, t), [U, TAM]); } catch (e) { r = { erro: String(e).slice(0, 200) }; }
  await page.waitForTimeout(300);
  const det = [];
  for (const q of reqs) { const resp = await q.response().catch(() => null); const h = await q.allHeaders(); const rh = resp ? await resp.allHeaders() : {}; let t = 0; try { t = (await q.sizes()).responseBodySize; } catch {} det.push(`${q.method()} ${resp && resp.status()} [${h.range || ''}] enc=${rh['content-encoding'] || '-'} cr=${rh['content-range'] || '-'} ${t}b`); }
  const scripts = await page.evaluate(() => [...document.scripts].map(s => s.src).filter(Boolean));
  res.navegadores[nome] = { versao: b.version(), resultado: r, requisicoes: det, bytes: 0, codigo_injetado: [...new Set(injetados)], scripts_na_pagina: scripts.map(s => s.split('/').slice(0, 3).join('/')) };
  console.log(nome, JSON.stringify(res.navegadores[nome]).slice(0, 900));
  await b.close();
}
fs.writeFileSync(saida, JSON.stringify(res, null, 1));
