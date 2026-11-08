"""Site estático: página inicial com busca, uma página por UF e uma por município, e o sitemap.

Tudo funciona sem JavaScript, menos a busca por nome, que só aparece quando o script carrega.
Os links internos são relativos, porque o site mora numa subpasta do GitHub Pages. O endereço
absoluto, usado no link canônico, no Open Graph, no JSON-LD e no sitemap, vem de projeto.yaml.
"""
from __future__ import annotations

import io
import json
import shutil
import unicodedata
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from . import buscadores, projeto

WEB = Path(__file__).resolve().parent.parent / "web"
NOME = projeto.NOME
PARQUET = "dados/ibge/populacao.parquet"
MANIFESTO_IBGE = f"{projeto.REPOSITORIO}/blob/main/manifesto/ibge.json"
# O Brasil não tem horário de verão desde 2019; o horário de Brasília é UTC−3 fixo.
BRASILIA = timezone(timedelta(hours=-3))


def numero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _momento(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(BRASILIA)


def data_hora(iso: str) -> str:
    return _momento(iso).strftime("%d/%m/%Y, %H:%M") + " (Brasília)"


def dia(iso: str) -> str:
    """Só a data, no horário de Brasília: 02:36 UTC de 08/11 ainda é 07/11."""
    return _momento(iso).strftime("%d/%m/%Y")


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


def pagina(titulo: str, descricao: str, raiz: str, corpo: str, nota: str, script: bool = False,
           endereco: str | None = None, dados: dict | None = None) -> str:
    """`endereco` é o caminho da página dentro do site; sem ele, a página não tem link canônico nem Open Graph."""
    cabeca = f'\n<script src="{raiz}busca.js" defer></script>' if script else ""
    if endereco is not None:
        url = escape(projeto.SITE + endereco)
        cabeca += (f'\n<link rel="canonical" href="{url}">'
                   '\n<meta property="og:type" content="website">'
                   f'\n<meta property="og:site_name" content="{NOME}">'
                   '\n<meta property="og:locale" content="pt_BR">'
                   f'\n<meta property="og:title" content="{escape(titulo)}">'
                   f'\n<meta property="og:description" content="{escape(descricao)}">'
                   f'\n<meta property="og:url" content="{url}">')
    if dados is not None:
        cabeca += "\n" + buscadores.script(dados)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)}</title>
<meta name="description" content="{escape(descricao)}">
<meta name="color-scheme" content="light dark">
<link rel="preload" href="{raiz}fontes/overpass-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{raiz}estilo.css">{cabeca}
</head>
<body>
<a class="pular" href="#conteudo">Pular para o conteúdo</a>
<div class="barra"><a class="marca-site" href="{raiz}">{NOME}</a><a href="{raiz}#estados">Estados</a></div>
{corpo}
<footer class="rodape">
<p>{escape(nota)}</p>
<p><a href="{projeto.REPOSITORIO}">Código aberto</a>, sob licença MIT. <a href="{projeto.REPOSITORIO}/tree/main/manifesto">Manifesto das coletas</a>.</p>
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


def _fonte(metrica: dict, nome: str, fonte: dict, m: dict, links: dict | None, extras: list[str] = ()) -> str:
    f = metrica["fonte"]
    url = f["acesso"]["url"].format(municipio=m["codigo"], periodo=fonte["periodo"])
    if fonte["origem"] == "release":
        coleta = (f"Partição fechada, guardada na Release <a href=\"{projeto.REPOSITORIO}/releases/tag/ibge-censo-2022\">"
                  f"ibge-censo-2022</a>. Coletada da fonte em {escape(data_hora(fonte['coletado_em']))}")
        if fonte.get("conferido_com_a_fonte_em"):
            coleta += f" e conferida de novo em {escape(data_hora(fonte['conferido_com_a_fonte_em']))}, sem mudança"
        coleta += "."
    else:
        coleta = f"{escape(data_hora(fonte['coletado_em']))}."
    ressalvas = "".join(f"<li>{escape(r)}</li>" for r in [*extras, *metrica["ressalvas"]])
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


# Revisões da estimativa: o IBGE muda um valor já publicado para o mesmo período.

