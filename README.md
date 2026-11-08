# Explorador de Dados Públicos

[![CI](https://github.com/MatheusCavalcanteF/explorador-dados-publicos/actions/workflows/ci.yml/badge.svg)](https://github.com/MatheusCavalcanteF/explorador-dados-publicos/actions/workflows/ci.yml)
[![Publicar](https://github.com/MatheusCavalcanteF/explorador-dados-publicos/actions/workflows/publicar.yml/badge.svg)](https://github.com/MatheusCavalcanteF/explorador-dados-publicos/actions/workflows/publicar.yml)

Site estático e gratuito com dados oficiais de cada município brasileiro, em que cada número mostra de onde veio, quando foi coletado e como conferir na fonte.

**Site:** https://matheuscavalcantef.github.io/explorador-dados-publicos/

## O problema

Os dados públicos dos municípios existem, mas cada base mora num sistema diferente, com formato, código de município e armadilhas próprios. Para comparar internações, emprego e educação de uma cidade é preciso passar por um FTP, um `.dbc`, um `.7z` de centenas de megabytes, uma planilha com cabeçalho na linha 10 e uma API por município. E um número copiado de um painel raramente diz de que versão do arquivo saiu.

## A solução

Um pipeline em Python que baixa as fontes oficiais, recusa dado fora do contrato e gera um site estático no GitHub Pages, sem servidor, login ou custo de operação. Cada número na tela abre o painel **Fonte e método**: órgão e pesquisa, link exato para o valor na origem (ou os passos para chegar a ele), período de referência, data da coleta, hash SHA-256 do arquivo coletado e ressalvas.

O plano completo, com as medições que decidiram cada escolha, está em [`docs/plano.md`](docs/plano.md).

## O que já está no ar (etapa F1a)

Publicado em 07/11/2026 pela execução manual [42439217829](https://github.com/MatheusCavalcanteF/explorador-dados-publicos/actions/runs/42439217829) do workflow `Publicar`:

- Uma página para cada um dos **5.571 municípios** da Divisão Territorial Brasileira 2025 do IBGE, com data-base em 31/12/2025, informada no rodapé de cada página. Cada página traz a população estimada de 2026 e a do Censo 2022. Há busca por nome e listas por estado.
- No painel **Fonte e método**: link exato da API da SIDRA para o valor de cada município, período de referência, data da coleta e SHA-256 da resposta de onde o número saiu, e o arquivo da DTB de onde vêm código, nome e UF.
- O Censo 2022 ficou guardado como partição fechada na Release [`ibge-censo-2022`](https://github.com/MatheusCavalcanteF/explorador-dados-publicos/releases/tag/ibge-censo-2022). As próximas execuções leem a Release e só a conferem com a fonte; se a fonte mudar, o pipeline para.
- O [manifesto](manifesto/) da execução está no git: arquivos coletados com hash, totais por UF, hash dos valores de cada fonte e o resultado das conferências.

Conferido no site publicado. O CI pediu ao site, em Python e Node, o Parquet da população e a página de Santos: gzip, `Range`, `HEAD` e leitor bateram com o plano, e 30 links exatos sorteados por métrica devolveram o valor publicado. Depois, em Chrome 157, Firefox 159 e WebKit 27.2, o Parquet de 225.932 bytes chegou com 116.787 em gzip e o mesmo SHA-256 do build. `Range` voltou `206` com bytes crus, e o leitor em JavaScript leu as 5.571 linhas sem divergência da coleta. O site tem 5.607 arquivos e 31,9 MB. A página de município tem mediana de 5,6 KB; servida em gzip, 2,1 KB numa amostra de 25 páginas.

A publicação semanal foi religada em 07/11/2026, aos domingos às 00:47 UTC. A primeira execução agendada ainda não aconteceu.

## Como funciona

```mermaid
flowchart LR
    I[("IBGE<br/>DTB no geoftp e SIDRA")] -->|"contrato de dados"| C["Coleta<br/>hash e data"]
    R[("Release<br/>Censo 2022")] --> C
    K["Catálogo<br/>fonte, tema, ressalvas"] --> S
    C --> S["Site estático<br/>uma página por município"]
    S --> P[("GitHub Pages")]
    P -->|"gzip, Range, HEAD, leitor, links"| M["Manifesto no git"]
    A[("DATASUS, CAGED,<br/>Siconfi")] -->|"teste de alcance"| M
```

| Parte | Onde | O que faz |
|---|---|---|
| Catálogo | `catalogo/catalogo.yaml` | Temas, bases e métricas, com fonte, tipo de acesso e ressalvas. Validado antes de cada execução |
| Coleta e contrato | `pipeline/dtb.py`, `pipeline/ibge.py` | Acha a DTB mais recente no geoftp e recusa planilha fora da estrutura esperada. Recusa JSON fora do formato, sinal de ausência tratado como número, município fora da DTB e cobertura baixa. Compara o hash dos valores com a coleta anterior |
| Site | `pipeline/site.py`, `web/` | HTML gerado em Python, funciona sem JavaScript; a busca é o único script |
| Conferências | `pipeline/alcance.py`, `hospedagem.py`, `links.py`, `ferramentas/leitor/` | Rodam no CI depois da publicação. Falha de alcance ou de hospedagem deixa a execução vermelha; link quebrado só fica marcado |
| Workflows | `.github/workflows/` | `ci.yml` roda os testes a cada push; `publicar.yml` coleta, publica e confere toda semana; `alcance.yml`, manual, testa cada fonte passo a passo (DNS, conexão, TLS ou FTP, resposta) e mostra o resultado no resumo da execução |

**Fontes que o runner não alcança.** Em 07/11/2026, a API de serviços do IBGE (`servicodados.ibge.gov.br`) e o INEP recusaram conexão do runner do GitHub. A coleta não usa mais essa API: a lista de municípios vem da DTB, e a população e o período mais recente, da SIDRA. O INEP só entra na etapa de educação (F1c); até lá, só o diagnóstico manual `alcance.yml` testa o INEP e essa API.

## Rodar localmente

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # no Windows: .venv\Scripts\pip
.venv/bin/python -m pytest                    # testes, sem rede
.venv/bin/python -m pipeline coletar --saida build/coleta
.venv/bin/python -m pipeline construir --coleta build/coleta --saida build/site
```

Os testes bloqueiam o acesso à rede e usam dados sintéticos no formato da DTB e da SIDRA.

## Dados e licenças

Os dados são do IBGE; o site cita a fonte em cada número. O código está sob licença [MIT](LICENSE). A fonte tipográfica Overpass está sob a [SIL Open Font License](web/fontes/OFL.txt).

O site publica só dados agregados. Nas etapas com dados de saúde e emprego, contagens abaixo de 5 ficam ocultas, com supressão complementar, como descrito no plano.
