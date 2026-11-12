[Índice do plano](../plano.md)

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
    publicacao: { site: false }   # nada do SIH em Releases
    superficie:                   # o que o site mostra é tudo o que é público (decidido em 10/11/2026)
      arquivo: dados/sih/superficie.parquet
      cruzamentos:
        sih_res_ano: { medidas: [internacoes, obitos] }
        sih_res_ano_capitulo: { medidas: [internacoes], anos_recentes: 2 }
    versoes: { motores: [intervalos, programacao_linear] }   # todos precisam dar zero
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

**Célula oculta.** A supressão guarda o motivo de cada célula (`contagem_pequena`, `complementar` ou `familia`), e ele fica no pipeline. O motivo também é informação para quem tenta deduzir: numa margem com uma oculta de cada tipo e soma 6, a pequena só pode ser 1. **Decidido em 08/11/2026:** o motivo não é publicado, e toda célula oculta aparece do mesmo jeito no gráfico, na tabela, no CSV e no PNG, sem texto que diga o intervalo dela. A regra fica explicada no painel "Fonte e método". O teste de dedução ainda sabe tratar o motivo como público (a pequena entre 0 e k−1, a complementar fora de 1 a k−1), e foi assim que o efeito foi medido; ver [Teste de dedução da F1b](privacidade-e-supressao.md#teste-de-dedução-da-f1b).

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