def revisoes(estimativa: dict) -> tuple[dict[str, dict], dict | None]:
    """Última revisão que alcançou cada município, e a última sem detalhe por município, que alcança todos."""
    por_codigo, geral = {}, None
    for evento in estimativa.get("revisoes") or []:
        if evento.get("municipios") is None:
            geral = evento
        else:
            for item in evento["municipios"]:
                por_codigo[item["codigo"]] = evento
    return por_codigo, geral


def revisao_do_municipio(codigo: str, por_codigo: dict, geral: dict | None) -> dict | None:
    candidatos = [e for e in (por_codigo.get(codigo), geral) if e]
    return max(candidatos, key=lambda e: e["detectada_em"]) if candidatos else None


def texto_revisao(evento: dict, periodo: str, codigo: str) -> str:
    quando = dia(evento["detectada_em"])
    if evento.get("municipios") is None:
        return (f"Revisado pelo IBGE. A coleta de {quando} encontrou valores diferentes dos que a SIDRA informava antes "
                f"para a estimativa de {periodo}, mas não conseguiu identificar quais municípios mudaram. "
                f"Por isso o aviso aparece em todas as páginas.")
    item = next(i for i in evento["municipios"] if i["codigo"] == codigo)
    if item["depois"] is None:
        return (f"Revisado pelo IBGE. Na coleta de {quando}, a SIDRA deixou de trazer este município na estimativa "
                f"de {periodo}, que antes tinha valor. O valor anterior está no manifesto das coletas.")
    if item["antes"] is None:
        return (f"Revisado pelo IBGE. Na coleta de {quando}, a SIDRA passou a trazer este município na estimativa "
                f"de {periodo}, que antes não tinha valor.")
    return (f"Revisado pelo IBGE. A coleta de {quando} encontrou, para a estimativa de {periodo}, um valor diferente "
            f"do que a SIDRA informava antes. O valor anterior está no manifesto das coletas.")


def alteracao_municipio(fontes: dict, evento: dict | None) -> str:
    """Data da última mudança nos valores que a página do município mostra."""
    est = fontes["estimativa"]
    datas = [buscadores.desde(fontes["dtb"]), buscadores.desde(fontes["censo"]),
             est.get("periodo_desde") or buscadores.desde(est)]
    if evento:
        datas.append(evento["detectada_em"])
    return max(datas)


def _dados_municipio(m: dict, coleta: dict, catalogo: dict, alterado_em: str) -> dict:
    fontes, metricas, bases = coleta["fontes"], catalogo["metricas"], catalogo["bases"]
    partes = [buscadores.parte_dtb(bases["ibge_dtb"], fontes["dtb"], m)]
    mostra = []
    for chave, fonte, texto in (("populacao_estimada", fontes["estimativa"], f"população estimada pelo IBGE para {fontes['estimativa']['periodo']}"),
                                ("populacao_censo", fontes["censo"], "população do Censo 2022")):
        if m[chave]:
            metrica = metricas[chave]
            partes.append(buscadores.parte_metrica(chave, metrica, bases[metrica["base"]], fonte, m))
            mostra.append(texto)
    onde = f"{m['nome']} ({m['uf']})"
    nome = f"População de {onde}" if mostra else f"{onde} na Divisão Territorial Brasileira"
    descricao = (f"Dados oficiais de {m['nome']} ({m['uf_nome']}), código IBGE {m['codigo']}"
                 + (": " + " e ".join(mostra) if mostra else ", na lista de municípios do IBGE")
                 + ", com fonte, período de referência e data da coleta de cada número.")
    return buscadores.dataset(nome, descricao, f"municipio/{m['codigo']}/", alterado_em, buscadores.lugar_municipio(m),
                              partes, [m["nome"], m["uf_nome"], "população", "IBGE", "município", "dados públicos"])


