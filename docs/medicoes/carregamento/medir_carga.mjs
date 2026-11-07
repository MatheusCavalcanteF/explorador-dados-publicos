// Bateria de carregamento. Limita a banda no servidor e a CPU com Job Object; cada cenário abre um navegador limpo.
import { chromium } from 'playwright-core'; import { execFileSync, execSync } from 'node:child_process'; import fs from 'node:fs';
const [py, limita, saida] = process.argv.slice(2);
const P = 'http://127.0.0.1:8931';
const st = async () => (await fetch(P + '/__stats')).json();
const soma = s => s.reduce((a, x) => a + x.bytes, 0);
const PERFIS = [
  { nome: 'sem limite (desktop)', kbps: 0, rtt: 0, cpu: 0, reps: 3 },
  { nome: '4G bom, CPU 4x', kbps: 9000, rtt: 60, cpu: 4, reps: 3 },
  { nome: '4G lento, CPU 4x', kbps: 1600, rtt: 150, cpu: 4, reps: 3 },
  { nome: '4G lento, CPU 6x', kbps: 1600, rtt: 150, cpu: 6, reps: 3 },
];
const pico = (pids) => {
  try {
    const s = execSync(`powershell -NoProfile -Command "(Get-Process -Id ${pids.join(',')} -ErrorAction SilentlyContinue | Measure-Object PeakWorkingSet64 -Maximum).Maximum"`).toString().trim();
    return +(+s / 1e6).toFixed(0);
  } catch { return null; }
};
async function abrir(perfil) {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await page.goto(P + '/index.html');
  const cdp = await b.newBrowserCDPSession();
  const { processInfo } = await cdp.send('SystemInfo.getProcessInfo');
  const pids = processInfo.filter(p => p.type === 'renderer').map(p => p.id);
  if (perfil.cpu) execFileSync(py, ['-I', limita, String(perfil.cpu), ...pids.map(String)]);
  await fetch(`${P}/__perfil?kbps=${perfil.kbps}&rtt=${perfil.rtt}`);
  await st();
  return { b, ctx, page, pids };
}
const fim = async (o) => { await fetch(`${P}/__perfil?kbps=0&rtt=0`); await o.b.close(); };
const resultados = [];
const anota = (perfil, cenario, dados) => {
  const l = { perfil: perfil.nome, cenario, ...dados };
  resultados.push(l);
  fs.writeFileSync(saida, JSON.stringify(resultados, null, 0));
  console.log(JSON.stringify(l));
};
const ARQ_BR = 'BR_res_tri_capitulo.parquet';
const ARQ_UF = 'uf35_res_tri_capitulo.parquet';
const tamBR = fs.statSync('site/dados/' + ARQ_BR).size;
const sql = (arq, m) => `SELECT tri, capitulo, internacoes FROM read_parquet('${P}/dados/${arq}') WHERE mun_res='${m}' ORDER BY 1,2`;
const carregarLeitor = async (o, js = '/hyp.js') => {
  await o.page.addScriptTag({ url: js, type: 'module' });
  await o.page.waitForFunction(() => window.__leitorPronto, null, { timeout: 120000 });
};

