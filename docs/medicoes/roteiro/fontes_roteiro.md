# Fontes municipais depois da primeira versão

Consulta em 7 de novembro de 2026. São 15 entradas: estabelecimentos e leitos foram separados, assim como Bolsa Família e CadÚnico. **13 fontes tiveram dados baixados e inspecionados; 2 ficaram somente documentadas.** Acesso nesta máquina não comprova alcance por um executor remoto.

**Como ler o catálogo.** `medido` identifica corpo de dados recebido e inspecionado, esquema observado ou resultado de tentativa de acesso. `documentado` identifica informação publicada pela origem, inclusive tamanho anunciado em cabeçalho HTTP. Tamanho anunciado não significa arquivo integralmente baixado. Nas duas fontes sem dados, a validação geral continua `documentado`, apesar de seus redirecionamentos terem sido medidos. Privacidade e dificuldade são avaliações técnicas identificadas como tal, baseadas no material indicado. Dificuldade: 1 simples, 5 com bloqueio operacional ou processamento expressivo. Campo não confirmado permanece explícito; amostra pequena não comprova cobertura nacional, completude ou atualização de toda a série.

## Saúde ampliada

**Medido:** SIM, SINASC, CNES estabelecimentos, CNES leitos e vacinação têm caminhos que responderam sem credencial. Códigos municipais observados têm seis dígitos: precisam de correspondência validada com o cadastro de sete dígitos. SIM e SINASC distinguem residência e ocorrência/nascimento. O SINASC funcionou por ZIP; sua API retornou listas vazias. Prévia, preliminar e versão revisada devem permanecer identificadas. [Catálogo SIM](https://dadosabertos.saude.gov.br/dataset/sim), [catálogo SINASC](https://dadosabertos.saude.gov.br/dataset/sistema-de-informacao-sobre-nascidos-vivos-sinasc).

**Medido:** estabelecimentos é uma fotografia cadastral; leitos é estoque por competência. Não somar estoques mensais como total anual. A API `cnes-leitos` fornece código municipal, enquanto o CSV relacionado **Hospitais e Leitos** usa nomes. São distribuições com esquemas diferentes. **Documentado:** o cadastro declara atualização diária. [Catálogo CNES](https://dadosabertos.saude.gov.br/dataset/cnes-cadastro-nacional-de-estabelecimentos-de-saude), [distribuição relacionada](https://dadosabertos.saude.gov.br/dataset/hospitais-e-leitos).

**Documentado:** os cabeçalhos dos 12 ZIPs CSV de vacinação de 2024 anunciam **26.073.801.684 bytes**, cerca de 26,07 GB compactados. **Medido:** a amostra traz doses individuais e municípios do paciente e do estabelecimento. Volume, deduplicação, registros excluídos, definição da métrica e proteção de casos raros são os principais bloqueios. A licença específica está vazia no metadado consultado. [Catálogo de vacinação](https://dadosabertos.saude.gov.br/dataset/doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-2024).

## Agropecuária

**Medido:** PAM e PPM entregaram agregados municipais pela API SIDRA, com código de sete dígitos. São as integrações mais simples desta lista. **Documentado:** os metadados consultados indicam séries anuais de 1974 a 2025. **Avaliação baseada na amostra:** preservar unidades, valores indisponíveis e sigilo estatístico. A tabela PPM medida cobre rebanhos; outros produtos exigem outras tabelas. Volume nacional anual e licença nominal específica não foram confirmados. [PAM 5457](https://sidra.ibge.gov.br/tabela/5457), [PPM 3939](https://sidra.ibge.gov.br/tabela/3939).

## Assistência social

**Somente documentado:** VIS DATA e Observatório oferecem agregados públicos e exportações. **Medido:** VIS DATA, relatórios, CECAD e caminhos antigos redirecionaram para aviso oficial de manutenção preventiva de segurança. Não foi confirmada uma rota operacional de descarga agregada; colunas, largura do código municipal, série efetiva e tamanho continuam desconhecidos. As duas fontes ficam **pendentes por indisponibilidade temporária**. A API do Portal da Transparência exige cadastro e chave e fica **inviável para este projeto**; não foi usada como substituta. [Ferramentas do MDS](https://www.gov.br/mds/pt-br/orgaos/SAGICAD/dados-e-ferramentas-informacionais), [aviso](https://www.gov.br/mds/pt-br/avisos), [regras da API](https://portaldatransparencia.gov.br/api-de-dados).

**Documentado:** o Observatório informa defasagem aproximada de dois meses e oculta resultados inferiores a 100 famílias ou 200 pessoas. Conservar a ocultação da origem e impedir recuperação por subtração. Essas regras não foram medidas em uma tabela recebida. [Documentação do Observatório](https://wiki-sagi.mds.gov.br/home/F/OBCAD).

## Saneamento

**Medido:** Gestão Municipal do SINISA foi baixado integralmente: 6.048.522 bytes e código de sete dígitos. A planilha inclui municípios não respondentes; presença de código não significa resposta válida. **Documentado:** a edição 2025 refere-se a 2024, foi publicada em dezembro de 2025 e sofreu revisão em 2026. **Avaliação baseada na amostra:** compatibilizar edição, ano de referência, cabeçalhos, dicionários e não resposta. Os demais módulos e a continuidade com SNIS precisam de validação própria; tamanho e esquema de Gestão Municipal não representam os cinco módulos. [Resultados SINISA 2025](https://www.gov.br/cidades/pt-br/acesso-a-informacao/acoes-e-programas/saneamento/sinisa/resultados-sinisa/resultados-sinisa-2025).

## Meio ambiente

**Medido:** focos de queimadas têm CSV diário e código de sete dígitos. Selecionar satélite, produto e referência temporal; foco não equivale a incêndio independente ou área queimada. **Documentado:** o ZIP nacional de todos os satélites de 2024 anuncia 117.030.540 bytes. [Distribuição oficial](https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/).

**Medido:** DETER fornece município e código de sete dígitos em WFS público. **Documentado:** a FAQ informa atraso público de uma semana; acesso diário antecipado exige autenticação e é inviável no projeto. **Avaliação baseada na amostra:** não transformar alertas em taxa anual. [FAQ](https://data.inpe.br/biomasbr/faq/).

**Medido:** a camada PRODES testada não contém município; a camada de limites oferece código de sete dígitos. A agregação exige interseção espacial. As amostras PRODES e DETER cobrem a Amazônia Legal, sem comprovar outras regiões. **Documentado:** a licença do programa no TerraBrasilis é Atribuição-CompartilhaIgual 4.0; não foi estendida automaticamente aos focos. Volumes anuais PRODES e DETER não foram determinados. [Downloads](https://terrabrasilis.dpi.inpe.br/downloads/), [licença](https://terrabrasilis.dpi.inpe.br/citacoes-e-licenca-de-uso/).

## Eleições

**Medido:** foi extraído um membro estadual do ZIP nacional de votação de 2024. `CD_MUNICIPIO` é código eleitoral próprio, exigindo correspondência com IBGE. **Documentado:** o ZIP desse produto anuncia 48.213.408 bytes. **Avaliação baseada na amostra:** separar cargo, turno, zona e destino dos votos e evitar duplicidade entre arquivos nacionais e estaduais. A correspondência municipal não foi construída nesta pesquisa. [Catálogo TSE](https://dadosabertos.tse.jus.br/dataset/resultados-2024).

## Segurança

**Medido:** a planilha SINESP VDE de 2024 foi baixada integralmente: 24.388.241 bytes. Não traz coluna IBGE; exige associação por UF e nome e tratamento de exceções. **Documentado:** há arquivos 2015–2026, cobertura variável e notas estaduais. A página orienta somar certas linhas mensais de Tentativa de Homicídio e Estupro. **Avaliação baseada na amostra:** distinguir vítimas de ocorrências, controlar revisões e proteger recortes raros de sexo e idade. O acesso público dispensa o sistema interno autenticado. [Planilhas e notas oficiais](https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica/dados-nacionais-1/base-de-dados-e-notas-metodologicas-dos-gestores-estaduais-sinesp-vde-2022-e-2023).

## Ordem sugerida e limites da coleta

**Avaliação técnica baseada nas amostras:** PAM e PPM; CNES estabelecimentos e leitos; SINISA Gestão Municipal; focos; TSE e DETER; SIM e SINASC; PRODES e SINESP; vacinação completa. Bolsa Família e CadÚnico aguardam retorno das rotas públicas. Licença não confirmada continua pendência antes da distribuição, mesmo onde o acesso funcionou. Esta ordem considera extração e tratamento, sem alterar o roteiro do projeto.

**Medido:** corpos recebidos ficaram abaixo de 50 MB por fonte e 300 MB no total. O total exato, bytes por fonte e pedidos por servidor estão em `amostras/resumo_coleta.json`; cada pedido, inclusive redirecionamento e falha, consta em `amostras/requisicoes.json`. O coletor impõe intervalo mínimo de 1,2 segundo entre inícios de pedidos ao mesmo servidor e limite inferior a 20. Downloads anuais grandes foram substituídos por cabeçalhos ou trechos. Somente armazenamento vinculado pelo catálogo oficial foi usado para os arquivos em nuvem. Servidores efetivamente tentados constam em cada linha do CSV, inclusive os que falharam; não foram testados em executor remoto.

As amostras de saúde contêm registros individuais. Para publicação do levantamento, usar o catálogo e o resumo; revisar separadamente qualquer distribuição das amostras brutas. Nenhum arquivo do projeto foi alterado.
