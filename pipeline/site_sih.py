"""Internações do SIH na página de município. Só entra com `construir --sih-local`, num build local.

Enquanto o catálogo disser `publicacao: {site: false}`, nada daqui vai para o site publicado: a opção de
linha de comando lê as partições já suprimidas de uma execução local do pipeline (`trabalho/particoes`),
não muda o catálogo e recusa rodar no CI.

O HTML leva as tabelas, que são a forma acessível dos dados, e um espaço para cada gráfico. O gráfico é
desenhado no navegador a partir da tabela (web/sih.js), na largura da tela, com texto de 12 px. O que a
página mostra, e como:
- célula oculta aparece sempre do mesmo jeito, "oculto", sem motivo nem intervalo, na tabela, no CSV, no
  gráfico (um anel na linha de base) e no PNG;
- contagem de período com mês preliminar aparece arredondada para múltiplo de 5 e marcada como
  "preliminar, arredondado" na tabela e no CSV, e no gráfico com listras sobre a cor cheia da série (o
  contraste de 3:1 com o fundo continua) e a faixa "preliminar";
- cruzamento não publicado num ano aparece como "não publicado", com o motivo, na tabela e no CSV, e fica
  sem marca no gráfico: zero é só a chave ausente de um cruzamento publicado;
- a taxa por mil habitantes usa o valor publicado, arredondado quando ele é, e só aparece em ano completo
  com população do mesmo ano;
- um cruzamento que não passou no critério do ano não aparece naquele ano, e a página diz por quê;
- arquivo de partição que falta é erro do build; linha que falta dentro de um arquivo é zero.
"""
from __future__ import annotations

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
FAIXAS = {"00": "menos de 1 ano", "01-04": "1 a 4 anos", "05-09": "5 a 9 anos", "10-14": "10 a 14 anos",
          "15-19": "15 a 19 anos", "20-29": "20 a 29 anos", "30-39": "30 a 39 anos", "40-49": "40 a 49 anos",
          "50-59": "50 a 59 anos", "60-69": "60 a 69 anos", "70-79": "70 a 79 anos", "80+": "80 anos ou mais",
          "ign": "idade ignorada"}
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
NAO_PUBLICADO = "não publicado"
FORA = {"v": None, "s": NAO_PUBLICADO}
LEGENDA = ('<span class="item"><span class="chave"></span>exato</span><span class="item"><span class="chave chave--prelim">'
           '</span>preliminar, arredondado para múltiplo de 5</span><span class="item"><span class="chave chave--oculta"></span>'
           'oculto pela regra de privacidade</span>')


class ErroSIH(ValueError):
    """As partições locais não servem para montar a página."""


