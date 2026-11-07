// O formato escolhido devolve o mesmo que o motor? Leitor leve + Parquet sem compressão, tabela inteira,
// nos três navegadores, contra o motor lendo o mesmo arquivo.
import { chromium, firefox, webkit } from 'playwright-core'; import fs from 'node:fs';
const saida = process.argv[2];
const P = 'http://127.0.0.1:8931';
const ARQS = fs.readdirSync('site/dados').filter(f => f.endsWith('_sem.parquet'));
const normal = v => (v === null || v === undefined ? null : (typeof v === 'number' ? Math.round(v * 100) / 100 : v));
const chave = l => JSON.stringify(Object.keys(l).sort().map(k => normal(l[k])));
const res = { arquivos: ARQS, comparacoes: [] };

// Referência: motor
const b = await chromium.launch({ channel: 'chrome', headless: true });
const page = await (await b.newContext()).newPage();
await page.goto(P + '/index.html');
await page.addScriptTag({ url: '/app.js', type: 'module' });
await page.waitForFunction(() => window.iniciar);
await page.evaluate(() => window.iniciar({}));
const referencia = {};
for (const a of ARQS) {
  const linhas = await page.evaluate(async url => {
    const r = await window.__con.query(`SELECT * FROM read_parquet('${url}')`);
    return JSON.parse(JSON.stringify(r.toArray().map(x => x.toJSON()), (k, v) => (typeof v === 'bigint' ? Number(v) : v)));
  }, `${P}/dados/${a}`);
  referencia[a] = linhas.map(chave).sort();
}
await b.close();

for (const [nome, tipo, opcoes] of [['chromium', chromium, { channel: 'chrome', headless: true }], ['firefox', firefox, { headless: true }], ['webkit', webkit, { headless: true }]]) {
  const br = await tipo.launch(opcoes);
  const pg = await (await br.newContext()).newPage();
  await pg.goto(P + '/index.html');
  await pg.addScriptTag({ url: '/hyp_leve.js', type: 'module' });
  await pg.waitForFunction(() => window.__leitorPronto);
  for (const a of ARQS) {
    const linhas = await pg.evaluate(u => window.lerLinhas(u), `${P}/dados/${a}`);
    const x = linhas.map(chave).sort();
    const y = referencia[a];
    let primeira = null;
    if (x.length === y.length) { for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) { primeira = i; break; } }
    const l = { navegador: nome, versao: br.version(), arquivo: a, linhas_leitor: x.length, linhas_motor: y.length, iguais: x.length === y.length && primeira === null };
    res.comparacoes.push(l);
    console.log(JSON.stringify(l));
  }
  await br.close();
}
fs.writeFileSync(saida, JSON.stringify(res, null, 1));
console.log('FIM');
