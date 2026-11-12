[Índice do plano](../plano.md)

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

Refeito em 08/11/2026 com as regras decididas, numa execução local do pipeline sobre a mesma versão dos arquivos ([`sih_local_f1b.json`](../medicoes/resultados/sih_local_f1b.json)). O teste vê o que a tela mostra: sem motivo, com os meses preliminares em múltiplo de 5 e, em cada ano, só os cruzamentos que passaram no critério. Com os valores exatos, 2025 revelava 55 e 2026, 1.100, em 3 rodadas; arredondados, nenhum dos dois precisa de reforço. Em 2021, 108 viraram 106 porque dois cruzamentos saíram do ano.

Óbitos, com máscara própria no total anual por município, deram zero em todos os anos, sem reforço.

**O que passa do critério de publicação.** Decidido em 08/11/2026: o cruzamento que reprova não é publicado naquele ano, a página diz por quê, e o que depende dele (filha ou trimestre) sai junto. O critério está em `supressao.criterio_publicacao`, e a supressão e o teste são refeitos sem o que saiu. **Num ano aberto, o que é publicado fica fixo** da primeira publicação daquele ano até ele fechar, sem refazer o critério a cada mês (decidido em 08/11/2026, `versoes.situacao_fixa_no_ano_aberto`): sem isso, o trimestre por capítulo de 2026 apareceria e sumiria de uma versão para a outra. A única exceção é o teste de dedução revelar algo com um cruzamento, que sempre o tira. Na execução de 08/11/2026: em 2021, saem residência x mês x urgência (6,7% das internações ocultas) e hospital x mês x caráter (5,1%); em 2026, residência x trimestre x capítulo (7,6% das internações e 50,5% das células). De 2022 a 2025, todos passam.

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

As 15 tabelas publicáveis somam **10,64 MB por ano** nestes arquivos nacionais com zstd; com os totais anuais de óbitos, 10,7 MB. No formato escolhido, por UF e sem compressão, são 22,9 MB, ou 11,9 MB em transferência com gzip. **Na F1b, com cada cruzamento levando só as métricas do catálogo** (dias e valor nas tabelas de município por ano e por mês; nas outras, só internações), são de 6,9 a 7,3 MB por ano completo, 3,8 a 3,9 MB com gzip, e o maior arquivo, residência x mês de MG, tem 170 KB ([`particoes_f1b.json`](../medicoes/resultados/particoes_f1b.json)). Com dias e valor em todas as tabelas, como na Etapa 0, seriam 20 a 22 MB. Juntar categorias raras ajuda muito: "caráter" com 3 grupos oculta 8,06%, porque a complementar acaba caindo em células grandes; com "urgência ou não", 1,60%.

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

**Medido na F1b, em 08/11/2026** ([`versoes_f1b.json`](../medicoes/resultados/versoes_f1b.json)). Como nada do SIH foi publicado, a versão "publicada" foi montada de dois jeitos, sempre com as 27 UFs e a supressão final (sem motivo por célula, reforço com o limite de rodadas do catálogo; as 16 versões montadas chegaram a zero no teste):
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

**Transição de fechamento e três versões, com a regra decidida** ([`versoes_transicao_f1b.json`](../medicoes/resultados/versoes_transicao_f1b.json), `medir_versoes_transicao.py`). Quem guarda as versões ataca todas juntas: cada uma como a tela mostra, e as células de período já fechado na mais nova iguais nas duas, porque nenhum arquivo com altas daquele período foi republicado entre elas (`deducao.atacar_juntos`). Em três versões, também d(1,3) = d(1,2) + d(2,3) (`deducao.diferencas_em_sequencia`).

| Versões | O que fecha | Teste de cada uma | Todas juntas | Diferenças de 1 a 4 |
|---|---|---|---:|---:|
| SP, setembro x outubro, 2025 | março de 2025 e o 1º trimestre | 0 e 0 | 0 | 0 |
| SP, setembro x outubro, 2026 | nada | 0 e 0 | 0 | 0 |
| Simuladas, 2605, 2606 e 2607, ano 2025 | janeiro, depois fevereiro de 2025 | 0, 0 e 0 | 0 | 0 nos três pares |
| Simuladas, 2605, 2606 e 2607, ano 2026 | nada | 0, 0 e 0 | 0 | 0 nos três pares |
| Simuladas, 2604 e 2605, ano 2024 | dezembro e o ano inteiro | 0 e 0 | **18 sem herança; 0 com herança** | 0 |