def numero(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def decimal(x: float) -> str:
    return f"{x:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def nome_mes(aaaamm: int | str) -> str:
    """O único formato de mês da seção: "jul/2026"."""
    aaaamm = int(aaaamm)
    return f"{MESES[aaaamm % 100 - 1]}/{aaaamm // 100}"


def dia(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def carregar(pasta: Path, catalogo: dict) -> dict:
    """Partições e situação de cada ano, agrupadas por município.

    Lê `ano=<AAAA>/situacao.json` de cada ano e só os arquivos que ela lista, conferidos um a um
    (sih.ler_situacao): cruzamento dado como publicado sem os arquivos dele para o build com erro claro.
    Ano que não passou no teste de dedução fica de fora.
    """
    from . import sih
    anos_na_pasta = sorted(int(p.name[4:]) for p in Path(pasta).glob("ano=*") if p.is_dir())
    if not anos_na_pasta:
        raise ErroSIH(f"{pasta}: nenhuma pasta ano=<AAAA>; rode antes `python -m pipeline sih`")
    try:
        situacoes = {ano: sih.ler_situacao(pasta, ano) for ano in anos_na_pasta}
    except sih.ErroDeParticao as erro:
        raise ErroSIH(f"Partições locais incompletas: {erro}") from None
    anos = [a for a, s in situacoes.items() if s["deducao"]["rodou"] and s["deducao"]["passou"]
            and s["deducao"]["obitos_passou"]]
    if not anos:
        raise ErroSIH("Nenhum ano das partições locais passou no teste de dedução")
    por_mun = {}
    for cid, geo in TABELAS.items():
        partes = []
        for ano in anos:
            if cid not in situacoes[ano]["publicados"]:
                continue
            for nome in sorted(n for n in situacoes[ano]["arquivos"] if n.startswith(cid + "/")):
                partes.append(pd.read_parquet(Path(pasta) / f"ano={ano}" / nome).assign(ano=ano))
        df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=[geo, "ano"])
        por_mun[cid] = {codigo: grupo for codigo, grupo in df.groupby(geo, sort=False)}
    return {"situacoes": situacoes, "anos": anos, "por_mun": por_mun, "catalogo": catalogo}


# Uma célula da tela: valor publicado (None quando oculto) e situação.

def celula(linha, medida: str = "internacoes") -> dict:
    """Sem linha, a contagem é zero: o arquivo existe (conferido em carregar) e não tem aquela chave."""
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
    if c["v"] is None:
        return NAO_PUBLICADO if c["s"] == NAO_PUBLICADO else OCULTO
    return numero(c["v"])


def td(c: dict) -> str:
    """Célula de tabela com o valor e a situação nos atributos, que o gráfico e o CSV leem. Cruzamento que
    não foi publicado no ano aparece como "não publicado", com o motivo na nota da tabela, e nunca como zero."""
    valor = "" if c["v"] is None else str(c["v"])
    classe = ' class="oculto"' if c["v"] is None else ""
    return f'<td data-v="{valor}" data-s="{escape(c["s"])}"{classe}>{escape(texto(c))}</td>'


def situacao_td(c: dict) -> str:
    return f'<td class="situacao">{escape(c["s"])}</td>'


def figura(id_: str, tipo: str, titulo: str, tabela: str) -> str:
    """Espaço do gráfico, que o navegador desenha a partir da tabela, legenda, exportação e a tabela."""
    return (f'<figure class="sih-figura"><div id="{id_}" class="grafico-sih" data-tipo="{tipo}" data-tabela="{id_}-tab" '
            f'data-titulo="{escape(titulo)}" role="img" aria-label="{escape(titulo)}. Os mesmos valores estão na tabela do gráfico."></div>'
            f'<figcaption class="legenda-sih legenda-sih--{tipo}">{LEGENDA}</figcaption>'
            f'<div class="exportar" hidden><button type="button" data-png="{id_}">Baixar PNG</button>'
            f'<button type="button" data-csv="{id_}-tab">Baixar CSV</button></div>'
            f'<details class="tabela-sih"><summary>Tabela do gráfico</summary><div class="rolagem">{tabela}</div></details></figure>')


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


def ultimo_do_ano(dados: dict, ano: int) -> int:
    return min(ano * 100 + 12, dados["situacoes"][ano]["ultimo_mes"])


def completo(dados: dict, ano: int) -> bool:
    return ultimo_do_ano(dados, ano) == ano * 100 + 12


def rotulo_ano(dados: dict, ano: int) -> str:
    return str(ano) if completo(dados, ano) else f"{ano} (até {nome_mes(ultimo_do_ano(dados, ano))})"


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
    # Zero só vale para chave ausente num cruzamento publicado; no ano em que ele não foi publicado, o motivo.
    fora = {(cid, ano): _nao_publicado(dados, cid, ano) for cid in ("sih_res_ano", "sih_hosp_ano", "sih_res_mes") for ano in anos}
    fora = {chave: motivo for chave, motivo in fora.items() if motivo}
    tem_hospital = bool(hosp) or any(cid == "sih_hosp_ano" for cid, _ in fora)
    linhas_ano = []
    for ano in anos:
        r, h = res.get((str(ano),)), hosp.get((str(ano),))
        res_fora = ("sih_res_ano", ano) in fora
        c_int = FORA if res_fora else celula(r)
        c_ob = FORA if res_fora else (celula(r, "obitos") if r is not None else {"v": 0, "s": ""})
        taxa = "<td>—</td>"
        if res_fora:
            taxa = td(FORA)
        elif completo(dados, ano) and ano in populacao and populacao[ano][0]:
            pop, fonte_pop = populacao[ano]
            if c_int["v"] is None:
                taxa = f'<td data-v="" data-s="{OCULTO}" class="oculto">{OCULTO}</td>'
            else:
                t = 1000 * c_int["v"] / pop
                taxa = f'<td data-v="{t:.1f}" data-s="{escape(c_int["s"])}" title="{escape(fonte_pop)}">{decimal(t)}</td>'
        situacao = c_int["s"] or ("fechado" if not dados["situacoes"][ano]["preliminares"] else "")
        coluna_hosp = (td(FORA if ("sih_hosp_ano", ano) in fora else celula(h))) if tem_hospital else ""
        linhas_ano.append(f'<tr><th scope="row" data-v="{ano}">{escape(rotulo_ano(dados, ano))}</th>{td(c_int)}{taxa}'
                          f'{td(c_ob)}{coluna_hosp}<td class="situacao">{escape(situacao)}</td></tr>')
    primeiro, ultimo = anos[0] * 100 + 1, s_ultimo["ultimo_mes"]
    cab_hosp = '<th scope="col">Internações nos hospitais do município</th>' if tem_hospital else ""
    tabela_ano = (f'<table id="sih-ano-tab" class="tabela" data-csv-nome="internacoes-por-ano">'
                  '<thead><tr><th scope="col">Ano da alta</th><th scope="col">Internações de moradores</th>'
                  '<th scope="col">Por mil habitantes</th><th scope="col">Óbitos de moradores</th>'
                  f'{cab_hosp}<th scope="col">Situação</th></tr></thead>'
                  f'<tbody>{"".join(linhas_ano)}</tbody></table>')
    nomes_fora = {"sih_res_ano": "Moradores por ano", "sih_hosp_ano": "Hospitais do município por ano",
                  "sih_res_mes": "Moradores por mês"}
    nota_fora = "".join(f'<p class="nota-sih"><strong>{escape(nomes_fora[cid])}:</strong> não publicado em {ano}, porque '
                        f'{escape(motivo)}.</p>\n' for (cid, ano), motivo in sorted(fora.items(), key=lambda kv: (kv[0][1], kv[0][0])))
    sem_hospital = ("" if tem_hospital else
                    f'<p class="nota-sih">Nenhuma internação pelo SUS em hospital de {escape(m["nome"])} de '
                    f'{nome_mes(primeiro)} a {nome_mes(ultimo)}. Os moradores foram internados em hospitais de outros municípios.</p>\n')
    # Mensal, com o nível de detalhe conforme o município.
    mensal = _por_chave(_linhas(dados, "sih_res_mes", codigo), ["mes"])
    prelim = {m_ for a in anos for m_ in dados["situacoes"][a]["preliminares"]}
    pontos = []
    for ano in anos:
        for mes in range(ano * 100 + 1, ultimo_do_ano(dados, ano) + 1):
            c = dict(FORA) if ("sih_res_mes", ano) in fora else celula(mensal.get((str(mes),)))
            if c["s"] == "" and str(mes) in prelim:
                c["s"] = "preliminar"
            pontos.append(c | {"rotulo": mes, "prelim": str(mes) in prelim})
    ocultos = sum(1 for p in pontos if p["v"] is None and p["s"] == OCULTO)
    linhas_mes = "".join(f'<tr{" data-p=1" if p["prelim"] else ""}><th scope="row" data-v="{p["rotulo"]}">'
                         f'{nome_mes(p["rotulo"])}</th>{td(p)}{situacao_td(p)}</tr>' for p in pontos)
    tabela_mes = (f'<table id="sih-mes-tab" class="tabela" data-csv-nome="internacoes-por-mes"><thead><tr><th scope="col">Mês da alta</th>'
                  f'<th scope="col">Internações de moradores</th><th scope="col">Situação</th></tr></thead><tbody>{linhas_mes}</tbody></table>')
    fig_mes = figura("sih-mes", "colunas", f"Internações de moradores de {m['nome']} ({m['uf']}) por mês da alta", tabela_mes)
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
    desde = (f"Os meses a partir de {nome_mes(min(prelim))} ainda podem mudar: as contagens deles aparecem arredondadas "
             "para múltiplo de 5.") if prelim else ""
    return f"""<section class="sih" aria-labelledby="sih" data-municipio="{escape(m['nome'])}" data-codigo="{m['codigo']}" data-fonte="Ministério da Saúde/DATASUS, SIH/SUS (AIH Reduzida)" data-coleta="{escape(dia(s_ultimo['coletado_em']))}" data-acesso="{escape(cat['metricas']['internacoes']['fonte']['acesso']['url'])}" data-ressalva="Meses pela data da alta; contagens de período com mês preliminar arredondadas para múltiplo de 5; células ocultas pela regra de privacidade.">
<h2 id="sih">Internações no SUS</h2>
<p class="sih-lead">Internações de moradores de {escape(m['nome'])} em qualquer hospital do país{", e as que aconteceram nos hospitais do município" if tem_hospital else ""}, pela data da alta, de {nome_mes(primeiro)} a {nome_mes(ultimo)}. {desde}</p>
<h3>Por ano da alta</h3>
<div class="rolagem">{tabela_ano}</div>
{nota_fora}{sem_hospital}<p class="nota-sih">A taxa por mil habitantes aparece só em ano completo com população do mesmo ano no site, o Censo 2022 ou a estimativa {escape(est['periodo'])} do IBGE. Num ano em andamento, ela compararia meses com um ano inteiro.</p>
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
    itens = [celula(r) | {"cap": r["capitulo"]} for r in linhas]
    itens.sort(key=lambda i: (i["v"] is None, -(i["v"] or 0), i["cap"]))
    id_ = f"sih-cap-{ano}"
    tabela = (f'<table id="{id_}-tab" class="tabela" data-csv-nome="internacoes-por-capitulo-{ano}"><thead><tr><th scope="col">Capítulo da CID-10</th>'
              '<th scope="col">Internações</th><th scope="col">Situação</th></tr></thead><tbody>'
              + "".join(f'<tr><th scope="row" data-v="{escape(nomes.get(i["cap"], i["cap"]))}" data-curto="{escape(CURTO.get(i["cap"], i["cap"]))}">'
                        f'{escape(nomes.get(i["cap"], i["cap"]))}</th>{td(i)}{situacao_td(i)}</tr>' for i in itens) + "</tbody></table>")
    titulo = f"Internações de moradores de {m['nome']} ({m['uf']}) por capítulo da CID-10, {rotulo_ano(dados, ano)}"
    return '<h5>Por capítulo da CID-10</h5>' + figura(id_, "barras", titulo, tabela)


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
    corpo = "".join(f'<tr><th scope="row" data-v="{escape(FAIXAS[f])}">{escape(FAIXAS[f])}</th>'
                    + "".join(td(cel[(f, s)]) for s in rotulos)
                    + f'<td class="situacao">{escape(_situacao_linha([cel[(f, s)] for s in rotulos]))}</td></tr>' for f in faixas)
    tabela = (f'<table id="{id_}-tab" class="tabela" data-csv-nome="internacoes-por-idade-e-sexo-{ano}"><thead><tr><th scope="col">Faixa etária</th>'
              + "".join(f'<th scope="col" data-serie="{s}">{escape(rotulos[s])}</th>' for s in rotulos)
              + f'<th scope="col">Situação</th></tr></thead><tbody>{corpo}</tbody></table>')
    titulo = f"Internações de moradores de {m['nome']} ({m['uf']}) por faixa etária e sexo, {rotulo_ano(dados, ano)}"
    nota = ('<p class="nota-sih">"Ignorado" reúne os códigos de sexo fora de 1, 2 e 3, como faz o TabWin do DATASUS. '
            'Ele fica na tabela e não no gráfico.</p>')
    return '<h5>Por faixa etária e sexo</h5>' + figura(id_, "piramide", titulo, tabela) + nota


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
<dt>Período de referência</dt><dd>Altas de {nome_mes(dados['anos'][0] * 100 + 1)} a {nome_mes(s['ultimo_mes'])}. Meses fechados até {nome_mes(s['ultimo_mes_fechado'])}: a partir daí, o FTP ainda republica as competências com altas deles.</dd>
<dt>Coleta</dt><dd>Arquivos RD das 27 UFs, na versão de {escape(dia(s['versao_dos_arquivos']))} do FTP do DATASUS, processados em {escape(dia(s['coletado_em']))}.</dd>
<dt>Privacidade</dt><dd>Nenhum número desta seção é de uma pessoa. Contagens de 1 a {regra['k'] - 1} não são publicadas, e outras células são ocultadas junto para que nenhuma possa ser descoberta por subtração, numa tabela, entre tabelas ou entre duas versões do site. Toda célula oculta aparece do mesmo jeito, sem dizer por que foi ocultada nem quanto pode valer. Um teste age como quem tenta deduzir e precisa dar zero antes de cada publicação.</dd>
<dt>Meses preliminares</dt><dd>Enquanto o período tem um mês que ainda pode mudar, cada contagem visível aparece arredondada para múltiplo de {multiplo} e marcada como preliminar e arredondada: assim, a diferença entre uma versão e a seguinte não revela grupos pequenos de internações. Zero continua zero. A taxa por mil habitantes usa o valor arredondado. Quando o mês fecha, o valor passa a exato.</dd>
<dt>Não publicado</dt><dd>{f"<ul>{''.join(fora)}</ul>" if fora else "Todos os cruzamentos passaram no critério em todos os anos."} O critério: no máximo {regra['criterio_publicacao']['internacoes_ocultas_pct_max']}% das internações e {regra['criterio_publicacao']['celulas_ocultas_pct_max']}% das células da tabela ocultas, e zero no teste de dedução. Num ano em andamento, o que foi publicado na primeira versão daquele ano continua até o ano fechar, e só o teste de dedução tira algum cruzamento.</dd>
<dt>Sexo ignorado</dt><dd>{escape(sexo4['tratamento'])} {escape(sexo4['visto'])}</dd>
<dt>Ressalvas</dt><dd><ul>{ressalvas}</ul></dd>
</dl>
</section>"""
