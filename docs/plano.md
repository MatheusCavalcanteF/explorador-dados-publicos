# Explorador de Dados Públicos: plano

Site estático e gratuito para consultar, cruzar e visualizar dados públicos dos municípios brasileiros. Saúde é um dos temas, não o tema.

**O problema.** Os dados existem, mas cada base mora em um lugar, com formato, código de município e armadilhas próprias. Para saber quantas internações os moradores de uma cidade tiveram e comparar com emprego e educação, é preciso passar por um FTP, um arquivo `.dbc`, um `.7z` que abre em cerca de 450 MB, uma planilha com cabeçalho na linha 10 e uma API por município.

**A proposta.** Uma página por município, um construtor de dashboards e uma busca em português, todos sobre a mesma especificação de consulta. Cada número mostra fonte, período, data da coleta e ressalvas. Sem servidor, sem login, sem custo de operação.

Este documento parte do que os dados mostraram. As medições foram feitas entre 06 e 08/11/2026; os scripts e os resultados estão em [`docs/medicoes/`](medicoes/README.md). Estimativa, quando há, está escrita como estimativa.

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
| HTTP Range resolve o carregamento e o DuckDB-WASM fica no construtor | Primeira carga do motor em 4G lento: quase 1 minuto. Um leitor em JavaScript devolveu os mesmos dados em 72 de 72 comparações, baixando poucas centenas de KB. Ver [Carregamento](#carregamento) | Leitor em JavaScript como padrão; arquivo por UF, sem depender de `Range`; motor fora da v1 |

## Fontes

Cada base foi testada com dados reais. "Licença" descreve o que a própria fonte declara; não é parecer jurídico.

| Base | Acesso | Licença declarada | Formato | Frequência | Revisões | Cobertura municipal |
|---|---|---|---|---|---|---|
| **SIH/SUS** (AIH Reduzida) | FTP anônimo, sem TLS nem hash | Nenhuma no FTP. Site do Ministério: CC BY-ND 3.0 para o conteúdo do site e "licença aberta", creditando a fonte, para dados abertos. Um conjunto do portal consultado declara CC BY | `.dbc` (DBF comprimido), 1 arquivo por UF e mês. 880 MB por ano fora SP | Mensal. 2608 publicada em 16/10/2026; AC e RR ainda ausentes em 07/11/2026 | Últimas 12 competências republicadas de uma vez. Ver abaixo | 5.570 por residência; 3.146 por hospital nas competências de 2025, 3.145 com alta em 2025 |
| **IBGE DTB** (Divisão Territorial Brasileira) | geoftp, HTTPS, um `.zip` por ano, em pasta por ano | Sem termo específico localizado; publicações do IBGE pedem a citação da fonte | `.zip` com planilhas `.ods` e `.xls`. A de municípios tem título, data-base e o cabeçalho na 5ª linha, com código e nome da UF, sem a sigla | Anual. A edição 2025, com data-base 31/12/2025, saiu em 26/03/2026; não há pasta de 2026 em 07/11/2026 | Sem histórico. O nome da planilha muda entre edições, e em 2022 o `.ods` era um `.xls` com outra extensão | 5.571 |
| **IBGE SIDRA** | API REST sem chave (`apisidra.ibge.gov.br`) | Idem | JSON | Anual nas tabelas testadas | A API de períodos informa a data de modificação: Censo 2022 em 07/05/2026; estimativas 2025 e 2026 em 28/08/2026; PIB 2021 a 2023 em 19/12/2025. Ela fica em `servicodados.ibge.gov.br`, que não aceita o runner, então o pipeline detecta mudança pelo hash dos valores | 5.570 no Censo 2022 e no PIB; 5.571 na estimativa 2026 |
| **Novo CAGED** | FTP anônimo, sem TLS | Página do ministério: CC BY-ND 3.0 para o site. A API do portal federal pede chave, então a licença do conjunto não foi lida | `.7z` com TXT em UTF-8, separado por `;`. Em média, 53 MB por mês comprimidos e 447 MB abertos | Mensal. 202609 publicada em 04/11/2026 | Arquivos separados: `MOV`, `FOR` (fora do prazo) e `EXC` (exclusões) | 5.566, mais o código `999999` |
| **INEP Censo Escolar** | HTTPS | Site: CC BY-ND 3.0. O manual cita a Lei de Acesso à Informação e a LGPD | `.zip` com CSV em latin-1, uma linha por escola, 426 colunas | Anual. A última é 2024; 2025 responde 404 | O `.zip` de 2024 mudou em 08/07/2026, em pasta chamada `..._defeso`, sem explicação no manual | 5.570 |
| **INEP IDEB** | HTTPS | Idem | `.xlsx`, com cabeçalho na linha 10 | Bienal. A última é 2023; 2025 não está na URL esperada | Arquivos de 13/08/2024 | Anos iniciais 5.567 (5.432 com nota em 2023); finais 5.568 (5.384); médio 5.559 (5.076) |
| **Siconfi** | API REST sem chave, paginada, uma consulta por município | **ODbL** nos metadados de todas as APIs consultadas (DCA, RREO, RGF, MSC, extrato, entes) | JSON | DCA anual, RREO bimestral, RGF quadrimestral | Relatórios retificados aparecem como `RE` no extrato | 59 de 60 municípios sorteados no DCA 2023, 2024 e 2025 |

### Detalhes que importam

**SIH/SUS**
- A série atual em `.dbc` vai de jan/2008 a ago/2026 (224 competências). A pasta `CSV` traz só um aviso de 2015 dizendo que os arquivos foram retirados "temporariamente", e `DBF` e `XML` param em 2014.
- Há um arquivo `base_aih1.duck` de 12 GB na raiz, de 07/06/2026, sem documentação. Não é usado aqui.
- **Internações por período usam a data da alta**, e os meses vão recebendo o processamento tardio. O arquivo é por competência, então as competências não coincidem com os meses publicados: 4,4% das linhas de 2025 têm alta antes de 2025. A defasagem máxima medida é de 5 meses.
- **Mudança no tamanho do arquivo não significa mudança nos números.** Entre as versões de setembro e outubro de 2026, 2509 a 2602 mudaram de tamanho sem alterar as internações de SP.
- **Republicar pode piorar o dado, e depois corrigir.** Na versão de outubro, 6 estabelecimentos de Santo André com 50 AIHs ou mais sumiram das competências 2605, 2606 e 2607. Em 2605, o município caiu de 3.616 para 1.269 internações (−64,9%). Na direção contrária, Paulínia estava com 111 internações de moradores em setembro e voltou a 507 em outubro.
- **Conferência com o TabNet, por competência:** 150 comparações (5 municípios, 3 competências, 5 medidas, por local de internação e de residência). 132 são idênticas. As outras 18 são todas da capital, em duas competências, com diferença de até 0,04%. A causa não foi identificada. Na queda de Santo André, as 3 competências no TabNet já mostram os valores da versão de outubro.
- **O TabNet não tem o eixo do site.** Seu "Ano/mês atendimento" é a data de internação, como diz a nota técnica ("período correspondente à data de internação do paciente") e como os dados confirmam: em 10 comparações (5 municípios, 2 visões, competências de 2025), 135 de 163 meses batem com a data de internação e só 5 com a data da alta. Fora da capital, são 120 de 121. Por isso, os meses do site não coincidem com os do TabNet, e a tela precisa dizer isso. O que dá para conferir é o conjunto de AIHs: o total das 12 competências coincide em 7 das 10 comparações, e as outras 3 diferem em até 0,02%. **Nenhum número por mês da alta foi conferido em ferramenta oficial.**
- **Conferência da F1b, em 08/11/2026, sobre o Parquet mínimo do pipeline** ([`conferencia_tabnet_f1b.json`](medicoes/resultados/conferencia_tabnet_f1b.json)). Dois municípios por região, a capital e um do interior: Manaus e Cruzeiro do Sul, Salvador e Picos, Belo Horizonte e São Paulo, Porto Alegre e Chapecó, Goiânia e Rondonópolis. Por competência (2503 e 2601), nas visões de hospital e de residência, com internações, valor, óbitos e dias de permanência: **137 de 160 comparações idênticas**. As 23 diferentes são de 3 municípios, São Paulo, Goiânia e Rondonópolis, todas com o pipeline de 1 a 4 internações acima. Por data de internação, com as 12 competências de 2025: 317 de 366 meses idênticos, e 8 das 20 comparações com o total igual; nas outras 12, o pipeline tem mais, e a maior diferença é de 31 internações, em São Paulo (0,004%). Diferença de 1 a 4 entre as duas fontes é um grupo pequeno de AIHs, então o resultado gravado não traz os dois valores nesses casos, nem o valor, os dias e os óbitos do mesmo município, visão e competência. **O pipeline nunca tem menos que o TabNet.** Dias de permanência batem somando todas as AIHs, inclusive as de prorrogação.
- **A diferença da capital ficou localizada, sem causa** ([`conferencia_tabnet_f1b_capital.json`](medicoes/resultados/conferencia_tabnet_f1b_capital.json)). Em 2503, só 2 dos 101 estabelecimentos diferem, e o TabNet deixa as AIHs a mais de fora mesmo sem filtro de município, em vez de atribuí-las a outro. Não há N_AIH repetido no arquivo nem reapresentado em outra competência, e nenhum de 11 campos administrativos do RD tem valor raro nelas. Resta a hipótese de o TabNet ter sido gerado de outra versão do arquivo, que daqui não dá para testar.
- **Existe ferramenta oficial com o eixo da alta: o TabWin.** A definição `RD2008.DEF`, dentro do `TAB_SIH.zip` da pasta `Auxiliar` do próprio FTP (de 15/10/2026), tem "Ano/Mês de saída" sobre `DT_SAIDA` como linha, coluna e seleção ([`tabwin_eixo_saida.json`](medicoes/resultados/tabwin_eixo_saida.json)). O TabWin é um programa do DATASUS para Windows, interativo; a conferência por ele ainda não foi feita.
- **Sexo 4.** Aparece a partir da competência 2606: 182 AIHs nas competências 2606 e 2607, de 133 municípios de residência, e 276 AIHs de 194 municípios contando a 2608. Nenhum documento oficial lido em 08/11/2026 define o código no RD: o layout da reduzida do SIHD lista só 1 e 3, o informe técnico do FTP não lista valores, e o `SEXO.CNV` do TabWin manda todo código fora de 1, 2 e 3 para "Ignorado". Na captação, o layout do SISAIH01 passou a ter "I- Indeterminado" a partir da competência 01/2026, mas nenhum documento liga esse "I" ao 4. O pipeline segue o TabWin, e o catálogo registra o que foi lido em `dimensoes.sexo.fora_do_dicionario`.

**Novo CAGED**
- Somando `MOV` + `FOR` − `EXC` de 2025, dá **26.599.777 admissões, 25.320.279 desligamentos e saldo de 1.279.498**, os três iguais à [apresentação do Ministério do Trabalho e Emprego](https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/acoes-e-programas/programas-projetos-acoes-obras-e-atividades/estatisticas-trabalho/novo-caged/2025/dezembro/apresentacao-dezembro-de-2025-1.pdf). O saldo também está no [comunicado oficial](https://www.gov.br/trabalho-e-emprego/pt-br/noticias-e-conteudo/2026/janeiro/novo-caged-brasil-encerra-2025-com-saldo-positivo-de-1-27-milhao-de-empregos-formais). Só com `MOV`, o saldo daria 1.256.997, um erro de 1,8%. A conferência é do total nacional, sem amostra por município.
- O [sumário executivo](https://www.gov.br/trabalho-e-emprego/pt-br/acesso-a-informacao/acoes-e-programas/programas-projetos-acoes-obras-e-atividades/estatisticas-trabalho/novo-caged/2025/dezembro/sumario-executivo_-acumulado-e-dezembro-2025.pdf) do mesmo ministério traz outras admissões e desligamentos (26.599.698 e 25.320.179), cuja diferença não fecha com o saldo que ele mesmo informa. Por isso a referência aqui é a apresentação.
- Nos arquivos de 2025, as declarações fora do prazo chegam em até 12 meses (63,7% no mês seguinte). Um mês só pode ser considerado fechado depois disso, e os recentes aparecem como preliminares.

**INEP**
- Conferência: 47.088.922 matrículas e 179.286 escolas com matrícula, contra os 47,1 milhões e 179,3 mil divulgados. O MD5 declarado dentro do `.zip` confere.
- A linha é por escola, não por pessoa, desde a mudança de 2022. O arquivo inclui escolas paralisadas e extintas.
- As etapas "especial" e "profissional" se sobrepõem às demais: somar todas dá 50,3 milhões. A tabela usa só as que não se sobrepõem (infantil, fundamental, médio e EJA), que somam 45,7 milhões. Elas não fecham no total, e a tela diz isso.

**Siconfi**
- A ODbL pede atribuição e que bases derivadas sejam compartilhadas pela mesma licença. O código segue MIT; os dados derivados do Siconfi saem sob ODbL, em arquivos separados.
- 25 dos 60 municípios não têm "RREO" no 6º bimestre de 2025; 24 deles têm "RREO Simplificado". O tipo de demonstrativo é regra do catálogo.
- No Anexo I-E do DCA, `cod_conta` é `TotalDespesas` em todas as linhas. A função está no texto da coluna `conta`.
- Cada município-ano custa ~340 KB de JSON. O Brasil inteiro seriam 5.570 consultas por ano de referência: ~1,6 h a 1 consulta por segundo (estimativa). A rajada de 15 chamadas sem espera não foi barrada, mas não localizei o limite oficial. Um endpoint de catálogo teve 4 de 10 pedidos em timeout.

**Municípios**
- A lista vem da DTB mais recente do geoftp: o pipeline percorre as pastas de ano, da mais nova para a mais antiga, e usa a primeira que tiver `DTB_{ano}.zip`. Uma pasta com outro `.zip` para o pipeline, em vez de cair para o ano anterior. A sigla da UF não vem na DTB e sai de uma tabela fixa, conferida com o nome da UF.
- Lida pelo pipeline, a DTB 2025 tem os mesmos 5.571 códigos, nomes e UFs da API de localidades, conferido em 07/11/2026 numa máquina local. O mesmo leitor abre as edições 2023 (5.570 municípios, data-base 22/11/2024) e 2024 (5.571, 31/12/2024); a de 2022 é recusada.
- Os códigos do IBGE têm 7 dígitos; SIH e CAGED usam 6. Os primeiros 6 dígitos são únicos nos 5.571 municípios, então a conversão é segura.
- Boa Esperança do Norte (MT, 5101837) existe nas localidades e na estimativa, mas não no Censo 2022, no PIB nem nas internações de 2025.
- **Município na SIDRA que a DTB não tem para a coleta.** Decidido em 08/11/2026: em vez de publicar um número sem município na lista oficial, a coleta para com um erro que diz quantos são, os códigos, a edição da DTB e o que conferir, e o site anterior continua no ar. Um município novo só entra quando a DTB seguinte o incluir.

## Arquitetura

```mermaid
flowchart LR
    F[("Fontes oficiais<br/>FTP, HTTPS, APIs")] -->|"janela aberta"| P["Pipeline em Python<br/>GitHub Actions"]
    P -->|"contrato de dados<br/>comparação de versões"| A["Agregados<br/>supressão por família<br/>teste de dedução"]
    C["Catálogo<br/>métricas, cruzamentos, regras"] --> A
    R[("Releases<br/>partições fechadas,<br/>já suprimidas")] --> A
    A -->|"ano que fecha"| R
    A --> J["JSON por município"]
    A --> Q["Parquet por tema, UF e ano"]
    A --> X["Manifesto no git<br/>versões das fontes"]
    J --> S[("GitHub Pages")]
    Q --> S
    C --> S
    S --> M["Página do município"]
    S -->|"leitor em JavaScript"| D["Construtor de dashboards"]
    S --> B["Busca em português"]
    B -->|"especificação validada"| D
```

**Pipeline.** Idempotente, com a mesma disciplina do projeto de origem: `.part` até conferir o tamanho, versão da fonte nos metadados, contrato que recusa dado errado. A supressão só é determinística com linhas em ordem fixa, porque os empates são resolvidos pela posição: medido em duas rodadas, as máscaras das 27 tabelas saíram idênticas. O site só é trocado se tudo passar; se algo falhar, a versão anterior continua no ar. Nada sem supressão sai do runner.

**Três caminhos de leitura:**
1. **Página de município:** HTML estático + um JSON. Estimativa para a v1: mediana de 20,6 KB (4,2 KB com gzip).
2. **Construtor:** Parquet por tema, UF e ano, lido por um leitor em JavaScript. Baixa o arquivo inteiro, o que funciona em qualquer host.
3. **Busca:** dicionário de sinônimos e correspondência aproximada, tudo no navegador. Só gera uma especificação, validada no catálogo. A consulta sai de um modelo fixo, e nenhuma consulta livre é gerada.

**Especificação.** Pergunta, gráfico e dashboard usam o mesmo objeto, que também vai para a URL:

```json
{
  "tema": "saude",
  "metrica": "internacoes",
  "filtros": { "municipio_residencia": ["3548500"], "capitulo_cid": ["10"] },
  "periodo": { "de": "2025-T1", "ate": "2025-T4" },
  "grafico": "linha"
}
```

A validação liga a especificação a **um cruzamento pré-calculado, no grão exato**. O navegador nunca soma células de uma tabela suprimida para chegar a outro grão: somar por cima de células ocultas daria um total errado e silencioso. Se o cruzamento pedido não existe, a resposta é uma recusa com sugestões.

### Por que leitor em JavaScript, e não motor

Com cruzamentos pré-calculados, a tela só precisa filtrar um arquivo por município e desenhar. Não há junção livre nem agregação nova, porque somar sobre células ocultas é justamente o que não pode acontecer.

**Formato: Parquet sem compressão, com o gzip do host, e leitor sem descompressor.** Medido com a maior tabela testada (residência x trimestre x capítulo, SP):

| | Sem compressão + leitor leve | zstd + leitor com descompressor |
|---|---:|---:|
| Código do leitor, com gzip | 18,6 KB | 94,7 KB |
| Arquivo em transferência, com gzip | 268,6 KB | 259,9 KB |
| Primeira carga: código + arquivo | 287 KB | 355 KB |
| Tempo em 4G lento, CPU 4x | 2,2 s | 2,6 s |
| Pico de memória | 87 a 90 MB | 91 a 95 MB |
| Publicado por ano (15 tabelas, por UF) | 22,9 MB | 11,6 MB |
| Maior arquivo por UF e ano | 488 KB (280 KB com gzip) | 279 KB |
| Igual ao motor | 12 de 12 tabelas inteiras, nos 3 navegadores | 72 de 72 comparações, mais 24 em Firefox e 24 em WebKit |

O preço é ocupar o dobro no site, o que cabe no orçamento. O risco é depender do gzip do host: o GitHub Pages comprimiu `.parquet` nos arquivos testados, e o site deste projeto confirmou em 07/11/2026: o `populacao.parquet` sem compressão, de 225.932 bytes, saiu com 116.787 em gzip nos três navegadores e no teste do CI. Se deixar de comprimir, o formato é um parâmetro do build, e basta voltar ao zstd.

**O motor (DuckDB-WASM) fica fora da v1.** Só volta se uma função concreta provar que precisa dele, por exemplo análise em várias tabelas que o leitor não consiga fazer em tempo razoável. Nesse caso: carregamento sob demanda, só naquela função, vindo do jsDelivr (6,2 a 7,1 MB com brotli, conforme a CDN que atende) em vez do site, porque o arquivo de 35,9 MB passa do limite de 25 MiB por arquivo. O teste de aceitação é o mesmo: dados iguais aos do leitor e tempo medido em 4G lento.

### Hospedagem: GitHub Pages

Limites confirmados na documentação oficial em 07/11/2026: site publicado de até 1 GB, 100 GB por mês de banda (limite flexível), deploy com timeout de 10 minutos, e proibição de uso como hospedagem de negócio. O Cloudflare Pages tem 25 MiB por arquivo e 20.000 arquivos no plano gratuito, sem limite de banda declarado na página.

O que decidiu foi o comportamento medido em navegador real:

| Teste com `Range` | GitHub Pages | Cloudflare Pages |
|---|---|---|
| Chrome 157, Firefox 159, WebKit 27.2 | `206`, bytes crus, tamanho real em `Content-Range` | `200`, arquivo inteiro |
| Amostras | 2 arquivos e 1 Parquet (leitor e motor) nos 3 navegadores | 1 arquivo nos 3 navegadores, mais 3 arquivos `.js` testados fora do navegador, de 4 sites |
| `HEAD` | Devolve o tamanho **comprimido** | Sem `Content-Length` |

O Cloudflare não documenta isso de forma oficial na página de limites; um relato no repositório das ferramentas dele descreve o mesmo. Como o leitor padrão baixa o arquivo inteiro, a escolha não depende mais de `Range`, e outro host continua possível. **Confirmado no deploy próprio em 07/11/2026**, com o Parquet do IBGE, em Chrome 157, Firefox 159 e WebKit 27.2: `206` com bytes crus e `Content-Range` sobre o tamanho real (225.932), também no rodapé do arquivo; `HEAD` com o tamanho do gzip (116.787); e o leitor leu as 5.571 linhas sem divergência da coleta. Fora do navegador há uma diferença: pedindo `Range` com `Accept-Encoding: gzip`, o teste do CI, em Python, recebeu `206` com uma fatia do gzip e `Content-Range` sobre o tamanho comprimido. O Firefox manda `Range` com `gzip, deflate, br, zstd` e recebe bytes crus; o WebKit manda `identity`. Os cabeçalhos de cada pedido estão em [`site_publicado_navegadores.json`](medicoes/resultados/site_publicado_navegadores.json).

**Cloudflare na frente do GitHub Pages não deve ser usado com `Range`:** em `shell.duckdb.org`, que tem essa montagem, a leitura parcial falha com `No magic bytes found`, porque o tamanho informado é o do gzip em cache.

As medições de 07/11/2026 no site próprio foram feitas no endereço anterior à renomeação, descrita a seguir. O Parquet não mudou de conteúdo, e o CI refez gzip, `Range`, `HEAD` e leitor no endereço novo em 08/11/2026, com o mesmo resultado; nos navegadores, o teste não foi refeito.

### Endereço e buscadores

**Endereço.** O repositório passou de `explorador-dados-publicos` para `explorador-de-dados-publicos` em 08/11/2026, e o site agora mora em https://matheuscavalcantef.github.io/explorador-de-dados-publicos/. O GitHub redireciona os links do repositório, mas não os do site de projeto. Medido às 03:23 UTC, depois da execução 42442355751 do `Publicar`: no endereço antigo, a página inicial, a de Santos e o sitemap responderam `404`, com a página padrão do GitHub; no novo, as três responderam `200`, e um caminho inexistente devolveu a página 404 do próprio site ([`endereco_e_buscadores.json`](medicoes/resultados/endereco_e_buscadores.json)). Medições e manifestos anteriores guardam o endereço da época.

O endereço do site e o do repositório ficam só em `projeto.yaml`. Link canônico, Open Graph, JSON-LD, sitemap, links do rodapé, a página 404 e a identificação dos pedidos às fontes saem dali, e um teste falha se o endereço aparecer escrito em outro arquivo do pipeline, do site ou dos workflows. A conferência de hospedagem também falha se o deploy publicar em outro endereço.

**O que cada página leva:**
- Link canônico e Open Graph (`og:title`, `og:description`, `og:url`, `og:site_name`, `og:locale`), sem imagem.
- JSON-LD do schema.org, do tipo `Dataset`. A página de município descreve o próprio município (nome, UF e código IBGE em `spatialCoverage`) e tem uma parte por fonte: a DTB, a estimativa e o Censo, cada uma com órgão, citação, licença da base, período de referência, a tabela oficial em `isBasedOn` e o link exato do valor em `distribution`. Município sem dado numa fonte não ganha a parte dela. As páginas de UF e a inicial seguem o mesmo modelo; a inicial também aponta para o Parquet e a lista de municípios.
- A licença sai do catálogo. Nas três bases do IBGE, que não declaram licença, o JSON-LD diz "Licença não declarada na origem", em vez de inventar uma. O catálogo recusa base sem licença, e licença declarada sem endereço.
- O pipeline valida cada bloco antes de gravar (descrição de 50 a 5.000 caracteres, como pede o Google; licença, órgão, fonte oficial, período ISO 8601, link canônico) e não publica um inválido. Nomes com `<`, `>` ou `&` saem escapados dentro do `<script>`.
- A página 404 fica sem link canônico e sem JSON-LD. O host já responde `404`, então `meta robots` não é necessária, e nenhuma página usa.

**Sitemap.** Gerado pelo pipeline em `sitemap.xml`, com as 5.599 páginas: a inicial, as 27 UFs e os 5.571 municípios. O `lastmod` é a data em que a coleta viu pela primeira vez os valores que a página mostra, não a data da execução: toda página é refeita a cada semana, com a data da coleta no rodapé, mas só muda de fato quando um valor muda. Para isso, o manifesto passou a guardar, por fonte, `valores_desde`, e na estimativa também `periodo_desde`. Um município revisado pelo IBGE ganha a data da revisão; os outros, não. Na primeira execução com o registro, todas as páginas ficaram com 08/11/2026, 02:36 UTC, a coleta mais antiga do manifesto. No site publicado, o sitemap tem exatamente as páginas esperadas pela lista de municípios, e o JSON-LD de Santos passou no validador com os mesmos valores do Parquet.

**robots.txt.** O GitHub Pages serve um site de projeto numa subpasta do domínio `matheuscavalcantef.github.io`, e os buscadores só leem `robots.txt` na raiz do domínio, que pertence a um site de usuário, outro repositório. Por isso não há `robots.txt`; o sitemap é enviado direto no Search Console. Decidido em 08/11/2026: o repositório do site de usuário não será criado só para isso, porque o endereço antigo ficou um dia no ar e não foi indexado.

**Google Search Console.** O suporte ao arquivo de verificação está pronto: com o código em `google_search_console`, no `projeto.yaml`, o pipeline grava `google<código>.html` na raiz do site, com o conteúdo que o Google pede. Hoje não há código nem arquivo. A propriedade a cadastrar é a do prefixo de URL do site, e não a do domínio inteiro.

**Peso.** Com o JSON-LD, o site passou de 31,9 MB para 58,1 MB (5.608 arquivos, no build local de 08/11/2026). A página de município foi de 5,6 KB para 10,1 KB de mediana, 3,7 KB deles de JSON-LD. Servida em gzip, a mediana de 25 páginas sorteadas pelo hash do código foi de 3,0 KB; antes, 2,1 KB, noutra amostra de 25. O sitemap tem 817 KB, ou 22,8 KB em gzip.

### Carregamento

**Peso em transferência:** leitor sem descompressor, 18,6 KB com gzip; leitor com descompressor, 94,7 KB; motor, 8,4 MB (8,1 MB do `.wasm` e 241 KB de JavaScript, com 35,9 MB brutos no `.wasm`).

**Dados iguais.** O leitor com zstd devolveu exatamente o mesmo que o motor em 72 de 72 comparações (4 tabelas, 6 municípios, 3 modos), inclusive os 146.671 valores ocultos de uma tabela inteira, e os 24 casos repetidos em Firefox e WebKit também bateram. O leitor leve, no formato escolhido, bateu em 4 tabelas inteiras de SP nos 3 navegadores. No GitHub Pages real, leu um Parquet público inteiro (231.083 linhas) e, por `Range`, o rodapé e as primeiras 1.000 linhas, com o mesmo resultado nos três navegadores.

**O motor não usa `Range` por padrão.** Sem configuração, baixa o arquivo inteiro. Com `forceFullHTTPReads: false`, o GitHub Pages direto entregou **17.934 bytes em vez de 800.249** para a mesma contagem. É mais um motivo para não depender dele.

**Tempos medidos.** Mediana de 3 execuções, sem cache salvo nas linhas de volta. Os arquivos são de residência x trimestre x capítulo, a maior tabela testada.

**Limite da emulação:** nada disso rodou em celular ou no site real. É Chrome em desktop com tela de celular (390 × 844), um servidor local que imita o comportamento medido no GitHub Pages, banda limitada no servidor, e CPU limitada por Job Object do Windows. A limitação de CPU das ferramentas do navegador não alcança workers: a 4x, a thread principal ficou 4,5 vezes mais lenta e o worker não mudou; com Job Object, os dois ficam 3,9 vezes mais lentos a 4x, e 5,9 vezes a 6x. O teto é pessimista quando motor e tela trabalham juntos, porque um celular real tem mais de um núcleo. O antivírus da máquina altera o tráfego do Chrome e não foi desligado. Cada pico de memória inclui cerca de 80 MB da página vazia.

| Cenário | Transferido | Desktop, sem limite | 4G bom (9 Mbps), CPU 4x | 4G lento (1,6 Mbps), CPU 4x | 4G lento, CPU 6x | Pico de memória |
|---|---:|---:|---:|---:|---:|---:|
| JSON do município (Bertioga) | 5,5 KB | 0,15 s | 0,09 s | 0,20 s | 0,20 s | 85 a 88 MB |
| JSON do município (São Paulo) | 7,8 KB | 0,06 s | 0,09 s | 0,21 s | 0,21 s | 86 a 91 MB |
| **Leitor leve + arquivo da UF sem compressão (padrão)** | 287 KB | 0,10 s | 0,56 s | **2,2 s** | **2,2 s** | 87 a 90 MB |
| Leitor com zstd + arquivo da UF | 355 KB | 0,08 s | 0,61 s | 2,6 s | 2,6 s | 91 a 95 MB |
| Leitor com zstd, outra cidade no mesmo arquivo | 0 | 0,02 s | 0,03 s | 0,03 s | 0,03 s | 103 a 108 MB |
| Leitor com zstd + leitura parcial, arquivo do Brasil | 430 KB | 0,10 s | 0,77 s | 3,3 s | 3,4 s | 99 MB |
| Leitor com zstd + ranking nacional (arquivo de 0,77 MB) | 864 KB | 0,22 s | 1,6 s | 6,5 s | 7,6 s | 145 a 147 MB |
| Motor, primeira carga, sem consulta | 8,4 MB (3 arquivos, `200`) | 0,6 s | 11,5 s | **54,9 s** | **56,2 s** | 248 a 323 MB |
| Motor, consulta com `Range`, arquivo do Brasil | 108 KB | 0,55 s | 1,6 s | 2,7 s | 3,3 s | 290 a 323 MB |
| Motor, outra cidade, arquivo do Brasil | 98 KB | 0,02 s | 0,41 s | 1,2 s | 1,3 s | 290 a 323 MB |
| Motor, consulta, arquivo da UF inteiro | 260 KB | 0,57 s | 1,7 s | 3,2 s | 3,8 s | 293 a 323 MB |
| Motor, volta com cache válido | 0, sem pedidos | não medido | 2,6 s | 3,2 s | 4,4 s | não medido |
| Motor, volta revalidando o cache | 0 (3 arquivos, `304`) | não medido | 3,3 s | 3,3 s | 5,1 s | não medido |

As linhas de consulta do motor somam-se à primeira carga dele. O que isso decide:

- **A página de município não precisa de nada além do JSON.** Os dados chegam em 0,2 s no 4G lento. O número considera só os dados: o JavaScript e os gráficos do site ainda entram na conta.
- **Para o construtor, o leitor resolve.** Em 4G lento, 2,2 s e cerca de 90 MB, contra cerca de 58 s (primeira carga + consulta) e cerca de 295 MB do motor. Mesmo o pior caso medido, um ranking lendo o país inteiro, leva 6,5 s.
- **O gargalo do motor é a rede.** CPU 4x e 6x quase empatam na primeira carga.
- **`Range` não compensa a dependência.** Para o motor, lendo o arquivo do Brasil, poupa 0,5 s em relação a baixar o da UF inteiro; para o leitor, leva mais tempo que o arquivo da UF. Grupos de linhas menores também não ajudam: de 50 mil para 2 mil linhas, o arquivo cresce 27%, e a primeira consulta sobe de 108 KB para 176 KB.

**O cenário de volta foi refeito.** A primeira versão deste teste mostrava 53 s e 8,1 MB na visita repetida. Era defeito do teste, medido assim: no contexto anônimo que o Playwright usa por padrão, o `.wasm` volta com `200` em recarga, em navegação nova e em aba nova, porque esse cache em memória guardou arquivos de até 4 MB e não guardou os de 8 MB ou mais. Com perfil em disco, são 0 bytes nos 4 tipos de navegação, inclusive com o navegador reaberto. O efeito é real para quem usa janela anônima, que baixaria o motor inteiro a cada navegação; o arquivo de dados do leitor fica abaixo desse limite.

## CI e histórico

Os dados não entram no git, e o que está publicado não serve de base para recalcular: as tabelas já estão suprimidas, e somar por cima de célula oculta dá errado. Guardar agregados sem supressão em lugar público também não pode.

**De onde vem cada período:**

| Período | Origem | Por quê |
|---|---|---|
| **Anos abertos:** contêm meses que ainda podem mudar | Recalculados a cada execução, das fontes | O FTP republica as últimas 12 competências, mas a partição é por ano, então cada ano aberto exige todas as suas competências. Hoje são 20 competências; no pior caso, 28. Estimativa: 540 arquivos e ~1,9 GB hoje, 756 arquivos e ~2,6 GB no pior caso, e de 8 a 11 min de download, a partir de 312 arquivos e 880 MB em 223 s, medidos fora do CI |
| **Partições fechadas:** anos que não mudam mais | Arquivos já suprimidos, guardados em **Releases** do próprio repositório | Só têm dado que já é público no site. Sem limite declarado de total ou banda; cada arquivo abaixo de 2 GiB, até 1.000 por release |
| **Reconstrução:** regra mudou (valor de k, novo cruzamento) | Execução manual que rebaixa tudo das fontes | Estimativa para 2021 em diante: 1.836 arquivos, ~6 GB, ~25 min de download. Cabe nos 14 GB de disco se processar e apagar arquivo a arquivo, e no limite de 6 h por job |

**Quando um mês fecha.** O mês M do SIH fecha quando todas as competências que podem conter altas dele saíram da janela republicada: `M + 5 ≤ última competência − 12`. Em novembro de 2026, com a última competência em 2608, estão fechados os meses até 2503. O ano vira partição fechada quando dezembro fecha. No CAGED, um mês fecha após 12 meses de declarações fora do prazo. A defasagem de 5 meses foi medida só nas competências de 2025; se uma competência congelada mudar de tamanho, o pipeline avisa em vez de ignorar.

**A supressão é por partição.** Cada ano é suprimido sozinho, sem margem que atravesse anos. Assim, uma partição fechada nunca precisa ser recalculada, e não há total de vários anos publicado.

**Se a fonte sumir.** As partições fechadas continuam nas Releases e o site segue no ar. Só a reconstrução fica impossível para o período perdido.

**O que a documentação oficial confirma** (lida em 07/11/2026):

| Item | O que diz | Consequência |
|---|---|---|
| Cache do Actions | Entrada sem acesso há mais de 7 dias é removida (padrão; configurável até 90 dias em repositório público). 10 GB por repositório | Um job mensal encontraria o cache vazio no padrão. **Não é fonte de dados:** nem "cópia em cache" do INEP, nem histórico |
| Agendamentos | Em repositório público, são desativados após 60 dias sem atividade. A documentação não define "atividade" nem diz se commit do próprio workflow conta | O job grava o manifesto no git todo mês, e a página mostra a idade dos dados. **Se o commit do workflow conta não foi verificado** |
| Atrasos | O agendamento pode atrasar, e na carga alta execuções podem ser descartadas, sobretudo na virada da hora | Execução semanal em minuto quebrado, idempotente, com disparo manual disponível |
| Artefatos | Retenção de 1 a 90 dias em repositório público; download exige acesso de leitura | Nada sem supressão vira artefato, nem aparece em log |
| Runner público | 4 CPUs, 16 GB de RAM, 14 GB de disco, 6 h por job. Relida em 08/11/2026: os mesmos números; Releases com até 1.000 arquivos de menos de 2 GiB, sem limite de total nem de banda | Executado na F1b; ver [SIH no runner](#sih-no-runner) |

**INEP e IBGE.** O ano do Censo vira partição fechada na Release. O job só rebaixa se o `Last-Modified` mudar, e confere o MD5 que vem no `.zip`. Na DTB e na SIDRA, a mudança é detectada pelo hash dos valores (código, nome e UF; valor por município), comparado com o da coleta anterior gravada no manifesto. A data de modificação da SIDRA saiu do contrato, porque vem do `servicodados`, que não aceita o runner. Se essas fontes estiverem fora do ar, o site mantém o que tem e marca a coleta como atrasada.

**Revisão da estimativa pelo IBGE.** Decidido em 08/11/2026: não bloqueia. Quando o hash da estimativa muda sem mudar o período, a coleta lê o Parquet que está no ar e só o usa se ele tiver o hash da coleta anterior do manifesto. Os municípios que mudaram ganham na página a ressalva "Revisado pelo IBGE", com a data da coleta que detectou, e o manifesto guarda o valor antes e depois de cada um, por código. Variação acima de 5%, ou município que entrou ou saiu da estimativa, vira aviso na execução do `Publicar`; o limite é regra do catálogo. Se o site anterior não responder, ou não bater com o manifesto, a revisão fica registrada sem o detalhe por município, com o motivo, e a ressalva aparece em todas as páginas. As revisões valem dentro do período: a estimativa de um ano novo começa sem nenhuma. O caminho foi testado com dados sintéticos; nenhuma revisão real aconteceu até 08/11/2026. Só uma falha estrutural do SIH impede a atualização, e nesse caso o site anterior continua no ar.

**Manifesto no git.** Um JSON por base com versão, tamanho e data de cada arquivo de origem, totais por UF e competência, e a lista de meses em revisão, com o valor anterior. A comparação de versões lê as tabelas já publicadas no site, então nada sem supressão precisa ser guardado. É o único dado que entra no git, e seu histórico mostra o que mudou.

**Conferência de links.** Uma tarefa agendada do CI, separada dos testes, abre os links oficiais do catálogo e uma amostra dos links exatos, e marca no manifesto os que falharem, com status e data. Um link exato também precisa devolver o valor publicado. Os testes continuam sem rede. Link quebrado não impede a publicação: o painel avisa que o link falhou na última conferência.

### SIH no runner

Medido em 08/11/2026 com o workflow manual `SIH (medição)`, que roda o pipeline inteiro (coleta, contrato, tabelas por ano da alta, supressão, teste de dedução com reforço e partições por UF) e só guarda a medição. Nada vai para o site nem para as Releases, e o artefato não tem dado: os `.dbc`, o Parquet mínimo e as partições somem com o runner. Medições em `sih_runner_*.json`.

| Execução | Arquivos | Baixado | Coleta (download e conversão) | Total | Pico de memória | Disco no fim |
|---|---:|---:|---:|---:|---:|---:|
| RR, 2021 a 2026 (42459740987) | 67 | 16,9 MB | 43 s | 62 s | 0,30 GB | 3,8 MB |
| SP, 2021 a 2026 (42459747506) | 67 | 1,18 GB | 409 s | 7 min 20 s | 1,25 GB | 171 MB |
| **Brasil, 2021 a 2026 (42460657525)** | **1.809** | **5,65 GB** | **39 min 26 s** | **41 min 43 s** | **4,7 GB** | **859 MB** |

**O gargalo é o FTP.** Com 4 conexões, cada arquivo de SP (20 MB) levou cerca de 24 s para baixar e 2,7 s para converter. Pelas duas execuções, a coleta custa 0,56 s por arquivo mais 0,31 s por MB. A projeção para as 27 UFs de 2021 a 2026, 1.809 arquivos e 5,65 GB, feita antes de rodar o Brasil, foi de 46 min de coleta e cerca de 1 h no total; a execução levou 39 min 26 s de coleta e 41 min 43 s no total. Montar, suprimir, testar e gravar cada ano levou de 20 a 24 s. A execução semanal, que só refaz os anos abertos (hoje 513 arquivos e 1,78 GB, das competências 2501 a 2607), ficaria em torno de 14 min de coleta, pela mesma conta. As duas cabem nas 6 h por job.

**Disco.** O `.dbc` é apagado depois de convertido, e o Parquet mínimo das 27 UFs, de 2021 a 2026, tem 737 MB, medido localmente. O volume de trabalho do runner tinha 94 GB livres nas duas execuções; a documentação garante 14 GB.

**O teste de dedução numa UF sozinha não vale.** Em RR e SP sozinhos, ele não chega a zero: sem os arquivos das outras UFs, os moradores de fora internados ali viram margens de UF minúsculas. A medição que vale para o teste é a do Brasil. **No Brasil, o teste deu zero nos seis anos**, com as mesmas contagens, rodada a rodada, da execução local: a supressão sai igual em duas máquinas diferentes.

**As partições medidas no runner ainda levavam dias e valor em todas as tabelas** (121,6 MB, igual ao medido localmente nesse formato). Corrigido depois, cada cruzamento leva só as métricas do catálogo: 41,1 MB, medido localmente.

### Trava de queda

Medido entre as versões de setembro e outubro de 2026, só em SP, porque é a única UF com as duas versões guardadas. Queda de 30% ou mais, com pelo menos 100 internações:

| Eixo e visão | Pares município-período | Mudaram | Acionaram a trava | Alarmes falsos |
|---|---:|---:|---:|---:|
| Competência, por hospital | 3.555 | 21 | 3 | 0 |
| Competência, por residência | 14.989 | 100 | 3 | 0 |
| Mês da alta, por hospital | 4.014 | 36 | 4 | 0 |
| Mês da alta, por residência | 16.676 | 141 | 4 | 0 |

Todos os acionamentos são de Santo André. "Alarme falso" aqui é queda em que o valor novo condiz com a mediana das competências 2501 a 2508, que não mudaram: não houve nenhum, porque por competência o valor novo ficou de 64% a 72% abaixo dela. Por competência, baixar a base para 20 internações ou subir o limite para 50% não muda a contagem. É uma única republicação, em um único estado: o limite precisa ser reavaliado com mais versões.

Comparar com a própria história, em vez de comparar versões, seria pior: 36 pares que nem mudaram estão abaixo de 70% da mediana.

**A trava age em dois níveis, no eixo publicado.** O município é comparado por mês da alta, que é o que a página mostra; a competência serve para achar a causa. Nos 4 acionamentos por mês da alta, o valor novo também fica abaixo de 70% da mediana.
- **Município e mês: marca, não bloqueia.** O site publica o valor novo, que é o do arquivo oficial mais recente, marcado como "em revisão", com o valor da versão anterior ao lado e fora de variações e comparações. O TabNet já mostra a mesma versão, conferido em Santo André por competência; por mês da alta, ele não tem como confirmar. A marca sai sozinha quando uma versão seguinte volta para dentro do limite. O valor antigo nunca substitui o novo: misturar versões quebra as margens, e o antigo também pode estar errado, como em Paulínia.
- **Publicação inteira: só em falha estrutural.** Queda de 5% ou mais no total de uma UF e competência (a maior medida foi −0,88%), ou arquivo que reprove o contrato. Nesses casos o site anterior continua no ar e um alerta é aberto.

Barrar a publicação inteira por causa de um município teria parado 5.570 páginas por 6 estabelecimentos de uma cidade, e por tempo indeterminado.

**No pipeline, em 08/11/2026** (`sih_trava.py`, [`trava_f1b.json`](medicoes/resultados/trava_f1b.json)). Sobre as tabelas já suprimidas, no mesmo par de versões de SP e com as 27 UFs: por mês da alta, 4 acionamentos por residência e 4 por hospital, todos de Santo André, de 2604 a 2607, e nenhum em outro município. Entre os pares visíveis nas duas versões, mudaram 2 por residência e 1 por hospital em 2025, e 139 e 18 em 2026. A maior queda de uma UF numa competência foi de 0,88%, abaixo dos 5% da falha estrutural. A trava parte das células visíveis na versão anterior. Se a célula some da tabela nova, que só tem chaves com alguma AIH, conta como queda para zero; se fica oculta, não é comparada, porque não há valor publicado. A medição foi refeita com essa regra, com o mesmo resultado.

## Esquema do catálogo

O catálogo é a fonte de verdade: gera os agregados, valida a especificação, alimenta a busca e escreve as ressalvas na tela. Cada base tem regras próprias.

```yaml
versao: 1

temas:   # lista fixa; o filtro mostra só os que têm métrica publicada
  populacao: População
  saude: Saúde
  educacao: Educação
  economia: Economia
  trabalho: Trabalho
  financas_publicas: Finanças públicas
  agropecuaria: Agropecuária
  assistencia_social: Assistência social
  saneamento: Saneamento
  meio_ambiente: Meio ambiente
  eleicoes: Eleições
  seguranca: Segurança

bases:
  sih:
    nome: Internações hospitalares do SUS
    orgao: Ministério da Saúde / DATASUS
    licenca: { id: nao-declarada-na-origem, atribuicao: "Ministério da Saúde/DATASUS, SIH/SUS" }
    coleta:
      origem: ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados
      padrao: "RD{uf}{aamm}.dbc"
      colunas: [N_AIH, ANO_CMPT, MES_CMPT, IDENT, CNES, MUNIC_MOV, MUNIC_RES, DIAG_PRINC, DT_SAIDA,
                DIAS_PERM, VAL_TOT, MORTE, ESPEC, CAR_INT, SEXO, IDADE, COD_IDADE, RACA_COR]
      so_para_validar: [N_AIH]     # confere a chave no pipeline e nunca sai dele
      todas_as_ufs: true           # residência depende de internações em outros estados
    tempo:
      eixo: mes_da_alta            # DT_SAIDA, incorporando o processamento tardio
      janela_republicada_meses: 12
      defasagem_maxima_meses: 5    # fecha o mês M quando M + 5 <= última competência - 12
    maturacao:
      meses_padrao: 3
      por_uf: { AL: 6, BA: 4 }
    revisao:
      municipio: { queda_pct: 30, minimo_internacoes: 100, acao: marcar_em_revisao }
      publicacao: { queda_uf_competencia_pct: 5, acao: manter_site_anterior }
    supressao:
      aplica: true
      k: 5
      contagens: [aihs, internacoes]  # oculta se qualquer uma estiver entre 1 e k-1
      nao_publicar: [aihs]            # a diferença entre as duas seria outra contagem pequena
      complementar: true
      familia: true
    ressalvas:
      - Só SUS. Internações particulares e por plano não aparecem.
      - O valor é o pago pela tabela SIGTAP, não o custo do hospital.
      - Os meses são da data da alta. No TabNet, "atendimento" é a data de internação, e os meses não coincidem.

metricas:
  populacao_estimada:
    tema: populacao
    etiquetas: []
    base: ibge_estimativa
    rotulo: População estimada
    fonte:
      orgao: IBGE
      pesquisa: Estimativas da População, tabela 6579 da SIDRA, variável 9324
      acesso:
        tipo: exato     # exato | tabela | arquivo | receita
        url: "https://apisidra.ibge.gov.br/values/t/6579/n6/{municipio}/v/9324/p/{periodo}"
      tabela: "https://sidra.ibge.gov.br/tabela/6579"
  internacoes:
    tema: saude
    etiquetas: []
    base: sih
    rotulo: Internações
    sinonimos: [internação, hospitalização, baixa hospitalar]
    regra: "IDENT = 1"
    fonte:
      orgao: Ministério da Saúde / DATASUS
      acesso:
        tipo: receita
        url: "http://tabnet.datasus.gov.br/cgi/deftohtm.exe?sih/cnv/nrbr.def"
        receita: "Linha: Município; Conteúdo: Internações; Períodos disponíveis: as competências do ano"
    conferencia: { ferramenta: TabNet, medida: "Internações", eixos: [competencia, data_de_internacao] }
  obitos:
    tema: saude
    etiquetas: []
    base: sih
    rotulo: Óbitos hospitalares
    regra: "soma de MORTE"
    cruzamentos: [sih_res_ano, sih_hosp_ano]   # só o total anual
    ressalvas: [Hospitais de referência recebem casos mais graves. A taxa sozinha não mede qualidade.]
  taxa_internacao:
    tema: saude
    etiquetas: [populacao]
    rotulo: Internações por mil habitantes
    formula: "internacoes / populacao_estimada * 1000"
    fontes: [internacoes, populacao_estimada]   # calculada: cada parcela traz a própria fonte
    oculta_se: [internacoes]                     # herda a máscara do numerador

dimensoes:
  municipio_residencia: { base: sih, coluna: mun_res, conversao: ibge6_para_ibge7 }
  municipio_hospital:   { base: sih, coluna: mun_hosp, conversao: ibge6_para_ibge7 }
  faixa_5: { base: sih, valores: [00-14, 15-29, 30-49, 50-69, 70+], aninhada_em: faixa_12 }

cruzamentos:
  - id: sih_res_mes
    dimensoes: [municipio_residencia, mes]
    metricas: [internacoes, dias, valor]
    arquivo: "sih/res_mes/uf={uf}/ano={ano}.parquet"
    margens_publicadas: [municipio_ano, uf_mes, brasil_mes]
    medido: { celulas_ocultas_pct: 0.7, internacoes_ocultas_pct: 0.02, mb_por_ano: 0.55 }
  - id: sih_res_mes_sexo
    mae: sih_res_mes              # oculta na mãe esconde as filhas da mesma chave
    dimensoes: [municipio_residencia, mes, sexo]
    metricas: [internacoes]
    margens_publicadas: [municipio_mes, municipio_ano_sexo]

ambiguidades:
  - gatilho: "em {municipio}"
    opcoes: [municipio_residencia, municipio_hospital]
    padrao: null     # a tela sempre pergunta
```

As margens são declaradas porque são elas que definem o que dá para deduzir. Publicar uma margem nova exige passar de novo no teste.

**Tema e etiquetas.** Cada métrica tem um `tema` principal e `etiquetas` com os outros temas em que aparece. A lista de temas é fixa e fica no catálogo; criar um tema é mudança de catálogo, não de tela. O filtro mostra só temas com métrica publicada e entra na especificação e na URL (`"tema": "saude"`).

**Fonte.** Cada métrica diz como chegar ao número na origem:

| `acesso.tipo` | Quando | O que a tela mostra |
|---|---|---|
| `exato` | A origem tem um endereço que devolve aquele valor | O link, já com município e período |
| `tabela` | O endereço abre a tabela, e é preciso escolher município e período | O link e os filtros a aplicar |
| `arquivo` | O número sai de um arquivo baixado | O endereço do arquivo |
| `receita` | Não há link para o resultado, como no TabNet | Os passos na ferramenta oficial |

Hash e data da coleta de cada arquivo usado vêm do manifesto, não do catálogo: o catálogo diz de onde vem, o manifesto diz o que foi baixado. Quando o número usa muitos arquivos, como o SIH por residência, o painel mostra o resumo e o link para a lista completa. Métrica calculada lista todas as parcelas em `fontes` e a `formula`, e cada parcela traz a própria fonte.

**Célula oculta.** A supressão guarda o motivo de cada célula (`contagem_pequena`, `complementar` ou `familia`), e ele fica no pipeline. O motivo também é informação para quem tenta deduzir: numa margem com uma oculta de cada tipo e soma 6, a pequena só pode ser 1. **Decidido em 08/11/2026:** o motivo não é publicado, e toda célula oculta aparece do mesmo jeito no gráfico, na tabela, no CSV e no PNG, sem texto que diga o intervalo dela. A regra fica explicada no painel "Fonte e método". O teste de dedução ainda sabe tratar o motivo como público (a pequena entre 0 e k−1, a complementar fora de 1 a k−1), e foi assim que o efeito foi medido; ver [Teste de dedução da F1b](#teste-de-dedução-da-f1b).

## Regras do SIH levadas para o catálogo

As regras vieram do projeto [Dados-Hospitalares-SUS](https://github.com/MatheusCavalcanteF/datasus-etl-baixada-santista) e foram reconferidas com os dados do Brasil inteiro.

| Regra | Evidência |
|---|---|
| Internação = AIH com `IDENT=1`; as de `IDENT=5` são prorrogações | Confere com o TabNet. No Brasil, 135.213 de 14,6 milhões |
| Chave: (`N_AIH`, competência, `IDENT`, `DT_SAIDA`) | Contrato do projeto de origem |
| Dias de permanência somam todas as AIHs; a média divide pelas internações | Confere com o TabNet só somando todas |
| Ticket médio exclui valor zero | 43.934 AIHs com valor zero no Brasil, 98,2% em leitos de saúde mental (especialidade 87) |
| Período pela data da alta, não pela competência nem pela internação | 4,4% das linhas de 2025 têm alta antes de 2025; a defasagem chega a 5 meses. O "atendimento" do TabNet é a data de internação, então os meses não coincidem |
| Consolidação: 3 meses; AL e BA pedem mais | 99,7% no Brasil em 3 meses; AL 97,6%, BA 98,5% |
| Hospital e residência são visões diferentes | 36,4% das internações ocorrem fora do município de residência. 2.424 municípios não têm internação por hospital |
| Residência exige as 27 UFs | Ver a primeira tabela deste documento |
| Cada CNES pertence a um município | Vale para os 4.880 hospitais de 2025 |
| Sexo: `1` masculino; `2` e `3` feminino | Em 2025, só `1` e `3` aparecem |
| Idade por `COD_IDADE` (2 dias, 3 meses, 4 anos, 5 = 100 + idade) | Código fora da tabela é caso residual no país, e vai para "ignorada" |
| Só colunas da lista são lidas | CEP, nascimento e CPFs não saem do arquivo de origem. `N_AIH` serve só para conferir a chave e não chega ao agregado |

A qualidade dos códigos surpreendeu positivamente: nenhum município fora da lista do IBGE, nenhum CID fora do formato, nenhuma data inválida, nenhuma permanência negativa nos 14,6 milhões de registros. As categorias U09 e U10 (30 registros) não constam da tabela CID-10 de 2008.

## Privacidade e supressão

O site publica só agregados. Contagens de 1 a 4 não são publicadas, e toda célula oculta aparece do mesmo jeito, sem motivo nem intervalo; zero é mostrado como zero. A regra fica explicada no painel "Fonte e método".

**A regra tem quatro camadas, e cada uma existe porque a anterior deixou passar algo medido:**

1. **Por métrica.** A célula fica oculta quando as AIHs **ou** as internações estão entre 1 e 4. Decidir só pelas AIHs deixava 2.225 células visíveis com 1 a 4 internações nas 14 tabelas publicáveis, e 720 no fluxo por ano. As AIHs não são publicadas: a diferença entre as duas medidas seria outra contagem pequena.
2. **Complementar, por tabela.** Oculta também o menor valor visível em cada linha marginal que permitiria deduzir: uma só célula oculta com margem visível, ou ocultas somando menos que 5. Isso vale inclusive para o município somado dentro da UF.
3. **Por família, entre tabelas.** Uma célula oculta na tabela-mãe esconde todas as filhas da mesma chave, e a única filha de uma mãe visível não serve de complementar, porque seu valor já é público. Um trimestre herda a ocultação de qualquer mês dele. Faixas etárias precisam ser aninhadas: as de 5 grupos cabem nas de 12, para não permitir subtração.
4. **Teste de dedução.** Age como quem tenta deduzir: parte do que é visível e usa as margens publicadas em cadeia. **Sem família, 113 contagens de 1 a 4 eram dedutíveis; com família e só as margens declaradas, zero.** Se todas as margens fossem publicadas (UF x categoria, por exemplo), sobrariam 157 em hospital x mês x caráter, por isso elas não são publicadas.

**Critério para publicar um cruzamento:** no máximo 5% das internações e 50% das células ocultas, e zero no teste de dedução com as margens declaradas. Tabelas de cauda longa, como fluxo entre municípios, podem passar com recorte (os maiores valores e "demais").

### Teste de dedução da F1b

Medido em 08/11/2026, com as 27 UFs, nos seis anos da alta de 2021 a 2026 (2026 até julho), na versão dos arquivos de 16/10/2026. Scripts no pipeline: `deducao.py`, `sih_deducao.py`, `supressao.py`.

**O ataque ficou mais forte que o da Etapa 0.** Em vez de usar só as margens declaradas, ele parte de tudo o que é publicado (os 14 cruzamentos e as margens de UF e do Brasil) e de toda soma que se pode montar com isso: trimestre por faixa etária, UF por sexo, município por trimestre, e assim por diante, 82 tabelas por ano, das quais 64 ninguém publica. Cada célula ganha um intervalo do que pode valer, e o ataque aperta os intervalos pelas somas, em cadeia, até nada mudar. Uma contagem é revelada quando o intervalo vira um ponto entre 1 e 4. O teste confere que o valor verdadeiro nunca sai do intervalo.

**O motivo da célula oculta, se publicado, entrega quase tudo.** Com o motivo público, a pequena entre 0 e 4 (0 porque a regra também oculta pelas AIHs) e a complementar fora de 1 a 4, a supressão da Etapa 0 deixou 4.365 contagens reveladas em 2025, quase todas em residência x trimestre x capítulo e residência x mês x faixa etária, e 10.078 estreitadas a dois valores possíveis. O reforço descrito abaixo baixou para cerca de 365 e empacou, depois de 10 rodadas e 1,6 ponto percentual a mais de células ocultas. Sem o motivo, quem lê só sabe que a célula está oculta, e a mesma supressão revelou 1. **Decidido em 08/11/2026: o motivo por célula não é publicado**, e toda célula oculta aparece do mesmo jeito, sem texto que diga o intervalo dela. A regra continua explicada no painel "Fonte e método". Está em `supressao.motivo_por_celula: false` no catálogo.

**Reforço guiado pelo teste.** Quando o ataque revela algo, as células ocultas que ficaram exatas e as que compõem uma soma revelada estão expostas, e cada margem que contém uma delas perde a menor célula visível. Uma soma não publicada costuma sair de um total menos as vizinhas exatas, como o trimestre de um município: o total da UF no trimestre, que sai das margens mensais publicadas, menos os trimestres dos outros municípios. Nesse caso o reforço oculta um retângulo: um mês do mesmo trimestre e um de outro trimestre num município vizinho, para que as quatro somas deixem de ser exatas. Repete até o teste dar zero.

**A complementar protege só as margens conhecidas.** Antes, ela tratava como conhecida toda soma de uma coluna, inclusive as que só saem da própria tabela, como eletivo mais outros num hospital e mês. Agora protege as publicadas e as que dá para calcular a partir de outra tabela publicada, e o teste com o reforço cobre o resto. Nos três anos medidos dos dois jeitos (2021, 2025, 2026), os dois passam no teste, e as margens conhecidas ocultam de 10% a 12% menos células. É `supressao.margens_complementar: conhecidas`.

| Ano da alta | Internações | Reveladas antes do reforço | Rodadas | Teste depois do reforço |
|---|---:|---:|---:|---|
| 2021 | 11.559.233 | 106 | 1 | zero |
| 2022 | 12.363.273 | 96 | 1 | zero |
| 2023 | 13.229.794 | 113 | 1 | zero |
| 2024 | 14.029.372 | 82 | 1 | zero |
| 2025 | 14.546.743 | 0 | 0 | zero |
| 2026, até julho | 7.899.844 | 0 | 0 | zero |

Refeito em 08/11/2026 com as regras decididas, numa execução local do pipeline sobre a mesma versão dos arquivos ([`sih_local_f1b.json`](medicoes/resultados/sih_local_f1b.json)). O teste vê o que a tela mostra: sem motivo, com os meses preliminares em múltiplo de 5 e, em cada ano, só os cruzamentos que passaram no critério. Com os valores exatos, 2025 revelava 55 e 2026, 1.100, em 3 rodadas; arredondados, nenhum dos dois precisa de reforço. Em 2021, 108 viraram 106 porque dois cruzamentos saíram do ano.

Óbitos, com máscara própria no total anual por município, deram zero em todos os anos, sem reforço.

**O que passa do critério de publicação.** Decidido em 08/11/2026: o cruzamento que reprova não é publicado naquele ano, a página diz por quê, e o que depende dele (filha ou trimestre) sai junto. O critério está em `supressao.criterio_publicacao`, e a supressão e o teste são refeitos sem o que saiu. Na execução de 08/11/2026: em 2021, saem residência x mês x urgência (6,7% das internações ocultas) e hospital x mês x caráter (5,1%); em 2026, residência x trimestre x capítulo (7,6% das internações e 50,5% das células). De 2022 a 2025, todos passam.

**Trimestre só com os três meses na base.** O trimestre que ainda não terminou fica fora do arquivo. A supressão o trata como publicado, porque o ano menos os trimestres completos o devolve, e ele nunca serve de complementar. Mesmo sem o terceiro trimestre, que em 2026 só tinha julho, residência x trimestre x capítulo reprova: 7,6% das internações e 50,5% das células, contra 7,9% e 52,9% com ele.

**Os dois de sexo de 2026 passaram.** Antes, residência x mês x sexo ocultava 6,3% das internações, e residência x ano x faixa x sexo, 5,1%; agora, 4,77% e 0,83%. A categoria não foi retirada, porque o total de outra tabela a devolveria por subtração. A mudança veio do arredondamento: com o teste vendo os preliminares em múltiplo de 5, 2026 não precisa mais de rodada de reforço, e eram as rodadas que ocultavam masculino ou feminino nas linhas com o sexo 4. Mês x sexo ficou perto do limite e pode reprovar numa versão seguinte.

### SIH, Brasil, 2025

A coluna "Internações ocultas" mede internações, não AIHs. Percentuais com todas as margens consideradas na complementar.

| Cruzamento | Linhas | Células ocultas | Internações ocultas | Parquet | Situação |
|---|---:|---:|---:|---:|---|
| Residência x ano | 5.570 | 0,0% | 0,00% | 0,06 MB | Publicar |
| Hospital x ano | 3.145 | 0,1% | 0,00% | 0,04 MB | Publicar |
| Residência x mês | 66.828 | 0,7% | 0,02% | 0,55 MB | Publicar |
| Hospital x mês | 36.862 | 4,0% | 0,05% | 0,31 MB | Publicar |
| Residência x mês x sexo | 133.505 | 6,5% | 0,39% | 0,97 MB | Publicar |
| Residência x ano x capítulo CID | 106.957 | 16,3% | 0,37% | 0,77 MB | Publicar |
| Residência x ano x cor/raça | 22.483 | 25,7% | 0,72% | 0,17 MB | Publicar |
| Residência x ano x faixa etária (12) x sexo | 131.936 | 16,0% | 0,85% | 0,89 MB | Publicar |
| Hospital x ano x especialidade | 10.984 | 11,0% | 0,70% | 0,10 MB | Publicar |
| Hospital x trimestre x capítulo CID | 171.984 | 35,4% | 1,50% | 0,98 MB | Publicar |
| Residência x mês x urgência ou não | 133.018 | 13,4% | 1,60% | 0,92 MB | Publicar |
| Residência x mês x faixa etária (5) | 326.761 | 23,6% | 2,05% | 1,88 MB | Publicar |
| Residência x trimestre x capítulo CID | 380.845 | 38,5% | 2,95% | 1,93 MB | Publicar |
| Hospital x mês x caráter | 58.540 | 13,9% | 4,53% | 0,45 MB | Publicar, sem margem anual por caráter |
| Fluxo residência → hospital x ano | 117.068 | 61,1% | 2,75% | 0,62 MB | Com recorte |
| Hospital x mês x especialidade | 116.828 | 26,3% | 2,55% | 0,75 MB | Fora da v1: 37 valores dedutíveis pelo total anual |
| Hospital x mês x capítulo CID | 429.330 | 44,6% | 3,23% | 2,02 MB | Fora da v1: redundante com o trimestre, e soma com ele permite subtrair |
| Estabelecimento x mês | 55.870 | 5,8% | 1,07% | 0,48 MB | Fora da v1 |
| Estabelecimento x ano x capítulo CID | 70.323 | 24,7% | 4,06% | 0,53 MB | Fora da v1 |
| Residência x mês x capítulo CID | 942.679 | 54,1% | 7,75% | 3,61 MB | **Não** |
| Residência x mês x caráter (3 grupos) | 142.840 | 23,3% | 8,06% | 0,91 MB | **Não** |
| Fluxo residência → hospital x mês | 524.048 | 67,0% | 9,50% | 1,90 MB | **Não** |
| Residência x ano x procedimento | 1.217.371 | 71,5% | 10,55% | 4,31 MB | **Não** |
| Residência x ano x categoria CID (3 dígitos) | 1.485.310 | 73,1% | 13,24% | 5,09 MB | **Não** |
| Residência x ano x capítulo x faixa (5) x sexo | 678.619 | 68,5% | 21,87% | 2,08 MB | **Não** |
| Residência x mês x categoria CID | 4.612.115 | 88,8% | 44,09% | 12,16 MB | **Não** |
| Residência x mês x capítulo x faixa (5) x sexo | 3.296.997 | 92,3% | 54,42% | 5,44 MB | **Não** |

As 15 tabelas publicáveis somam **10,64 MB por ano** nestes arquivos nacionais com zstd; com os totais anuais de óbitos, 10,7 MB. No formato escolhido, por UF e sem compressão, são 22,9 MB, ou 11,9 MB em transferência com gzip. **Na F1b, com cada cruzamento levando só as métricas do catálogo** (dias e valor nas tabelas de município por ano e por mês; nas outras, só internações), são de 6,9 a 7,3 MB por ano completo, 3,8 a 3,9 MB com gzip, e o maior arquivo, residência x mês de MG, tem 170 KB ([`particoes_f1b.json`](medicoes/resultados/particoes_f1b.json)). Com dias e valor em todas as tabelas, como na Etapa 0, seriam 20 a 22 MB. Juntar categorias raras ajuda muito: "caráter" com 3 grupos oculta 8,06%, porque a complementar acaba caindo em células grandes; com "urgência ou não", 1,60%.

**A média nacional esconde as cidades pequenas.** O critério acima olha o país inteiro. Por faixa de população (células ocultas / internações ocultas):

| Cruzamento | Até 5 mil (1.286) | 5 a 20 mil (2.530) | 20 a 100 mil (1.417) | 100 a 500 mil (289) | Mais de 500 mil (49) |
|---|---:|---:|---:|---:|---:|
| Residência x mês | 2,8% / 0,61% | 0,2% / 0,02% | 0% / 0% | 0% / 0% | 0% / 0% |
| Residência x mês x sexo | 22,4% / 10,56% | 2,9% / 0,74% | 0,1% / 0,02% | 0% / 0% | 0% / 0% |
| Residência x ano x capítulo CID | 31,5% / 4,67% | 16,6% / 1,08% | 6,6% / 0,22% | 1,6% / 0,04% | 2,4% / 0,03% |
| Residência x mês x urgência ou não | 36,8% / 24,09% | 10,5% / 5,56% | 0,9% / 0,39% | 0% / 0% | 0% / 0% |
| Residência x ano x faixa etária (12) x sexo | 41,4% / 15,59% | 14,6% / 2,79% | 0,4% / 0,04% | 0% / 0% | 0% / 0% |
| Residência x mês x faixa etária (5) | 60,4% / 33,58% | 21,7% / 6,89% | 1,8% / 0,37% | 0,1% / 0,01% | 0% / 0% |
| Residência x trimestre x capítulo CID | 65,9% / 31,69% | 43,2% / 9,24% | 20,8% / 1,84% | 7,6% / 0,41% | 3,4% / 0,17% |
| Hospital x trimestre x capítulo CID | 72,6% / 27,01% | 50,1% / 9,65% | 28,7% / 2,26% | 13,1% / 0,46% | 4,8% / 0,20% |

Por isso, cada página começa pelo menor nível de detalhe que funciona naquele município: se metade ou mais dos meses vier oculta, ela abre no ano e oferece o detalhe depois. Sem isso, 68,5% dos municípios, os de até 20 mil habitantes, veriam gráficos cheios de lacunas.

### Óbitos

O caminho anterior, de só trocar 1 a 4 por nulo, não protegia: entre as tabelas por residência, o valor exato era dedutível em 9 casos, e em hospital x ano x especialidade 816 de 3.145 municípios tinham uma única célula nula, que um total publicado revelaria. Foram medidas duas saídas:

| | A: por categoria, com complementar própria | B: só o total anual por município |
|---|---|---|
| Células com óbito oculto | 30,4% a 62,4%, conforme a tabela | 2,6% por residência (144 de 5.570); 11,6% por hospital (364 de 3.145) |
| Óbitos ocultos | 7,1% a 19,5% | 0,07% por residência; 0,15% por hospital |
| Cidades de até 5 mil | 29,7% a 97,5% dos óbitos ocultos | 115 de 1.286 municípios ocultos, por residência |
| Municípios com ao menos metade dos capítulos visível | 11 de 1.284 até 5 mil; 49 de 49 acima de 500 mil | Não se aplica |
| "Sobreviventes" de 1 a 4 deduzíveis | Casos nas tabelas de capítulo, faixa e especialidade | 0 |
| Tamanho | Coluna a mais em cada tabela | 0,05 MB por ano |

**Decisão: opção B na v1.** O total anual responde à pergunta principal em quase todos os municípios, com uma fração do risco. A opção A só serve bem a cidades grandes e multiplica as margens a defender. A taxa de mortalidade segue a mesma máscara do numerador. Por mês, nem o total: 49,2% das células têm de 1 a 4 óbitos e ficariam ocultas antes de qualquer complementar, e só 793 municípios teriam a série inteira.

### Comparação entre versões

A republicação mensal também permite subtrair. Medido em SP, entre setembro e outubro de 2026, por mês da alta: **77 pares visíveis nas duas versões mudaram de 1 a 4 internações por residência (em 56 municípios), e 7 por hospital.** Quem guardar as duas versões descobre essa contagem pequena, ainda que sem detalhe de categoria.

O teste de dedução da F1 inclui essa comparação, sobre o site publicado e a versão candidata, em todos os cruzamentos. **Decidido em 08/11/2026:** os meses preliminares saem arredondados para múltiplo de 5, com o valor exato só quando o mês fecha, o que também combina com a natureza provisória do dado. Cada valor arredondado aparece marcado como preliminar e arredondado no gráfico, na tabela e no CSV, e as taxas usam o valor arredondado (`bases.sih.preliminares` no catálogo).

**Medido na F1b, em 08/11/2026** ([`versoes_f1b.json`](medicoes/resultados/versoes_f1b.json)). Como nada do SIH foi publicado, a versão "publicada" foi montada de dois jeitos, sempre com as 27 UFs e a supressão final (sem motivo por célula, reforço com o limite de rodadas do catálogo; as 16 versões montadas chegaram a zero no teste):
- **Par real:** SP com os arquivos de setembro de 2026 (2509 a 2607, guardados no projeto de origem) contra os de outubro. As outras UFs entram iguais nas duas versões, porque só SP tem as duas guardadas.
- **Pares simulados:** a versão com a última competência L contra a com L−1, para L de 2604 a 2607, tirando as AIHs das competências que ainda não teriam saído. Mede o processamento tardio, que é a maior parte do que muda de um mês para o outro, e deixa de fora as correções de republicação.

Quem guarda as duas versões conhece a diferença onde as duas são exatas e pode deduzir mais pelas mesmas somas, porque a diferença também respeita todas as arestas (`deducao.diferencas`). Diferença exata de 1 a 4, em módulo, conta como revelada.

| Par | Ano | Meses preliminares | Exato: diferenças de 1 a 4 | Em tabelas publicadas | Múltiplo de 5 | Múltiplo de 10 |
|---|---|---:|---:|---:|---:|---:|
| Real, SP setembro x outubro | 2025 | 9 | 62 | 31 | 0 | 0 |
| Real, SP setembro x outubro | 2026 | 8 | 2.193 | 1.342 | 0 | 0 |
| Simulado, 2603 x 2604 | 2025 | 12 | 19.452 | 9.999 | 0 | 0 |
| Simulado, 2603 x 2604 | 2026 | 4 | 126.513 | 109.476 | 0 | 0 |
| Simulado, 2604 x 2605 | 2025 | 12 | 5.830 | 2.837 | 0 | 0 |
| Simulado, 2604 x 2605 | 2026 | 5 | 156.150 | 127.927 | 0 | 0 |
| Simulado, 2605 x 2606 | 2026 | 6 | 184.910 | 149.020 | 0 | 0 |
| Simulado, 2606 x 2607 | 2026 | 7 | 194.045 | 158.632 | 0 | 0 |

Todas as diferenças reveladas vêm direto de duas células exatas; a cadeia não acrescentou nenhuma. As que mais aparecem são residência x ano x faixa x sexo, residência x ano x capítulo e residência x mês x faixa etária: o processamento tardio de uma competência traz poucas AIHs por município e categoria. **Com os valores exatos, toda atualização mensal revela milhares de grupos de 1 a 4 internações.**

**O custo do arredondamento.** Arredonda-se toda célula visível de período que contém mês preliminar: o mês, o trimestre dele e, nas tabelas anuais, o ano aberto inteiro, porque um total anual exato entregaria a soma dos meses arredondados. Ocultas continuam ocultas, e zero continua zero. Com a janela de 12 competências e a defasagem de 5 meses, um mês fica preliminar por 17 meses, então em novembro de 2026 isso alcança 80,4% das células visíveis de 2025 e todas as de 2026.

| | Múltiplo de 5 | Múltiplo de 10 |
|---|---:|---:|
| Erro médio por célula | 1,17 a 1,18 internação | 2,53 a 2,57 internações |
| Células com erro acima de 10% | 19,5% a 23,4% | 37,5% a 42,9% |
| Células com erro acima de 20% | 5,8% a 7,3% | 19,8% a 24,4% |
| Diferenças de 1 a 4 reveladas entre versões | 0 | 0 |
| Contagens reveladas dentro de cada versão | 0 | 0 |

Faixas dos 8 pares acima, sobre as células arredondadas da versão mais nova.

**Transição de fechamento e três versões, com a regra decidida** ([`versoes_transicao_f1b.json`](medicoes/resultados/versoes_transicao_f1b.json), `medir_versoes_transicao.py`). Quem guarda as versões ataca todas juntas: cada uma como a tela mostra, e as células de período já fechado na mais nova iguais nas duas, porque nenhum arquivo com altas daquele período foi republicado entre elas (`deducao.atacar_juntos`). Em três versões, também d(1,3) = d(1,2) + d(2,3) (`deducao.diferencas_em_sequencia`).

| Versões | O que fecha | Teste de cada uma | Todas juntas | Diferenças de 1 a 4 |
|---|---|---|---:|---:|
| SP, setembro x outubro, 2025 | março de 2025 e o 1º trimestre | 0 e 0 | 0 | 0 |
| SP, setembro x outubro, 2026 | nada | 0 e 0 | 0 | 0 |
| Simuladas, 2605, 2606 e 2607, ano 2025 | janeiro, depois fevereiro de 2025 | 0, 0 e 0 | 0 | 0 nos três pares |
| Simuladas, 2605, 2606 e 2607, ano 2026 | nada | 0, 0 e 0 | 0 | 0 nos três pares |
| Simuladas, 2604 e 2605, ano 2024 | dezembro e o ano inteiro | 0 e 0 | **18 sem herança; 0 com herança** | 0 |

**Quando o ano fecha, as duas versões juntas revelavam 18 contagens.** Com dezembro fechado, as tabelas do ano passam de arredondadas a exatas, a supressão é refeita e escolhe outras complementares. Quem guardou a versão anterior cruza os dois padrões: a célula que estava oculta e agora aparece entrega o que ela protegia, e a que estava exata e agora some não protege nada. Foram 11 em residência x mês x faixa etária e 7 em tabelas de hospital, em cada versão. **Por isso, nas células de período fechado, a versão nova herda o padrão da anterior** (`sih.fixas_da_anterior`): a oculta continua oculta, e a visível e exata não pode virar complementar; a que estava arredondada pode ser ocultada. Com a herança, a versão de 2605 precisou de 3 rodadas de reforço, e o ataque conjunto deu zero. Nos outros grupos, que já davam zero, nada mudou. O comando `sih` recebe a versão publicada antes em `--anterior`.

Nas simuladas de 2026, residência x trimestre x capítulo passa no critério com a última competência 2606 e reprova com 2605 e 2607. Publicado assim, ele apareceria e sumiria de um mês para o outro. O ataque conjunto conta com isso e deu zero.

**Quanto um mês ainda muda depois de 6, 9 e 12 meses.** Só medição, sem mudar regra ([`mudanca_tardia_f1b.json`](medicoes/resultados/mudanca_tardia_f1b.json), `medir_mudanca_tardia.py`). São duas leituras, com dados diferentes:
- **Depois do fechamento.** Fechado, um mês só muda se o DATASUS regravar uma competência que já saiu da janela. Pela data de modificação na listagem do FTP, nas 27 UFs, nenhum mês de 2021 em diante mudou depois de fechar: em cada UF, 45 meses estão fechados há 6 meses ou mais, 42 há 9 e 39 há 12, e em nenhum uma competência com altas dele foi regravada. Em SP, a última cópia na janela das competências 2501 a 2508, guardada no projeto de origem, é idêntica byte a byte à de hoje. Antes de 2021 houve regravações em lote (a mais recente, AC de setembro de 2009, em 22/05/2024), então o aviso para competência congelada que muda continua necessário.
- **Depois do próprio mês.** O processamento tardio acaba no 5º mês em todas as UFs, como garante o contrato: depois de 6, 9 e 12 meses, nada mais chega. No próprio mês da alta já estão de 20,0% (RR) a 82,8% (PE) das internações dele; três meses depois, de 98,0% (AL) a 100%. Depois do 5º mês, só a correção numa republicação muda o mês, e só SP tem duas versões guardadas: de setembro para outubro de 2026, o mês com 6 meses de idade (fevereiro de 2026) mudou em 13 municípios de residência, 8 deles por 1 a 4 internações, e o total subiu 424; os de 9 e 12 meses (novembro e agosto de 2025) não mudaram. Nas outras UFs, a correção depois do 5º mês só pode ser medida guardando versões.

### Novo CAGED, Brasil, 2025

**Base desta tabela: só o arquivo `MOV` de 2025.** Linhas, tamanhos e supressão dos cruzamentos não incluem `FOR` nem `EXC`, e a conferência com os ajustes, descrita em [Novo CAGED](#fontes), é só do total nacional. Com os três arquivos, esses números podem mudar, e a F6 precisa medi-los de novo.

O problema é o mesmo, e maior. A regra anterior decidia só pelo total de movimentos e deixava de 7.390 a 225.434 células visíveis com admissões ou desligamentos de 1 a 4, conforme a tabela. Com a regra por métrica e a família:

| Cruzamento | Linhas | Células ocultas | Movimentos ocultos | Parquet | Situação |
|---|---:|---:|---:|---:|---|
| Município x mês | 65.721 | 19,0% | 0,19% | 0,30 MB | Publicar |
| Município x ano x seção de atividade | 70.903 | 38,0% | 0,31% | 0,31 MB | Publicar |
| Município x mês x sexo | 127.354 | 39,2% | 1,14% | 0,42 MB | Publicar |
| Município x ano x subclasse de atividade | 588.508 | 58,1% | 3,34% | 1,90 MB | Com recorte |
| Município x mês x faixa etária | 303.271 | 59,3% | 3,15% | 0,74 MB | Com recorte |
| Município x mês x grande grupo de ocupação | 441.539 | 59,9% | 2,75% | 1,01 MB | Com recorte |
| Município x mês x seção de atividade | 578.672 | 64,0% | 3,60% | 1,35 MB | Com recorte |
| Município x mês x instrução | 456.746 | 66,0% | 3,15% | 0,97 MB | Com recorte |
| Município x ano x ocupação | 994.623 | 72,8% | 5,18% | 2,56 MB | **Não** |
| Município x mês x divisão de atividade | 1.194.336 | 70,8% | 7,15% | 2,50 MB | **Não** |
| Município x ano x seção x sexo x faixa | 441.455 | 78,4% | 9,13% | 0,85 MB | **Não** |
| Município x mês x seção x sexo | 932.445 | 78,8% | 11,38% | 1,58 MB | **Não** |

A F6 deve testar máscara por medida, escondendo só as admissões quando elas forem pequenas e mantendo os desligamentos, o que pode recuperar parte disso. O teste de dedução da F1 ainda não cobre o CAGED.

### Educação, Brasil, 2024

| Tabela | Linhas | Células ocultas | Valor oculto | Parquet |
|---|---:|---:|---:|---:|
| Município x rede x etapa: matrículas | 45.072 | 4,7% | 2,11% | 0,14 MB |
| Município x rede: matrículas | 14.951 | 0,2% | 0,02% | 0,10 MB (as 3 medidas) |
| Município x rede: docentes | 14.951 | 3,1% | 0,45% | |

### Onde a regra se aplica

- **Aplica:** internações, óbitos, emprego, matrículas e docentes.
- **Não aplica:** contas públicas, índices (IDEB), população e contagem de estabelecimentos. PIB e turmas também ficam fora: não são contagem de pessoas.

Os microdados de origem são públicos, e o TabNet mostra contagens pequenas abertamente. A regra protege o que este site expõe e cruza, e é escolha deste projeto: em cidades pequenas, o site vai mostrar menos detalhe que o TabNet.

## Limites de tamanho

Os limites valem para o que é publicado. O orçamento total deixa margem no 1 GB do GitHub Pages.

| Tema | Medido (Brasil) | Janela da v1 | Previsto (estimativa) | Limite |
|---|---:|---|---:|---:|
| SIH, agregados Parquet | Medido na F1b: 41,1 MB de 2021 a julho de 2026 (6,9 a 7,3 MB por ano completo), por UF e sem compressão; 22,2 MB com gzip | 2021 em diante | ~45 MB até o fim de 2026 | 200 MB |
| INEP, Censo Escolar e IDEB | 0,24 MB por ano + IDEB | 2019 em diante | ~5 MB | 20 MB |
| IBGE | < 1 MB | Última + série de população | ~2 MB | 10 MB |
| JSON por município | 113,8 MB (estimativa, 36 meses) | 36 meses | ~115 MB | 200 MB |
| JavaScript do site | Leitor: 18,6 KB com gzip | | Até 2 MB | 5 MB |
| Novo CAGED, agregados Parquet | 7,0 MB por ano nas tabelas aprovadas, só `MOV`, nacional com zstd | 2020 em diante (fora da v1) | ~50 MB com zstd; sem compressão, cerca do dobro | 100 MB |
| Siconfi | Não medido em escala | Fora da v1 | Não estimado | 60 MB |
| **Total** | | | | **595 MB** |

As páginas HTML não entraram neste orçamento. Em 08/11/2026, com o JSON-LD, o build local do site inteiro tem 58,1 MB, quase todo em páginas de município (mediana de 10,1 KB).

**Limite por página, definido em 08/11/2026: 100 KB sem compressão**, em `limites.pagina_html_kb` no catálogo. No build da coleta da execução 42442355751, a maior página é a de MG, com 56,4 KB, porque lista 853 municípios. O build falha se uma página passar, e o erro diz qual e com quantos bytes; um teste garante isso. **Com o SIH**, no build local de 08/11/2026: municípios de até 5 mil habitantes, mediana de 71,7 KB e 75,8 KB a maior (10,9 KB com gzip); capitais, de 78,5 KB (Rio de Janeiro) a 79,2 KB (Belo Horizonte), cerca de 13,3 KB com gzip. Cabe, mas usa quase 80% do limite; a tabela e o gráfico mensais são a maior parte.

Limites por arquivo:
- **Até 25 MiB para qualquer arquivo publicado, sem exceção.** Mantém a porta aberta para outro host. O `.wasm` do motor tem 35,9 MB e não entra no site; se um dia for usado, vem do CDN.
- **Até 5 MB** para arquivo que o celular baixa inteiro. O maior por UF e ano hoje tem 488 KB, ou 280 KB com gzip (residência x mês x faixa etária, MG).
- **Até 50 KB para o JSON de um município, e 15 KB com gzip.** Estimativa para a v1 com 36 meses: 30,2 KB em São Paulo (8,1 KB com gzip), o maior; mediana de 20,6 KB (4,2 KB). A parte do SIH responde por quase tudo: mediana de 18,7 KB, contra 1,8 KB de educação e 0,1 KB de IBGE.

O pipeline falha se algum limite for passado, e o erro aponta a tabela.

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

## Escopo da v1

**Entra (F1 a F3):**
- Página para cada um dos 5.571 municípios da lista do IBGE, com busca por nome.
- SIH (2021 em diante), IBGE (população e PIB), Censo Escolar e IDEB.
- Construtor de dashboards sobre cruzamentos pré-calculados, links compartilháveis, exportação para CSV e PNG.
- Filtro por tema, com só os temas que têm dado publicado. O tema entra na especificação e na URL.
- **Painel "Fonte e método" em todo número, gráfico e dashboard:** órgão e pesquisa, tipo de acesso e link (ou receita), período de referência, arquivos usados com hash e data da coleta, fórmula e parcelas quando a métrica é calculada, a regra de supressão (sem o motivo de cada célula, que não é publicado) e as ressalvas. Num dashboard, o painel junta as fontes de todos os gráficos.
- **Exportação que leva a fonte junto:** o CSV tem colunas de fonte, link ou receita, data da coleta e ressalva em cada linha; o PNG traz no rodapé a fonte e o link do estado que o gerou.
- Busca em português com avaliação publicada.
- Arquivos abertos para download, com caminhos estáveis.
- Tema claro e escuro, tabela equivalente a cada gráfico, uso bom no celular.

**Não entra:**
- CAGED, Siconfi e cidades parecidas (próximas fases).
- Diagnóstico por categoria CID de 3 dígitos, procedimento por município e dados por estabelecimento.
- Óbito por mês ou por categoria no município.
- Margens de UF ou Brasil por categoria, até passarem no teste de dedução.
- Consulta livre, qualquer dado individual, login ou servidor.

## Riscos

| Risco | Efeito | O que fazer |
|---|---|---|
| **FTPs sem TLS nem hash** | Não dá para provar que o arquivo é o publicado | Validar a estrutura, comparar versões, registrar tamanho e data da origem |
| **Fontes que recusam o runner** | Medido em 07/11/2026, em 3 execuções do workflow `Alcance das fontes`. A API de serviços do IBGE (`servicodados.ibge.gov.br`: localidades e períodos da SIDRA) não aceitou conexão TCP em nenhuma, nem pelo curl. O INEP aceitou a conexão na primeira e respondeu com reset no TLS; nas outras duas recusou a conexão, também pelo curl, com e sem a chave híbrida no ClientHello. SIDRA, FTP do IBGE, geoftp do IBGE, FTP do DATASUS (um `RD` baixado, com o mesmo SHA-256 da máquina local), FTP do PDET e Siconfi responderam nas 3. Da máquina local, a API do IBGE respondeu nas 3 rodadas; o INEP falhou no TLS nas 3 rodadas completas e respondeu em 5 de 5 tentativas isoladas | Nada da coleta depende do `servicodados`: a lista vem da DTB do geoftp, e a população e o período mais recente, da `apisidra`. Sem a data de modificação, a mudança é detectada pelo hash dos valores. O INEP fica fora do alcance obrigatório do `Publicar` até a F1c. **Hipótese, não confirmada:** bloqueio por excesso de pedidos, porque a primeira execução abriu conexão e as seguintes, feitas minutos depois, não. **Em teste de 08 a 14/11/2026:** o workflow `INEP diário` faz um único pedido por dia (o primeiro KB do Censo Escolar 2024), sem nova tentativa, guarda passo a passo e resultado num artefato de 90 dias e se desliga depois do último dia. Nesse período, o `Alcance das fontes` só pede ao INEP se isso for marcado no disparo. Se os 7 pedidos falharem, a hipótese cai, e a F1c parte para outra origem oficial dos arquivos |
| **Agendamento desativado** | 60 dias sem atividade param a atualização, e a documentação não define "atividade" | Manifesto mensal no git, idade dos dados visível na página, verificação na F1. O commit que altera o `cron` reativa |
| **Fonte republica e piora** | Santo André caiu 64,9% em uma versão | Trava de dois níveis: marca o município, só para tudo em falha estrutural. Limite a reavaliar com mais versões |
| **Dedução entre tabelas** | Sem família, 113 contagens eram dedutíveis. Na F1b, com todas as somas e o motivo da célula público, 4.365 em 2025 | Teste em cadeia sobre os 14 cruzamentos e as margens, em 6 anos, com reforço até zero. Motivo por célula fora do site (decidido). Reprovou, não publica no ano, e a página diz por quê. CAGED e educação entram no teste quando entrarem no site |
| **Dedução entre versões** | Medido na F1b: de 62 a 194.045 diferenças de 1 a 4 por atualização, conforme o par e o ano | Decidido: preliminares em múltiplo de 5, e a versão nova herda o padrão dos períodos fechados. Zero nos 8 pares, nas transições de fechamento e em três versões seguidas. Falta o `Publicar` passar a versão no ar em `--anterior` |
| **Comportamento do host muda** | O `HEAD` já informa tamanho comprimido, `Range` depende de detalhes não documentados, e o formato escolhido conta com o gzip do host. Pedido com `Range` e `Accept-Encoding: gzip` recebe uma fatia do gzip, medido em Python | Leitor padrão baixa o arquivo inteiro. Teste semanal no site publicado, em Python e Node, no CI; nos navegadores, o teste é manual. Se o gzip sumir, o build volta ao zstd |
| **Site e TabNet em eixos diferentes** | O site usa a data da alta, e o TabNet, a de internação. Quem comparar um mês vai ver números diferentes e pode achar que é erro | Ressalva junto ao número, explicando a diferença. Conferência pública por competência e por data de internação |
| **Mês da alta sem conferência oficial** | Nenhuma ferramenta oficial testada oferece esse eixo | Conferir as mesmas AIHs pelos outros dois eixos e testar a data da alta no pipeline. Fica registrado como limite |
| **Leitor sem motor de consulta** | Filtrar, ordenar e juntar com população viram código do projeto | Só filtro e desenho sobre cruzamentos prontos; teste de igualdade com o motor no CI, usando-o só como referência |
| **Celular real e iOS sem teste** | Os números são de emulação; WebKit no Windows não é o Safari do iOS | Testar em aparelho antes de lançar a F2 |
| **Licenças ambíguas** | O site do governo declara "SemDerivações" para o conteúdo, sem deixar claro se vale para dados; Siconfi é ODbL | Atribuição em cada número, licença por base, ODbL isolada. Rever antes de publicar os dados para download |
| **Leitura errada** | Mortalidade alta em hospital de referência, só SUS, residência x hospital | Ressalva no catálogo, exibida junto ao número |
| **Limite de banda** | 100 GB por mês | A carga típica tem poucos KB. Com o motor fora, o risco caiu; o maior arquivo por UF transfere 280 KB |
| **Disponibilidade das fontes** | Numa bateria, um endpoint do Siconfi teve 4 de 10 pedidos em timeout. Quedas de conexão vistas no `curl` para o INEP não se repetiram em 20 pedidos em Python, mas o primeiro pedido da coleta de `fontes.json` levou reset, e os outros 11 responderam. A causa não foi identificada, e a máquina tem antivírus que intercepta tráfego | Novas tentativas, e partições fechadas guardadas nas Releases. Reavaliar no runner |
| **Avaliação da busca ruim** | Taxa de resposta errada alta invalida a função | Publicar o número mesmo assim, e recusar mais em vez de errar |

## Fases

As fases originais mudaram com as medições. O que mudou está marcado em **negrito**.

### F1. Páginas por município, em três etapas publicáveis

A divisão proposta (deploy e CI; SIH e catálogo; educação e IBGE) foi mantida, com uma mudança: **o IBGE não pode ser o último**. A página mínima precisa da lista de 5.571 municípios, e o SIH precisa de população para taxas e dos códigos de 7 dígitos. Por isso localidades e população vão para a primeira etapa, e só o PIB fica para a última.

**F1a. Deploy, CI e uma página real**
- Deploy próprio no GitHub Pages; workflow agendado; Release e manifesto no git. Fim de linha fixado em LF no `.gitattributes` antes do primeiro workflow.
- Coleta real pelo runner: lista de municípios pela DTB do geoftp, população pela SIDRA, e um teste de alcance de cada fonte (um `RD` pequeno do DATASUS, a listagem do CAGED, uma consulta do Siconfi). **O INEP saiu do teste semanal até a F1c:** recusou o runner nas 3 execuções do diagnóstico manual, que continua a testá-lo.
- Página de cada município com nome, UF, população, fonte e data da coleta, e o painel "Fonte e método" com o link exato do IBGE para a população.
- Conferência agendada de links, marcando os quebrados no manifesto.
- Repetir no site real os testes de `Range`, `HEAD`, gzip e leitor. Feito em 07/11/2026, nos três navegadores; ver [Hospedagem](#hospedagem-github-pages).
- **Fechamento, em 08/11/2026:** repositório renomeado, endereço numa configuração única, sitemap, link canônico, Open Graph e JSON-LD em cada página, suporte ao arquivo do Search Console, revisão da estimativa marcada na página, e o teste diário do INEP. Ver [Endereço e buscadores](#endereço-e-buscadores) e [Riscos](#riscos).

*Pronto quando:* o workflow agendado publica sozinho, as fontes respondem do runner e os testes de hospedagem batem com este plano. Se o runner não alcançar os FTPs, parar e avisar: é o que mais pode mudar o plano. Em 08/11/2026, só falta a primeira execução agendada, em 15/11.

**F1b. SIH do Brasil, com catálogo e supressão**
- **As 27 UFs**, partições por ano em Releases, janela aberta recalculada.
- Catálogo, contrato de dados, trava de queda, supressão por família.
- **Teste de dedução em cadeia, incluindo a comparação entre versões publicadas e a candidata.** Decisão sobre os meses preliminares.
- Página com gráficos, ressalvas, nível de detalhe conforme o município, filtros.
- **Conferência por mês da alta.** O TabNet não tem esse eixo, então a conferência é em duas partes. Com o TabNet, amostra por município em cada região, nos eixos que ele oferece: competência e data de internação, confirmando que o pipeline parte das mesmas AIHs. No pipeline, teste com AIHs sintéticas de que cada uma cai no mês da sua data de alta, e que os totais fecham entre os três eixos. Investigar a diferença da capital. Procurar outra ferramenta oficial com esse eixo; se não houver, o limite fica declarado na tela.

*Pronto quando:* o teste de dedução dá zero, a amostra bate com o TabNet nos dois eixos dele, os totais fecham com o mês da alta, e o JSON respeita o limite. A meta de abrir a página em menos de 3 s em 4G lento é medida no site real.

**Estado em 08/11/2026, parada antes de publicar o SIH:**
- Feito: coleta das 27 UFs com contrato por linha, janela recalculada a cada execução, tabelas por ano da alta, supressão por família, teste de dedução em cadeia com reforço (zero nos seis anos), critério de publicação por ano, trimestre só completo, preliminares arredondados na partição, comparação entre versões com transição de fechamento e três versões, herança do padrão nos períodos fechados, trava de queda, conferência com o TabNet e o workflow `SIH (medição)` no runner. A página com gráficos, tabela, CSV e PNG existe só no build local (`construir --sih-local`, que para no CI). O SIH está no catálogo com `publicacao: {site: false, releases: false}`.
- Decidido em 08/11/2026: o motivo por célula não é publicado; meses preliminares em múltiplo de 5; o cruzamento que reprova no ano não é publicado naquele ano, com o motivo na página.
- Não feito: as Releases das partições fechadas (nada sobe enquanto o catálogo disser `releases: false`); o `Publicar` rodar o SIH e passar a versão no ar em `--anterior`; o ataque conjunto com a versão publicada como etapa do pipeline, que hoje só a medição faz; o JSON-LD do SIH na página; a conferência pelo mês da alta no TabWin; e o teste em celular real.
- Contrato: nos 76,1 milhões de AIHs das competências 2101 a 2608, nenhuma linha violou as regras (competência, IDENT, UF do hospital, municípios na DTB, datas, defasagem de até 5 meses, CID, dicionários, chave única). O sexo 4, novo e sem definição em documento oficial, vai para "Ignorado", como no TabWin.

**F1c. Educação e o restante do IBGE**
- **Antes de tudo, uma rota do runner até o INEP**, que recusou a conexão em 07/11/2026. Se a hipótese de bloqueio por excesso de pedidos não se confirmar, procurar outra origem oficial dos mesmos arquivos. Sem rota, a educação não entra.
- **Censo Escolar e IDEB**, PIB, amostra conferida com as ferramentas do INEP e do SIDRA.
- O teste de dedução passa a cobrir as tabelas novas.

*Pronto quando:* a página de município mostra saúde, educação e IBGE, cada número com sua fonte. É aqui que o produto deixa de parecer só de saúde. O custo medido é baixo (0,24 MB por ano e 4,7% das células ocultas), então esta etapa pode vir junto da F1b se houver folga.

### F2. Construtor de dashboards
- Especificação na URL, exportação, **leitor em JavaScript sobre arquivos por UF**.
- **Teste de igualdade entre leitor e motor no CI.** O motor só entra na v1 se uma função provar que precisa dele.
- **Publicar os arquivos como dados abertos e documentar os caminhos estáveis**: já são públicos, então isso custa só documentação.
- Teste em aparelho físico e Safari no iOS.

### F3. Busca em português
- Pelo menos 100 perguntas escritas antes de ajustar o sistema, incluindo as sem resposta, com treino e teste separados.
- Dicionário e correspondência aproximada primeiro. Embeddings no navegador só se o ganho compensar o peso.
- Taxas de acerto, recusa correta e resposta errada publicadas no README.

### Depois da v1

**Nesta ordem, revista em 08/11/2026: agropecuária primeiro.** Cada área começa como a Etapa 0: medir a fonte antes de prometer a tela. Em todas, a medição responde às mesmas perguntas: se o runner alcança a fonte, formato e tamanho por ano, cobertura municipal, defasagem e republicação, licença declarada, quanto a supressão oculta em cada cruzamento e com que ferramenta oficial o resultado pode ser conferido.

**O levantamento de 07/11/2026.** Um levantamento à parte, feito numa máquina local, testou 15 entradas (estabelecimentos e leitos separados, assim como Bolsa Família e Cadastro Único): 13 tiveram dados baixados e inspecionados, e 2 ficaram só documentadas. A tabela segue a marcação dele: **medido** é corpo recebido e inspecionado, esquema observado ou resultado de tentativa de acesso; **documentado** é o que a origem publica, inclusive tamanho anunciado em cabeçalho HTTP, que não é arquivo baixado inteiro. CAGED e Siconfi foram medidos na Etapa 0 e estão em [Fontes](#fontes). O catálogo do levantamento está em [`docs/medicoes/roteiro/`](medicoes/roteiro/README.md), sem a pasta de amostras, que tem registros individuais.

| Fase | Área e fonte | Acesso | Código do município | Tamanho | Licença declarada | Situação |
|---|---|---|---|---|---|---|
| F4 | **Agropecuária.** IBGE, Produção Agrícola Municipal (PAM, tabela 5457) e Pesquisa da Pecuária Municipal (PPM, tabela 3939), pela SIDRA | Medido: API da SIDRA sem chave, um município e um ano no endereço | Medido: 7 dígitos | Documentado: não determinado para o Brasil; depende das variáveis e classificações escolhidas | Documentado: não localizada, como nas outras tabelas do IBGE | **Primeira.** Já vem agregada e sai da `apisidra`, que o runner alcança na coleta semanal. Preservar unidades, ausência e sigilo do SIDRA. A tabela 3939 cobre rebanhos; leite, ovos e outros produtos ficam em outras tabelas |
| F5 | **Saúde ampliada.** SIM e SINASC | Medido: SIM pela API sem credencial; SINASC pelo ZIP, porque a API devolveu listas vazias | Medido: 6 dígitos; residência e ocorrência separadas | Documentado: CSV nacional de 2024 com 95,4 MB (SIM) e 92,3 MB (SINASC) compactados | Documentado: CC BY no metadado, sem versão | Registros individuais: supressão por família, começando pelo total anual |
| F5 | CNES, estabelecimentos e leitos | Medido: API sem credencial; leitos por competência | Medido: 6 dígitos na API de leitos; o CSV "Hospitais e Leitos" só tem o nome | Documentado: fotografia de estabelecimentos com 56,8 MB; CSV de leitos de 2024 com 25,2 MB | Documentado: CC BY em estabelecimentos; nenhuma específica para a API de leitos | Leito é estoque: não somar competências como total anual |
| F5 | Vacinação (SI-PNI) | Medido: API e arquivos sem credencial | Medido: 6 dígitos, do paciente e do estabelecimento | Documentado: **cerca de 26 GB compactados por ano**, somando os 12 ZIPs mensais de 2024 | Documentado: vazia no metadado | **Cara.** Medido: uma linha por dose aplicada, com dados do paciente. Exige deduplicação, registros excluídos e proteção de casos raros, e dose não é pessoa vacinada. Fica por último na fase |
| F6 | **Trabalho e finanças públicas.** Novo CAGED e Siconfi | Ver [Fontes](#fontes) | | | | Como antes da revisão da ordem |
| F7 | **Assistência social.** MDS: Bolsa Família e Cadastro Único agregados (VIS DATA e Observatório) | Medido: as rotas testadas redirecionaram para um aviso de manutenção, sem dados | Documentado: recorte municipal; presença e largura do código não confirmadas | Não determinado | Documentado: não localizada | **Pendente**, só documentada. Volta quando as rotas públicas responderem, e não segura as fases seguintes. A API do Portal da Transparência pede cadastro e chave e fica fora. Documentado: o Observatório oculta menos de 100 famílias ou 200 pessoas, e essa ocultação precisa resistir a subtração aqui |
| F8 | **Saneamento.** SINISA, Gestão Municipal | Medido: planilha baixada inteira | Medido: 7 dígitos, inclusive de municípios que não responderam | Medido: 6,0 MB do módulo Gestão Municipal; os outros quatro módulos, não | Documentado: não localizada; o CC BY-ND 3.0 do rodapé é do site | Código presente não é resposta válida, e não resposta não é zero |
| F9 | **Meio ambiente.** INPE: PRODES, DETER e focos de queimada | Medido: WFS público (PRODES e DETER) e CSV diário (focos) | Medido: 7 dígitos no DETER e nos focos. **O PRODES não tem município**: exige interseção espacial com a camada de limites | Documentado: ZIP nacional de focos de 2024 com 117 MB; PRODES e DETER não determinados | Documentado: **PRODES e DETER sob CC BY-SA 4.0**, pelo TerraBrasilis; nos focos, nenhuma formal | A CC BY-SA pede atribuição e a mesma licença nos derivados: arquivos próprios, como os do Siconfi sob ODbL. As amostras cobrem só a Amazônia Legal |
| F10 | **Eleições.** TSE, resultados por município | Medido: catálogo e ZIP sem credencial | Medido: **sem código IBGE**. `CD_MUNICIPIO` é código eleitoral próprio | Documentado: ZIP nacional de votação por município e zona de 2024 com 48,2 MB | Documentado: CC BY, sem versão | Exige correspondência TSE x IBGE, a construir e conferir. Não somar cargos, turnos, nem os arquivos nacional e estaduais |
| F11 | **Segurança.** SINESP VDE, do Ministério da Justiça | Medido: planilha de 2024 baixada inteira | Medido: **sem código IBGE**. Só UF e nome do município | Medido: 24,4 MB em 2024 | Documentado: CC BY no catálogo antigo; não confirmada na planilha atual | Associação por UF e nome, com as exceções explícitas. Vítimas e ocorrências separadas; sexo e idade em cidades pequenas pedem supressão |

Nenhuma dessas fontes foi testada do runner. O diagnóstico manual `Alcance das fontes` passou a pedir um endereço de cada servidor de dados delas, numa tabela à parte, sem torná-las obrigatórias: nenhuma etapa depende delas, e o `Publicar` não as testa. Ficam de fora a API do Portal da Transparência e as páginas que só documentam a fonte. Da máquina local, em 08/11/2026, as 13 rotas responderam, e as duas do MDS ainda redirecionavam para o aviso de manutenção ([`alcance_roteiro_local.json`](medicoes/resultados/alcance_roteiro_local.json)).

**F4. Agropecuária**
- PAM e PPM por município e ano, pela SIDRA, com o mesmo contrato da estimativa de população: colunas pelo cabeçalho, sinais de ausência e sigilo nunca lidos como número.
- Antes da tela, escolher os produtos e as unidades de cada um: somar toneladas de culturas diferentes, ou cabeças de rebanhos diferentes, não tem sentido.

**F5. Saúde ampliada**
- Nesta ordem, como sugere o levantamento: CNES; SIM e SINASC; vacinação.
- SIM e SINASC por residência, com a mesma supressão por família do SIH. Óbito por causa tem o mesmo problema medido nos óbitos hospitalares, então a medição começa pelo total anual.
- CNES liga leitos e profissionais ao município do hospital, que o SIH já usa.
- Os códigos de 6 dígitos passam pela mesma conversão do SIH, já conferida nos 5.571 municípios.

**F6. Trabalho e finanças públicas**
- CAGED: `MOV` + `FOR` − `EXC`, máscara por medida, comparação entre cidades parecidas. Refazer tamanho e supressão dos cruzamentos com os três arquivos, porque a medição atual usa só `MOV`. O cruzamento entre saúde e educação já é possível desde a F2.
- Siconfi, com licença ODbL em arquivos próprios.
- Relatório municipal para imprimir.
- **Saem daqui:** SIH do Brasil e INEP (para a F1); dados abertos e caminhos estáveis (para a F2).

**F7 a F11.** Cada área entra quando a medição dela estiver pronta, com seu tema na lista fixa do catálogo.

## Reprodução

Ambiente das medições: Windows 11, Ryzen 7 5700X3D, 32 GB, Python 3.14, DuckDB 2.0.0, Node 24, Chrome 157, com antivírus ativo. Os agregados de 2025 usam a versão dos arquivos disponível em novembro de 2026; para SP, parte vem de cópia de setembro de 2026 cujas competências de 2025 não mudaram nos totais. Tamanhos multianuais são estimados por proporção, a partir de um ano medido.

Veja [`docs/medicoes/README.md`](medicoes/README.md).