**Quando o ano fecha, as duas versões juntas revelavam 18 contagens.** Com dezembro fechado, as tabelas do ano passam de arredondadas a exatas, a supressão é refeita e escolhe outras complementares. Quem guardou a versão anterior cruza os dois padrões: a célula que estava oculta e agora aparece entrega o que ela protegia, e a que estava exata e agora some não protege nada. Foram 11 em residência x mês x faixa etária e 7 em tabelas de hospital, em cada versão. **Por isso, nas células de período fechado, a versão nova herda o padrão da anterior** (`sih.fixas_da_anterior`): a oculta continua oculta, e a visível e exata não pode virar complementar; a que estava arredondada pode ser ocultada. Com a herança, a versão de 2605 precisou de 3 rodadas de reforço, e o ataque conjunto deu zero. Nos outros grupos, que já davam zero, nada mudou. O comando `sih` recebe a versão publicada antes e só lê dela o que foi publicado: desde 10/11/2026, a superfície (`--no-ar`, pela consulta ao site, ou `--anterior`, um arquivo de superfície ou uma pasta de partições escolhidos à mão). A herança vale, então, só para os cruzamentos que a página mostrou.

**Decidido em 08/11/2026:** a herança é regra (`versoes.herdar_padrao_fechado`), e o ataque conjunto com a versão no ar é obrigatório antes de toda publicação (`versoes.ataque_conjunto_obrigatorio`). Se ele não rodar, se revelar alguma contagem, ou se a versão no ar não puder ser lida ou não bater com a situação dela, nada é publicado e o site anterior fica no ar. A leitura e a conferência da versão anterior param o pipeline. A herança supõe o mesmo k nas duas versões: subir o k depois de publicar deixa sem proteção as contagens iguais ao k antigo, que já foram mostradas, e o pipeline bloqueia; ver [Mudança de regra no runner](ci-e-historico.md#mudança-de-regra-no-runner).

**O ataque conjunto é uma etapa do pipeline** (`sih_versoes.py`), entre a supressão do ano e a gravação da partição. Tem duas metades, para que o motor possa ser trocado. A primeira descreve o problema sem dizer como resolvê-lo: as células de cada tabela alinhadas nas mesmas chaves, o intervalo que cada versão deixa ver em cada uma, as somas que ligam as tabelas e as células que valem o mesmo nas duas versões, porque o período já tinha fechado. As duas versões entram só com a superfície: a versão no ar, lida do arquivo publicado com o site; a candidata, montada das mesmas tabelas que vão para a página. Os nós que ninguém publica (UF, Brasil, trimestre, faixa de 5 grupos, e assim por diante) entram como incógnitas ligadas pelas somas. A segunda metade é o motor, que recebe esse problema e devolve quantas contagens de 1 a 4 ficam exatas em cada versão e quantas diferenças exatas de 1 a 4 aparecem entre elas. **São dois motores, e os dois precisam dar zero** (decidido em 10/11/2026, `versoes.motores`): o de intervalos, o mesmo da medição, e um por programação linear; ver [Motor por programação linear](#motor-por-programação-linear). Motor que não roda, por falta da dependência ou porque não termina, conta contra a publicação. A etapa roda em internações e em óbitos, em cada ano que a versão no ar tem. Se revelar algo, se a versão no ar não puder ser lida, ou se as duas versões não fecharem entre si, o ano não vira partição e o comando termina com erro.

**Ciclo simulado no build local, em 10/11/2026** ([`ciclo_publicacao_f1b.json`](../medicoes/resultados/ciclo_publicacao_f1b.json), `simular_ciclo_sih.py`), com as 27 UFs e os anos de 2021 a 2026, pelo próprio pipeline. Foi feito antes da decisão sobre a superfície, com a versão no ar em Release e o ataque sobre as partições e as margens, um ataque com mais tabelas que o de hoje:

| Cenário | O que acontece | Teste de cada ano | Ataque conjunto | Partições gravadas |
|---|---|---|---|---|
| Primeira publicação, última competência 2604 | Nenhuma versão no ar | zero nos 6 anos | não se aplica | 6 de 6 |
| Release | Cada ano empacotado, baixado pela consulta e conferido | | | 2.241 arquivos conferidos por SHA-256, 41,0 MB |
| Versão seguinte, 2605, com a versão no ar | Dezembro de 2024 fecha; herança do padrão | zero nos 6 anos | zero nos 6 anos, em internações e óbitos | 6 de 6 |
| A mesma, sem a herança | O fechamento de 2024 cruza dois padrões | zero nos 6 anos | **2024: 18 contagens reveladas em cada versão**; zero nos outros 5 | 5 de 6: 2024 fica sem partição |
| Primeira publicação sem o reforço, anos 2021 e 2025 | O teste de 2021 revela 106 contagens | 2021 reprova; 2025 zero | não se aplica | 1 de 2: 2021 fica sem partição |
| Versão no ar com um byte trocado | A leitura para | | | nenhuma |

Em cada cenário, o script confere a pasta: há pasta do ano se, e só se, ele passou em tudo, e cada pasta bate com a situação dela, arquivo por arquivo. As 18 contagens de 2024 sem herança são as mesmas da medição de 08/11/2026, agora achadas pela etapa do pipeline a partir das partições publicadas, e não dos dados sem supressão. Com a versão no ar, o ataque conjunto leva de 12 a 33 s por ano, e a versão inteira, 362 s, contra 193 s da primeira. Um ano reprovado basta para a versão inteira não ser publicável: os outros anos ficam na pasta de trabalho, e o comando sai com erro.

**O que o ataque conjunto supõe, e não foi medido.** As células de período fechado na candidata valem o mesmo nas duas versões. Isso vale entre duas listagens seguidas do FTP. Se uma publicação pular um mês, a competência que saiu da janela nesse intervalo ainda pode ter mudado depois da versão no ar; nesse caso a suposição é mais forte que a realidade, e o efeito possível é a etapa parar com "as versões não fecham entre si", não deixar passar.

### Motor por programação linear

**Por que um segundo motor.** O motor por intervalos aperta uma soma de cada vez, em cadeia, e não alcança o que só sai de várias somas ao mesmo tempo. O caso que a auditoria independente de 08/11/2026 usou: quatro células ocultas, as três partições delas em pares (cada par soma 6) e o total 12, tudo visível. Só há uma solução, as quatro valem 3, mas cada soma sozinha deixa cada célula entre 0 e 6. O motor por intervalos revela 0; o por programação linear, 4. O caso é teste do pipeline (`test_quatro_contagens_de_3_so_a_programacao_linear_acha`). **Decidido em 10/11/2026: os dois rodam no ataque conjunto, e os dois precisam dar zero** (`versoes.motores`).

**Como funciona** (`deducao_lp.py`). O mesmo Problema do motor por intervalos vira um programa linear: cada célula de cada versão é uma variável no intervalo que a tela deixa ver (o valor exato, a meia base do arredondado, de 0 ao infinito na oculta e na soma que ninguém publica), cada aresta é uma igualdade, e a célula que vale o mesmo nas duas versões é uma variável só. Uma contagem está revelada quando o mínimo e o máximo, arredondados para dentro, coincidem num inteiro de 1 a 4; uma diferença entre versões, quando fica exata entre 1 e 4 em módulo. É a regra da auditoria independente. Resolver o mínimo e o máximo de cada célula levaria dias no Brasil inteiro, então o motor descarta antes, com poucos pontos viáveis, o que já se mostra não revelado: um ponto com a célula em 0, em 5 ou mais, ou dois pontos com ela em inteiros diferentes. As versões só se ligam pelas células comuns: cada ponto sai de uma versão resolvida sozinha e da outra com as comuns presas no valor da primeira, e por isso é viável no conjunto. Os objetivos empurram as candidatas para baixo, para cima e, em pares, para uma direção sorteada e para a oposta (semente fixa). O que sobra é conferido célula a célula, do mais barato ao mais caro, e só um conjunto que contém o verdadeiro declara revelação. Célula que nem a versão inteira decide, além de um limite, ou resolução que não termina, conta como inconclusiva, e inconclusiva conta contra a publicação. Antes de responder, o motor confere que o valor verdadeiro da candidata, que o pipeline tem, cabe no Problema; se não couber, ele para. HiGHS pelo `scipy` 1.18.1, em `requirements-sih.txt`, o do workflow do SIH e dos testes, não o do site.

**Limite.** A relaxação é contínua: quando o intervalo contínuo não fixa um inteiro, o motor não conclui nada, ainda que só uma solução inteira exista. A auditoria independente tem o mesmo limite.

**Medido em 11/11/2026** ([`motor_lp_f1b.json`](../medicoes/resultados/motor_lp_f1b.json), `medir_motor_lp.py`), nas 27 UFs, ano da alta de 2025, com os 459 arquivos do FTP das competências 2501 a 2605 baixados em 10/11/2026. Duas versões do próprio pipeline: A com a última competência 2607, sem versão no ar; B com 2608 e a superfície de A como versão no ar (março de 2025 fecha entre elas). Nesta máquina (Ryzen 7 5700X3D, 32 GB), cada resolução do HiGHS num núcleo:

| Ataque, internações, 2025 | Variáveis livres | Igualdades | Células conferidas | Intervalos | Programação linear | Revelado |
|---|---:|---:|---:|---:|---:|---:|
| Uma versão (a superfície de B) | 484.478 | 237.551 | 216.966 | 0,4 s | 68 s | 0 nos dois |
| Duas versões juntas (o ataque conjunto de B, no pipeline) | 963.201 | 475.102 | 935.048, com as diferenças | 1,2 s | 742 s | 0 nos dois |

Em óbitos, que a página só mostra no total anual por residência, os dois motores levam menos de 0,1 s. A versão B inteira levou 766 s, 746 deles no ataque conjunto. As superfícies de A e B têm 530.447 e 536.629 bytes (314.881 células, num ano com o detalhe).

**O que isso diz e o que não diz.** 2025 é o caso pesado: quase todas as células estão arredondadas, então quase todas são variáveis. Os anos fechados têm quase tudo exato e devem ser bem mais leves, e 2026, aberto, deve pesar como 2025. Medido no runner em 12/11/2026 ([SIH no runner](ci-e-historico.md#sih-no-runner)): 2025 em 554 e 570 s, 2026 em 247 s, e os anos fechados em até 0,4 s, quando as duas versões são iguais neles. O primeiro caminho, que resolvia o programa inteiro a cada ponto, levava cerca de 200 s por resolução com as duas versões e deixava 41 mil candidatas depois de dois pontos; foi abandonado.

Nas simuladas de 2026, residência x trimestre x capítulo passa no critério com a última competência 2606 e reprova com 2605 e 2607. Publicado assim, ele apareceria e sumiria de um mês para o outro. O ataque conjunto conta com isso e deu zero.

**Quanto um mês ainda muda depois de 6, 9 e 12 meses.** Só medição, sem mudar regra ([`mudanca_tardia_f1b.json`](../medicoes/resultados/mudanca_tardia_f1b.json), `medir_mudanca_tardia.py`). São duas leituras, com dados diferentes:
- **Depois do fechamento.** Fechado, um mês só muda se o DATASUS regravar uma competência que já saiu da janela. Pela data de modificação na listagem do FTP, nas 27 UFs, nenhum mês de 2021 em diante mudou depois de fechar: em cada UF, 45 meses estão fechados há 6 meses ou mais, 42 há 9 e 39 há 12, e em nenhum uma competência com altas dele foi regravada. Em SP, a última cópia na janela das competências 2501 a 2508, guardada no projeto de origem, é idêntica byte a byte à de hoje. Antes de 2021 houve regravações em lote (a mais recente, AC de setembro de 2009, em 22/05/2024), então o aviso para competência congelada que muda continua necessário.
- **Depois do próprio mês.** O processamento tardio acaba no 5º mês em todas as UFs, como garante o contrato: depois de 6, 9 e 12 meses, nada mais chega. No próprio mês da alta já estão de 20,0% (RR) a 82,8% (PE) das internações dele; três meses depois, de 98,0% (AL) a 100%. Depois do 5º mês, só a correção numa republicação muda o mês, e só SP tem duas versões guardadas: de setembro para outubro de 2026, o mês com 6 meses de idade (fevereiro de 2026) mudou em 13 municípios de residência, 8 deles por 1 a 4 internações, e o total subiu 424; os de 9 e 12 meses (novembro e agosto de 2025) não mudaram. Nas outras UFs, a correção depois do 5º mês só pode ser medida guardando versões.

### Novo CAGED, Brasil, 2025

**Base desta tabela: só o arquivo `MOV` de 2025.** Linhas, tamanhos e supressão dos cruzamentos não incluem `FOR` nem `EXC`, e a conferência com os ajustes, descrita em [Novo CAGED](fontes.md#fontes), é só do total nacional. Com os três arquivos, esses números podem mudar, e a F6 precisa medi-los de novo.

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
