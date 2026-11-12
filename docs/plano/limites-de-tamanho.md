[Índice do plano](../plano.md)

## Limites de tamanho

Os limites valem para o que é publicado. O orçamento total deixa margem no 1 GB do GitHub Pages.

| Tema | Medido (Brasil) | Janela da v1 | Previsto (estimativa) | Limite |
|---|---:|---|---:|---:|
| SIH, superfície (um arquivo) | Medido em 11/11/2026: 0,54 MB para 2025, com o detalhe, em zstd. As partições (41,1 MB de 2021 a julho de 2026) ficam no runner e não são publicadas | 2021 em diante | Não estimado para os seis anos | 200 MB |
| INEP, Censo Escolar e IDEB | 0,24 MB por ano + IDEB | 2019 em diante | ~5 MB | 20 MB |
| IBGE | < 1 MB | Última + série de população | ~2 MB | 10 MB |
| JSON por município | 113,8 MB (estimativa, 36 meses) | 36 meses | ~115 MB | 200 MB |
| JavaScript do site | Leitor: 18,6 KB com gzip | | Até 2 MB | 5 MB |
| Novo CAGED, agregados Parquet | 7,0 MB por ano nas tabelas aprovadas, só `MOV`, nacional com zstd | 2020 em diante (fora da v1) | ~50 MB com zstd; sem compressão, cerca do dobro | 100 MB |
| Siconfi | Não medido em escala | Fora da v1 | Não estimado | 60 MB |
| **Total** | | | | **595 MB** |

As páginas HTML não entraram neste orçamento. Em 08/11/2026, com o JSON-LD, o build local do site inteiro tem 58,1 MB, quase todo em páginas de município (mediana de 10,1 KB).

**Limite por página, definido em 08/11/2026: 100 KB sem compressão**, em `limites.pagina_html_kb` no catálogo. No build da coleta da execução 42442355751, a maior página é a de MG, com 56,4 KB, porque lista 853 municípios. O build falha se uma página passar, e o erro diz qual e com quantos bytes; um teste garante isso. **Com o SIH**, no build local de 08/11/2026, os gráficos passaram a ser desenhados no navegador a partir das tabelas da página, que ficam como a forma acessível dos mesmos valores (`web/sih.js`, 17,1 KB, ou 5,9 KB com gzip, baixado uma vez). Com o SVG pronto no HTML, as páginas de municípios de até 5 mil habitantes tinham mediana de 71,7 KB, e as das capitais, de 78,5 a 79,2 KB; desenhando no navegador, 47,2 KB e de 50,4 a 50,7 KB, cerca de 8 a 9,4 KB com gzip. O gráfico ocupa a largura da tela, com texto de 12 px: num celular emulado de 375 px, no Chrome, nos temas claro e escuro, a página não rola na horizontal e os gráficos têm 349 px. A taxa por mil habitantes só aparece em ano completo, e o município sem internação em hospital próprio (2.341 de 2021 a 2026) ganha uma frase no lugar da coluna de zeros. Cruzamento que não foi publicado num ano aparece como "não publicado", com o motivo, na tabela, no CSV e na série mensal, e fica sem marca no gráfico: zero é só a chave ausente de um cruzamento publicado. **O preliminar é marcado por listras**, sobre a cor cheia da série: com opacidade, como antes, o contraste com o fundo caía para 1,6 a 2,1:1. Agora toda marca do gráfico fica em 3:1 ou mais nos dois temas, de 3,46:1 (o laranja do tema claro, que passou de `#eb6834`, com 2,83:1, para `#d9581f`) a 5,92:1 ([`sih_local_f1b.json`](../medicoes/resultados/sih_local_f1b.json)).

Limites por arquivo:
- **Até 25 MiB para qualquer arquivo publicado, sem exceção.** Mantém a porta aberta para outro host. O `.wasm` do motor tem 35,9 MB e não entra no site; se um dia for usado, vem do CDN.
- **Até 5 MB** para arquivo que o celular baixa inteiro. O maior por UF e ano hoje tem 488 KB, ou 280 KB com gzip (residência x mês x faixa etária, MG).
- **Até 50 KB para o JSON de um município, e 15 KB com gzip.** Estimativa para a v1 com 36 meses: 30,2 KB em São Paulo (8,1 KB com gzip), o maior; mediana de 20,6 KB (4,2 KB). A parte do SIH responde por quase tudo: mediana de 18,7 KB, contra 1,8 KB de educação e 0,1 KB de IBGE.

O pipeline falha se algum limite for passado, e o erro aponta a tabela.