for (const perfil of PERFIS) for (let rep = 0; rep < perfil.reps; rep++) {
  // Página de município em JSON
  for (const [rotulo, id] of [['JSON Bertioga', 3506359], ['JSON Santos', 3548500], ['JSON São Paulo', 3550308]]) {
    const o = await abrir(perfil);
    await o.page.addScriptTag({ url: '/pagina_json.js' });
    await st();
    const r = await o.page.evaluate(i => window.pagina(i), id);
    const s = await st();
    anota(perfil, rotulo, { ms: Math.round(r.ms), bytes: soma(s), req: s.length, status: s.map(x => x.status), celulas: r.celulas, pico_mb: pico(o.pids) });
    await fim(o);
  }
  // Leitor, arquivo da UF inteiro, sem Range
  {
    const o = await abrir(perfil);
    const t = Date.now();
    await carregarLeitor(o);
    const r = await o.page.evaluate(a => window.lerInteiro(a), { url: `${P}/dados/${ARQ_UF}`, coluna: 'mun_res', valor: '354850' });
    const ms = Date.now() - t;
    let s = await st();
    anota(perfil, 'Leitor: código + arquivo da UF inteiro', { ms, bytes: soma(s), req: s.length, status: s.map(x => x.status), r206: s.filter(x => x.status === 206).length, linhas: r.linhas.length, total: r.total, pico_mb: pico(o.pids) });
    // Outra cidade da mesma UF, com o arquivo já em cache
    const r2 = await o.page.evaluate(a => window.lerInteiro(a), { url: `${P}/dados/${ARQ_UF}`, coluna: 'mun_res', valor: '350635' });
    s = await st();
    anota(perfil, 'Leitor: outra cidade, mesmo arquivo', { ms: Math.round(r2.ms), bytes: soma(s), req: s.length, status: s.map(x => x.status), linhas: r2.linhas.length, pico_mb: pico(o.pids) });
    await fim(o);
  }
  // Leitor, leitura parcial no arquivo do Brasil
  {
    const o = await abrir(perfil);
    const t = Date.now();
    await carregarLeitor(o);
    const r = await o.page.evaluate(a => window.lerParcial(a), { url: `${P}/dados/${ARQ_BR}`, byteLength: tamBR, coluna: 'mun_res', valor: '354850' });
    const ms = Date.now() - t;
    const s = await st();
    anota(perfil, 'Leitor: código + leitura parcial, arquivo Brasil', { ms, bytes: soma(s), req: s.length, r206: s.filter(x => x.status === 206).length, linhas: r.linhas.length, grupos: `${r.gruposLidos}/${r.grupos}`, pico_mb: pico(o.pids) });
    await fim(o);
  }
  // Leitor, ranking nacional: lê o país inteiro
  {
    const o = await abrir(perfil);
    const t = Date.now();
    await carregarLeitor(o);
    const r = await o.page.evaluate(a => window.ranking(a), { url: `${P}/dados/BR_res_ano_capitulo.parquet`, coluna: 'mun_res', medida: 'internacoes', filtroColuna: 'capitulo', filtroValor: '10' });
    const ms = Date.now() - t;
    const s = await st();
    anota(perfil, 'Leitor: código + ranking nacional', { ms, bytes: soma(s), req: s.length, total: r.total, pico_mb: pico(o.pids) });
    await fim(o);
  }
  // Leitor sem descompressor, arquivo sem compressão
  {
    const o = await abrir(perfil);
    const t = Date.now();
    await carregarLeitor(o, '/hyp_leve.js');
    const r = await o.page.evaluate(a => window.lerInteiro(a), { url: `${P}/dados/uf35_res_tri_capitulo_sem.parquet`, coluna: 'mun_res', valor: '354850' });
    const ms = Date.now() - t;
    const s = await st();
    anota(perfil, 'Leitor leve: código + arquivo da UF sem compressão', { ms, bytes: soma(s), req: s.length, linhas: r.linhas, total: r.total, pico_mb: pico(o.pids) });
    await fim(o);
  }
  // Motor
  {
    const o = await abrir(perfil);
    const t = Date.now();
    await o.page.addScriptTag({ url: '/app.js', type: 'module' });
    await o.page.waitForFunction(() => window.iniciar, null, { timeout: 180000 });
    await o.page.evaluate(() => window.iniciar({ forceFullHTTPReads: false }));
    const msMotor = Date.now() - t;
    let s = await st();
    anota(perfil, 'Motor: código, 1ª carga', { ms: msMotor, bytes: soma(s), req: s.length, status: s.map(x => x.status), pico_mb: pico(o.pids) });
    let r = await o.page.evaluate(q => window.consultar(q), sql(ARQ_BR, '354850'));
    s = await st();
    anota(perfil, 'Motor: consulta com Range, arquivo Brasil', { ms: Math.round(r.ms), bytes: soma(s), req: s.length, r206: s.filter(x => x.status === 206).length, linhas: r.linhas, pico_mb: pico(o.pids) });
    r = await o.page.evaluate(q => window.consultar(q), sql(ARQ_BR, '350635'));
    s = await st();
    anota(perfil, 'Motor: outra cidade, arquivo Brasil', { ms: Math.round(r.ms), bytes: soma(s), req: s.length, linhas: r.linhas, pico_mb: pico(o.pids) });
    await fim(o);
  }
  {
    const o = await abrir(perfil);
    await o.page.addScriptTag({ url: '/app.js', type: 'module' });
    await o.page.waitForFunction(() => window.iniciar, null, { timeout: 180000 });
    await o.page.evaluate(() => window.iniciar({}));
    await st();
    const r = await o.page.evaluate(q => window.consultar(q), sql(ARQ_UF, '354850'));
    const s = await st();
    anota(perfil, 'Motor: consulta, arquivo da UF inteiro', { ms: Math.round(r.ms), bytes: soma(s), req: s.length, r206: s.filter(x => x.status === 206).length, linhas: r.linhas, pico_mb: pico(o.pids) });
    await fim(o);
  }
}
console.log('FIM');