def pagina_municipio(m: dict, coleta: dict, catalogo: dict, links: dict | None,
                     revisao: dict | None = None, alterado_em: str | None = None) -> str:
    fontes, metricas = coleta["fontes"], catalogo["metricas"]
    est, censo = fontes["estimativa"], fontes["censo"]
    linhas = [_linha(f"Estimativa {est['periodo']}", m["populacao_estimada"], " placa__linha--principal"),
              _linha("Censo 2022", m["populacao_censo"])]
    faltam = [nome for nome, valor in ((f"A estimativa de {est['periodo']}", m["populacao_estimada"]),
                                       ("O Censo 2022", m["populacao_censo"])) if not valor]
    avisos = "".join(f'<p class="nota">{escape(f)} não traz dado para este município. A ausência não é zero.</p>'
                     for f in faltam)
    extras = []
    # Vale também quando o valor saiu da estimativa: a página passa a mostrar "sem dado" e precisa dizer por quê.
    if revisao:
        avisos += (f'<p class="nota">{escape(texto_revisao(revisao, est["periodo"], m["codigo"]))} '
                   f'<a href="{MANIFESTO_IBGE}">Ver no manifesto</a>.</p>')
        extras.append(f"Revisado pelo IBGE: a mudança foi detectada na coleta de {dia(revisao['detectada_em'])}.")
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
{avisos}
<details class="fonte">
<summary>Fonte e método{SETA}</summary>
{_fonte(metricas['populacao_estimada'], 'populacao_estimada', est, m, links, extras)}
{_fonte(metricas['populacao_censo'], 'populacao_censo', censo, m, links)}
{_fonte_dtb(catalogo['bases']['ibge_dtb'], fontes['dtb'])}
</details>
</main>"""
    descricao = f"{m['nome']} ({m['uf']}): população estimada pelo IBGE e Censo 2022, com fonte e método."
    alterado_em = alterado_em or alteracao_municipio(fontes, revisao)
    return pagina(f"{m['nome']} ({m['uf']}) · {NOME}", descricao, "../../", corpo, rodape(coleta),
                  endereco=f"municipio/{m['codigo']}/", dados=_dados_municipio(m, coleta, catalogo, alterado_em))


def pagina_uf(uf: str, uf_nome: str, municipios: list[dict], coleta: dict, catalogo: dict) -> str:
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
    base, dtb = catalogo["bases"]["ibge_dtb"], coleta["fontes"]["dtb"]
    endereco = f"uf/{uf.lower()}/"
    dados = buscadores.dataset(
        f"Municípios de {uf_nome}",
        f"Lista dos {numero(len(municipios))} municípios de {uf_nome} ({uf}) na Divisão Territorial Brasileira "
        f"{dtb['periodo']} do IBGE, com data-base em {data(dtb['data_base'])}, com o código IBGE e a página de cada um.",
        endereco, buscadores.desde(dtb), buscadores.lugar_uf(municipios[0]["codigo"][:2], uf_nome),
        [buscadores.parte_dtb(base, dtb, uf_nome=uf_nome)], [uf_nome, "municípios", "IBGE", "dados públicos"])
    return pagina(f"{uf_nome} · {NOME}", f"Os {len(municipios)} municípios de {uf_nome}, com dados do IBGE.", "../../",
                  corpo, rodape(coleta), endereco=endereco, dados=dados)


def _dados_brasil(coleta: dict, catalogo: dict) -> dict:
    fontes, metricas, bases = coleta["fontes"], catalogo["metricas"], catalogo["bases"]
    partes = [buscadores.parte_dtb(bases["ibge_dtb"], fontes["dtb"])]
    for chave, fonte in (("populacao_estimada", fontes["estimativa"]), ("populacao_censo", fontes["censo"])):
        partes.append(buscadores.parte_metrica(chave, metricas[chave], bases[metricas[chave]["base"]], fonte))
    n, dtb = len(coleta["municipios"]), fontes["dtb"]
    descricao = (f"Lista dos {numero(n)} municípios do Brasil na Divisão Territorial Brasileira {dtb['periodo']} do IBGE, "
                 f"com a população estimada para {fontes['estimativa']['periodo']} e a do Censo 2022, em Parquet e JSON, "
                 f"com fonte, período de referência e data da coleta de cada número.")
    distribuicao = [
        {"@type": "DataDownload", "contentUrl": projeto.SITE + PARQUET, "encodingFormat": "application/vnd.apache.parquet"},
        {"@type": "DataDownload", "contentUrl": projeto.SITE + "dados/municipios.json", "encodingFormat": "application/json"}]
    alterado_em = max(buscadores.desde(f) for f in fontes.values())
    return buscadores.dataset("Municípios do Brasil: lista e população", descricao, "", alterado_em, buscadores.BRASIL,
                              partes, ["municípios", "população", "IBGE", "Brasil", "dados públicos"], distribuicao)


def pagina_inicial(coleta: dict, catalogo: dict) -> str:
    municipios = coleta["municipios"]
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
    return pagina(NOME, "Dados públicos oficiais de cada município brasileiro, com fonte e método em cada número.", "",
                  corpo, rodape(coleta), script=True, endereco="", dados=_dados_brasil(coleta, catalogo))


def pagina_404(nota: str) -> str:
    # O GitHub Pages serve este arquivo em qualquer pasta, então os caminhos são absolutos a partir do site.
    # Sem link canônico nem JSON-LD: o host responde 404, e a página não é para indexar.
    raiz = projeto.CAMINHO_DO_SITE
    corpo = f"""<header class="placa" id="conteudo"><div class="placa__face">
