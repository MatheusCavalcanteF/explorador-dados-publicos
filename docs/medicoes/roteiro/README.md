# Levantamento das fontes do roteiro depois da v1

`fontes_roteiro.csv` e `fontes_roteiro.md` são o levantamento citado em [Depois da v1](../../plano.md#depois-da-v1), copiados para cá em 08/11/2026. Antes, ficavam só numa pasta local, fora do repositório.

## Data e método

- **Consulta:** 07/11/2026, numa máquina local. Nada foi pedido a partir do runner do GitHub Actions; o alcance das mesmas rotas a partir do runner é outro teste, no workflow `Alcance das fontes`.
- **15 entradas.** Estabelecimentos e leitos do CNES estão separados, assim como Bolsa Família e Cadastro Único. 13 tiveram dados baixados e inspecionados; 2, as do MDS, ficaram só documentadas, porque as rotas redirecionavam para um aviso de manutenção.
- **Marcação de cada campo.** `medido`: corpo recebido e inspecionado, esquema observado ou resultado de tentativa de acesso. `documentado`: o que a origem publica, inclusive tamanho anunciado em cabeçalho HTTP, que não é arquivo baixado inteiro. Privacidade e dificuldade são avaliações técnicas, marcadas como tal no texto.
- **Coleta.** Intervalo mínimo de 1,2 s entre pedidos ao mesmo servidor, menos de 20 pedidos por servidor, e corpos abaixo de 50 MB por fonte e 300 MB no total. Downloads anuais grandes foram trocados por cabeçalhos ou trechos.

## O que ficou de fora

A pasta de amostras do levantamento não entrou no repositório: as amostras de saúde (SIM, SINASC e vacinação) trazem registros individuais. Por isso, os caminhos `amostras/...` citados nos dois arquivos, como `amostras/resumo_coleta.json` e `amostras/requisicoes.json`, não existem aqui. Os arquivos copiados descrevem as amostras (quantos bytes, quantos registros, quais colunas), sem nenhum valor delas.

## Conferência antes do commit

- Termos bloqueados pela regra do repositório: nenhum, nos dois arquivos.
- Registro individual: o CSV tem 15 linhas, uma por fonte, e 26 colunas de descrição. A varredura por padrões de CPF, número de 11 ou 15 dígitos e datas só achou datas de publicação das fontes. As colunas `colunas_conferidas` e `amostra_baixada` trazem nomes de colunas e tamanhos, não valores.
- Caminhos da máquina: nenhum.

## Arquivos

| Arquivo | SHA-256 do original | Diferença da cópia |
|---|---|---|
| `fontes_roteiro.csv` | `a951834ff36d38062a2dd4f00bf3b4e3646df80160f78c6ed7862d05d79d5850` | Fim de linha passou de CRLF para LF, pela regra do `.gitattributes`. A cópia tem `da4f9eab19d2b106fa389d18739fe64dc2543ded79f644b9661c5b9cefec4012`. Conteúdo igual; o arquivo começa com BOM |
| `fontes_roteiro.md` | `3ae721f5f6f1a68f3e743cec361739befb59c4f5486e1883c5e3f6133510e213` | Nenhuma |
