// A limitação de CPU alcança a thread principal e o worker? Compara a das ferramentas do navegador com o teto por Job Object.
// Uso: node calibra2.mjs <porta> <python> <limitar_cpu.py> <saida.json>. Mediana de 3 execuções.
import { chromium } from 'playwright-core'; import { execFileSync } from 'node:child_process'; import { writeFileSync } from 'node:fs';
const [porta, py, limita, saida] = process.argv.slice(2);
const mediana = v => [...v].sort((a, b) => a - b)[Math.floor(v.length / 2)];

async function ferramentas(fator) {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await b.newContext(); const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: fator });
  await page.goto(`http://127.0.0.1:${porta}/calibra.html`);
  const r = await page.evaluate(() => window.medir());
  await b.close();
  return r;
}

async function jobObject(fator) {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await b.newContext(); const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${porta}/index.html`);
  const cdp = await b.newBrowserCDPSession();
  const { processInfo } = await cdp.send('SystemInfo.getProcessInfo');
  const pids = processInfo.filter(p => p.type === 'renderer').map(p => String(p.id));
  if (fator > 1) execFileSync(py, ['-I', limita, String(fator), ...pids]);
  await page.goto(`http://127.0.0.1:${porta}/calibra.html`);
  const r = await page.evaluate(() => window.medir());
  await b.close();
  return r;
}

const res = {};
for (const [nome, medir] of [['ferramentas_do_navegador', ferramentas], ['job_object', jobObject]]) {
  const base = {};
  res[nome] = [];
  for (const fator of [1, 4, 6]) {
    const rodadas = [];
    for (let i = 0; i < 3; i++) rodadas.push(await medir(fator));
    const principal = mediana(rodadas.map(r => r.principal)); const worker = mediana(rodadas.map(r => r.noWorker));
    if (fator === 1) Object.assign(base, { principal, worker });
    const linha = { fator, principal_ms: Math.round(principal), worker_ms: Math.round(worker), principal_vezes: +(principal / base.principal).toFixed(1), worker_vezes: +(worker / base.worker).toFixed(1) };
    res[nome].push(linha);
    console.log(nome, JSON.stringify(linha));
  }
}
writeFileSync(saida, JSON.stringify({ descricao: 'Tempo da mesma carga, na thread principal e em um worker, com cada forma de limitar a CPU', calculo: 'Mediana de 3 execuções; vezes = tempo com limite / tempo sem limite', ...res }, null, 1));
