"""Site estático: página inicial com busca, uma página por UF e uma por município.

Tudo funciona sem JavaScript, menos a busca por nome, que só aparece quando o script carrega.
Os caminhos são relativos, porque o site mora numa subpasta do GitHub Pages.
"""
from __future__ import annotations

import json
import shutil
import unicodedata
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

WEB = Path(__file__).resolve().parent.parent / "web"
REPOSITORIO = "https://github.com/MatheusCavalcanteF/explorador-dados-publicos"
NOME = "Explorador de Dados Públicos"
# O Brasil não tem horário de verão desde 2019; o horário de Brasília é UTC−3 fixo.
BRASILIA = timezone(timedelta(hours=-3))


def numero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def data_hora(iso: str) -> str:
    momento = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(BRASILIA)
    return momento.strftime("%d/%m/%Y, %H:%M") + " (Brasília)"


def megabytes(n: int) -> str:
    return f"{n / 1e6:.1f}".replace(".", ",") + " MB"


def ordem(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFD", nome)
    return "".join(c for c in sem_acento if unicodedata.category(c) != "Mn").casefold()


MARCAS = {
    "ok": '<svg class="marca" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 7-7" /></svg>',
    "falhou": '<svg class="marca" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>',
    "pendente": '<svg class="marca" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10" /></svg>',
}
SETA = '<svg class="seta" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3l5 5-5 5" /></svg>'


def rodape(coleta: dict) -> str:
    d = coleta["fontes"]["dtb"]
    return (f"Municípios da Divisão Territorial Brasileira {d['periodo']} do IBGE, com data-base em {data(d['data_base'])}. "
            f"Dados coletados em {data_hora(coleta['coletado_em'])}. Cada número tem a fonte e o método logo abaixo dele.")


def pagina(titulo: str, descricao: str, raiz: str, corpo: str, nota: str, script: bool = False) -> str:
    js = f'\n<script src="{raiz}busca.js" defer></script>' if script else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<meta name="description" content="{escape(descricao)}">
<meta name="color-scheme" content="light dark">
<link rel="preload" href="{raiz}fontes/overpass-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{raiz}estilo.css">{js}
</head>
<body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
<div class="barra"><a class="marca-site" href="{raiz}">{NOME}</a><a href="{raiz}#estados">Estados</a></div>
{corpo}
<footer class="rodape">
<p>{escape(nota)}</p>
<p><a href="{REPOSITORIO}">Código aberto</a>, sob licença MIT. <a href="{REPOSITORIO}/tree/main/manifesto">Manifesto das coletas</a>.</p>
</footer>
</body>
</html>
"""


def _conferencia(links: dict | None, metrica: str, codigo: str) -> str:
    """Resumo da última conferência dos links desta métrica, com marca e texto, não só cor."""
    if not links or metrica not in links.get("metricas", {}):
        return f'<p class="estado">{MARCAS["pendente"]}Link ainda sem conferência registrada.</p>'
    item = links["metricas"][metrica]
    quando = data(links["conferido_em"])
    amostra = [a for a in item["amostra"] if a["codigo"] == codigo]
    certos = sum(1 for a in item["amostra"] if a["ok"])
    estado = "ok" if certos == len(item["amostra"]) and item["tabela"]["ok"] else "falhou"
    texto = (f"Em {quando}, o link exato devolveu o valor publicado em {certos} de {len(item['amostra'])} "
             f"municípios sorteados, e a tabela {'respondeu' if item['tabela']['ok'] else 'não respondeu'}.")
    if amostra:
        texto += " Este município estava na amostra" + (" e conferiu." if amostra[0]["ok"] else ", e o link falhou.")
    return f'<p class="estado estado--{estado}">{MARCAS[estado]}{escape(texto)}</p>'


def _fonte(metrica: dict, nome: str, fonte: dict, m: dict, links: dict | None) -> str:
    f = metrica["fonte"]
    url = f["acesso"]["url"].format(municipio=m["codigo"], periodo=fonte["periodo"])
    if fonte["origem"] == "release":
        coleta = (f"Partição fechada, guardada na Release <a href=\"{REPOSITORIO}/releases/tag/ibge-censo-2022\">"
                  f"ibge-censo-2022</a>. Coletada da fonte em {escape(data_hora(fonte['coletado_em']))}")
        if fonte.get("conferido_com_a_fonte_em"):
            coleta += f" e conferida de novo em {escape(data_hora(fonte['conferido_com_a_fonte_em']))}, sem mudança"
        coleta += "."
    else:
        coleta = f"{escape(data_hora(fonte['coletado_em']))}."
    ressalvas = "".join(f"<li>{escape(r)}</li>" for r in metrica["ressalvas"])
    return f"""<section class="fonte__bloco" aria-labelledby="f-{nome}">
<h3 id="f-{nome}">{escape(metrica['rotulo'])}</h3>
<dl class="ficha">
<dt>Órgão e pesquisa</dt><dd>{escape(f['orgao'])}, {escape(f['pesquisa'])}.</dd>
<dt>Acesso</dt><dd><a href="{escape(url)}">Valor exato deste município</a>, na API da SIDRA, em JSON. <a href="{escape(f['tabela'])}">Tabela completa</a>, para escolher outro município ou período.</dd>
<dt>Período de referência</dt><dd>{escape(fonte['periodo'])}</dd>
<dt>Coleta</dt><dd>{coleta}</dd>
<dt>Arquivo usado</dt><dd>Resposta da API para todos os municípios, {escape(megabytes(fonte['bytes']))}. SHA-256 <code class="hash">{escape(fonte['sha256'])}</code></dd>
<dt>Ressalvas</dt><dd><ul>{ressalvas}</ul></dd>
<dt>Conferência do link</dt><dd>{_conferencia(links, nome, m['codigo'])}</dd>
</dl>
</section>"""


def _fonte_dtb(base: dict, fonte: dict) -> str:
    """Bloco da lista de municípios: de onde vêm código, nome e UF."""
    ressalvas = "".join(f"<li>{escape(r)}</li>" for r in base["ressalvas"])
    pasta = fonte["url"].rsplit("/", 2)[0] + "/"
    return f"""<section class="fonte__bloco" aria-labelledby="f-municipio">
<h3 id="f-municipio">Código, nome e UF do município</h3>
<dl class="ficha">
<dt>Órgão e pesquisa</dt><dd>{escape(base['orgao'])}, {escape(base['nome'])} {escape(fonte['periodo'])}.</dd>
<dt>Acesso</dt><dd><a href="{escape(fonte['url'])}">Arquivo da DTB {escape(fonte['periodo'])}</a>, em .zip, com a planilha <code>{escape(fonte['planilha'])}</code>. <a href="{escape(pasta)}">Todas as edições</a>, uma pasta por ano.</dd>
<dt>Data-base</dt><dd>{escape(data(fonte['data_base']))}, como informa a própria planilha</dd>
<dt>Coleta</dt><dd>{escape(data_hora(fonte['coletado_em']))}.</dd>
<dt>Arquivo usado</dt><dd>{escape(fonte['url'].rsplit('/', 1)[1])}, {escape(megabytes(fonte['bytes']))}. SHA-256 <code class="hash">{escape(fonte['sha256'])}</code></dd>
<dt>Ressalvas</dt><dd><ul>{ressalvas}</ul></dd>
</dl>
</section>"""


def _linha(rotulo: str, valor: int | None, classe: str = "") -> str:
    numero_ou_ausencia = (f'<dd><data value="{valor}">{numero(valor)}</data></dd>' if valor
                          else '<dd class="ausente">sem dado</dd>')
    return f'<div class="placa__linha{classe}"><dt>{escape(rotulo)}</dt>{numero_ou_ausencia}</div>'


def pagina_municipio(m: dict, coleta: dict, catalogo: dict, links: dict | None) -> str:
    fontes, metricas = coleta["fontes"], catalogo["metricas"]
    est, censo = fontes["estimativa"], fontes["censo"]
    linhas = [_linha(f"Estimativa {est['periodo']}", m["populacao_estimada"], " placa__linha--principal"),
              _linha("Censo 2022", m["populacao_censo"])]
    faltam = [nome for nome, valor in ((f"A estimativa de {est['periodo']}", m["populacao_estimada"]),
                                       ("O Censo 2022", m["populacao_censo"])) if not valor]
    ausencia = "".join(f'<p class="nota">{escape(f)} não traz dado para este município. A ausência não é zero.</p>'
                       for f in faltam)
    corpo = f"""<header class="placa" id="conteudo">
<div class="placa__face">
<nav class="trilha" aria-label="Trilha"><a href="../../">Brasil</a> <span aria-hidden="true">/</span> <a href="../../uf/{m['uf'].lower()}/">{escape(m['uf_nome'])}</a></nav>
<h1 class="placa__nome">{escape(m['nome'])}</h1>
<p class="placa__sub"><span class="escudo" title="{escape(m['uf_nome'])}">{escape(m['uf'])}</span> Código IBGE {m['codigo']}</p>
<h2 class="placa__titulo">População, em pessoas</h2>
<dl class="placa__dados">
{''.join(linhas)}
</dl>
</div>
</header>
<main class="coluna">
{ausencia}
<details class="fonte">
<summary>Fonte e método{SETA}</summary>
{_fonte(metricas['populacao_estimada'], 'populacao_estimada', est, m, links)}
{_fonte(metricas['populacao_censo'], 'populacao_censo', censo, m, links)}
{_fonte_dtb(catalogo['bases']['ibge_dtb'], fontes['dtb'])}
</details>
</main>"""
    descricao = f"{m['nome']} ({m['uf']}): população estimada pelo IBGE e Censo 2022, com fonte e método."
    return pagina(f"{m['nome']} ({m['uf']}) · {NOME}", descricao, "../../", corpo, rodape(coleta))


def pagina_uf(uf: str, uf_nome: str, municipios: list[dict], nota: str) -> str:
    itens = "\n".join(f'<li><a href="../../municipio/{m["codigo"]}/">{escape(m["nome"])}</a></li>'
                      for m in sorted(municipios, key=lambda m: ordem(m["nome"])))
    corpo = f"""<header class="placa" id="conteudo">
<div class="placa__face">
<nav class="trilha" aria-label="Trilha"><a href="../../">Brasil</a></nav>
<h1 class="placa__nome">{escape(uf_nome)}</h1>
<p class="placa__sub"><span class="escudo">{escape(uf)}</span> {numero(len(municipios))} municípios</p>
</div>
</header>
<main class="coluna">
<ul class="municipios">
{itens}
</ul>
</main>"""
    return pagina(f"{uf_nome} · {NOME}", f"Os {len(municipios)} municípios de {uf_nome}, com dados do IBGE.", "../../", corpo, nota)


def pagina_inicial(municipios: list[dict], nota: str) -> str:
    por_uf: dict[str, list[dict]] = {}
    for m in municipios:
        por_uf.setdefault(m["uf"], []).append(m)
    estados = "\n".join(
        f'<li><a href="uf/{uf.lower()}/"><span class="escudo">{uf}</span> <span class="estados__nome">{escape(lista[0]["uf_nome"])}</span>'
        f' <span class="estados__total">{numero(len(lista))}</span></a></li>'
        for uf, lista in sorted(por_uf.items(), key=lambda par: ordem(par[1][0]["uf_nome"])))
    corpo = f"""<header class="placa placa--inicio" id="conteudo">
<div class="placa__face">
<h1 class="placa__nome">{NOME}</h1>
<p class="placa__lead">Dados oficiais dos {numero(len(municipios))} municípios do Brasil. Cada número diz de onde veio, quando foi coletado e como conferir na fonte.</p>
<form class="busca" role="search" hidden>
<label for="busca">Buscar município pelo nome</label>
<input id="busca" type="search" autocomplete="off" spellcheck="false" placeholder="Ex.: Santos, ou Santos SP" aria-describedby="busca-aviso">
</form>
</div>
</header>
<main class="coluna">
<p id="busca-aviso" class="aviso" aria-live="polite"></p>
<ul id="resultados" class="resultados"></ul>
<h2 id="estados">Municípios por estado</h2>
<ul class="estados">
{estados}
</ul>
</main>"""
    return pagina(NOME, "Dados públicos oficiais de cada município brasileiro, com fonte e método em cada número.", "", corpo, nota, script=True)


def pagina_404(nota: str) -> str:
    # O GitHub Pages serve este arquivo em qualquer pasta, então os caminhos são absolutos a partir do site.
    corpo = """<header class="placa" id="conteudo"><div class="placa__face">
<h1 class="placa__nome">Página não encontrada</h1>
<p class="placa__lead">O endereço não existe. Os municípios estão na <a href="/explorador-dados-publicos/">página inicial</a>, pela busca ou pela lista de estados.</p>
</div></header>"""
    return pagina(f"Página não encontrada · {NOME}", "Página não encontrada.", "/explorador-dados-publicos/", corpo, nota)


def parquet(municipios: list[dict], destino: Path) -> None:
    """Sem compressão: o host comprime em gzip, e o leitor do navegador dispensa descompressor."""
    tabela = pa.table({
        "codigo": pa.array([m["codigo"] for m in municipios], pa.string()),
        "nome": pa.array([m["nome"] for m in municipios], pa.string()),
        "uf": pa.array([m["uf"] for m in municipios], pa.string()),
        "populacao_estimada": pa.array([m["populacao_estimada"] for m in municipios], pa.int32()),
        "populacao_censo_2022": pa.array([m["populacao_censo"] for m in municipios], pa.int32()),
    })
    destino.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabela, destino, compression="NONE")


def construir(coleta: dict, catalogo: dict, saida: Path, links: dict | None = None, execucao: str = "local") -> dict:
    if saida.exists():
        shutil.rmtree(saida)
    shutil.copytree(WEB, saida)
    municipios = coleta["municipios"]
    quando = coleta["coletado_em"]
    nota = rodape(coleta)

    def gravar(caminho: str, texto: str) -> None:
        destino = saida / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8", newline="\n")

    gravar("index.html", pagina_inicial(municipios, nota))
    gravar("404.html", pagina_404(nota))
    por_uf: dict[str, list[dict]] = {}
    for m in municipios:
        por_uf.setdefault(m["uf"], []).append(m)
        gravar(f"municipio/{m['codigo']}/index.html", pagina_municipio(m, coleta, catalogo, links))
    for uf, lista in por_uf.items():
        gravar(f"uf/{uf.lower()}/index.html", pagina_uf(uf, lista[0]["uf_nome"], lista, nota))
    gravar("dados/municipios.json", json.dumps([[m["codigo"], m["nome"], m["uf"]] for m in municipios],
                                               ensure_ascii=False, separators=(",", ":")))
    parquet(municipios, saida / "dados" / "ibge" / "populacao.parquet")
    versao = {"execucao": execucao, "coletado_em": quando, "municipios": len(municipios)}
    gravar("versao.json", json.dumps(versao, ensure_ascii=False))
    return versao
