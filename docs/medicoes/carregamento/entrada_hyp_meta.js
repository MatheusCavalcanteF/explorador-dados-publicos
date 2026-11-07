// Teste do leitor em host real, a partir da própria origem do arquivo.
import { asyncBufferFromUrl, cachedAsyncBuffer, parquetMetadataAsync, parquetRead } from 'hyparquet';
import { compressors } from 'hyparquet-compressors';

window.lerFaixaReal = async (url, byteLength) => {
  const t = performance.now();
  const file = cachedAsyncBuffer(await asyncBufferFromUrl({ url, byteLength }));
  const metadata = await parquetMetadataAsync(file, { initialFetchSize: 65536 });
  const linhas = await new Promise((res, rej) => parquetRead({ file, metadata, compressors, rowStart: 0, rowEnd: 1000, rowFormat: 'object', onComplete: res }).catch(rej));
  return { ms: performance.now() - t, linhas_no_arquivo: Number(metadata.num_rows), grupos: metadata.row_groups.length, linhas_lidas: linhas.length, primeira: JSON.parse(JSON.stringify(linhas[0], (k, v) => (typeof v === 'bigint' ? Number(v) : v))) };
};
