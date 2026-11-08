// Site publicado, nos três navegadores: gzip, Range, HEAD e o leitor em JavaScript lendo o Parquet do site,
// comparado com o arquivo do build e com a coleta. Tudo na mesma origem do site, como a página fará.
// O leitor é o hyparquet 1.32.0 sem descompressor, servido pelo Playwright numa pasta que o site não tem.
// Uso: node testar_site_publicado.mjs <saida.json> <ibge.json da coleta> <populacao.parquet do build> [url do site]
import { chromium, firefox, webkit } from 'playwright-core';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const [saida, caminhoColeta, caminhoParquet, base = 'https://matheuscavalcantef.github.io/explorador-dados-publicos/'] = process.argv.slice(2);
const SITE = base.endsWith('/') ? base : `${base}/`;
const PARQUET = `${SITE}dados/ibge/populacao.parquet`;
const PAGINA = `${SITE}municipio/3548500/`;
const LEITOR = dirname(fileURLToPath(import.meta.resolve('hyparquet')));
const local = readFileSync(caminhoParquet);
const coleta = JSON.parse(readFileSync(caminhoColeta, 'utf-8'));
const sha = (b) => createHash('sha256').update(b).digest('hex');

const navegadores = [['chromium', chromium, { channel: 'chrome', headless: true }], ['firefox', firefox, { headless: true }], ['webkit', webkit, { headless: true }]];
const resultado = { site: SITE, parquet_bytes_reais: local.length, parquet_sha256: sha(local), navegadores: {} };

for (const [nome, tipo, opcoes] of navegadores) {
  const navegador = await tipo.launch(opcoes);
  const contexto = await navegador.newContext();
  const pagina = await contexto.newPage();
  const pedidos = [];
  contexto.on('requestfinished', async (r) => {
    if (!r.url().startsWith(PARQUET)) return;
    const resposta = await r.response();
    const enviados = await r.allHeaders();
    const recebidos = resposta ? await resposta.allHeaders() : {};
    let transferido = null;
    try { transferido = (await r.sizes()).responseBodySize; } catch {}
    pedidos.push({ url: r.url().slice(SITE.length), metodo: r.method(), range: enviados.range || null,
      accept_encoding: enviados['accept-encoding'] || null, status: resposta && resposta.status(),
      content_encoding: recebidos['content-encoding'] || null, content_length: recebidos['content-length'] || null,
      content_range: recebidos['content-range'] || null, corpo_transferido: transferido });
  });
  await contexto.route(`${SITE}__leitor__/**`, (rota) => {
    const arquivo = join(LEITOR, rota.request().url().slice(`${SITE}__leitor__/`.length).split('?')[0]);
    rota.fulfill({ status: 200, contentType: 'text/javascript', body: readFileSync(arquivo) });
  });
  const aberta = await pagina.goto(`${PAGINA}?navegador=${nome}-${Date.now()}`, { waitUntil: 'load' });
  const htmlPagina = await pagina.content();
  const medido = await pagina.evaluate(async ({ parquet, real, marca }) => {
    const hex = async (buf) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', buf))].map((x) => x.toString(16).padStart(2, '0')).join('');
    const texto = (buf) => String.fromCharCode(...new Uint8Array(buf));
    const out = {};
    let r = await fetch(`${parquet}?teste=${marca}-gzip`, { cache: 'no-store' });
    let buf = await r.arrayBuffer();
    out.gzip = { status: r.status, content_encoding: r.headers.get('content-encoding'), content_length: r.headers.get('content-length'),
      bytes: buf.byteLength, sha256: await hex(buf), inicio: texto(buf.slice(0, 4)), fim: texto(buf.slice(-4)) };
    r = await fetch(`${parquet}?teste=${marca}-range`, { cache: 'no-store', headers: { Range: 'bytes=0-1023' } });
    buf = await r.arrayBuffer();
    out.range = { status: r.status, content_encoding: r.headers.get('content-encoding'), content_range: r.headers.get('content-range'),
      bytes: buf.byteLength, sha256: await hex(buf) };
    r = await fetch(`${parquet}?teste=${marca}-rodape`, { cache: 'no-store', headers: { Range: `bytes=${real - 8}-${real - 1}` } });
    buf = await r.arrayBuffer();
    out.range_rodape = { status: r.status, content_encoding: r.headers.get('content-encoding'), content_range: r.headers.get('content-range'),
      bytes: buf.byteLength, fim: texto(buf.slice(-4)) };
    r = await fetch(`${parquet}?teste=${marca}-head`, { cache: 'no-store', method: 'HEAD' });
    out.head = { status: r.status, content_encoding: r.headers.get('content-encoding'), content_length: r.headers.get('content-length') };
    const inicio = performance.now();
    const { parquetReadObjects } = await import('../../__leitor__/index.js');
    r = await fetch(`${parquet}?teste=${marca}-leitor`, { cache: 'no-store' });
    const linhas = await parquetReadObjects({ file: await r.arrayBuffer() });
    out.leitor = { status: r.status, segundos: Math.round(performance.now() - inicio) / 1000, linhas };
    return out;
  }, { parquet: PARQUET, real: local.length, marca: `${nome}-${Date.now()}` });
  await pagina.waitForTimeout(300);

  const esperado = new Map(coleta.municipios.map((m) => [m.codigo, m]));
  const linhas = medido.leitor.linhas;
  const divergentes = linhas.filter((l) => {
    const m = esperado.get(l.codigo);
    return !m || l.nome !== m.nome || l.uf !== m.uf || l.populacao_estimada !== m.populacao_estimada
      || (l.populacao_censo_2022 ?? null) !== m.populacao_censo;
  }).map((l) => l.codigo);
  delete medido.leitor.linhas;
  const transferidoGzip = pedidos.find((p) => p.url.includes('-gzip'))?.corpo_transferido ?? null;
  const confere = {
    pagina: aberta.status() === 200 && htmlPagina.includes('<h1 class="placa__nome">Santos</h1>')
      && htmlPagina.includes('com data-base em 31/12/2025'),
    gzip: medido.gzip.status === 200 && medido.gzip.content_encoding === 'gzip' && medido.gzip.bytes === local.length
      && medido.gzip.sha256 === sha(local),
    range: medido.range.status === 206 && !medido.range.content_encoding && medido.range.bytes === 1024
      && medido.range.content_range === `bytes 0-1023/${local.length}` && medido.range.sha256 === sha(local.subarray(0, 1024)),
    range_rodape: medido.range_rodape.status === 206 && medido.range_rodape.bytes === 8 && medido.range_rodape.fim === 'PAR1'
      && medido.range_rodape.content_range === `bytes ${local.length - 8}-${local.length - 1}/${local.length}`,
    // O plano mediu que o HEAD informa o tamanho comprimido, não o real.
    head: medido.head.status === 200 && medido.head.content_length !== null && Number(medido.head.content_length) < local.length,
    leitor: medido.leitor.status === 200 && linhas.length === esperado.size && divergentes.length === 0,
  };
  resultado.navegadores[nome] = { versao: navegador.version(), confere, medido,
    leitor_linhas: linhas.length, leitor_divergentes: divergentes.length, exemplos_divergentes: divergentes.slice(0, 10),
    gzip_transferido_bytes: transferidoGzip, pedidos };
  console.log(nome, navegador.version(), JSON.stringify(confere));
  await navegador.close();
}
resultado.tudo_confere = Object.values(resultado.navegadores).every((n) => Object.values(n.confere).every(Boolean));
writeFileSync(saida, JSON.stringify(resultado, null, 1) + '\n');
console.log('tudo confere:', resultado.tudo_confere);
