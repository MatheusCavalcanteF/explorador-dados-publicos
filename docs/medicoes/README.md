# Medições

Scripts e resultados por trás dos números de [`docs/plano.md`](../plano.md), coletados entre 06 e 08/11/2026. Não fazem parte do site nem do pipeline. Foram escritos para responder a perguntas pontuais, então cada um recebe caminhos pela linha de comando e não há um comando único que rode tudo.

## Dependências

Python: `duckdb`, `numpy`, `pandas`, `pyarrow`, `datasus-dbc`, `py7zr`, `openpyxl`, `pypdf`. Os scripts que leem `.dbc` também precisam de `dbf_reader.py`, do projeto [Dados-Hospitalares-SUS](https://github.com/MatheusCavalcanteF/datasus-etl-baixada-santista).

Node: `@duckdb/duckdb-wasm@1.33.1-dev57.0`, `playwright-core@1.65.0`, `hyparquet@1.32.0`, `hyparquet-compressors@1.1.3`, `esbuild@0.25.11`.

## Scripts

| Arquivo | Responde a |
|---|---|
| `scripts/suprimir.py` | Supressão primária, complementar e dedução em cadeia, usada pelos demais |
| `scripts/probe_sih_ftp.py`, `probe_sih_extra.py` | O que existe no FTP do SIH, datas de republicação, cópia local x FTP |
| `scripts/baixar_rd_brasil.py` | Coleta do SIH de 2025 nas 26 UFs fora SP, só com as colunas usadas |
| `scripts/medir_sih.py` | Tamanho, supressão por métrica e por família, e dedução entre tabelas. O argumento `sem-familia` mede sem a família |
| `scripts/rodar_sih_duas_vezes.sh`, `comparar_rodadas.py` | Se duas rodadas produzem as mesmas máscaras |
| `scripts/medir_obitos.py` | Óbitos: por categoria ou só no total anual |
| `scripts/medir_educacao.py` | Censo Escolar e IDEB: supressão e tamanho |
| `scripts/medir_trava.py` | Trava de queda entre as versões de setembro e outubro de 2026, em SP, e subtração entre versões |
| `scripts/qualidade_sih.py` | Maturação por UF, qualidade dos códigos |
| `scripts/conferir_tabnet.py`, `conferir_tabnet2.py` | Comparação com o TabNet por competência; a segunda usa as 27 UFs na visão de residência e mede o que se perde lendo só o arquivo de SP |
| `scripts/conferir_tabnet_alta.py` | O eixo "Ano/mês atendimento" do TabNet: compara com a data de alta e a de internação |
| `scripts/conferir_tabnet_versao.py` | Se o TabNet já mostra a versão de outubro em Santo André, e o que diz a nota técnica |
| `scripts/particoes.py`, `tamanho_sem_compressao.py` | Tamanho por UF e formatos de compressão |
| `scripts/rg2000.py` | Arquivo com grupos de 2 mil linhas, para o teste de grupos |
| `scripts/gerar_json_municipios.py` | Estimativa do JSON por município com o conteúdo da v1 e 36 meses |
| `scripts/baixar_caged.py`, `medir_caged.py` | Coleta do CAGED de 2025 e supressão por métrica. Os cruzamentos usam só `MOV`; o saldo com `FOR` e `EXC` é só o total nacional |
| `scripts/conferir_fontes.py` | O que as fontes informam sobre si mesmas: listagens dos FTPs, datas do INEP e da SIDRA, listas de municípios e respostas do Siconfi |
| `scripts/conferir_hosts.py` | Tamanho do motor no pacote e no CDN, e `Range` no Cloudflare Pages fora do navegador |
| `scripts/conferir_caged_oficial.py` | Admissões, desligamentos e saldo de 2025 contra a divulgação do ministério |
| `scripts/medir_inep.py`, `medir_inep2.py` | Primeira leitura do Censo Escolar e do IDEB, conferência de MD5 |
| `scripts/medir_siconfi.py` | Cobertura em 60 municípios sorteados, a 1 consulta por segundo |
| `scripts/testar_inep_conexao.py` | Taxa de falha de conexão no INEP e em outras fontes |
| `scripts/limitar_cpu.py` | Teto de CPU por Job Object do Windows |
| `scripts/conferir_endereco.py` | Depois da renomeação do repositório: o endereço antigo do site dá 404 e o novo responde; o sitemap publicado tem exatamente as páginas esperadas; o JSON-LD de Santos passa no validador do pipeline e bate com o Parquet; peso servido de 25 páginas. Roda da raiz do repositório |
| `scripts/conferir_tabnet_f1b.py` | F1b: o Parquet mínimo do pipeline contra o TabNet, em dois municípios por região, por competência e por data de internação. Valores de 1 a 4 não são gravados |
| `scripts/medir_versoes_f1b.py` | F1b: dedução entre duas versões publicadas (o par real de SP e pares simulados de processamento tardio, nas 27 UFs) e o efeito de arredondar os meses preliminares |
| `scripts/medir_trava_f1b.py` | F1b: a trava de queda do pipeline no par real de SP, por mês da alta, e o total por UF e competência |
| `scripts/medir_versoes_transicao.py` | F1b, com a regra decidida: versões atacadas juntas, na transição em que um mês ou o ano fecha e em três versões seguidas, com e sem a herança do padrão dos períodos fechados |
| `scripts/medir_mudanca_tardia.py` | F1b: quanto um mês ainda muda depois de 6, 9 e 12 meses, por UF, depois do fechamento (listagem do FTP) e depois do próprio mês (processamento tardio e o par real de SP) |
| `scripts/resumo.py`, `resumo_carga.py` | Tabelas-resumo dos agregados e do carregamento |
| `scripts/derivar_numeros.py` | Números do plano que são contas sobre outros resultados, com origem e cálculo |
| `scripts/verificar_resultados.py` | Caminhos da máquina em `docs/` e contagens abaixo de 5 por município nos resultados. O que é próprio da máquina vem por `--termo-local`, nunca fica no código: `verificar_resultados.py <resultados> <municipios.json> --texto docs --termo-local <usuário>` |

## Carregamento no navegador

Preparação, numa cópia de `carregamento/` fora do repositório. Os bundles saem idênticos aos medidos só com o `package.json` entregue, que fixa as versões e `"type": "module"`:

```sh
npm install
mkdir -p site/duckdb
cp node_modules/@duckdb/duckdb-wasm/dist/duckdb-eh.wasm node_modules/@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js site/duckdb/
for par in entrada:app entrada_teste_real:app_teste entrada_hyp:hyp entrada_hyp_leve:hyp_leve entrada_hyp_meta:hyp_meta; do
  npx esbuild "${par%%:*}.js" --bundle --format=esm --target=es2020 --minify --outfile="site/${par##*:}.js"
done
node servidor.mjs site 8931
```

`teste_real3.mjs` e `teste_real4.mjs` usam `site/app_teste.js`, gerado de `entrada_teste_real.js`: é a entrada do motor mais o registro de arquivo por URL. Esses dois, `range_real.mjs` e `calibra2.mjs` não precisam de dados locais.

`testar_site_publicado.mjs` só usa `playwright-core` e `hyparquet`, e lê o `ibge.json` e o `site/dados/ibge/populacao.parquet` do artefato `coleta` da execução do `Publicar` que gerou o site em teste.

Os testes de tempo e de igualdade precisam dos dados no site. A partir dos Parquet de `medir_sih.py`, `particoes.py` e `tamanho_sem_compressao.py` gravam em `site/dados/`, e `rg2000.py` gera o arquivo com grupos de 2 mil linhas. `gerar_json_municipios.py` grava em `site/json/`. Os argumentos estão no início de cada script. Fora o `app_teste.js`, os bundles desta preparação são idênticos aos usados nas medições; a pasta limpa não refez a bateria de tempos, que continua em `carga.json`.

| Arquivo | Responde a |
|---|---|
| `carregamento/range_real.mjs` | `Range` em Chrome, Firefox e WebKit reais, contra GitHub Pages e Cloudflare Pages |
| `carregamento/teste_real3.mjs`, `teste_real4.mjs` | DuckDB-WASM contra Parquet em host real, com o tráfego do worker |
| `carregamento/testar_leitor.mjs` | Se o leitor em JavaScript devolve o mesmo que o motor, linha a linha, nos três navegadores |
| `carregamento/testar_formato.mjs` | O mesmo, com o leitor leve e o Parquet sem compressão, em tabelas inteiras |
| `carregamento/testar_host_real.mjs` | Leitor no GitHub Pages real, na mesma origem do arquivo |
| `carregamento/testar_site_publicado.mjs` | O site deste projeto, depois de publicado: página, gzip, `Range`, `HEAD` e leitor, nos três navegadores, comparados com o build e a coleta |
| `carregamento/calibra2.mjs` | Se a limitação de CPU alcança a thread principal e o worker, pelas ferramentas do navegador e por Job Object |
| `carregamento/servidor.mjs` | Servidor local que reproduz o comportamento medido no GitHub Pages e limita a banda |
| `carregamento/medir_carga.mjs` | A bateria de tempos e bytes |
| `carregamento/medir_cache.mjs` | Por que a visita repetida baixava o motor de novo: contexto, tipo de navegação, status HTTP e limite de tamanho |
| `carregamento/medir_repeticao.mjs` | Visita repetida com perfil em disco, revalidação e tamanho do grupo de linhas |

## Resultados

`resultados/` traz os números agregados de cada medição, em JSON. Nenhum arquivo traz linha por pessoa ou internação, nem caminho local, e os valores por município citados têm pelo menos 100 internações. Html, binários e Parquet ficam de fora.

| Arquivo | Conteúdo |
|---|---|
| `sih_agregados.json`, `sih_sem_familia.json` | Cada cruzamento, com e sem a supressão por família, e o teste de dedução |
| `obitos_opcoes.json` | As duas opções de óbitos |
| `caged_agregados.json`, `educacao.json` | Cruzamentos do CAGED e da educação |
| `trava_versoes.json` | Pares acionados, alarmes falsos e subtração entre versões |
| `sih_regras.json` | Maturação por UF, qualidade dos códigos, revisão entre versões |
| `conferencia_tabnet_resumo.json` | Placar da comparação com o TabNet por competência, e as diferenças da capital |
| `conferencia_tabnet_alta.json` | Eixo "atendimento" x data de alta e de internação: quantos meses batem e os totais de cada comparação, sem valores por mês |
| `conferencia_tabnet_versao.json` | Santo André no TabNet por competência, e o trecho da nota técnica |
| `conferencia_caged_oficial.json` | Admissões, desligamentos e saldo de 2025 contra a apresentação do ministério, e a divergência do sumário executivo |
| `particoes.json`, `json_municipios.json` | Tamanhos por UF, formatos e estimativa do JSON |
| `carga.json`, `carga_repeticao.json`, `cache_causa.json` | Tempos, bytes, status HTTP e causa do cenário de cache |
| `leitor_x_motor.json`, `formato_x_motor.json`, `leitor_host_real.json` | Igualdade entre leitor e motor, nos dois formatos, e leitor em host real |
| `siconfi_amostra.json`, `conexao_fontes.json` | Cobertura do Siconfi e falhas de conexão |
| `rd_brasil_coleta.json`, `caged_coleta.json` | Arquivos baixados, com tamanho |
| `sih_perda_so_uf.json` | O que se perde na visão de residência ao ler só o arquivo de SP, com população, período e cálculo |
| `fontes.json`, `hosts.json` | Saída de `conferir_fontes.py` e `conferir_hosts.py` |
| `calibracao_cpu.json` | Quanto cada forma de limitar a CPU desacelera a thread principal e o worker |
| `site_publicado_navegadores.json` | Saída de `testar_site_publicado.mjs` sobre a execução 42439217829 do `Publicar`, com os cabeçalhos de cada pedido |
| `endereco_e_buscadores.json` | Saída de `conferir_endereco.py` sobre a execução 42442355751 do `Publicar`, a primeira no endereço novo |
| `alcance_roteiro_local.json` | `diagnostico.executar(diagnostico.ROTEIRO)` numa máquina local, em 08/11/2026: as rotas das fontes do roteiro depois da v1, só com tamanho e hash de cada corpo |
| `conferencia_tabnet_f1b.json` | Saída de `conferir_tabnet_f1b.py`: 160 comparações por competência e 20 por data de internação, nas 5 regiões. O bloco por competência foi regravado em colunas e linhas, com nome e região num mapa por código, sem mudar os valores; diferenças de 1 a 4 entre as fontes saem sem os dois valores |
| `conferencia_tabnet_f1b_capital.json` | O que foi testado para achar a diferença da capital de SP, sem atributos das AIHs envolvidas |
| `versoes_f1b.json` | Saída de `medir_versoes_f1b.py`: diferenças exatas de 1 a 4 entre versões, por política, e o erro do arredondamento |
| `trava_f1b.json` | Saída de `medir_trava_f1b.py` |
| `versoes_transicao_f1b.json` | Saída de `medir_versoes_transicao.py`: teste de cada versão, das versões juntas e diferenças de 1 a 4 por par; os grupos sem herança em `sem_heranca` |
| `mudanca_tardia_f1b.json` | Saída de `medir_mudanca_tardia.py`. Percentuais com uma casa; resto ou variação de 1 a 4 sai nulo |
| `sih_local_f1b.json` | Resumo da execução local do pipeline com as regras decididas (teste por ano, critério, o que não foi publicado e por quê) e o peso das páginas do build local com o SIH |
| `particoes_f1b.json` | Tamanho das partições do SIH por ano, com só as métricas do catálogo em cada cruzamento e com dias e valor em todos |
| `sih_runner_*.json` | Medições do workflow `SIH (medição)` no runner, reduzidas ao que o plano cita: tempos, disco, memória, tamanho das partições e, por ano, o teste de dedução (no Brasil, também a supressão por cruzamento) |
| `derivados.json` | Somas e percentuais citados no plano, com origem e cálculo |
| `range_hosts.json`, `motor_host_real.json`, `motor_host_real_consultas.json` | `Range` nos 3 navegadores, e o motor em host real, com e sem leitura parcial |

## Levantamento do roteiro

[`roteiro/`](roteiro/README.md) traz o catálogo das fontes do roteiro depois da v1, consultadas em 07/11/2026 numa máquina local, com a data, o método, o que ficou de fora e os hashes dos originais.

## Limites destas medições

- Nenhum deploy próprio foi feito: a leitura em host real usou arquivos públicos de terceiros, e os tempos usam um servidor local que imita o GitHub Pages.
- "Celular" é emulação em desktop: viewport, banda e CPU limitadas. Não houve teste em aparelho físico nem em Safari no iOS.
- O antivírus desta máquina altera o tráfego do Chrome, injetando script e cabeçalho de segurança nas páginas. Ele não foi desligado, e parte dos resultados passa por ele.
- O teste de dedução da Etapa 0 cobre o SIH de um ano, com as margens declaradas. O da F1b, no pipeline, cobre os seis anos e todas as somas que se pode montar com o publicado, mas também não prova ausência de dedução: aperta intervalos soma a soma e não resolve o sistema inteiro de uma vez. Não cobre CAGED nem educação.
- A trava de queda foi medida em uma única republicação, só em SP, na Etapa 0 e de novo pelo pipeline na F1b. Os pares simulados da F1b medem só o processamento tardio, sem as correções de republicação.
- A estimativa de JSON gera dois dos três anos a partir de um ano medido.
- `medir_inep.py` e `medir_inep2.py` são a primeira leitura, com dados que `medir_educacao.py` refez.
- A amostra do Siconfi tem 60 municípios, sem carga completa.
- Nenhum número por mês da alta foi conferido em ferramenta oficial. O eixo "atendimento" do TabNet é a data de internação. O TabWin tem o eixo da alta (`tabwin_eixo_saida.json`), mas não foi rodado.
- Tamanhos e supressão dos cruzamentos do CAGED foram medidos só sobre `MOV`. O CAGED foi conferido com o ministério só no total nacional de 2025. `educacao.json` traz a supressão de turmas, medida antes de turmas ficarem fora da regra.
- Em `leitor_x_motor.json`, o bloco `host_real` traz uma leitura parcial entre origens que falhou, com `Failed to fetch`. A chamada de leitura foi alcançada: o pedido com `Range` saiu e ficou sem resposta (`GET null`), mas a causa não foi investigada, e o antivírus desta máquina está nesse caminho. No site, leitor e dados ficam na mesma origem, caso que `leitor_host_real.json` mostra funcionando.
- `verificar_resultados.py` não detecta contagem pequena que só apareça por subtração. A verificação disso foi uma varredura pontual nos resumos, que achou dois casos, já corrigidos nos scripts: em `sih_regras.json`, categorias com menos de 5 são somadas à menor seguinte (`cod_idade` traz `5 + 0`), e `conferencia_tabnet_alta.json` não lista mais valores por mês. Ela não prova que não haja outro caso.
- Em `carga.json`, o leitor leve é a versão que devolvia só a contagem; a versão atual de `entrada_hyp_leve.js` também devolve as linhas, para o teste de igualdade.
