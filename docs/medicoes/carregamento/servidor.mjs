// Servidor local que reproduz o comportamento medido no GitHub Pages: gzip na hora, Range sobre o gzip
// quando o cliente aceita gzip, HEAD com o tamanho comprimido, max-age=600. A banda e a latência são limitadas aqui.
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'; import zlib from 'node:zlib';
const raiz = path.resolve(process.argv[2]); const porta = +process.argv[3] || 8931;
let perfil = { kbps: 0, rtt: 0 };
let stats = [];
let gzipBinario = true;
let maxAge = 600;
const registra = (req, status, bytes) => stats.push({ m: req.method, u: req.url, r: req.headers.range || '', ae: req.headers['accept-encoding'] || '', status, bytes });
const cacheGz = new Map();
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.mjs': 'application/javascript', '.wasm': 'application/wasm', '.json': 'application/json', '.parquet': 'application/octet-stream' };
let prontoEm = 0; // balde global: a banda é um enlace só, como num celular
async function enviar(res, buf) {
  if (!perfil.kbps) { res.end(buf); return; }
  const taxa = perfil.kbps * 1000 / 8; const passo = Math.max(4096, Math.floor(taxa / 20));
  for (let i = 0; i < buf.length; i += passo) {
    const pedaco = buf.subarray(i, i + passo);
    const agora = Date.now(); prontoEm = Math.max(prontoEm, agora) + pedaco.length / taxa * 1000;
    const espera = prontoEm - agora; if (espera > 1) await new Promise(r => setTimeout(r, espera));
    if (!res.write(pedaco)) await new Promise(r => res.once('drain', r));
  }
  res.end();
}
http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/__cache') { maxAge = +url.searchParams.get('maxage'); res.end('ok'); return; }
  if (url.pathname === '/__modo') { gzipBinario = url.searchParams.get('gzip') === '1'; res.end('ok'); return; }
  if (url.pathname === '/__stats') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(stats)); stats = []; return; }
  if (url.pathname === '/__perfil') { perfil = { kbps: +url.searchParams.get('kbps') || 0, rtt: +url.searchParams.get('rtt') || 0 }; prontoEm = 0; res.end('ok'); return; }
  const arq = path.join(raiz, decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
  if (!arq.startsWith(path.resolve(raiz)) || !fs.existsSync(arq) || fs.statSync(arq).isDirectory()) { res.statusCode = 404; res.end('nao achou'); return; }
  if (perfil.rtt) await new Promise(r => setTimeout(r, perfil.rtt));
  const ext = path.extname(arq); const cru = fs.readFileSync(arq);
  const aceitaGzip = /gzip/.test(req.headers['accept-encoding'] || '');
  let corpo = cru; const h = { 'Content-Type': TIPOS[ext] || 'application/octet-stream', 'Accept-Ranges': 'bytes', 'Cache-Control': `max-age=${maxAge}`, 'Vary': 'Accept-Encoding', 'Access-Control-Allow-Origin': '*', 'ETag': `"${cru.length.toString(16)}-${fs.statSync(arq).mtimeMs.toString(16)}"` };
  if (aceitaGzip && (gzipBinario || ext !== '.parquet')) { const chaveGz = arq + '|' + fs.statSync(arq).mtimeMs; if (!cacheGz.has(chaveGz)) cacheGz.set(chaveGz, zlib.gzipSync(cru, { level: 6 })); corpo = cacheGz.get(chaveGz); h['Content-Encoding'] = 'gzip'; h['ETag'] = 'W/' + h['ETag']; }
  if (req.headers['if-none-match'] === h['ETag']) { registra(req, 304, 0); res.writeHead(304, h); res.end(); return; }
  if (req.method === 'HEAD') { registra(req, 200, 0); h['Content-Length'] = corpo.length; res.writeHead(200, h); res.end(); return; }
  const faixa = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
  if (faixa) {
    let ini = faixa[1] === '' ? corpo.length - +faixa[2] : +faixa[1]; let fim = faixa[1] !== '' && faixa[2] !== '' ? +faixa[2] : corpo.length - 1;
    ini = Math.max(0, ini); fim = Math.min(fim, corpo.length - 1);
    if (ini > fim) { res.writeHead(416, { 'Content-Range': `bytes */${corpo.length}` }); res.end(); return; }
    h['Content-Range'] = `bytes ${ini}-${fim}/${corpo.length}`; h['Content-Length'] = fim - ini + 1; registra(req, 206, fim - ini + 1); res.writeHead(206, h); await enviar(res, corpo.subarray(ini, fim + 1)); return;
  }
  h['Content-Length'] = corpo.length; registra(req, 200, corpo.length); res.writeHead(200, h); await enviar(res, corpo);
}).listen(porta, '127.0.0.1', () => console.log('servidor pronto em', porta));
