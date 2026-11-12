[Índice do plano](../plano.md)

## Reaproveitamento do Dados-Hospitalares-SUS

Mesmo autor, licença MIT. Os arquivos copiados levam uma nota de origem no topo, com o commit `52edc79`.

| Origem | O que fazer |
|---|---|
| `src/dbf_reader.py` e `tests/test_dbf_reader.py` | Copiar sem alteração |
| `src/log_config.py` | Copiar sem alteração |
| `src/extract.py` | Adaptar: `download_file`, `convert_dbc_to_parquet`, `month_range`, `_report_missing`. Tirar o padrão SP, percorrer as 27 UFs, trocar a lista de colunas proibidas por lista de colunas permitidas |
| `src/transform.py` | Adaptar: `_classify_outcome`, `_age_in_years`, decodificações, `validate_trusted`. Sai o filtro da Baixada |
| `src/reference.py` | Adaptar: CID-10 com SHA-256, API do CNES com cache (4.880 hospitais, ~16 min na primeira carga, estimativa) |
| `tests/conftest.py`, `tests/test_transform.py` | Adaptar, **trocando os números de AIH reais por sintéticos** |
| `.github/workflows/ci.yml`, `.github/dependabot.yml` | Copiar como base |
| `src/load.py` | Não copiar o Star Schema. Levar a ideia da conciliação antes de publicar |
| `powerbi/dax_measures.md` | Levar as regras para o catálogo. **Não copiar a tabela de referência**, que traz contagens abaixo de 5 |
| `benchmarks/` | Não copiar. O README de origem já documenta |

## Produtos parecidos

| Produto | O que faz | Limitação observada | Onde este projeto acrescenta |
|---|---|---|---|
| **IBGE Cidades** | Panorama por município com indicadores selecionados, e comparação entre municípios. A API de pesquisas do IBGE lista 94 pesquisas, entre elas "Panorama municipal" | O portal recusou leitura automatizada, então a descrição vem de fontes secundárias e da API, sem exame direto da tela | Séries mensais de saúde e emprego, cruzamentos, dashboard próprio |
| **Atlas Brasil** | IDHM e 78 indicadores municipais anuais. Mapa, tabela, gráfico e ranking | Foco em desenvolvimento humano. Sem dado mensal | Dado mensal, regras de maturação visíveis, busca em português |
| **Base dos Dados** | Tabelas tratadas de muitas fontes, com acesso por SQL no BigQuery, Python e R | A versão aberta tem defasagem de seis meses; dados recentes são para assinantes. O acesso principal pede SQL, Python ou R, e o download direto tem limites. As páginas lidas não citam gráficos | Público que não programa, sem conta, com o dado mais recente disponível |
| **TabNet** | Tabula bases do DATASUS com linha, coluna e conteúdo. Referência para conferir números | Uma base por vez. O resultado sai em tabela, com CSV e TabWin, sem gráfico na página. A consulta é por formulário, sem link para compartilhar. A maturação aparece só como nota genérica ("últimos seis meses"), embora o FTP republique 12 | Cruzamento entre temas, gráfico, link, ressalvas por número. **O TabNet tem mais detalhe, e isso continua sendo verdade** |
| **Dadosfera e UFMG** | Anunciado em outubro de 2025 (CartaCapital, 24/10/2025): consulta em linguagem natural ao DATASUS, 12 meses, protótipos em seis, abertura ao público numa segunda fase | Nenhum lançamento público localizado em 06/11/2026. O site da empresa não mostra o produto | Vários temas, resposta verificável, avaliação de acerto publicada, custo zero de operação |

Pelo que foi possível examinar, nenhum junta os quatro pontos: temas diferentes no mesmo município, sem login, resposta com fonte e ressalva em cada número, e link compartilhável. É o espaço deste projeto. Ele não substitui o TabNet para quem precisa de detalhe nem a Base dos Dados para quem programa.
