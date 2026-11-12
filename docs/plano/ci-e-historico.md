[Índice do plano](../plano.md)

## CI e histórico

Os dados não entram no git, e o que está publicado não serve de base para recalcular: as tabelas já estão suprimidas, e somar por cima de célula oculta dá errado. Guardar agregados sem supressão em lugar público também não pode.

**De onde vem cada período:**

| Período | Origem | Por quê |
|---|---|---|
| **Anos abertos:** contêm meses que ainda podem mudar | Recalculados a cada execução, das fontes | O FTP republica as últimas 12 competências, mas a partição é por ano, então cada ano aberto exige todas as suas competências. Hoje são 20 competências; no pior caso, 28. Estimativa: 540 arquivos e ~1,9 GB hoje, 756 arquivos e ~2,6 GB no pior caso, e de 8 a 11 min de download, a partir de 312 arquivos e 880 MB em 223 s, medidos fora do CI |
| **Partições fechadas:** anos que não mudam mais | Censo: arquivo já conferido, guardado em **Release** do próprio repositório. SIH: nada em Release (decidido em 10/11/2026); o que foi publicado de um ano fechado está na superfície no ar, publicada com o site | Só têm dado que já é público no site. Releases: sem limite declarado de total ou banda; cada arquivo abaixo de 2 GiB, até 1.000 por release. Desde 12/11/2026, o ano fechado do SIH é copiado da superfície no ar enquanto as regras e o algoritmo de supressão forem os dela; ver [Superfície pública do SIH](#superfície-pública-do-sih) |
| **Reconstrução:** regra mudou (valor de k, novo cruzamento) | Execução manual que rebaixa tudo das fontes | Estimativa para 2021 em diante: 1.836 arquivos, ~6 GB, ~25 min de download. Cabe nos 14 GB de disco se processar e apagar arquivo a arquivo, e no limite de 6 h por job |

**Quando um mês fecha.** O mês M do SIH fecha quando todas as competências que podem conter altas dele saíram da janela republicada: `M + 5 ≤ última competência − 12`. Em novembro de 2026, com a última competência em 2608, estão fechados os meses até 2503. O ano vira partição fechada quando dezembro fecha. No CAGED, um mês fecha após 12 meses de declarações fora do prazo. A defasagem de 5 meses foi medida só nas competências de 2025; se uma competência congelada mudar de tamanho, o pipeline avisa em vez de ignorar.

**A supressão é por partição.** Cada ano é suprimido sozinho, sem margem que atravesse anos. Assim, uma partição fechada nunca precisa ser recalculada, e não há total de vários anos publicado. Cada ano fica numa pasta (`ano=AAAA/<cruzamento>/uf=XX.parquet`) com um `situacao.json`: o que foi publicado, o que não foi e por quê, os testes e cada arquivo com tamanho e SHA-256. A pasta do ano é trocada inteira, de uma vez, e quem lê confere cada arquivo com a lista: arquivo listado que falta para tudo, e linha que falta dentro de um arquivo é zero. **Só existe pasta de ano que passou em todos os testes:** o que reprova no teste de dedução, em internações ou em óbitos, ou no ataque conjunto com a versão no ar, não é gravado, a pasta que uma execução anterior tenha deixado para ele é apagada, e o comando termina com erro. Antes, a partição era gravada mesmo com o teste reprovado, só com a marca na situação. As partições ficam no runner: nenhum Parquet do SIH vai para o site nem para Releases (decidido em 10/11/2026; ver [Superfície pública do SIH](#superfície-pública-do-sih)). As margens de UF e do Brasil, que entre 10/11/2026 e essa decisão iam para `margens/` dentro da partição, saíram dela: a página não as mostra, e a supressão continua a protegê-las como se fossem publicadas.

**Se a fonte sumir.** A superfície no ar continua no site, e o Censo, na Release. Só a reconstrução fica impossível para o período perdido.

**O que a documentação oficial confirma** (lida em 07/11/2026):

| Item | O que diz | Consequência |
|---|---|---|
| Cache do Actions | Entrada sem acesso há mais de 7 dias é removida (padrão; configurável até 90 dias em repositório público). 10 GB por repositório | Um job mensal encontraria o cache vazio no padrão. **Não é fonte de dados:** nem "cópia em cache" do INEP, nem histórico |
| Agendamentos | Em repositório público, são desativados após 60 dias sem atividade. A documentação não define "atividade" nem diz se commit do próprio workflow conta | O job grava o manifesto no git todo mês, e a página mostra a idade dos dados. **Se o commit do workflow conta não foi verificado** |
| Atrasos | O agendamento pode atrasar, e na carga alta execuções podem ser descartadas, sobretudo na virada da hora | Execução semanal em minuto quebrado, idempotente, com disparo manual disponível |
| Artefatos | Retenção de 1 a 90 dias em repositório público; download exige acesso de leitura | Nada sem supressão vira artefato, nem aparece em log |
| Runner público | 4 CPUs, 16 GB de RAM, 14 GB de disco, 6 h por job. Relida em 08/11/2026: os mesmos números; Releases com até 1.000 arquivos de menos de 2 GiB, sem limite de total nem de banda. Relida em 12/11/2026: os mesmos 4 CPUs, 16 GB e 14 GB, e "Each job in a workflow can run for up to 6 hours of execution time. If a job reaches this limit, the job is terminated and fails" | Executado na F1b; ver [SIH no runner](#sih-no-runner) |

**Releases: não achar é diferente de não conseguir consultar.** O `Publicar` pede a lista de Releases uma vez, pela API do GitHub (`python -m pipeline releases`). O que não está na lista não existe, e a execução segue: primeira coleta do Censo. Qualquer outra resposta, falha de rede, arquivo que falta numa Release que existe, ou tamanho e SHA-256 diferentes dos que a Release registra param o job antes da coleta, e o site anterior continua no ar. Antes, uma falha da consulta era lida como Release inexistente, e a coleta seguia sem a partição congelada do Censo. O resultado fica em `consulta.json`. Só o Censo usa Releases.

### Superfície pública do SIH

**Decidido em 10/11/2026: a superfície pública do SIH é só o que o site mostra**, nas páginas de município e no CSV que sai delas. Nada de Release com as partições em Parquet, nem Parquet do SIH no site: as partições ficam no runner. Está em `bases.sih.superficie` e em `publicacao: {site: false}` no catálogo, que recusa a chave `releases`.

**O que a página mostra, por ano** (`sih_superficie.py`): moradores por ano (internações e óbitos), hospitais do município por ano (internações), moradores por mês (internações) e, nos dois anos mais novos publicados, moradores por capítulo da CID e por faixa etária e sexo (internações). **O que foi publicado continua publicado** (decidido em 11/11/2026): quando um ano sai dos dois mais novos, o detalhe que a versão no ar mostrava dele sai do padrão da página, mas continua na superfície, no seletor de ano e no ataque conjunto, com o ano aberto ou fechado. A situação do ano o lista em `detalhe_mantido`. Dias de permanência, valor pago, óbitos por hospital, as margens de UF e do Brasil e os outros nove cruzamentos não aparecem. A supressão e o teste de dedução de cada versão continuam a tratar os 14 cruzamentos e as margens como publicados, do lado seguro.

**A página sai da superfície.** A superfície de cada ano é montada das mesmas tabelas que vão para a partição (`sih.tabelas_publicaveis`), e a página é desenhada a partir dela (`site_sih.carregar`). Um teste desenha as páginas das partições e as do arquivo da superfície e confere que são idênticas. A mesma conferência célula a célula vale na montagem e na leitura: chave inteira e única, valor nulo só na célula oculta, arredondado só em múltiplo de 5.

**A versão no ar é um arquivo com exatamente essa superfície**, publicado com o site em `dados/sih/superficie.parquet`: uma linha por célula da tela e, nos metadados, a situação de cada ano (o que foi publicado, o que não foi e por quê, os testes, os meses preliminares e o múltiplo do arredondamento, que o painel "Fonte e método" já mostra) o SHA-256 do conteúdo e com que regras a versão foi calculada (`calculo`). É dele que `--no-ar`, a herança do padrão e o ataque conjunto leem. O pipeline o grava em `trabalho/superficie.parquet` só quando todos os anos passam; um ano reprovado apaga o que houver ali.

**Consulta à versão no ar** (`python -m pipeline no-ar`, no `Publicar`, só quando o catálogo mandar publicar o SIH). Pede o arquivo ao site, com uma marca de consulta no endereço para não receber cópia velha de cache. Resposta 200: o arquivo é conferido inteiro, e um ano que não poderia ter ido ao ar, linha de cruzamento que a situação não declara ou conteúdo que não bate com o próprio SHA-256 param. 404 com a página inicial do site respondendo: não há versão no ar, e é a primeira publicação. Qualquer outra resposta, ou falha de rede, para o job, e o site anterior continua no ar. O resultado fica em `consulta.json`, e o SIH só aceita a falta de versão no ar com ele presente. **O passo que leva a superfície e as páginas do SIH ao site ainda não existe**: nada vai enquanto o catálogo disser `site: false`.

**Anos fechados copiados da versão no ar** (`sih_reaproveitamento.py`, implementado em 12/11/2026, como decidido em 11/11/2026). O `calculo` da superfície tem o SHA-256 de tudo o que o pipeline do SIH lê do catálogo (a base, as dimensões e os cruzamentos dela, as margens publicadas e as referências, inclusive o texto) e o número do algoritmo de supressão (`supressao.ALGORITMO_DE_SUPRESSAO`). Se os dois baterem com os da execução, o ano que já estava fechado na versão no ar e continua fechado é copiado dela como está: as competências dele não são baixadas, e ele não passa de novo pela supressão nem pelo ataque conjunto. Fica sem partição no runner, porque a versão no ar só tem a superfície. Se algum dos dois mudar, todos os anos são recalculados das fontes, com a herança do padrão da versão no ar, e o ataque conjunto decide. Com as regras iguais, o ano ainda é recalculado quando o FTP regravou um arquivo dele depois da versão dos arquivos com que foi calculado (com aviso no log), quando a página mostraria dele outros cruzamentos, e quando a execução tem só parte das UFs; `--sem-reaproveitar` recalcula tudo. Antes de copiar, o ano é conferido na versão no ar: não pode ter célula preliminar ou arredondada nem contagem visível de 1 a 4, e tem de fechar com as próprias somas, sem nada revelado pelo motor por intervalos. Se não passar, a execução para antes de baixar qualquer arquivo. Um arquivo forjado com somas coerentes e o `calculo` certo passaria nessas conferências: o que o impede é a versão no ar vir só do próprio site, com o SHA-256 conferido. O número do algoritmo é mudado à mão, e um teste guarda a impressão do código que decide as células (a árvore sintática dos módulos, sem comentários): se o código muda e o número não, o teste falha e pede a decisão. Testado com AIHs inventadas; com os dados reais, ver [SIH no runner](#sih-no-runner).

**INEP e IBGE.** O ano do Censo vira partição fechada na Release. O job só rebaixa se o `Last-Modified` mudar, e confere o MD5 que vem no `.zip`. Na DTB e na SIDRA, a mudança é detectada pelo hash dos valores (código, nome e UF; valor por município), comparado com o da coleta anterior gravada no manifesto. A data de modificação da SIDRA saiu do contrato, porque vem do `servicodados`, que não aceita o runner. Se essas fontes estiverem fora do ar, o site mantém o que tem e marca a coleta como atrasada.

**Revisão da estimativa pelo IBGE.** Decidido em 08/11/2026: não bloqueia. Quando o hash da estimativa muda sem mudar o período, a coleta lê o Parquet que está no ar e só o usa se ele tiver o hash da coleta anterior do manifesto. Os municípios que mudaram ganham na página a ressalva "Revisado pelo IBGE", com a data da coleta que detectou, e o manifesto guarda o valor antes e depois de cada um, por código. Variação acima de 5%, ou município que entrou ou saiu da estimativa, vira aviso na execução do `Publicar`; o limite é regra do catálogo. Se o site anterior não responder, ou não bater com o manifesto, a revisão fica registrada sem o detalhe por município, com o motivo, e a ressalva aparece em todas as páginas. As revisões valem dentro do período: a estimativa de um ano novo começa sem nenhuma. O caminho foi testado com dados sintéticos; nenhuma revisão real aconteceu até 08/11/2026. Só uma falha estrutural do SIH impede a atualização, e nesse caso o site anterior continua no ar.

**Manifesto no git.** Um JSON por base com versão, tamanho e data de cada arquivo de origem, totais por UF e competência, e a lista de meses em revisão, com o valor anterior. A comparação de versões lê as tabelas já publicadas no site, então nada sem supressão precisa ser guardado. É o único dado que entra no git, e seu histórico mostra o que mudou.

**Conferência de links.** Uma tarefa agendada do CI, separada dos testes, abre os links oficiais do catálogo e uma amostra dos links exatos, e marca no manifesto os que falharem, com status e data. Um link exato também precisa devolver o valor publicado. Os testes continuam sem rede. Link quebrado não impede a publicação: o painel avisa que o link falhou na última conferência. A conferência é da coleta daquele dia, então o selo só vale se cada link conferido for o que a página mostra hoje, com o mesmo período, e se o valor conferido for o publicado hoje. Se não for (a estimativa de um ano novo, uma revisão do IBGE), o painel diz que a conferência está pendente, com o motivo, até a seguinte.

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

**Ciclo de três versões, com e sem reaproveitamento, em 12/11/2026** (execução 43147627212 de `SIH (medição)`, com `ciclo`; [`sih_runner_ciclo.json`](../medicoes/resultados/sih_runner_ciclo.json), reduzido por `reduzir_sih_runner_ciclo.py`). O workflow continua só com disparo manual, sem agendamento, e o artefato só tem tempos e contagens. As três fases rodaram no mesmo job, sobre a mesma versão do FTP (última competência 2609, completa 2607, fechado até abril de 2025): **a**, a primeira publicação; **b**, a seguinte, com a superfície de a como versão no ar e os anos fechados copiados dela; **c**, a mesma sem reaproveitar, com os `.dbc` de a, sem download.

| Fase | O que calculou | Coleta | Ataque conjunto, programação linear, internações | Total | Memória: máquina / maior processo | Disco usado |
|---|---|---:|---|---:|---:|---:|
| a. Primeira publicação | 2021 a 2026 | 1.809 arquivos, 5,65 GB, 53 min 59 s | não roda: não há versão anterior | 56 min 17 s | 5,2 GB / 4,8 GB | 6,5 GB, com os `.dbc` guardados para c |
| b. Seguinte, com reaproveitamento | 2025 e 2026; 2021 a 2024 copiados de a | 513 arquivos, 1,78 GB, 16 min 29 s | 2025: 554 s; 2026: 247 s | 30 min 34 s | 5,1 GB / 4,8 GB | 0,25 GB |
| c. Seguinte, sem reaproveitar | 2021 a 2026 | 1.809 arquivos convertidos, sem download, 10 min 47 s | 2025: 570 s; 2026: 247 s; 2021 a 2024: 0,1 a 0,4 s | 27 min 6 s | 5,0 GB / 5,0 GB | 0,79 GB |

Os dois motores deram zero em todos os anos atacados, em internações e em óbitos, sem célula inconclusiva. O de intervalos levou até 0,4 s por ano; a programação linear em óbitos, até 0,1 s. Em 2025, o problema tem o mesmo tamanho da medição local de 11/11/2026 (475.102 igualdades e 935.048 células conferidas), e o runner levou 554 e 570 s, contra 742 s nesta máquina.

**Cabe, com folga.** A execução semanal com reaproveitamento é a fase b: 31 minutos, 16 deles na coleta e 13 no ataque conjunto de 2025 e 2026. Depois de uma mudança de regra, todos os anos voltam das fontes: pela soma da coleta de a e do cálculo de c, cerca de 70 minutos (estimativa). O reaproveitamento poupa sobretudo a coleta, 513 arquivos em vez de 1.809; nos anos fechados, a programação linear já levava menos de meio segundo. A memória ficou em um terço dos 16 GB.

**O que a medição não cobre.** As três fases usaram a mesma versão do FTP, então o ataque comparou versões montadas dos mesmos arquivos; a medição local de 11/11/2026, com versões de meses diferentes, deu um problema do mesmo tamanho em 2025. A fase c recalcula com as mesmas regras, e por isso os anos fechados saem iguais nas duas versões: depois de uma mudança de regra de verdade eles mudam, e o tempo da programação linear neles não foi medido. A coleta levou 54 minutos, contra 39 em 08/11/2026: a velocidade do FTP varia.

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

**No pipeline, em 08/11/2026** (`sih_trava.py`, [`trava_f1b.json`](../medicoes/resultados/trava_f1b.json)). Sobre as tabelas já suprimidas, no mesmo par de versões de SP e com as 27 UFs: por mês da alta, 4 acionamentos por residência e 4 por hospital, todos de Santo André, de 2604 a 2607, e nenhum em outro município. Entre os pares visíveis nas duas versões, mudaram 2 por residência e 1 por hospital em 2025, e 139 e 18 em 2026. A maior queda de uma UF numa competência foi de 0,88%, abaixo dos 5% da falha estrutural. A trava parte das células visíveis na versão anterior. Se a célula some da tabela nova, que só tem chaves com alguma AIH, conta como queda para zero; se fica oculta, não é comparada, porque não há valor publicado. A medição foi refeita com essa regra, com o mesmo resultado.
