[Índice do plano](../plano.md)

## O que as medições mudaram

| Premissa inicial | O que foi medido | Decisão |
|---|---|---|
| Começar pelo SIH de SP | Só o arquivo de SP perde 9.174 internações de moradores de SP tratados em outros estados: 0,32% no total, mas 20,9% no pior município, com 506 de 645 municípios afetados | Processar as 27 UFs sempre |
| O Brasil inteiro fica para o fim, por ser pesado | 14,6 milhões de AIHs de 2025 viram 22,9 MB de agregados publicáveis, ou 11,9 MB em transferência. Baixar e converter as 26 UFs fora SP levou 223 s | O Brasil entra na F1 |
| Saúde primeiro, educação no fim | Censo Escolar por município: 0,24 MB por ano, com 4,7% das células ocultas | Educação entra na F1 e deixa claro que o produto não é só sobre saúde |
| Pode cruzar tudo por município e mês | Mês x capítulo da CID oculta 54,1% das células e 7,75% das internações; por trimestre, 38,5% e 2,95% | Lista fechada de cruzamentos, com critério publicado |
| Óbitos por categoria e por mês | Por mês, 49,2% das células ficariam ocultas. Por categoria, até 97,5% dos óbitos somem nas cidades pequenas | Óbito municipal só no total anual |
| Suprimir cada tabela isoladamente basta | Entre tabelas, 113 contagens de 1 a 4 continuavam dedutíveis | Supressão por família, com teste de dedução em cadeia. Com ela, zero |
| A curva de maturação da Baixada vale para o país | Altas processadas no próprio mês: 87% na Baixada, 81,7% em SP, 66,1% no Brasil, 18,6% em RR | Regra por UF no catálogo |
| A API de localidades do IBGE dá a lista de municípios, e a de períodos diz quando a SIDRA mudou | Em 3 execuções, o runner não abriu conexão com `servicodados.ibge.gov.br`, onde ficam as duas. O geoftp e a `apisidra` responderam nas 3 | Lista pela DTB do geoftp, período mais recente pela `apisidra`, mudança detectada pelo hash dos valores |
| Supressão por família e as margens declaradas bastam | Com todas as somas que se pode montar, 82 tabelas por ano, e o motivo de cada célula oculta público, o teste revelou 4.365 contagens em 2025 | Motivo por célula fora do site (decidido em 08/11/2026), complementar nas margens conhecidas e reforço guiado pelo teste: zero nos seis anos, de 2021 a 2026 |
| Arredondar os meses preliminares é uma alternativa a avaliar | Com valores exatos, cada atualização mensal revela de 62 (SP, setembro x outubro, 2025) a 194.045 (simulado, 27 UFs, 2026) diferenças de 1 a 4. Em múltiplos de 5, zero, com erro médio de 1,2 internação | Decidido em 08/11/2026: múltiplo de 5. Quando o ano fecha, as duas versões juntas revelavam 18 contagens; com a nova herdando o padrão dos períodos fechados, zero |
| O SIH publicado são as partições em Parquet, no site e em Releases | A página de município mostra 5 dos 14 cruzamentos, sem dias, valor nem margens de UF e do Brasil | Decidido em 10/11/2026: o público é só o que o site mostra; a versão no ar é um arquivo com essa superfície, publicado com o site, e nada do SIH vai para Releases |
| O ataque por intervalos basta para o conjunto | Quatro células ocultas presas por três partições em pares e o total: os intervalos revelam 0, a programação linear revela 4. Nas 27 UFs, 2025, duas versões juntas: os dois dão zero, em 1,2 s e 742 s | Decidido em 10/11/2026: os dois motores rodam, e os dois precisam dar zero |
| HTTP Range resolve o carregamento e o DuckDB-WASM fica no construtor | Primeira carga do motor em 4G lento: quase 1 minuto. Um leitor em JavaScript devolveu os mesmos dados em 72 de 72 comparações, baixando poucas centenas de KB. Ver [Carregamento](arquitetura.md#carregamento) | Leitor em JavaScript como padrão; arquivo por UF, sem depender de `Range`; motor fora da v1 |
