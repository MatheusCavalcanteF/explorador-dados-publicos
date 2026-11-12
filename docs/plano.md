# Explorador de Dados Públicos: plano

Site estático e gratuito para consultar, cruzar e visualizar dados públicos dos municípios brasileiros. Saúde é um dos temas, não o tema.

**O problema.** Os dados existem, mas cada base mora em um lugar, com formato, código de município e armadilhas próprias. Para saber quantas internações os moradores de uma cidade tiveram e comparar com emprego e educação, é preciso passar por um FTP, um arquivo `.dbc`, um `.7z` que abre em cerca de 450 MB, uma planilha com cabeçalho na linha 10 e uma API por município.

**A proposta.** Uma página por município, um construtor de dashboards e uma busca em português, todos sobre a mesma especificação de consulta. Cada número mostra fonte, período, data da coleta e ressalvas. Sem servidor, sem login, sem custo de operação.

Este documento parte do que os dados mostraram. As medições foram feitas entre 06 e 08/11/2026; os scripts e os resultados estão em [`docs/medicoes/`](medicoes/README.md). Estimativa, quando há, está escrita como estimativa.

## Índice

O plano está dividido por assunto, em [`docs/plano/`](plano/).

| Arquivo | O que tem | Seções |
|---|---|---|
| [`o-que-as-medicoes-mudaram.md`](plano/o-que-as-medicoes-mudaram.md) | Cada premissa inicial, o que foi medido e a decisão que saiu disso | [O que as medições mudaram](plano/o-que-as-medicoes-mudaram.md#o-que-as-medições-mudaram) |
| [`fontes.md`](plano/fontes.md) | As bases testadas com dados reais: acesso, licença, formato, revisões e os detalhes de cada uma | [Fontes](plano/fontes.md#fontes); [Detalhes que importam](plano/fontes.md#detalhes-que-importam) |
| [`arquitetura.md`](plano/arquitetura.md) | Pipeline, especificação de consulta, leitor em JavaScript, hospedagem, endereço e carregamento | [Arquitetura](plano/arquitetura.md#arquitetura); [Por que leitor em JavaScript, e não motor](plano/arquitetura.md#por-que-leitor-em-javascript-e-não-motor); [Hospedagem: GitHub Pages](plano/arquitetura.md#hospedagem-github-pages); [Endereço e buscadores](plano/arquitetura.md#endereço-e-buscadores); [Carregamento](plano/arquitetura.md#carregamento) |
| [`ci-e-historico.md`](plano/ci-e-historico.md) | De onde vem cada período, a superfície pública do SIH, o SIH no runner e a trava de queda | [CI e histórico](plano/ci-e-historico.md#ci-e-histórico); [Superfície pública do SIH](plano/ci-e-historico.md#superfície-pública-do-sih); [SIH no runner](plano/ci-e-historico.md#sih-no-runner); [Trava de queda](plano/ci-e-historico.md#trava-de-queda) |
| [`catalogo.md`](plano/catalogo.md) | O esquema do catálogo e as regras do SIH que foram para ele | [Esquema do catálogo](plano/catalogo.md#esquema-do-catálogo); [Regras do SIH levadas para o catálogo](plano/catalogo.md#regras-do-sih-levadas-para-o-catálogo) |
| [`privacidade-e-supressao.md`](plano/privacidade-e-supressao.md) | Supressão, teste de dedução, comparação entre versões e o motor por programação linear | [Privacidade e supressão](plano/privacidade-e-supressao.md#privacidade-e-supressão); [Teste de dedução da F1b](plano/privacidade-e-supressao.md#teste-de-dedução-da-f1b); [SIH, Brasil, 2025](plano/privacidade-e-supressao.md#sih-brasil-2025); [Óbitos](plano/privacidade-e-supressao.md#óbitos); [Comparação entre versões](plano/privacidade-e-supressao.md#comparação-entre-versões); [Motor por programação linear](plano/privacidade-e-supressao.md#motor-por-programação-linear); [Novo CAGED, Brasil, 2025](plano/privacidade-e-supressao.md#novo-caged-brasil-2025); [Educação, Brasil, 2024](plano/privacidade-e-supressao.md#educação-brasil-2024); [Onde a regra se aplica](plano/privacidade-e-supressao.md#onde-a-regra-se-aplica) |
| [`limites-de-tamanho.md`](plano/limites-de-tamanho.md) | Os orçamentos de tamanho do site e dos arquivos | [Limites de tamanho](plano/limites-de-tamanho.md#limites-de-tamanho) |
| [`origem-e-produtos-parecidos.md`](plano/origem-e-produtos-parecidos.md) | O que veio do projeto de origem e o que outros produtos já fazem | [Reaproveitamento do Dados-Hospitalares-SUS](plano/origem-e-produtos-parecidos.md#reaproveitamento-do-dados-hospitalares-sus); [Produtos parecidos](plano/origem-e-produtos-parecidos.md#produtos-parecidos) |
| [`escopo-e-riscos.md`](plano/escopo-e-riscos.md) | O que entra na v1 e os riscos | [Escopo da v1](plano/escopo-e-riscos.md#escopo-da-v1); [Riscos](plano/escopo-e-riscos.md#riscos) |
| [`fases.md`](plano/fases.md) | F1 a F3 e o que fica para depois da v1 | [Fases](plano/fases.md#fases); [F1. Páginas por município, em três etapas publicáveis](plano/fases.md#f1-páginas-por-município-em-três-etapas-publicáveis); [F2. Construtor de dashboards](plano/fases.md#f2-construtor-de-dashboards); [F3. Busca em português](plano/fases.md#f3-busca-em-português); [Depois da v1](plano/fases.md#depois-da-v1) |

## Reprodução

Ambiente das medições: Windows 11, Ryzen 7 5700X3D, 32 GB, Python 3.14, DuckDB 2.0.0, Node 24, Chrome 157, com antivírus ativo. Os agregados de 2025 usam a versão dos arquivos disponível em novembro de 2026; para SP, parte vem de cópia de setembro de 2026 cujas competências de 2025 não mudaram nos totais. Tamanhos multianuais são estimados por proporção, a partir de um ano medido.

Veja [`docs/medicoes/README.md`](medicoes/README.md).
