"""Superfície pública do SIH: exatamente as células que o site mostra, e o arquivo da versão no ar.

Decidido em 10/11/2026: o SIH publicado é só o que as páginas de município mostram, e o CSV que sai delas.
Nenhum Parquet do SIH vai para o site nem para Releases; as partições ficam no runner. A superfície de um
ano são os cruzamentos de `bases.sih.superficie`, nas medidas que a página mostra (óbitos só no total anual
por residência), e os de detalhe nos anos mais novos publicados (`anos_recentes`), como na página. O detalhe
que a versão no ar já mostrava de um ano continua publicado quando o ano sai dos mais novos (detalhe_mantido).

A página é desenhada a partir da superfície (site_sih.carregar), e a superfície sai das mesmas tabelas que
vão para as partições (sih.tabelas_publicaveis): o que a tela mostra e o que o arquivo guarda não têm como
divergir. O arquivo, publicado com o site, é a versão no ar: é dele que a versão seguinte lê a herança do
padrão, a situação de cada ano e o que entra no ataque conjunto.

O arquivo é um Parquet só, com uma linha por célula da tela e a situação de cada ano nos metadados (o que foi
publicado, o que não foi e por quê, os testes, os meses preliminares e o múltiplo do arredondamento). Os
metadados também guardam o SHA-256 do conteúdo, que quem lê confere célula por célula, e com que regras a versão
foi calculada (`calculo`: o SHA-256 das regras do SIH no catálogo e o número do algoritmo de supressão), que
decide se a versão seguinte pode reaproveitar dela os anos fechados (sih_reaproveitamento).

Baixar e conferir o arquivo só precisa do pyarrow (requirements.txt): o Publicar faz isso antes de instalar as
dependências do SIH.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from . import projeto, rede, sih_particoes
from .contrato import ErroDeContrato

FORMATO = 1
METADADOS = b"sih_superficie"
ARQUIVO = "superficie.parquet"
CONSULTA = "consulta.json"
# Por medida, as colunas que a página lê: a contagem, a marca de oculta e a de arredondada.
COLUNAS = {"internacoes": ("internacoes", "oculto", "arredondado"),
           "obitos": ("obitos", "obitos_oculto", "obitos_arredondado")}
TEMPO = {"mes": ["mes"], "tri": ["tri"], "ano": []}
# O que `calculo` registra: o SHA-256 das regras do SIH no catálogo e o número do algoritmo de supressão.
CALCULO = ("regras_sha256", "algoritmo_de_supressao")


class ErroDeSuperficie(ErroDeContrato):
    """A superfície não pode ser montada, lida ou conferida."""


@dataclass
class Superficie:
    """`anos`: a situação de cada ano publicado, com `superficie` ({cruzamento: medidas mostradas}).
    `tabelas`: por (ano, cruzamento), as chaves (município com 7 dígitos), as contagens mostradas e as marcas
    de cada uma, com os nomes das partições. `reprovados`: anos de uma pasta de partições que não passaram nos
    testes; nunca vão para o arquivo. `calculo`: com que regras a versão foi calculada (CALCULO), ou None quando
    a origem não registra, como uma pasta de partições."""
    anos: dict[int, dict] = field(default_factory=dict)
    tabelas: dict[tuple[int, str], pa.Table] = field(default_factory=dict)
    reprovados: dict[int, dict] = field(default_factory=dict)
    calculo: dict | None = None

    def tabela(self, ano: int, cid: str):
        """A tabela de um cruzamento num ano, em pandas, ou None se ele não está na superfície daquele ano."""
        t = self.tabelas.get((ano, cid))
        return None if t is None else t.to_pandas()


def regras(catalogo: dict) -> dict:
    return catalogo["bases"]["sih"]["superficie"]


def _mostrados(catalogo: dict) -> dict:
    """Os cruzamentos da superfície que o catálogo em uso tem (o do repositório tem todos: catalogo.validar)."""
    ids = {c["id"] for c in catalogo["cruzamentos"]}
    return {cid: regra for cid, regra in regras(catalogo)["cruzamentos"].items() if cid in ids}


def chaves_de(cid: str, catalogo: dict) -> list[str]:
    """As colunas da chave de um cruzamento (o mesmo que sih_tabelas.colunas_de, sem depender do pandas)."""
    c = next((x for x in catalogo["cruzamentos"] if x["id"] == cid), None)
    if c is None:
        raise ErroDeSuperficie(f"Cruzamento {cid} fora do catálogo")
    return [catalogo["dimensoes"][d]["niveis"][0] for d in c["dimensoes"]] + TEMPO[c["tempo"]]


def cruzamentos_do_ano(catalogo: dict, ano: int, anos, mantidos=()) -> dict[str, list[str]]:
    """O que a página mostra de um ano, quando os anos publicados são `anos`: {cruzamento: medidas}.

    Os de detalhe (`anos_recentes`) entram nos anos mais novos e, fora deles, só os `mantidos` (detalhe_mantido).
    """
    saida = {}
    for cid, regra in _mostrados(catalogo).items():
        recentes = regra.get("anos_recentes")
        if recentes and ano not in sorted(anos)[-recentes:] and cid not in mantidos:
            continue
        saida[cid] = list(regra["medidas"])
    return saida


def detalhe_mantido(catalogo: dict, ano: int, anos, no_ar: Superficie | None) -> list[str]:
    """O detalhe que a versão no ar mostrava de um ano que saiu dos mais novos: continua publicado.

    Decidido em 11/11/2026: o que foi publicado continua publicado. O detalhe do ano sai do padrão da página,
    mas fica no seletor de ano, na versão no ar e no ataque conjunto, aberto ou fechado o ano. A lista vai
    para a situação do ano, de onde a superfície, a pasta de partições e a página a leem.
    """
    if no_ar is None or ano not in no_ar.anos:
        return []
    padrao, mostrados = cruzamentos_do_ano(catalogo, ano, anos), _mostrados(catalogo)
    return sorted(cid for cid in no_ar.anos[ano]["superficie"] if cid in mostrados and cid not in padrao)


def _esquema(catalogo: dict) -> pa.Schema:
    """As colunas do arquivo: ano, cruzamento, as chaves de todos os cruzamentos da superfície e as contagens."""
    chaves = []
    for cid in _mostrados(catalogo):
        chaves += [c for c in chaves_de(cid, catalogo) if c not in chaves]
    campos = [pa.field("ano", pa.int16()), pa.field("cruzamento", pa.string())]
    campos += [pa.field(c, pa.string()) for c in chaves]
    for valor, oculto, arredondado in COLUNAS.values():
        campos += [pa.field(valor, pa.int64()), pa.field(oculto, pa.bool_()), pa.field(arredondado, pa.bool_())]
    return pa.schema(campos + [pa.field("preliminar", pa.bool_())])


def _colunas(cid: str, medidas, catalogo: dict) -> list[str]:
    return chaves_de(cid, catalogo) + [c for m in medidas for c in COLUNAS[m]] + ["preliminar"]


def _tipada(t: pa.Table, colunas: list[str], esquema: pa.Schema, onde: str) -> pa.Table:
    faltam = [c for c in colunas if c not in t.column_names]
    if faltam:
        raise ErroDeSuperficie(f"{onde}: faltam as colunas {faltam}")
    return pa.table({c: t[c].cast(esquema.field(c).type) for c in colunas})


def do_ano(tabelas: dict[str, pa.Table], situacao: dict, catalogo: dict, anos) -> tuple[dict, dict[str, pa.Table]]:
    """A superfície de um ano: a situação (sem a lista de arquivos das partições, que não é publicada) com o que a
    página mostra, e a tabela de cada cruzamento mostrado, só com as colunas que a página lê.

    `tabelas` são as do ano como vão para as partições (sih.tabelas_publicaveis, ou lidas delas), e `anos`, os
    anos que a versão publica: os cruzamentos de detalhe só aparecem nos mais novos e nos que a situação
    lista em `detalhe_mantido`.
    """
    ano = int(situacao["ano"])
    esquema = _esquema(catalogo)
    regra = cruzamentos_do_ano(catalogo, ano, anos, situacao.get("detalhe_mantido", ()))
    mostra = {cid: m for cid, m in regra.items() if cid in situacao["publicados"]}
    saida = {}
    meta = {c: v for c, v in situacao.items() if c != "arquivos"} | {"superficie": mostra}
    for cid, medidas in mostra.items():
        if cid not in tabelas:
            raise ErroDeSuperficie(f"{ano}: {cid} consta como publicado, mas a tabela dele não veio")
        saida[cid] = _tipada(tabelas[cid], _colunas(cid, medidas, catalogo), esquema, f"{cid} de {ano}")
        # A mesma conferência da leitura do arquivo: a tela nunca mostra o que o arquivo recusaria.
        _conferir_tabela(saida[cid], cid, medidas, meta, catalogo, f"{cid} de {ano}")
    return meta, saida


def extrair(particoes: Path, catalogo: dict, anos=None) -> Superficie:
    """A superfície de uma pasta de partições, lendo só o que a situação de cada ano lista, conferido arquivo
    por arquivo (sih_particoes.ler_situacao). Ano que não passou nos testes fica em `reprovados`."""
    particoes = Path(particoes)
    lista = [a for a in sih_particoes.anos_na_pasta(particoes) if anos is None or a in set(anos)]
    sup, situacoes = Superficie(), {}
    for ano in lista:
        s = sih_particoes.ler_situacao(particoes, ano)
        motivo = sih_particoes.nao_publicavel(s)
        if motivo:
            sup.reprovados[ano] = s | {"motivo": motivo}
        else:
            situacoes[ano] = s
    esquema = _esquema(catalogo)
    for ano, s in situacoes.items():
        tabelas = {}
        for cid, medidas in cruzamentos_do_ano(catalogo, ano, situacoes, s.get("detalhe_mantido", ())).items():
            if cid not in s["publicados"]:
                continue
            colunas = _colunas(cid, medidas, catalogo)
            nomes = sorted(n for n in s["arquivos"] if n.startswith(cid + "/"))
            partes = [_tipada(pq.read_table(particoes / f"ano={ano}" / n), colunas, esquema, f"{cid} de {ano}, {n}")
                      for n in nomes]
            tabelas[cid] = pa.concat_tables(partes) if partes else esquema.empty_table().select(colunas)
        meta, tabs = do_ano(tabelas, s, catalogo, situacoes)
        sup.anos[ano] = meta
        sup.tabelas.update({(ano, cid): t for cid, t in tabs.items()})
    return sup


def _conteudo(tabela: pa.Table) -> str:
    """SHA-256 das células, como texto: não depende de como o Parquet foi comprimido nem dos metadados."""
    saida = io.BytesIO()
    pacsv.write_csv(tabela, saida)
    return hashlib.sha256(saida.getvalue()).hexdigest()


def gravar(sup: Superficie, caminho: Path, catalogo: dict) -> dict:
    """O arquivo da superfície, trocado de uma vez (.part e renomeação). Devolve bytes, SHA-256 e linhas."""
    if sup.reprovados:
        raise ErroDeSuperficie(f"Anos que não passaram nos testes não vão para a superfície: {sorted(sup.reprovados)}")
    esquema = _esquema(catalogo)
    partes = []
    for (ano, cid), t in sorted(sup.tabelas.items()):
        n = t.num_rows
        colunas = {"ano": pa.array([ano] * n, pa.int16()), "cruzamento": pa.array([cid] * n, pa.string())}
        for campo in esquema:
            if campo.name not in colunas:
                colunas[campo.name] = t[campo.name] if campo.name in t.column_names else pa.nulls(n, campo.type)
        partes.append(pa.table(colunas, schema=esquema))
    tabela = pa.concat_tables(partes) if partes else esquema.empty_table()
    meta = {"formato": FORMATO, "anos": {str(a): m for a, m in sorted(sup.anos.items())}, "conteudo_sha256": _conteudo(tabela)}
    if sup.calculo is not None:
        meta["calculo"] = _calculo(sup.calculo, caminho)
    tabela = tabela.replace_schema_metadata({METADADOS: json.dumps(meta, ensure_ascii=False, sort_keys=True)})
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    parcial = caminho.with_name(caminho.name + ".part")
    pq.write_table(tabela, parcial, compression="zstd")
    os.replace(parcial, caminho)
    bruto = caminho.read_bytes()
    return {"bytes": len(bruto), "sha256": hashlib.sha256(bruto).hexdigest(), "linhas": tabela.num_rows}


def _calculo(calculo, onde) -> dict:
    """`calculo` só com as chaves de CALCULO: o SHA-256 em hexadecimal e o número do algoritmo, inteiro positivo."""
    regras, algoritmo = (calculo.get(c) for c in CALCULO) if isinstance(calculo, dict) else (None, None)
    if (not isinstance(calculo, dict) or set(calculo) != set(CALCULO) or not isinstance(regras, str)
            or len(regras) != 64 or set(regras) - set("0123456789abcdef")
            or not isinstance(algoritmo, int) or isinstance(algoritmo, bool) or algoritmo < 1):
        raise ErroDeSuperficie(f"{onde}: o registro das regras do cálculo não está no formato esperado")
    return dict(calculo)


def _conferir_tabela(t: pa.Table, cid: str, medidas, meta: dict, catalogo: dict, onde: str) -> None:
    chaves = chaves_de(cid, catalogo)
    if any(t[c].null_count for c in chaves):
        raise ErroDeSuperficie(f"{onde}: célula sem chave completa")
    if t.num_rows and t.group_by(chaves).aggregate([([], "count_all")]).num_rows != t.num_rows:
        raise ErroDeSuperficie(f"{onde}: chave repetida")
    if t["preliminar"].null_count:
        raise ErroDeSuperficie(f"{onde}: célula sem a marca de preliminar")
    base = int(meta.get("arredondar_multiplo") or 0)
    for medida in medidas:
        valor, oculto, arredondado = COLUNAS[medida]
        if t[oculto].null_count or t[arredondado].null_count:
            raise ErroDeSuperficie(f"{onde}: célula sem a marca de oculta ou de arredondada em {medida}")
        if t.num_rows and not pc.all(pc.equal(pc.is_null(t[valor]), t[oculto])).as_py():
            raise ErroDeSuperficie(f"{onde}: valor nulo e marca de oculta não coincidem em {medida}")
        if pc.any(pc.and_(t[arredondado], t[oculto])).as_py():
            raise ErroDeSuperficie(f"{onde}: célula oculta marcada como arredondada em {medida}")
        if pc.any(t[arredondado]).as_py():
            valores = pc.filter(t[valor], t[arredondado]).to_pylist()
            if base < 2 or any(v % base for v in valores):
                raise ErroDeSuperficie(f"{onde}: valor marcado como arredondado fora do múltiplo de {base} da situação")


def ler(caminho: Path, catalogo: dict) -> Superficie:
    """Lê o arquivo da superfície e confere tudo: o SHA-256 do conteúdo, que cada ano poderia ter ido ao ar
    (sih_particoes.nao_publicavel), que só há linhas dos cruzamentos que a situação diz mostrar, e cada célula
    (chave inteira e única, valor nulo só na oculta, arredondado só em múltiplo da base daquele ano)."""
    caminho = Path(caminho)
    try:
        tabela = pq.read_table(caminho)
    except (pa.ArrowException, OSError) as erro:
        raise ErroDeSuperficie(f"{caminho}: não é um Parquet legível ({type(erro).__name__})") from None
    bruto = (tabela.schema.metadata or {}).get(METADADOS)
    try:
        meta = json.loads(bruto.decode("utf-8")) if bruto else None
    except (ValueError, UnicodeDecodeError):
        meta = None
    if not isinstance(meta, dict) or meta.get("formato") != FORMATO or not isinstance(meta.get("anos"), dict):
        raise ErroDeSuperficie(f"{caminho}: sem os metadados da superfície no formato {FORMATO}")
    esquema = _esquema(catalogo)
    if tabela.schema.remove_metadata() != esquema:
        raise ErroDeSuperficie(f"{caminho}: as colunas não são as da superfície do catálogo")
    tabela = tabela.replace_schema_metadata(None)
    if _conteudo(tabela) != meta.get("conteudo_sha256"):
        raise ErroDeSuperficie(f"{caminho}: o conteúdo não confere com o SHA-256 que o próprio arquivo registra")
    sup = Superficie(calculo=_calculo(meta["calculo"], caminho) if "calculo" in meta else None)
    declarados = set()
    for chave, m in meta["anos"].items():
        ano = int(chave)
        if not isinstance(m, dict) or m.get("ano") != ano or not isinstance(m.get("superficie"), dict):
            raise ErroDeSuperficie(f"{caminho}: a situação de {chave} não é a desse ano ou não diz o que a página mostra")
        motivo = sih_particoes.nao_publicavel(m)
        if motivo:
            raise ErroDeSuperficie(f"{caminho}: {ano} consta como publicado, mas {motivo}")
        sup.anos[ano] = m
        for cid, medidas in m["superficie"].items():
            declarados.add((ano, cid))
            linhas = tabela.filter(pc.and_(pc.equal(tabela["ano"], ano), pc.equal(tabela["cruzamento"], cid)))
            t = linhas.select(_colunas(cid, medidas, catalogo))
            outras = [c for c in esquema.names if c not in t.column_names and c not in ("ano", "cruzamento")]
            if any(linhas[c].null_count != linhas.num_rows for c in outras):
                raise ErroDeSuperficie(f"{caminho}: {cid} de {ano} tem colunas que a página não mostra")
            _conferir_tabela(t, cid, medidas, m, catalogo, f"{caminho}: {cid} de {ano}")
            sup.tabelas[ano, cid] = t
    pares = {(int(a), c) for a, c in zip(tabela["ano"].to_pylist(), tabela["cruzamento"].to_pylist())}
    if pares - declarados:
        raise ErroDeSuperficie(f"{caminho}: linhas de cruzamentos que a situação não diz mostrar: {sorted(pares - declarados)[:5]}")
    return sup


def carregar(caminho: Path, catalogo: dict) -> Superficie:
    """A superfície de um arquivo (o publicado) ou de uma pasta de partições (execução local)."""
    caminho = Path(caminho)
    return ler(caminho, catalogo) if caminho.is_file() else extrair(caminho, catalogo)


def consultar(destino: Path, catalogo: dict, pedir=rede.pedir, site: str | None = None, agora=None) -> dict:
    """Baixa a versão no ar do site e a confere. "Não existe" e "não consegui consultar" são diferentes.

    200: o arquivo vai para `destino`, conferido por `ler`. 404 com o site respondendo: não há versão no ar, e
    é a primeira publicação. Qualquer outra resposta, ou falha de rede, para com erro: seguir sem a versão no ar
    trocaria o que está publicado sem o ataque conjunto. O resultado só é gravado no fim, em `consulta.json`.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    for nome in (CONSULTA, ARQUIVO):
        (destino / nome).unlink(missing_ok=True)
    site = site or projeto.SITE
    instante = agora or datetime.now(timezone.utc)
    url = site + regras(catalogo)["arquivo"]
    marca = f"?consulta={instante:%Y%m%dT%H%M%S}"
    try:
        r = pedir(url + marca, descomprimir=False)
        if r.status == 404:
            raiz = pedir(site + marca)
    except rede.ErroDeRede as erro:
        raise ErroDeSuperficie(f"Não consegui consultar a versão no ar do SIH: {erro}") from None
    consulta = {"consultado_em": instante.strftime("%Y-%m-%dT%H:%M:%SZ"), "url": url}
    if r.status == 200:
        (destino / ARQUIVO).write_bytes(r.corpo)
        try:
            sup = ler(destino / ARQUIVO, catalogo)
        except ErroDeSuperficie:
            (destino / ARQUIVO).unlink(missing_ok=True)
            raise
        consulta |= {"existe": True, "bytes": len(r.corpo), "sha256": hashlib.sha256(r.corpo).hexdigest(),
                     "anos": sorted(sup.anos)}
    elif r.status == 404 and raiz.status == 200:
        consulta |= {"existe": False, "anos": []}
    else:
        situacao = f"HTTP {r.status}" + (f", e o site respondeu HTTP {raiz.status}" if r.status == 404 else "")
        raise ErroDeSuperficie(f"Não consegui consultar a versão no ar do SIH: {situacao} em {url}")
    (destino / CONSULTA).write_text(json.dumps(consulta, ensure_ascii=False, indent=1), encoding="utf-8")
    return consulta


def versao_no_ar(pasta: Path, catalogo: dict) -> Superficie | None:
    """A versão no ar baixada por `consultar`, conferida de novo, ou None na primeira publicação.

    Só responde com a consulta feita: sem `consulta.json`, para, em vez de concluir que não há versão.
    """
    pasta = Path(pasta)
    caminho = pasta / CONSULTA
    if not caminho.exists():
        raise ErroDeSuperficie(f"{caminho} não existe: a versão no ar do SIH não foi consultada, e sem isso não dá "
                               "para saber se ela existe. Rode antes `python -m pipeline no-ar`.")
    consulta = json.loads(caminho.read_text(encoding="utf-8"))
    if not consulta.get("existe"):
        return None
    arquivo = pasta / ARQUIVO
    if not arquivo.exists() or hashlib.sha256(arquivo.read_bytes()).hexdigest() != consulta.get("sha256"):
        raise ErroDeSuperficie(f"{arquivo}: ausente ou diferente do que a consulta baixou")
    sup = ler(arquivo, catalogo)
    if sorted(sup.anos) != consulta.get("anos"):
        raise ErroDeSuperficie(f"{arquivo}: os anos não são os da consulta ({consulta.get('anos')})")
    return sup
