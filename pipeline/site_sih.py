"""Internações do SIH na página de município. Só entra com `construir --sih-local`, num build local.

Enquanto o catálogo disser `publicacao: {site: false}`, nada daqui vai para o site publicado: a opção de
linha de comando lê as partições já suprimidas de uma execução local do pipeline (`trabalho/particoes`),
não muda o catálogo e recusa rodar no CI.

O que a página mostra, e como:
- célula oculta aparece sempre do mesmo jeito, "oculto", sem motivo nem intervalo, no gráfico (um anel na
  linha de base), na tabela, no CSV e no PNG;
- contagem de período com mês preliminar aparece arredondada para múltiplo de 5 e marcada como
  "preliminar, arredondado" na tabela e no CSV, e com o tom claro e a faixa "preliminar" no gráfico;
- a taxa por mil habitantes usa o valor publicado, arredondado quando ele é;
- um cruzamento que não passou no critério do ano não aparece naquele ano, e a página diz por quê.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd

TABELAS = {"sih_res_ano": "mun_res", "sih_hosp_ano": "mun_hosp", "sih_res_mes": "mun_res",
           "sih_res_ano_capitulo": "mun_res", "sih_res_ano_faixa12_sexo": "mun_res"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
CURTO = {"00": "Sem capítulo", "01": "Infecciosas", "02": "Neoplasias", "03": "Sangue e imunidade", "04": "Endócrinas",
         "05": "Mentais", "06": "Sistema nervoso", "07": "Olho", "08": "Ouvido", "09": "Circulatório", "10": "Respiratório",
         "11": "Digestivo", "12": "Pele", "13": "Osteomuscular", "14": "Geniturinário", "15": "Gravidez e parto",
         "16": "Perinatal", "17": "Malformações", "18": "Sintomas e achados", "19": "Lesões e envenenamentos",
         "20": "Causas externas", "21": "Contato com serviços", "22": "Propósitos especiais"}
NOMES_CRUZAMENTO = {
    "sih_res_ano": "Moradores por ano", "sih_hosp_ano": "Hospitais do município por ano",
    "sih_res_mes": "Moradores por mês", "sih_hosp_mes": "Hospitais do município por mês",
    "sih_res_mes_sexo": "Moradores por mês e sexo", "sih_res_mes_urgencia": "Moradores por mês e urgência",
    "sih_res_mes_faixa5": "Moradores por mês e faixa etária", "sih_res_ano_capitulo": "Moradores por capítulo da CID",
    "sih_res_ano_faixa12_sexo": "Moradores por faixa etária e sexo", "sih_res_ano_raca": "Moradores por cor ou raça",
    "sih_res_tri_capitulo": "Moradores por trimestre e capítulo da CID",
    "sih_hosp_ano_especialidade": "Hospitais do município por especialidade do leito",
    "sih_hosp_tri_capitulo": "Hospitais do município por trimestre e capítulo da CID",
    "sih_hosp_mes_carater": "Hospitais do município por mês e caráter da internação"}
OCULTO = "oculto"
ARREDONDADO = "preliminar, arredondado"


class ErroSIH(ValueError):
    """As partições locais não servem para montar a página."""


def numero(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def decimal(x: float) -> str:
    return f"{x:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def nome_mes(aaaamm: int | str) -> str:
    aaaamm = int(aaaamm)
    return f"{MESES[aaaamm % 100 - 1]}/{aaaamm // 100}"


def carregar(pasta: Path, catalogo: dict) -> dict:
    """Partições e situação de cada ano, agrupadas por município. Ano que não passou no teste fica de fora."""
    situacoes = {}
    for arquivo in sorted(Path(pasta).glob("situacao_*.json")):
        s = json.loads(arquivo.read_text(encoding="utf-8"))
        situacoes[int(s["ano"])] = s
    if not situacoes:
        raise ErroSIH(f"{pasta}: nenhum situacao_<ano>.json; rode antes `python -m pipeline sih`")
    anos = [a for a, s in sorted(situacoes.items()) if s["deducao"]["rodou"] and s["deducao"]["passou"]
            and s["deducao"]["obitos_passou"]]
    if not anos:
        raise ErroSIH("Nenhum ano das partições locais passou no teste de dedução")
    por_mun = {}
    for cid, geo in TABELAS.items():
        partes = []
        for ano in anos:
            if cid not in situacoes[ano]["publicados"]:
                continue
            for arquivo in sorted((Path(pasta) / cid).glob(f"uf=*/ano={ano}.parquet")):
                partes.append(pd.read_parquet(arquivo).assign(ano=ano))
        df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=[geo, "ano"])
        por_mun[cid] = {codigo: grupo for codigo, grupo in df.groupby(geo, sort=False)}
    return {"situacoes": situacoes, "anos": anos, "por_mun": por_mun, "catalogo": catalogo}


# Uma célula da tela: valor publicado (None quando oculto) e situação.

def celula(linha, medida: str = "internacoes") -> dict:
    if linha is None:
        return {"v": 0, "s": ""}
    oculto = bool(linha["obitos_oculto"] if medida == "obitos" else linha["oculto"])
    if oculto:
        return {"v": None, "s": OCULTO}
    arred = bool(linha["obitos_arredondado"] if medida == "obitos" else linha["arredondado"])
    if arred:
        return {"v": int(linha[medida]), "s": ARREDONDADO}
    return {"v": int(linha[medida]), "s": "preliminar" if bool(linha["preliminar"]) else ""}


def texto(c: dict) -> str:
    return OCULTO if c["v"] is None else numero(c["v"])


def td(c: dict, extra: str = "") -> str:
    """Célula de tabela com o valor e a situação nos atributos, que o CSV lê."""
    valor = "" if c["v"] is None else str(c["v"])
    classe = ' class="oculto"' if c["v"] is None else ""
    return f'<td data-v="{valor}" data-s="{escape(c["s"])}"{classe}>{escape(texto(c))}{extra}</td>'


def situacao_td(c: dict) -> str:
    return f'<td class="situacao">{escape(c["s"])}</td>'


# Gráficos em SVG. As cores vêm do CSS (classes); o PNG copia os estilos calculados antes de desenhar.

def _escala(maximo: int) -> tuple[int, list[int]]:
    """Topo e marcas do eixo, em números redondos."""
    if maximo <= 0:
        return 5, [0, 5]
    bruto = maximo / 4
    potencia = 10 ** (len(str(int(bruto))) - 1)
    passo = next(p * potencia for p in (1, 2, 2.5, 5, 10) if p * potencia >= bruto)
    passo = max(1, int(passo))
    topo = passo * -(-maximo // passo)
    return topo, list(range(0, topo + 1, passo))


def _marca(n: int) -> str:
    return numero(n) if n < 10000 else f"{n / 1000:g}".replace(".", ",") + " mil"


def grafico_mensal(id_: str, titulo: str, pontos: list[dict]) -> str:
    """Colunas por mês. `pontos`: rotulo (AAAAMM), v (None se oculto), s (situação)."""
    larg, alt, esq, base, topo_y = 760, 230, 52, 196, 16
    n = len(pontos)
    passo = (larg - esq - 8) / max(n, 1)
    coluna = max(2.0, min(24.0, passo - 2))
    valores = [p["v"] for p in pontos if p["v"]]
    topo, marcas = _escala(max(valores) if valores else 0)
    y = lambda v: base - (base - topo_y) * v / topo
    partes = [f'<svg id="{id_}" class="grafico" viewBox="0 0 {larg} {alt}" role="img" aria-labelledby="{id_}-t" '
              f'data-titulo="{escape(titulo)}"><title id="{id_}-t">{escape(titulo)}</title>']
    for m in marcas:
        partes.append(f'<line class="grade" x1="{esq}" x2="{larg - 4}" y1="{y(m):.1f}" y2="{y(m):.1f}"/>'
                      f'<text class="eixo" x="{esq - 6}" y="{y(m) + 4:.1f}" text-anchor="end">{_marca(m)}</text>')
    prelim = [i for i, p in enumerate(pontos) if p["s"] in (ARREDONDADO, "preliminar") or (p["v"] is None and p.get("prelim"))]
    if prelim:
        x0, x1 = esq + prelim[0] * passo, esq + (prelim[-1] + 1) * passo
        partes.append(f'<rect class="faixa" x="{x0:.1f}" y="{topo_y - 12}" width="{x1 - x0:.1f}" height="{base - topo_y + 12}"/>'
                      f'<text class="eixo" x="{x0 + 4:.1f}" y="{topo_y - 2}">preliminar</text>')
    for i, p in enumerate(pontos):
        x = esq + i * passo + (passo - coluna) / 2
        dica = f'{nome_mes(p["rotulo"])}: {texto(p)}' + (f' ({p["s"]})' if p["s"] else "")
        if p["v"] is None:
            partes.append(f'<circle class="oculta" cx="{x + coluna / 2:.1f}" cy="{base - 5}" r="4" data-tip="{escape(dica)}"/>')
        elif p["v"]:
            h = base - y(p["v"])
            classe = "barra barra--prelim" if p["s"] == ARREDONDADO else "barra"
            raio = min(4, coluna / 2, h)
            partes.append(f'<path class="{classe}" d="M{x:.1f},{base} v{-(h - raio):.1f} q0,{-raio:.1f} {raio:.1f},{-raio:.1f} '
                          f'h{coluna - 2 * raio:.1f} q{raio:.1f},0 {raio:.1f},{raio:.1f} v{h - raio:.1f} z" data-tip="{escape(dica)}"/>')
        if int(p["rotulo"]) % 100 == 1:
            partes.append(f'<text class="eixo" x="{esq + i * passo:.1f}" y="{base + 18}">{int(p["rotulo"]) // 100}</text>')
    partes.append(f'<line class="base" x1="{esq}" x2="{larg - 4}" y1="{base}" y2="{base}"/></svg>')
    return "".join(partes)


def grafico_barras(id_: str, titulo: str, itens: list[dict]) -> str:
    """Barras horizontais. `itens`: rotulo, v (None se oculto), s."""
    larg, linha, esq = 560, 24, 172
    alt = linha * len(itens) + 10
    visiveis = [i["v"] for i in itens if i["v"]]
    topo = max(visiveis) if visiveis else 1
    util = larg - esq - 70
    partes = [f'<svg id="{id_}" class="grafico grafico--estreito" viewBox="0 0 {larg} {alt}" role="img" aria-labelledby="{id_}-t" '
              f'data-titulo="{escape(titulo)}"><title id="{id_}-t">{escape(titulo)}</title>']
    for k, item in enumerate(itens):
        y = 6 + k * linha
        dica = f'{item["rotulo"]}: {texto(item)}' + (f' ({item["s"]})' if item["s"] else "")
        partes.append(f'<text class="rotulo" x="{esq - 8}" y="{y + 15}" text-anchor="end">{escape(item["rotulo"])}</text>')
        if item["v"] is None:
            partes.append(f'<circle class="oculta" cx="{esq + 5}" cy="{y + 10}" r="4" data-tip="{escape(dica)}"/>'
                          f'<text class="valor" x="{esq + 16}" y="{y + 15}">{OCULTO}</text>')
            continue
        w = max(1.0, util * item["v"] / topo) if item["v"] else 0
        classe = "barra barra--prelim" if item["s"] == ARREDONDADO else "barra"
        if w:
            raio = min(4, w)
            partes.append(f'<path class="{classe}" d="M{esq},{y + 2} h{w - raio:.1f} q{raio},0 {raio},{raio} v{16 - 2 * raio} '
                          f'q0,{raio} {-raio},{raio} h{-(w - raio):.1f} z" data-tip="{escape(dica)}"/>')
        partes.append(f'<text class="valor" x="{esq + w + 6:.1f}" y="{y + 15}">{numero(item["v"])}</text>')
    partes.append(f'<line class="base" x1="{esq}" x2="{esq}" y1="2" y2="{alt - 2}"/></svg>')
    return "".join(partes)


def grafico_piramide(id_: str, titulo: str, faixas: list[str], homens: list[dict], mulheres: list[dict]) -> str:
    """Pirâmide: homens à esquerda, mulheres à direita, uma linha por faixa etária."""
    larg, linha, meio, cab, calha = 560, 22, 280, 26, 62
    alt = cab + linha * len(faixas) + 8
    visiveis = [c["v"] for c in homens + mulheres if c["v"]]
    topo = max(visiveis) if visiveis else 1
    util = meio - calha - 8
    partes = [f'<svg id="{id_}" class="grafico grafico--estreito" viewBox="0 0 {larg} {alt}" role="img" aria-labelledby="{id_}-t" '
              f'data-titulo="{escape(titulo)}"><title id="{id_}-t">{escape(titulo)}</title>'
              f'<rect class="serie-1" x="{meio - 96}" y="6" width="10" height="10" rx="2"/>'
              f'<text class="rotulo" x="{meio - 82}" y="15">Masculino</text>'
              f'<rect class="serie-2" x="{meio + 24}" y="6" width="10" height="10" rx="2"/>'
              f'<text class="rotulo" x="{meio + 38}" y="15">Feminino</text>']
    for k, faixa in enumerate(faixas):
        y = cab + k * linha
        partes.append(f'<text class="eixo" x="{meio}" y="{y + 14}" text-anchor="middle">{escape(faixa)}</text>')
        for c, lado, serie in ((homens[k], -1, "serie-1"), (mulheres[k], 1, "serie-2")):
            inicio = meio + lado * calha
            dica = f'{faixa}, {"masculino" if lado < 0 else "feminino"}: {texto(c)}' + (f' ({c["s"]})' if c["s"] else "")
            if c["v"] is None:
                partes.append(f'<circle class="oculta" cx="{inicio + lado * 6}" cy="{y + 10}" r="4" data-tip="{escape(dica)}"/>')
                continue
            w = util * c["v"] / topo if c["v"] else 0
            if w:
                x = inicio if lado > 0 else inicio - w
                classe = serie + (" barra--prelim" if c["s"] == ARREDONDADO else "")
                partes.append(f'<rect class="{classe}" x="{x:.1f}" y="{y + 3}" width="{w:.1f}" height="15" rx="3" data-tip="{escape(dica)}"/>')
    partes.append("</svg>")
    return "".join(partes)


def figura(id_: str, svg: str, legenda: str, tabela: str, aberto: bool = False) -> str:
    """Gráfico, legenda do que cada marca quer dizer, botões de exportação e a tabela equivalente."""
    return (f'<figure class="sih-figura">{svg}<figcaption class="legenda-sih">{legenda}</figcaption>'
            f'<div class="exportar" hidden><button type="button" data-png="{id_}">Baixar PNG</button>'
            f'<button type="button" data-csv="{id_}-tab">Baixar CSV</button></div>'
            f'<details class="tabela-sih"{" open" if aberto else ""}><summary>Tabela do gráfico</summary>'
            f'<div class="rolagem">{tabela}</div></details></figure>')


LEGENDA = ('<span class="chave chave--barra"></span> exato <span class="chave chave--prelim"></span> preliminar, '
           'arredondado para múltiplo de 5 <span class="chave chave--oculta"></span> oculto pela regra de privacidade')


def _linhas(dados: dict, cid: str, codigo: str) -> pd.DataFrame | None:
    return dados["por_mun"][cid].get(codigo)


def _por_chave(df: pd.DataFrame | None, colunas: list[str]) -> dict:
    if df is None:
        return {}
    return {tuple(str(x) for x in chave): linha for chave, linha in zip(df[colunas].itertuples(index=False), df.to_dict("records"))}


def _nao_publicado(dados: dict, cid: str, ano: int) -> str | None:
    s = dados["situacoes"].get(ano)
    if s is None or ano not in dados["anos"]:
        return "o ano não passou no teste de dedução"
    if cid in s["nao_publicados"]:
        return s["nao_publicados"][cid]["motivo"]
    return None


def rotulo_ano(dados: dict, ano: int) -> str:
    ultimo = dados["situacoes"][ano]["ultimo_mes"]
    return f"{ano} (jan. a {MESES[ultimo % 100 - 1]}.)" if ultimo // 100 == ano and ultimo % 100 < 12 else str(ano)


def secao(m: dict, dados: dict, coleta: dict) -> str:
    """A seção de internações da página do município."""
    codigo, anos = m["codigo"], dados["anos"]
    cat = dados["catalogo"]
    s_ultimo = dados["situacoes"][anos[-1]]
    est = coleta["fontes"]["estimativa"]
    populacao = {2022: (m.get("populacao_censo"), "Censo 2022")}
    if m.get("populacao_estimada"):
        populacao[int(est["periodo"])] = (m["populacao_estimada"], f"estimativa {est['periodo']}")
    res = _por_chave(_linhas(dados, "sih_res_ano", codigo), ["ano"])
    hosp = _por_chave(_linhas(dados, "sih_hosp_ano", codigo), ["ano"])
    linhas_ano, pontos_ano = [], []
    for ano in anos:
        r, h = res.get((str(ano),)), hosp.get((str(ano),))
        c_int, c_ob, c_h = celula(r), celula(r, "obitos") if r is not None else {"v": 0, "s": ""}, celula(h)
        taxa = "<td>—</td>"
        if ano in populacao and populacao[ano][0]:
            pop, fonte_pop = populacao[ano]
            if c_int["v"] is None:
                taxa = f'<td data-v="" data-s="{OCULTO}" class="oculto">{OCULTO}</td>'
            else:
                t = 1000 * c_int["v"] / pop
                taxa = (f'<td data-v="{t:.1f}" data-s="{escape(c_int["s"])}" title="{escape(fonte_pop)}">{decimal(t)}</td>')
        situacao = c_int["s"] or ("fechado" if not dados["situacoes"][ano]["preliminares"] else "")
        linhas_ano.append(f'<tr><th scope="row" data-v="{ano}">{escape(rotulo_ano(dados, ano))}</th>{td(c_int)}{taxa}'
                          f'{td(c_ob)}{td(c_h)}<td class="situacao">{escape(situacao)}</td></tr>')
        pontos_ano.append(c_int)
    tabela_ano = (f'<table id="sih-ano-tab" class="tabela" data-csv-nome="internacoes-por-ano">'
                  '<thead><tr><th scope="col">Ano da alta</th><th scope="col">Internações de moradores</th>'
                  '<th scope="col">Por mil habitantes</th><th scope="col">Óbitos de moradores</th>'
                  '<th scope="col">Internações nos hospitais do município</th><th scope="col">Situação</th></tr></thead>'
                  f'<tbody>{"".join(linhas_ano)}</tbody></table>')
    # Mensal, com o nível de detalhe conforme o município.
    mensal = _por_chave(_linhas(dados, "sih_res_mes", codigo), ["mes"])
    prelim = {m_ for a in anos for m_ in dados["situacoes"][a]["preliminares"]}
    pontos = []
    for ano in anos:
        ultimo = min(ano * 100 + 12, dados["situacoes"][ano]["ultimo_mes"])
        for mes in range(ano * 100 + 1, ultimo + 1):
            c = celula(mensal.get((str(mes),)))
            if c["s"] == "" and str(mes) in prelim:
                c["s"] = "preliminar"
            pontos.append(c | {"rotulo": mes, "prelim": str(mes) in prelim})
    ocultos = sum(1 for p in pontos if p["v"] is None)
    linhas_mes = "".join(f'<tr><th scope="row" data-v="{p["rotulo"]}">{nome_mes(p["rotulo"])}</th>{td(p)}{situacao_td(p)}</tr>'
                         for p in pontos)
    tabela_mes = (f'<table id="sih-mes-tab" class="tabela" data-csv-nome="internacoes-por-mes"><thead><tr><th scope="col">Mês da alta</th>'
                  f'<th scope="col">Internações de moradores</th><th scope="col">Situação</th></tr></thead><tbody>{linhas_mes}</tbody></table>')
    titulo_mes = f"Internações de moradores de {m['nome']} ({m['uf']}) por mês da alta"
    fig_mes = figura("sih-mes", grafico_mensal("sih-mes", titulo_mes, pontos), LEGENDA, tabela_mes)
    if pontos and ocultos * 2 >= len(pontos):
        bloco_mes = (f'<details class="detalhe"><summary>Ver por mês</summary><p class="nota-sih">Neste município, '
                     f'{ocultos} de {len(pontos)} meses estão ocultos pela regra de privacidade, por isso a página '
                     f'abre no total do ano.</p>{fig_mes}</details>')
    else:
        bloco_mes = f'<h3>Por mês da alta</h3>{fig_mes}'
    # Detalhe dos dois últimos anos: capítulo da CID e faixa etária por sexo.
    paineis, opcoes = [], []
    for ano in anos[-2:][::-1]:
        conteudo = [_painel_capitulo(dados, codigo, ano, m, cat), _painel_piramide(dados, codigo, ano, m, cat)]
        paineis.append(f'<div class="painel" data-ano="{ano}"><h4>{escape(rotulo_ano(dados, ano))}</h4>{"".join(conteudo)}</div>')
        opcoes.append(f'<label><input type="radio" name="sih-ano" value="{ano}"{" checked" if not opcoes else ""}> '
                      f'{escape(rotulo_ano(dados, ano))}</label>')
    ultimo = s_ultimo["ultimo_mes"]
    return f"""<section class="sih" aria-labelledby="sih" data-municipio="{escape(m['nome'])}" data-codigo="{m['codigo']}" data-fonte="Ministério da Saúde/DATASUS, SIH/SUS (AIH Reduzida)" data-coleta="{escape(s_ultimo['coletado_em'])}" data-acesso="{escape(cat['metricas']['internacoes']['fonte']['acesso']['url'])}" data-ressalva="Meses pela data da alta; contagens de período com mês preliminar arredondadas para múltiplo de 5; células ocultas pela regra de privacidade.">