<h1 class="placa__nome">Página não encontrada</h1>
<p class="placa__lead">O endereço não existe. Os municípios estão na <a href="{raiz}">página inicial</a>, pela busca ou pela lista de estados.</p>
</div></header>"""
    return pagina(f"Página não encontrada · {NOME}", "Página não encontrada.", raiz, corpo, nota)


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


def estimativa_publicada(corpo: bytes) -> dict[str, int]:
    """Estimativa por município no Parquet publicado: a coleta seguinte compara com ela para achar revisões."""
    tabela = pq.read_table(io.BytesIO(corpo), columns=["codigo", "populacao_estimada"]).to_pydict()
    return {c: v for c, v in zip(tabela["codigo"], tabela["populacao_estimada"]) if v is not None}


def construir(coleta: dict, catalogo: dict, saida: Path, links: dict | None = None, execucao: str = "local",
              google: str | None = projeto.GOOGLE_SEARCH_CONSOLE) -> dict:
    if saida.exists():
        shutil.rmtree(saida)
    shutil.copytree(WEB, saida)
    municipios, fontes = coleta["municipios"], coleta["fontes"]

    def gravar(caminho: str, texto: str) -> None:
        destino = saida / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8", newline="\n")

    gravar("index.html", pagina_inicial(coleta, catalogo))
    gravar("404.html", pagina_404(rodape(coleta)))
    enderecos = [("", max(buscadores.desde(f) for f in fontes.values()))]
    por_uf: dict[str, list[dict]] = {}
    por_codigo, geral = revisoes(fontes["estimativa"])
    paginas_municipio = []
    for m in municipios:
        por_uf.setdefault(m["uf"], []).append(m)
        # Sem condição sobre o valor atual: uma estimativa retirada também é revisão, e muda o lastmod.
        revisao = revisao_do_municipio(m["codigo"], por_codigo, geral)
        alterado_em = alteracao_municipio(fontes, revisao)
        gravar(f"municipio/{m['codigo']}/index.html", pagina_municipio(m, coleta, catalogo, links, revisao, alterado_em))
        paginas_municipio.append((f"municipio/{m['codigo']}/", alterado_em))
    for uf, lista in sorted(por_uf.items()):
        gravar(f"uf/{uf.lower()}/index.html", pagina_uf(uf, lista[0]["uf_nome"], lista, coleta, catalogo))
        enderecos.append((f"uf/{uf.lower()}/", buscadores.desde(fontes["dtb"])))
    gravar("sitemap.xml", buscadores.sitemap(enderecos + sorted(paginas_municipio)))
    if google:
        nome, conteudo = buscadores.verificacao_google(google)
        gravar(nome, conteudo)
    gravar("dados/municipios.json", json.dumps([[m["codigo"], m["nome"], m["uf"]] for m in municipios],
                                               ensure_ascii=False, separators=(",", ":")))
    parquet(municipios, saida / PARQUET)
    versao = {"execucao": execucao, "coletado_em": coleta["coletado_em"], "municipios": len(municipios)}
    gravar("versao.json", json.dumps(versao, ensure_ascii=False))
    return versao
