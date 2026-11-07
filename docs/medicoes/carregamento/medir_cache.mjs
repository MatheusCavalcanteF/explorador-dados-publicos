// Por que a visita repetida baixou o motor de novo? Varia o contexto (anônimo x perfil em disco) e o tipo
// de navegação, registrando no servidor o status HTTP de cada arquivo. Depois procura o tamanho a partir do
// qual o modo anônimo deixa de guardar em cache.
import { chromium } from 'playwright-core'; import fs from 'node:fs'; import path from 'node:path'; import crypto from 'node:crypto';
const [saida, base] = process.argv.slice(2);
const P = 'http://127.0.0.1:8931';
const st = async () => (await fetch(P + '/__stats')).json();
const opcoes = { channel: 'chrome', headless: true };
const res = { versao_navegador: null, cenarios: [], tamanhos: [] };

async function motor(page) {
  await page.addScriptTag({ url: '/app.js', type: 'module' });
  await page.waitForFunction(() => window.iniciar, null, { timeout: 60000 });
  await page.evaluate(() => window.iniciar({ forceFullHTTPReads: false }));
}
const resumo = s => s.filter(x => !x.u.startsWith('/index')).map(x => ({ arquivo: x.u.split('/').pop().split('?')[0], status: x.status, bytes: x.bytes, condicional: x.inm === true }));

await fetch(`${P}/__cache?maxage=600`);
for (const contexto of ['anonimo', 'perfil em disco']) {
  for (const acao of ['recarregar (reload)', 'navegacao nova na mesma aba', 'aba nova', 'navegador reaberto']) {
    if (contexto === 'anonimo' && acao === 'navegador reaberto') continue;
    const dir = path.join(base, `c_${Date.now()}`);
    let b = null, ctx, page;
    if (contexto === 'anonimo') { b = await chromium.launch(opcoes); ctx = await b.newContext(); page = await ctx.newPage(); res.versao_navegador = b.version(); }
    else { ctx = await chromium.launchPersistentContext(dir, opcoes); page = ctx.pages()[0] || await ctx.newPage(); }
    await page.goto(P + '/index.html');
    await motor(page);
    await page.waitForTimeout(1500);
    await st();
    if (acao === 'recarregar (reload)') await page.reload();
    if (acao === 'navegacao nova na mesma aba') await page.goto(P + '/index.html?outra=1');
    if (acao === 'aba nova') { page = await ctx.newPage(); await page.goto(P + '/index.html?outra=2'); }
    if (acao === 'navegador reaberto') { await ctx.close(); ctx = await chromium.launchPersistentContext(dir, opcoes); page = ctx.pages()[0] || await ctx.newPage(); await page.goto(P + '/index.html?outra=3'); }
    const documento = await st();
    await motor(page);
    const s = await st();
    const l = { contexto, acao, documento: documento.map(x => x.status), arquivos: resumo(s), bytes: s.reduce((a, x) => a + x.bytes, 0) };
    res.cenarios.push(l);
    console.log(JSON.stringify(l));
    await ctx.close();
    if (b) await b.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

// Procura o limite: arquivos incompressíveis de vários tamanhos, pedidos duas vezes pela mesma página
fs.mkdirSync('site/teste_cache', { recursive: true });
const TAMANHOS = [256, 512, 1024, 1536, 2048, 4096, 8192, 16384, 32768];
for (const kb of TAMANHOS) fs.writeFileSync(`site/teste_cache/a${kb}.bin`, crypto.randomBytes(kb * 1024));
for (const contexto of ['anonimo', 'perfil em disco']) {
  const dir = path.join(base, `t_${Date.now()}`);
  let b = null, ctx, page;
  if (contexto === 'anonimo') { b = await chromium.launch(opcoes); ctx = await b.newContext(); page = await ctx.newPage(); }
  else { ctx = await chromium.launchPersistentContext(dir, opcoes); page = ctx.pages()[0] || await ctx.newPage(); }
  await page.goto(P + '/index.html');
  for (const kb of TAMANHOS) {
    await st();
    await page.evaluate(u => fetch(u).then(r => r.arrayBuffer()), `/teste_cache/a${kb}.bin`);
    await page.waitForTimeout(400);
    const primeiro = await st();
    await page.evaluate(u => fetch(u).then(r => r.arrayBuffer()), `/teste_cache/a${kb}.bin`);
    await page.waitForTimeout(150);
    const segundo = await st();
    const l = { contexto, kb, primeira_ida: primeiro.map(x => x.status), segunda_ida: segundo.map(x => x.status), reaproveitou_cache: segundo.length === 0 };
    res.tamanhos.push(l);
    console.log(JSON.stringify(l));
  }
  await ctx.close();
  if (b) await b.close();
  fs.rmSync(dir, { recursive: true, force: true });
}
fs.rmSync('site/teste_cache', { recursive: true, force: true });
fs.writeFileSync(saida, JSON.stringify(res, null, 1));
console.log('FIM');
