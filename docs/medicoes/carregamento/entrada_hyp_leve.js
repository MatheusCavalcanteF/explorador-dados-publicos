// Mesmo leitor, sem descompressores extras: lê Parquet sem compressão e com snappy.
import { parquetMetadataAsync, parquetRead } from 'hyparquet';

const ler = async (url) => {
  const resp = await fetch(url);
  const file = await resp.arrayBuffer();
  const metadata = await parquetMetadataAsync(file);
  return new Promise((resolve, reject) => parquetRead({ file, metadata, rowFormat: 'object', onComplete: resolve }).catch(reject));
};
window.lerInteiro = async ({ url, coluna, valor }) => {
  const t = performance.now();
  const linhas = await ler(url);
  const filtradas = coluna ? linhas.filter(l => l[coluna] === valor) : linhas;
  return { ms: performance.now() - t, total: linhas.length, linhas: filtradas.length };
};
window.lerLinhas = async (url) => JSON.parse(JSON.stringify(await ler(url), (k, v) => (typeof v === 'bigint' ? Number(v) : v)));
window.__leitorPronto = true;
