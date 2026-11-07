// Leitor de Parquet só em JavaScript, nos dois modos: arquivo inteiro e leitura parcial.
import { asyncBufferFromUrl, cachedAsyncBuffer, parquetMetadataAsync, parquetRead } from 'hyparquet';
import { compressors } from 'hyparquet-compressors';

const paraNumero = v => (typeof v === 'bigint' ? Number(v) : v);
const linhaLimpa = l => Object.fromEntries(Object.entries(l).map(([k, v]) => [k, paraNumero(v)]));

async function lerTudo(file, metadata) {
  return new Promise((resolve, reject) => {
    parquetRead({ file, metadata, compressors, rowFormat: 'object', onComplete: resolve }).catch(reject);
  });
}

// Baixa o arquivo inteiro, sem Range: funciona em qualquer host.
window.lerInteiro = async ({ url, coluna, valor }) => {
  const t = performance.now();
  const resp = await fetch(url);
  const file = await resp.arrayBuffer();
  const metadata = await parquetMetadataAsync(file);
  const linhas = await lerTudo(file, metadata);
  const filtradas = coluna ? linhas.filter(l => l[coluna] === valor) : linhas;
  return { ms: performance.now() - t, status: resp.status, total: linhas.length, linhas: filtradas.map(linhaLimpa) };
};

// Lê só o rodapé e os grupos de linhas que podem conter o município. O tamanho vem do catálogo.
window.lerParcial = async ({ url, byteLength, coluna, valor }) => {
  const t = performance.now();
  const file = cachedAsyncBuffer(await asyncBufferFromUrl({ url, byteLength }));
  const metadata = await parquetMetadataAsync(file, { initialFetchSize: 65536 });
  const i = metadata.schema.filter(c => !c.num_children).findIndex(c => c.name === coluna);
  const texto = v => (typeof v === 'string' ? v : new TextDecoder().decode(v));
  let inicio = 0;
  const faixas = [];
  for (const g of metadata.row_groups) {
    const fim = inicio + Number(g.num_rows);
    const st = g.columns[i].meta_data.statistics;
    const min = st?.min_value ?? st?.min;
    const max = st?.max_value ?? st?.max;
    if (!st || (texto(min) <= valor && valor <= texto(max))) faixas.push([inicio, fim]);
    inicio = fim;
  }
  const linhas = [];
  for (const [rowStart, rowEnd] of faixas) {
    await new Promise((res, rej) => parquetRead({ file, metadata, compressors, rowStart, rowEnd, rowFormat: 'object', onComplete: d => { for (const l of d) if (l[coluna] === valor) linhas.push(l); res(); } }).catch(rej));
  }
  return { ms: performance.now() - t, grupos: metadata.row_groups.length, gruposLidos: faixas.length, linhas: linhas.map(linhaLimpa) };
};

// Ranking nacional: lê a tabela do país inteiro e soma por município.
window.ranking = async ({ url, coluna, medida, filtroColuna, filtroValor }) => {
  const r = await window.lerInteiro({ url });
  const t = performance.now();
  const soma = new Map();
  for (const l of r.linhas) {
    if (filtroColuna && l[filtroColuna] !== filtroValor) continue;
    if (l[medida] === null || l[medida] === undefined) continue;
    soma.set(l[coluna], (soma.get(l[coluna]) || 0) + l[medida]);
  }
  const top = [...soma.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  return { ms: r.ms + (performance.now() - t), total: r.total, top };
};

// Só para medir o limite: conta quantos erros de decodificação aparecem nas colunas.
window.__leitorPronto = true;
