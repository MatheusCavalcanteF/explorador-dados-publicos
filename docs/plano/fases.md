[Índice do plano](../plano.md)

## Fases

As fases originais mudaram com as medições. O que mudou está marcado em **negrito**.

### F1. Páginas por município, em três etapas publicáveis

A divisão proposta (deploy e CI; SIH e catálogo; educação e IBGE) foi mantida, com uma mudança: **o IBGE não pode ser o último**. A página mínima precisa da lista de 5.571 municípios, e o SIH precisa de população para taxas e dos códigos de 7 dígitos. Por isso localidades e população vão para a primeira etapa, e só o PIB fica para a última.

**F1a. Deploy, CI e uma página real**
- Deploy próprio no GitHub Pages; workflow agendado; Release e manifesto no git. Fim de linha fixado em LF no `.gitattributes` antes do primeiro workflow.
- Coleta real pelo runner: lista de municípios pela DTB do geoftp, população pela SIDRA, e um teste de alcance de cada fonte (um `RD` pequeno do DATASUS, a listagem do CAGED, uma consulta do Siconfi). **O INEP saiu do teste semanal até a F1c:** recusou o runner nas 3 execuções do diagnóstico manual, que continua a testá-lo.
- Página de cada município com nome, UF, população, fonte e data da coleta, e o painel "Fonte e método" com o link exato do IBGE para a população.
- Conferência agendada de links, marcando os quebrados no manifesto.
- Repetir no site real os testes de `Range`, `HEAD`, gzip e leitor. Feito em 07/11/2026, nos três navegadores; ver [Hospedagem](arquitetura.md#hospedagem-github-pages).
- **Fechamento, em 08/11/2026:** repositório renomeado, endereço numa configuração única, sitemap, link canônico, Open Graph e JSON-LD em cada página, suporte ao arquivo do Search Console, revisão da estimativa marcada na página, e o teste diário do INEP. Ver [Endereço e buscadores](arquitetura.md#endereço-e-buscadores) e [Riscos](escopo-e-riscos.md#riscos).

*Pronto quando:* o workflow agendado publica sozinho, as fontes respondem do runner e os testes de hospedagem batem com este plano. Se o runner não alcançar os FTPs, parar e avisar: é o que mais pode mudar o plano. Em 08/11/2026, só falta a primeira execução agendada, em 15/11.

**F1b. SIH do Brasil, com catálogo e supressão**
- **As 27 UFs**, partições por ano no runner, janela aberta recalculada. **O público é só a superfície** que o site mostra, publicada com ele; nada do SIH em Releases (decidido em 10/11/2026).
- Catálogo, contrato de dados, trava de queda, supressão por família.
- **Teste de dedução em cadeia, incluindo a comparação entre versões publicadas e a candidata.** Decisão sobre os meses preliminares.
- Página com gráficos, ressalvas, nível de detalhe conforme o município, filtros.
- **Conferência por mês da alta.** O TabNet não tem esse eixo, então a conferência é em duas partes. Com o TabNet, amostra por município em cada região, nos eixos que ele oferece: competência e data de internação, confirmando que o pipeline parte das mesmas AIHs. No pipeline, teste com AIHs sintéticas de que cada uma cai no mês da sua data de alta, e que os totais fecham entre os três eixos. Investigar a diferença da capital. Procurar outra ferramenta oficial com esse eixo; se não houver, o limite fica declarado na tela.

*Pronto quando:* o teste de dedução dá zero, a amostra bate com o TabNet nos dois eixos dele, os totais fecham com o mês da alta, e o JSON respeita o limite. A meta de abrir a página em menos de 3 s em 4G lento é medida no site real.

**Estado em 08/11/2026, parada antes de publicar o SIH:**
- Feito: coleta das 27 UFs com contrato por linha, janela recalculada a cada execução, tabelas por ano da alta, supressão por família, teste de dedução em cadeia com reforço (zero nos seis anos), critério de publicação por ano, trimestre só completo, preliminares arredondados na partição, comparação entre versões com transição de fechamento e três versões, herança do padrão nos períodos fechados, situação fixa no ano aberto, partições trocadas por ano com a lista de arquivos conferida na leitura, trava de queda, conferência com o TabNet e o workflow `SIH (medição)` no runner. Em 10/11/2026: o ano que reprova em qualquer teste não vira partição; as margens publicadas vão na partição; o ataque conjunto com a versão no ar é etapa do pipeline, com motor trocável; e o ciclo inteiro foi simulado no build local. Ainda em 10/11/2026, depois da decisão sobre a superfície: a versão no ar é o arquivo da superfície, publicado com o site, e o `Publicar` o baixa e confere (`no-ar`) e o passa ao SIH em `--no-ar`, em passos que só rodam quando o catálogo mandar publicar; a herança e o ataque conjunto leem dele; as Releases do SIH e as margens na partição saíram; e o ataque roda com dois motores, intervalos e programação linear. A página com gráficos, tabela, CSV e PNG existe só no build local (`construir --sih-local`, que para no CI), desenhada da superfície. O SIH está no catálogo com `publicacao: {site: false}`.
- Decidido em 08/11/2026: o motivo por célula não é publicado; meses preliminares em múltiplo de 5; o cruzamento que reprova no ano não é publicado naquele ano, com o motivo na página; a herança do padrão é regra; o ataque conjunto com a versão no ar é obrigatório antes de toda publicação; num ano aberto, o que é publicado fica o da primeira publicação dele, e só o teste de dedução tira algum cruzamento. Decidido em 10/11/2026: a superfície pública do SIH é só o que o site mostra, sem Release com partições, e a versão no ar é o arquivo dessa superfície; o ataque conjunto roda com os dois motores, e os dois precisam dar zero. Decidido em 11/11/2026: o detalhe de um ano que sai dos dois mais novos continua publicado; e, quando os anos fechados do SIH forem reaproveitados da superfície no ar, o reaproveitamento se invalida sozinho se mudar o hash das regras do SIH no catálogo ou o número de versão do algoritmo de supressão no código: aí todos os anos são recalculados das fontes, com a herança do padrão da versão no ar, e o ataque conjunto decide o que pode ir ao ar (implementado em 12/11/2026).
- Não feito: levar a superfície e as páginas do SIH ao site pelo catálogo, e não só por `--sih-local`; o SIH roda no workflow próprio, `SIH (medição)`, só manual e sem publicar, e o `Publicar` com o SIH ligado nunca rodou: o job de 30 minutos dele não comporta a coleta do SIH; medir a programação linear nos anos fechados depois de uma mudança de regra real; o JSON-LD do SIH na página; a conferência pelo mês da alta no TabWin; e o teste em celular real.
- Contrato: nos 76,1 milhões de AIHs das competências 2101 a 2608, nenhuma linha violou as regras (competência, IDENT, UF do hospital, municípios na DTB, datas, defasagem de até 5 meses, CID, dicionários, chave única). O sexo 4, novo e sem definição em documento oficial, vai para "Ignorado", como no TabWin.

**F1c. Educação e o restante do IBGE**
- **Antes de tudo, uma rota do runner até o INEP**, que recusou a conexão em 07/11/2026. Se a hipótese de bloqueio por excesso de pedidos não se confirmar, procurar outra origem oficial dos mesmos arquivos. Sem rota, a educação não entra.
- **Censo Escolar e IDEB**, PIB, amostra conferida com as ferramentas do INEP e do SIDRA.
- O teste de dedução passa a cobrir as tabelas novas.

*Pronto quando:* a página de município mostra saúde, educação e IBGE, cada número com sua fonte. É aqui que o produto deixa de parecer só de saúde. O custo medido é baixo (0,24 MB por ano e 4,7% das células ocultas), então esta etapa pode vir junto da F1b se houver folga.

### F2. Construtor de dashboards
- Especificação na URL, exportação, **leitor em JavaScript sobre arquivos por UF**.
- **Teste de igualdade entre leitor e motor no CI.** O motor só entra na v1 se uma função provar que precisa dele.
- **Publicar os arquivos como dados abertos e documentar os caminhos estáveis**: já são públicos, então isso custa só documentação. Do SIH, só a superfície (decidido em 10/11/2026): um cruzamento a mais no construtor amplia a superfície e passa antes pelo teste de dedução e pelos dois motores.
- Teste em aparelho físico e Safari no iOS.

### F3. Busca em português
- Pelo menos 100 perguntas escritas antes de ajustar o sistema, incluindo as sem resposta, com treino e teste separados.
- Dicionário e correspondência aproximada primeiro. Embeddings no navegador só se o ganho compensar o peso.
- Taxas de acerto, recusa correta e resposta errada publicadas no README.

### Depois da v1

**Nesta ordem, revista em 08/11/2026: agropecuária primeiro.** Cada área começa como a Etapa 0: medir a fonte antes de prometer a tela. Em todas, a medição responde às mesmas perguntas: se o runner alcança a fonte, formato e tamanho por ano, cobertura municipal, defasagem e republicação, licença declarada, quanto a supressão oculta em cada cruzamento e com que ferramenta oficial o resultado pode ser conferido.

**O levantamento de 07/11/2026.** Um levantamento à parte, feito numa máquina local, testou 15 entradas (estabelecimentos e leitos separados, assim como Bolsa Família e Cadastro Único): 13 tiveram dados baixados e inspecionados, e 2 ficaram só documentadas. A tabela segue a marcação dele: **medido** é corpo recebido e inspecionado, esquema observado ou resultado de tentativa de acesso; **documentado** é o que a origem publica, inclusive tamanho anunciado em cabeçalho HTTP, que não é arquivo baixado inteiro. CAGED e Siconfi foram medidos na Etapa 0 e estão em [Fontes](fontes.md#fontes). O catálogo do levantamento está em [`docs/medicoes/roteiro/`](../medicoes/roteiro/README.md), sem a pasta de amostras, que tem registros individuais.

| Fase | Área e fonte | Acesso | Código do município | Tamanho | Licença declarada | Situação |
|---|---|---|---|---|---|---|
| F4 | **Agropecuária.** IBGE, Produção Agrícola Municipal (PAM, tabela 5457) e Pesquisa da Pecuária Municipal (PPM, tabela 3939), pela SIDRA | Medido: API da SIDRA sem chave, um município e um ano no endereço | Medido: 7 dígitos | Documentado: não determinado para o Brasil; depende das variáveis e classificações escolhidas | Documentado: não localizada, como nas outras tabelas do IBGE | **Primeira.** Já vem agregada e sai da `apisidra`, que o runner alcança na coleta semanal. Preservar unidades, ausência e sigilo do SIDRA. A tabela 3939 cobre rebanhos; leite, ovos e outros produtos ficam em outras tabelas |
| F5 | **Saúde ampliada.** SIM e SINASC | Medido: SIM pela API sem credencial; SINASC pelo ZIP, porque a API devolveu listas vazias | Medido: 6 dígitos; residência e ocorrência separadas | Documentado: CSV nacional de 2024 com 95,4 MB (SIM) e 92,3 MB (SINASC) compactados | Documentado: CC BY no metadado, sem versão | Registros individuais: supressão por família, começando pelo total anual |
| F5 | CNES, estabelecimentos e leitos | Medido: API sem credencial; leitos por competência | Medido: 6 dígitos na API de leitos; o CSV "Hospitais e Leitos" só tem o nome | Documentado: fotografia de estabelecimentos com 56,8 MB; CSV de leitos de 2024 com 25,2 MB | Documentado: CC BY em estabelecimentos; nenhuma específica para a API de leitos | Leito é estoque: não somar competências como total anual |
| F5 | Vacinação (SI-PNI) | Medido: API e arquivos sem credencial | Medido: 6 dígitos, do paciente e do estabelecimento | Documentado: **cerca de 26 GB compactados por ano**, somando os 12 ZIPs mensais de 2024 | Documentado: vazia no metadado | **Cara.** Medido: uma linha por dose aplicada, com dados do paciente. Exige deduplicação, registros excluídos e proteção de casos raros, e dose não é pessoa vacinada. Fica por último na fase |
| F6 | **Trabalho e finanças públicas.** Novo CAGED e Siconfi | Ver [Fontes](fontes.md#fontes) | | | | Como antes da revisão da ordem |
| F7 | **Assistência social.** MDS: Bolsa Família e Cadastro Único agregados (VIS DATA e Observatório) | Medido: as rotas testadas redirecionaram para um aviso de manutenção, sem dados | Documentado: recorte municipal; presença e largura do código não confirmadas | Não determinado | Documentado: não localizada | **Pendente**, só documentada. Volta quando as rotas públicas responderem, e não segura as fases seguintes. A API do Portal da Transparência pede cadastro e chave e fica fora. Documentado: o Observatório oculta menos de 100 famílias ou 200 pessoas, e essa ocultação precisa resistir a subtração aqui |
| F8 | **Saneamento.** SINISA, Gestão Municipal | Medido: planilha baixada inteira | Medido: 7 dígitos, inclusive de municípios que não responderam | Medido: 6,0 MB do módulo Gestão Municipal; os outros quatro módulos, não | Documentado: não localizada; o CC BY-ND 3.0 do rodapé é do site | Código presente não é resposta válida, e não resposta não é zero |
| F9 | **Meio ambiente.** INPE: PRODES, DETER e focos de queimada | Medido: WFS público (PRODES e DETER) e CSV diário (focos) | Medido: 7 dígitos no DETER e nos focos. **O PRODES não tem município**: exige interseção espacial com a camada de limites | Documentado: ZIP nacional de focos de 2024 com 117 MB; PRODES e DETER não determinados | Documentado: **PRODES e DETER sob CC BY-SA 4.0**, pelo TerraBrasilis; nos focos, nenhuma formal | A CC BY-SA pede atribuição e a mesma licença nos derivados: arquivos próprios, como os do Siconfi sob ODbL. As amostras cobrem só a Amazônia Legal |
| F10 | **Eleições.** TSE, resultados por município | Medido: catálogo e ZIP sem credencial | Medido: **sem código IBGE**. `CD_MUNICIPIO` é código eleitoral próprio | Documentado: ZIP nacional de votação por município e zona de 2024 com 48,2 MB | Documentado: CC BY, sem versão | Exige correspondência TSE x IBGE, a construir e conferir. Não somar cargos, turnos, nem os arquivos nacional e estaduais |
| F11 | **Segurança.** SINESP VDE, do Ministério da Justiça | Medido: planilha de 2024 baixada inteira | Medido: **sem código IBGE**. Só UF e nome do município | Medido: 24,4 MB em 2024 | Documentado: CC BY no catálogo antigo; não confirmada na planilha atual | Associação por UF e nome, com as exceções explícitas. Vítimas e ocorrências separadas; sexo e idade em cidades pequenas pedem supressão |

Nenhuma dessas fontes foi testada do runner. O diagnóstico manual `Alcance das fontes` passou a pedir um endereço de cada servidor de dados delas, numa tabela à parte, sem torná-las obrigatórias: nenhuma etapa depende delas, e o `Publicar` não as testa. Ficam de fora a API do Portal da Transparência e as páginas que só documentam a fonte. Da máquina local, em 08/11/2026, as 13 rotas responderam, e as duas do MDS ainda redirecionavam para o aviso de manutenção ([`alcance_roteiro_local.json`](../medicoes/resultados/alcance_roteiro_local.json)).

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
