// Lê o Parquet publicado com o leitor em JavaScript (hyparquet, sem descompressor), como o navegador fará,
// e compara linha a linha com a coleta. Grava o resultado e sai com 0: quem decide a falha é `pipeline exigir`.
// Uso: node conferir.mjs <url do parquet> <ibge.json> <saida.json>
import { readFileSync, writeFileSync } from 'node:fs';
import { parquetReadObjects } from 'hyparquet';

const [url, caminhoColeta, saida] = process.argv.slice(2);
const inicio = performance.now();
const resposta = await fetch(url, { headers: { 'Accept-Encoding': 'gzip' } });
const arquivo = await resposta.arrayBuffer();
const linhas = await parquetReadObjects({ file: arquivo });
const segundos = (performance.now() - inicio) / 1000;

const coleta = JSON.parse(readFileSync(caminhoColeta, 'utf-8'));
const esperado = new Map(coleta.municipios.map((m) => [m.codigo, m]));
const divergentes = linhas
  .filter((l) => {
    const m = esperado.get(l.codigo);
    return !m || l.nome !== m.nome || l.uf !== m.uf || l.populacao_estimada !== m.populacao_estimada
      || (l.populacao_censo_2022 ?? null) !== m.populacao_censo;
  })
  .map((l) => l.codigo);

const resultado = {
  conferido_em: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
  url,
  leitor: 'hyparquet 1.32.0, sem descompressor',
  status: resposta.status,
  content_encoding: resposta.headers.get('content-encoding'),
  bytes_lidos: arquivo.byteLength,
  linhas: linhas.length,
  esperadas: esperado.size,
  divergentes: divergentes.length,
  exemplos: divergentes.slice(0, 10),
  segundos: Math.round(segundos * 100) / 100,
  ok: resposta.ok && linhas.length === esperado.size && divergentes.length === 0,
};
writeFileSync(saida, JSON.stringify(resultado, null, 1));
console.log(`Leitor: ${resultado.linhas} linhas, ${resultado.divergentes} divergentes, ok=${resultado.ok}`);
