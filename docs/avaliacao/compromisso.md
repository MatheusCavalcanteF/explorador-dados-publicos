# Compromisso da bateria de perguntas

A busca em português vai ser avaliada com uma bateria de perguntas escrita antes do sistema. Para provar que ela existia antes e não foi ajustada depois, este arquivo registra só a impressão digital dela. As perguntas entram no repositório na F3, e quem quiser conferir calcula o SHA-256 do arquivo e compara com o daqui.

## O arquivo

| | |
|---|---|
| Nome | `perguntas_busca.csv` |
| SHA-256 | `ee279cd1de8731d20e75ebc675e701121eb811e9de1cb5bea91a83c79b4493ad` |
| Tamanho | 33.538 bytes |
| Codificação | UTF-8 sem BOM, fim de linha LF. O `.gitattributes` não altera esses bytes |
| Linhas | 120 perguntas, mais o cabeçalho; 120 `id` distintos |
| Colunas | `id`, `pergunta`, `categoria`, `resposta_esperada`, `ambiguidade`, `conjunto` |

## Contagens

| Categoria | Treino | Teste | Total |
|---|---:|---:|---:|
| `respondivel` | 42 | 18 | 60 |
| `ambigua` | 18 | 7 | 25 |
| `fora_do_catalogo` | 17 | 8 | 25 |
| `privacidade` | 7 | 3 | 10 |
| **Total** | **84** | **36** | **120** |

## Como foi registrado

Em 08/11/2026, um script leu o arquivo, calculou o SHA-256 dos bytes e contou as linhas pelas colunas `categoria` e `conjunto`. Só o cabeçalho e essas contagens foram exibidos: as perguntas, as respostas esperadas e as ambiguidades não foram lidas nesta etapa, e nada do sistema de busca existia ainda.

Para conferir, quando o arquivo entrar no repositório:

```sh
sha256sum perguntas_busca.csv
```

Se o hash não bater, a bateria mudou depois deste registro, e a avaliação publicada precisa dizer isso.
