// Visita repetida com perfil em disco, como um navegador comum. O cache é preenchido sem limites;
// depois o navegador é fechado, reaberto com limites de CPU e banda, e o motor é carregado de novo.
import { chromium } from 'playwright-core'; import { execFileSync } from 'node:child_process'; import fs from 'node:fs'; import path from 'node:path';
const [py, limita, saida, base] = process.argv.slice(2);
const P = 'http://127.0.0.1:8931';
const st = async () => (await fetch(P + '/__stats')).json();
const soma = s => s.reduce((a, x) => a + x.bytes, 0);
const PERFIS = [{ nome: '4G bom, CPU 4x', kbps: 9000, rtt: 60, cpu: 4 }, { nome: '4G lento, CPU 4x', kbps: 1600, rtt: 150, cpu: 4 }, { nome: '4G lento, CPU 6x', kbps: 1600, rtt: 150, cpu: 6 }];
const res = [];
const opcoes = { channel: 'chrome', headless: true, viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true };
async function carregar(ctx, perfil) {
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto(P + '/index.html');
  if (perfil) {
    const cdp = await ctx.browser()?.newBrowserCDPSession?.().catch(() => null);
    const sessao = cdp || await ctx.newCDPSession(page);
    const { processInfo } = await sessao.send('SystemInfo.getProcessInfo');
    execFileSync(py, ['-I', limita, String(perfil.cpu), ...processInfo.filter(p => p.type === 'renderer').map(p => String(p.id))]);
    await fetch(`${P}/__perfil?kbps=${perfil.kbps}&rtt=${perfil.rtt}`);
  }
  await st();
  const t = Date.now();
  await page.addScriptTag({ url: '/app.js', type: 'module' });
  await page.waitForFunction(() => window.iniciar, null, { timeout: 180000 });
  await page.evaluate(() => window.iniciar({ forceFullHTTPReads: false }));
  const ms = Date.now() - t;
  const s = await st();
  await fetch(`${P}/__perfil?kbps=0&rtt=0`);
  return { ms, bytes: soma(s), req: s.length, detalhe: s.map(x => `${x.u.split('/').pop()} ${x.status} ${x.bytes}`) };
}
// A validade vale desde o preenchimento: com max-age=0 o navegador precisa revalidar cada arquivo.
for (const perfil of PERFIS) for (let rep = 0; rep < 3; rep++) for (const [rotulo, maxage] of [['dentro da validade do cache', 600], ['cache vencido, revalidando', 0]]) {
  const dir = path.join(base, `perfil_${Date.now()}`);
  await fetch(`${P}/__cache?maxage=${maxage}`);
  let ctx = await chromium.launchPersistentContext(dir, opcoes);
  await carregar(ctx, null);
  await ctx.pages()[0].waitForTimeout(1500);
  await ctx.close();
  ctx = await chromium.launchPersistentContext(dir, opcoes);
  const r = await carregar(ctx, perfil);
  const l = { perfil: perfil.nome, cenario: 'Motor: visita repetida, ' + rotulo, ...r };
  res.push(l); fs.writeFileSync(saida, JSON.stringify(res)); console.log(JSON.stringify(l));
  await ctx.pages()[0].waitForTimeout(800);
  await ctx.close();
  fs.rmSync(dir, { recursive: true, force: true });
}
await fetch(`${P}/__cache?maxage=600`);
// Efeito do tamanho do grupo de linhas: bytes por consulta, sem limites
for (const [rotulo, arq] of [['grupos de 50 mil linhas', 'BR_res_tri_capitulo.parquet'], ['grupos de 2 mil linhas', 'BR_res_tri_capitulo_rg2000.parquet']]) {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await (await b.newContext()).newPage();
  await page.goto(P + '/index.html');
  await page.addScriptTag({ url: '/app.js', type: 'module' });
  await page.waitForFunction(() => window.iniciar);
  await page.evaluate(() => window.iniciar({ forceFullHTTPReads: false }));
  await st();
  for (const m of ['354850', '350635', '330455']) {
    const r = await page.evaluate(q => window.consultar(q), `SELECT tri, capitulo, internacoes FROM read_parquet('${P}/dados/${arq}') WHERE mun_res='${m}' ORDER BY 1,2`);
    const s = await st();
    const l = { cenario: 'Grupo de linhas', rotulo, municipio: m, linhas: r.linhas, ms: Math.round(r.ms), bytes: soma(s), req: s.length, r206: s.filter(x => x.status === 206).length };
    res.push(l); fs.writeFileSync(saida, JSON.stringify(res)); console.log(JSON.stringify(l));
  }
  await b.close();
}
console.log('FIM');
