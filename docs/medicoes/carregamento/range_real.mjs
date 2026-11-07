// Pergunta central: em navegador real, um fetch com Range num arquivo do GitHub Pages recebe bytes crus?
// Uso: node range_real.mjs <saida.json>
import { chromium, firefox, webkit } from 'playwright-core';
import { writeFileSync } from 'node:fs';
const SAIDA = process.argv[2];
const res = {};
const ALVOS = [
  { nome: 'GitHub Pages (sqlite)', pagina: 'https://phiresky.github.io/world-development-indicators-sqlite/split-db/config.json', arq: 'https://phiresky.github.io/world-development-indicators-sqlite/split-db/db.sqlite3.000', tam: 10485760 },
  { nome: 'GitHub Pages (wasm)', pagina: 'https://kripken.github.io/sql.js/dist/worker.sql-wasm.js', arq: 'https://kripken.github.io/sql.js/dist/sql-wasm.wasm', tam: 1450157 },
  { nome: 'Cloudflare Pages (zip)', pagina: 'https://nodeget.pages.dev/', arq: 'https://nodeget.pages.dev/NodeGet-StatusShow.zip', tam: 1248531 },
];
const navegadores = [['chromium', chromium, { channel: 'chrome', headless: true }], ['firefox', firefox, { headless: true }], ['webkit', webkit, { headless: true }]];
for (const [nome, tipo, opcoes] of navegadores) {
  let b; try { b = await tipo.launch(opcoes); } catch (e) { console.log(nome, 'não abriu:', String(e).slice(0, 160)); res[nome] = { erro: 'não abriu' }; continue; }
  console.log('==', nome, b.version());
  res[nome] = { versao: b.version(), alvos: {} };
  for (const a of ALVOS) {
    const ctx = await b.newContext(); const page = await ctx.newPage();
    const enviados = [];
    page.on('request', async (r) => { if (r.url() === a.arq) { try { enviados.push(await r.allHeaders()); } catch {} } });
    try {
      await page.goto(a.pagina, { waitUntil: 'domcontentloaded', timeout: 30000 });
      const r = await page.evaluate(async ({ arq }) => {
        const out = [];
        for (const faixa of ['bytes=0-1023', 'bytes=2048-3071']) {
          const resp = await fetch(arq, { headers: { Range: faixa }, cache: 'no-store' });
          const buf = await resp.arrayBuffer();
          out.push({ faixa, status: resp.status, bytes: buf.byteLength, contentRange: resp.headers.get('content-range'), encoding: resp.headers.get('content-encoding'), acceptRanges: resp.headers.get('accept-ranges'), comprimento: resp.headers.get('content-length') , inicio: Array.from(new Uint8Array(buf.slice(0, 4))).map(x => x.toString(16).padStart(2,'0')).join('') });
        }
        const head = await fetch(arq, { method: 'HEAD', cache: 'no-store' });
        out.push({ faixa: 'HEAD', status: head.status, comprimento: head.headers.get('content-length'), encoding: head.headers.get('content-encoding'), acceptRanges: head.headers.get('accept-ranges') });
        return out;
      }, { arq: a.arq });
      console.log(' ', a.nome, '| tamanho real', a.tam);
      for (const l of r) console.log('   ', JSON.stringify(l));
      const h = enviados.find(x => x.range);
      if (h) console.log('    pedido real: accept-encoding =', h['accept-encoding'], '| range =', h.range);
      res[nome].alvos[a.nome] = { arquivo: a.arq, tamanho_real: a.tam, respostas: r, accept_encoding_enviado: h ? h['accept-encoding'] : null };
    } catch (e) { console.log(' ', a.nome, 'ERRO', String(e).slice(0, 200)); res[nome].alvos[a.nome] = { arquivo: a.arq, erro: String(e).slice(0, 200) }; }
    await ctx.close();
  }
  await b.close();
}
writeFileSync(SAIDA, JSON.stringify(res, null, 1));