<h2 id="sih">Internações no SUS</h2>
<p class="sih-lead">Internações de moradores de {escape(m['nome'])} em qualquer hospital do país, e as que aconteceram nos hospitais do município, pela data da alta, de janeiro de {anos[0]} a {MESES[ultimo % 100 - 1]} de {ultimo // 100}. Os meses a partir de {nome_mes(min(prelim)) if prelim else "—"} ainda podem mudar: as contagens deles aparecem arredondadas para múltiplo de 5, e a taxa usa esse valor.</p>
<h3>Por ano da alta</h3>
<div class="rolagem">{tabela_ano}</div>
<p class="nota-sih">A taxa por mil habitantes só aparece nos anos com população do mesmo ano no site: o Censo 2022 e a estimativa {escape(est['periodo'])} do IBGE.</p>
<div class="exportar" hidden><button type="button" data-csv="sih-ano-tab">Baixar CSV</button></div>
{bloco_mes}
<h3>Diagnóstico, idade e sexo</h3>
<fieldset class="anos" hidden><legend>Ano</legend>{"".join(opcoes)}</fieldset>
{"".join(paineis)}
</section>"""


def _painel_capitulo(dados: dict, codigo: str, ano: int, m: dict, cat: dict) -> str:
    motivo = _nao_publicado(dados, "sih_res_ano_capitulo", ano)
    if motivo:
        return f'<p class="nota-sih"><strong>Por capítulo da CID:</strong> não publicado em {ano}, porque {escape(motivo)}.</p>'
    nomes = {f"{n:02d}": nome for n, _, _, nome in cat["referencias"]["cid10_capitulos"]["faixas"]}
    nomes["00"] = "Sem capítulo na tabela CID-10 de 2008"
    df = _linhas(dados, "sih_res_ano_capitulo", codigo)
    linhas = [] if df is None else [r for r in df.to_dict("records") if r["ano"] == ano]
    if not linhas:
        return '<p class="nota-sih"><strong>Por capítulo da CID:</strong> nenhuma internação de morador no ano.</p>'
    itens = [celula(r) | {"rotulo": CURTO.get(r["capitulo"], r["capitulo"]), "cap": r["capitulo"]} for r in linhas]
    itens.sort(key=lambda i: (i["v"] is None, -(i["v"] or 0), i["cap"]))
    id_ = f"sih-cap-{ano}"
    tabela = (f'<table id="{id_}-tab" class="tabela" data-csv-nome="internacoes-por-capitulo-{ano}"><thead><tr><th scope="col">Capítulo da CID-10</th>'
              '<th scope="col">Internações</th><th scope="col">Situação</th></tr></thead><tbody>'
              + "".join(f'<tr><th scope="row" data-v="{escape(nomes.get(i["cap"], i["cap"]))}">{escape(nomes.get(i["cap"], i["cap"]))}</th>'
                        f'{td(i)}{situacao_td(i)}</tr>' for i in itens) + "</tbody></table>")
    titulo = f"Internações de moradores de {m['nome']} ({m['uf']}) por capítulo da CID-10, {rotulo_ano(dados, ano)}"
    return f'<h5>Por capítulo da CID-10</h5>' + figura(id_, grafico_barras(id_, titulo, itens), LEGENDA, tabela)


FAIXAS = {"00": "menos de 1 ano", "01-04": "1 a 4 anos", "05-09": "5 a 9 anos", "10-14": "10 a 14 anos",
          "15-19": "15 a 19 anos", "20-29": "20 a 29 anos", "30-39": "30 a 39 anos", "40-49": "40 a 49 anos",
          "50-59": "50 a 59 anos", "60-69": "60 a 69 anos", "70-79": "70 a 79 anos", "80+": "80 anos ou mais",
          "ign": "idade ignorada"}


def _painel_piramide(dados: dict, codigo: str, ano: int, m: dict, cat: dict) -> str:
    motivo = _nao_publicado(dados, "sih_res_ano_faixa12_sexo", ano)
    if motivo:
        return f'<p class="nota-sih"><strong>Por faixa etária e sexo:</strong> não publicado em {ano}, porque {escape(motivo)}.</p>'
    df = _linhas(dados, "sih_res_ano_faixa12_sexo", codigo)
    linhas = {} if df is None else {(r["faixa12"], r["sexo"]): r for r in df.to_dict("records") if r["ano"] == ano}
    if not linhas:
        return '<p class="nota-sih"><strong>Por faixa etária e sexo:</strong> nenhuma internação de morador no ano.</p>'
    rotulos = cat["dimensoes"]["sexo"]["rotulos"]
    faixas = [f for f in FAIXAS if any((f, s) in linhas for s in rotulos)]
    cel = {(f, s): celula(linhas.get((f, s))) for f in faixas for s in rotulos}
    id_ = f"sih-idade-{ano}"
    nome_faixa = FAIXAS.get
    corpo = "".join(f'<tr><th scope="row" data-v="{escape(nome_faixa(f))}">{escape(nome_faixa(f))}</th>'
                    + "".join(td(cel[(f, s)]) for s in rotulos)
                    + f'<td class="situacao">{escape(_situacao_linha([cel[(f, s)] for s in rotulos]))}</td></tr>' for f in faixas)
    tabela = (f'<table id="{id_}-tab" class="tabela" data-csv-nome="internacoes-por-idade-e-sexo-{ano}"><thead><tr><th scope="col">Faixa etária</th>'
              + "".join(f'<th scope="col">{escape(rotulos[s])}</th>' for s in rotulos)
              + f'<th scope="col">Situação</th></tr></thead><tbody>{corpo}</tbody></table>')
    titulo = f"Internações de moradores de {m['nome']} ({m['uf']}) por faixa etária e sexo, {rotulo_ano(dados, ano)}"
    piramide = grafico_piramide(id_, titulo, [nome_faixa(f) for f in faixas], [cel[(f, "M")] for f in faixas],
                                [cel[(f, "F")] for f in faixas])
    nota = ('<p class="nota-sih">"Ignorado" reúne os códigos de sexo fora de 1, 2 e 3, como faz o TabWin do DATASUS. '
            'Ele fica na tabela e não no gráfico.</p>')
    return '<h5>Por faixa etária e sexo</h5>' + figura(id_, piramide, LEGENDA, tabela) + nota


def _situacao_linha(celulas: list[dict]) -> str:
    estados = {c["s"] for c in celulas if c["s"]}
    return ", ".join(sorted(estados))


def fonte(dados: dict, coleta: dict) -> str:
    """Bloco do SIH no painel "Fonte e método": de onde vem, como conferir, a regra de privacidade e o que
    não foi publicado em cada ano, com o motivo."""
    cat = dados["catalogo"]
    base, met = cat["bases"]["sih"], cat["metricas"]["internacoes"]
    s = dados["situacoes"][dados["anos"][-1]]
    regra = base["supressao"]
    multiplo = base["preliminares"]["arredondar_multiplo"]
    fechado = s["ultimo_mes_fechado"]
    fora = []
    for ano, sit in sorted(dados["situacoes"].items()):
        if ano not in dados["anos"]:
            fora.append(f"<li>{ano}: o ano inteiro, porque não passou no teste de dedução.</li>")
            continue
        for cid, motivo in sit["nao_publicados"].items():
            fora.append(f"<li>{ano}, {escape(NOMES_CRUZAMENTO.get(cid, cid).lower())}: {escape(motivo['motivo'])}.</li>")
    ressalvas = "".join(f"<li>{escape(r)}</li>" for r in [*base["ressalvas"], *met["ressalvas"]])
    sexo4 = cat["dimensoes"]["sexo"]["fora_do_dicionario"]["4"]
    return f"""<section class="fonte__bloco" aria-labelledby="f-sih">
<h3 id="f-sih">Internações no SUS</h3>
<dl class="ficha">
<dt>Órgão e pesquisa</dt><dd>{escape(met['fonte']['orgao'])}, {escape(met['fonte']['pesquisa'])}. {escape(met['regra'])}.</dd>
<dt>Acesso</dt><dd>Não há link para o resultado. No <a href="{escape(met['fonte']['acesso']['url'])}">TabNet</a>: {escape(met['fonte']['acesso']['receita'])}. O TabNet organiza os meses pela data de internação, e esta página pela data da alta: os meses não coincidem, mas o total das competências do ano confere.</dd>
<dt>Período de referência</dt><dd>Altas de janeiro de {dados['anos'][0]} a {nome_mes(s['ultimo_mes'])}. Meses fechados até {nome_mes(fechado)}: a partir daí, o FTP ainda republica as competências com altas deles.</dd>
<dt>Coleta</dt><dd>Arquivos RD das 27 UFs, na versão de {escape(s['versao_dos_arquivos'][8:10])}/{escape(s['versao_dos_arquivos'][5:7])}/{escape(s['versao_dos_arquivos'][:4])} do FTP do DATASUS, processados em {escape(s['coletado_em'][8:10])}/{escape(s['coletado_em'][5:7])}/{escape(s['coletado_em'][:4])}.</dd>
<dt>Privacidade</dt><dd>Nenhum número desta seção é de uma pessoa. Contagens de 1 a {regra['k'] - 1} não são publicadas, e outras células são ocultadas junto para que nenhuma possa ser descoberta por subtração, numa tabela, entre tabelas ou entre duas versões do site. Toda célula oculta aparece do mesmo jeito, sem dizer por que foi ocultada nem quanto pode valer. Um teste age como quem tenta deduzir e precisa dar zero antes de cada publicação.</dd>
<dt>Meses preliminares</dt><dd>Enquanto o período tem um mês que ainda pode mudar, cada contagem visível aparece arredondada para múltiplo de {multiplo} e marcada como preliminar e arredondada: assim, a diferença entre uma versão e a seguinte não revela grupos pequenos de internações. Zero continua zero. A taxa por mil habitantes usa o valor arredondado. Quando o mês fecha, o valor passa a exato.</dd>
<dt>Não publicado</dt><dd>{f"<ul>{''.join(fora)}</ul>" if fora else "Todos os cruzamentos passaram no critério em todos os anos."} O critério: no máximo {regra['criterio_publicacao']['internacoes_ocultas_pct_max']}% das internações e {regra['criterio_publicacao']['celulas_ocultas_pct_max']}% das células da tabela ocultas, e zero no teste de dedução.</dd>
<dt>Sexo ignorado</dt><dd>{escape(sexo4['tratamento'])} {escape(sexo4['visto'])}</dd>
<dt>Ressalvas</dt><dd><ul>{ressalvas}</ul></dd>
</dl>
</section>"""
