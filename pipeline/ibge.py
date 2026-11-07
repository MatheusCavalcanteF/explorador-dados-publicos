"""Coleta e contrato do IBGE: lista de municípios, população estimada e Censo 2022.

O contrato recusa resposta fora do formato, valor não numérico, município desconhecido
e cobertura baixa. O Censo 2022 é partição fechada: depois da primeira coleta, vem da
Release do repositório e só é conferido com a fonte.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import rede

URL_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_SIDRA = "https://apisidra.ibge.gov.br/values/t/{tabela}/n6/all/v/{variavel}/p/{periodo}"
URL_PERIODOS = "https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/periodos"
ESTIMATIVA = {"tabela": 6579, "variavel": 9324, "periodo": "last%201"}
CENSO = {"tabela": 4714, "variavel": 93, "periodo": "2022"}
# Um município novo pode entrar na lista antes de ter estimativa; mais do que isso é falha da fonte.
MAX_AUSENTES = 10


class ErroDeContrato(ValueError):
    """O dado chegou, mas não é o que o contrato aceita. Nada é publicado."""


def _json(corpo: bytes, onde: str):
    try:
        return json.loads(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErroDeContrato(f"{onde}: resposta não é JSON ({e})") from None


def ler_localidades(corpo: bytes) -> list[dict]:
    dados = _json(corpo, "Localidades do IBGE")
    if not isinstance(dados, list):
        raise ErroDeContrato("Localidades do IBGE: esperava uma lista de municípios")
    municipios, codigos, prefixos = [], set(), set()
    for item in dados:
        try:
            codigo, nome = str(item["id"]), item["nome"].strip()
            # A microrregião vem nula em município novo; a região imediata existe em todos.
            uf = item["regiao-imediata"]["regiao-intermediaria"]["UF"]
            sigla, uf_nome, uf_id = uf["sigla"], uf["nome"], str(uf["id"])
        except (KeyError, TypeError, AttributeError):
            raise ErroDeContrato(f"Localidades do IBGE: item sem código, nome ou UF: {str(item)[:160]}") from None
        if not re.fullmatch(r"\d{7}", codigo) or not codigo.startswith(uf_id):
            raise ErroDeContrato(f"Localidades do IBGE: código {codigo} inválido para a UF {sigla}")
        if not nome or not re.fullmatch(r"[A-Z]{2}", sigla):
            raise ErroDeContrato(f"Localidades do IBGE: nome ou sigla inválidos no código {codigo}")
        if codigo in codigos or codigo[:6] in prefixos:
            # SIH e CAGED usam 6 dígitos; a conversão só é segura se o prefixo for único.
            raise ErroDeContrato(f"Localidades do IBGE: código ou prefixo de 6 dígitos repetido em {codigo}")
        codigos.add(codigo)
        prefixos.add(codigo[:6])
        municipios.append({"codigo": codigo, "nome": nome, "uf": sigla, "uf_nome": uf_nome})
    ufs = {m["uf"] for m in municipios}
    if len(ufs) != 27 or not 5_500 <= len(municipios) <= 5_700:
        raise ErroDeContrato(f"Localidades do IBGE: {len(municipios)} municípios em {len(ufs)} UFs, fora do esperado")
    return sorted(municipios, key=lambda m: m["codigo"])


def ler_sidra(corpo: bytes, variavel: int, onde: str) -> tuple[str, dict[str, int]]:
    """Devolve (período, valores por código). As colunas são achadas pelo cabeçalho, não pela posição."""
    dados = _json(corpo, onde)
    if not isinstance(dados, list) or len(dados) < 2 or not isinstance(dados[0], dict):
        raise ErroDeContrato(f"{onde}: resposta sem cabeçalho ou sem linhas")
    cabecalho, *linhas = dados
    colunas = {}
    for chave, rotulo in cabecalho.items():
        if re.fullmatch(r"D\dC", chave):
            for nome, prefixo in (("municipio", "Município"), ("variavel", "Variável"), ("periodo", "Ano")):
                if str(rotulo).startswith(prefixo):
                    colunas[nome] = chave
    if set(colunas) != {"municipio", "variavel", "periodo"} or cabecalho.get("V") != "Valor":
        raise ErroDeContrato(f"{onde}: cabeçalho inesperado {sorted(cabecalho)}")
    valores, periodos = {}, set()
    for linha in linhas:
        codigo, valor = str(linha.get(colunas["municipio"])), str(linha.get("V"))
        if linha.get("NC") != "6" or linha.get(colunas["variavel"]) != str(variavel):
            raise ErroDeContrato(f"{onde}: linha de outro nível ou variável no código {codigo}")
        if not re.fullmatch(r"\d{7}", codigo) or codigo in valores:
            raise ErroDeContrato(f"{onde}: código {codigo} inválido ou repetido")
        # Na SIDRA, "-", "..." e "X" são sinais de ausência ou sigilo, não números.
        if not valor.isdigit() or int(valor) <= 0:
            raise ErroDeContrato(f"{onde}: valor {valor!r} não é contagem positiva no código {codigo}")
        valores[codigo] = int(valor)
        periodos.add(str(linha.get(colunas["periodo"])))
    if len(periodos) != 1:
        raise ErroDeContrato(f"{onde}: esperava um só período, veio {sorted(periodos)}")
    return periodos.pop(), valores


def ler_modificacao(corpo: bytes, periodo: str, onde: str) -> str:
    """Data em que a SIDRA diz ter modificado o período, em ISO."""
    for item in _json(corpo, onde):
        if str(item.get("id")) == periodo:
            dia, mes, ano = str(item.get("modificacao", "")).split("/")
            return f"{ano}-{mes}-{dia}"
    raise ErroDeContrato(f"{onde}: período {periodo} não aparece na lista de períodos")


def conferir_cobertura(codigos: set[str], valores: dict[str, int], onde: str) -> list[str]:
    desconhecidos = sorted(set(valores) - codigos)
    if desconhecidos:
        raise ErroDeContrato(f"{onde}: municípios fora da lista do IBGE: {desconhecidos[:5]}")
    ausentes = sorted(codigos - set(valores))
    if len(ausentes) > MAX_AUSENTES:
        raise ErroDeContrato(f"{onde}: {len(ausentes)} municípios sem valor, mais que o limite de {MAX_AUSENTES}")
    return ausentes


def _baixar(url: str, pedir, onde: str) -> rede.Resposta:
    resposta = pedir(url)
    if resposta.status != 200:
        raise ErroDeContrato(f"{onde}: HTTP {resposta.status} em {url}")
    return resposta


def _origem(url: str, resposta: rede.Resposta, coletado_em: str) -> dict:
    return {"url": url, "coletado_em": coletado_em, "bytes": len(resposta.corpo), "sha256": rede.sha256(resposta.corpo)}


def _censo(codigos, pedir, release: Path | None, coletado_em: str) -> tuple[dict, dict | None]:
    """Devolve (fonte, arquivo novo para a Release ou None se a Release já existe)."""
    url = URL_SIDRA.format(**CENSO)
    try:
        resposta = _baixar(url, pedir, "Censo 2022")
        _, valores = ler_sidra(resposta.corpo, CENSO["variavel"], "Censo 2022")
        modificacao = ler_modificacao(_baixar(URL_PERIODOS.format(tabela=CENSO["tabela"]), pedir, "Censo 2022").corpo,
                                      CENSO["periodo"], "Períodos do Censo 2022")
    except rede.ErroDeRede:
        if release is None:
            raise
        resposta = None
    if release is not None:
        bruto = release.read_bytes()
        guardado = json.loads(bruto)
        if resposta is not None and guardado["valores"] != valores:
            mudaram = sorted(c for c in set(valores) | set(guardado["valores"])
                             if valores.get(c) != guardado["valores"].get(c))
            raise ErroDeContrato(f"Censo 2022: a partição fechada mudou na origem em {len(mudaram)} municípios "
                                 f"(ex.: {mudaram[:3]}). A Release não foi substituída; decida antes de publicar.")
        fonte = guardado | {"origem": "release", "sha256_release": rede.sha256(bruto),
                            "conferido_com_a_fonte_em": coletado_em if resposta is not None else None}
        fonte["ausentes"] = conferir_cobertura(codigos, fonte["valores"], "Censo 2022")
        return fonte, None
    novo = {"base": "ibge_censo_2022", "periodo": CENSO["periodo"], "modificacao_na_origem": modificacao,
            **_origem(url, resposta, coletado_em), "valores": valores}
    fonte = {**novo, "origem": "fonte", "ausentes": conferir_cobertura(codigos, valores, "Censo 2022")}
    return fonte, novo


def coletar(saida: Path, release_censo: Path | None = None, pedir=rede.pedir, agora=None) -> dict:
    coletado_em = (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    loc = _baixar(URL_LOCALIDADES, pedir, "Localidades do IBGE")
    municipios = ler_localidades(loc.corpo)
    codigos = {m["codigo"] for m in municipios}

    url_est = URL_SIDRA.format(**ESTIMATIVA)
    est = _baixar(url_est, pedir, "Estimativa de população")
    periodo, estimativa = ler_sidra(est.corpo, ESTIMATIVA["variavel"], "Estimativa de população")
    modificacao = ler_modificacao(_baixar(URL_PERIODOS.format(tabela=ESTIMATIVA["tabela"]), pedir, "Estimativa").corpo,
                                  periodo, "Períodos da estimativa")
    fontes = {
        "localidades": _origem(URL_LOCALIDADES, loc, coletado_em) | {"municipios": len(municipios)},
        "estimativa": _origem(url_est, est, coletado_em) | {
            "base": "ibge_estimativa", "periodo": periodo, "modificacao_na_origem": modificacao,
            "origem": "fonte", "ausentes": conferir_cobertura(codigos, estimativa, "Estimativa de população")},
    }
    censo, novo = _censo(codigos, pedir, release_censo, coletado_em)
    valores_censo = censo.pop("valores")
    fontes["censo"] = censo
    for m in municipios:
        m["populacao_estimada"] = estimativa.get(m["codigo"])
        m["populacao_censo"] = valores_censo.get(m["codigo"])
    resultado = {"coletado_em": coletado_em, "fontes": fontes, "municipios": municipios}
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "ibge.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    if novo is not None:
        (saida / "censo-2022.json").write_text(json.dumps(novo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultado
