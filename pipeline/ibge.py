"""Coleta e contrato do IBGE: lista de municípios (DTB), população estimada e Censo 2022.

A lista vem da DTB no geoftp; a população, da API da SIDRA (apisidra), que também diz qual é o
período mais recente. Nada aqui usa a API de serviços do IBGE (servicodados), que não aceitou
conexão do runner. Sem a data de modificação que só ela informava, a mudança é detectada pelo
hash dos valores, comparado com a coleta anterior registrada no manifesto.

O contrato recusa resposta fora do formato, valor não numérico, município desconhecido
e cobertura baixa. O Censo 2022 é partição fechada: depois da primeira coleta, vem da
Release do repositório e só é conferido com a fonte.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import dtb, rede
from .contrato import ErroDeContrato, sha256_valores

URL_SIDRA = "https://apisidra.ibge.gov.br/values/t/{tabela}/n6/all/v/{variavel}/p/{periodo}"
# "last 1" pede o período mais recente à própria SIDRA.
ESTIMATIVA = {"tabela": 6579, "variavel": 9324, "periodo": "last%201"}
CENSO = {"tabela": 4714, "variavel": 93, "periodo": "2022"}
# Um município novo pode entrar na lista antes de ter estimativa; mais do que isso é falha da fonte.
MAX_AUSENTES = 10

__all__ = ["ErroDeContrato", "coletar", "comparar", "conferir_cobertura", "ler_sidra"]


def _json(corpo: bytes, onde: str):
    try:
        return json.loads(corpo)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErroDeContrato(f"{onde}: resposta não é JSON ({e})") from None


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
    periodo = periodos.pop()
    if not re.fullmatch(r"\d{4}", periodo):
        raise ErroDeContrato(f"{onde}: período {periodo!r} não é um ano")
    return periodo, valores


def conferir_cobertura(codigos: set[str], valores: dict[str, int], onde: str) -> list[str]:
    desconhecidos = sorted(set(valores) - codigos)
    if desconhecidos:
        raise ErroDeContrato(f"{onde}: municípios fora da lista da DTB: {desconhecidos[:5]}")
    ausentes = sorted(codigos - set(valores))
    if len(ausentes) > MAX_AUSENTES:
        raise ErroDeContrato(f"{onde}: {len(ausentes)} municípios sem valor, mais que o limite de {MAX_AUSENTES}")
    return ausentes


def comparar(anterior: dict | None, chave: str, periodo: str, hash_valores: str) -> str:
    """Compara com a coleta anterior do manifesto: sem_coleta_anterior, igual, periodo_novo ou valores_mudaram."""
    antes = (anterior or {}).get(chave) or {}
    if not antes.get("sha256_valores"):
        return "sem_coleta_anterior"
    if str(antes.get("periodo")) != periodo:
        return "periodo_novo"
    return "igual" if antes["sha256_valores"] == hash_valores else "valores_mudaram"


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
    except rede.ErroDeRede:
        if release is None:
            raise
        resposta = valores = None
    if release is not None:
        bruto = release.read_bytes()
        guardado = json.loads(bruto)
        hash_guardado = sha256_valores(guardado["valores"])
        if guardado.get("sha256_valores") not in (None, hash_guardado):
            raise ErroDeContrato("Censo 2022: os valores da Release não conferem com o hash gravado nela. "
                                 "A Release não foi usada; confira o arquivo antes de publicar.")
        if valores is not None and sha256_valores(valores) != hash_guardado:
            mudaram = sorted(c for c in set(valores) | set(guardado["valores"])
                             if valores.get(c) != guardado["valores"].get(c))
            raise ErroDeContrato(f"Censo 2022: a partição fechada mudou na origem em {len(mudaram)} municípios "
                                 f"(ex.: {mudaram[:3]}). A Release não foi substituída; decida antes de publicar.")
        fonte = guardado | {"origem": "release", "sha256_valores": hash_guardado, "sha256_release": rede.sha256(bruto),
                            "conferido_com_a_fonte_em": coletado_em if valores is not None else None}
        fonte["ausentes"] = conferir_cobertura(codigos, fonte["valores"], "Censo 2022")
        return fonte, None
    novo = {"base": "ibge_censo_2022", "periodo": CENSO["periodo"], **_origem(url, resposta, coletado_em),
            "sha256_valores": sha256_valores(valores), "valores": valores}
    fonte = {**novo, "origem": "fonte", "ausentes": conferir_cobertura(codigos, valores, "Censo 2022")}
    return fonte, novo


def coletar(saida: Path, release_censo: Path | None = None, anterior: dict | None = None,
            pedir=rede.pedir, agora=None) -> dict:
    """`anterior` são as fontes do manifesto da última coleta, para dizer o que mudou desde ela."""
    coletado_em = (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fonte_dtb, municipios = dtb.coletar(pedir, coletado_em)
    codigos = {m["codigo"] for m in municipios}

    url_est = URL_SIDRA.format(**ESTIMATIVA)
    est = _baixar(url_est, pedir, "Estimativa de população")
    periodo, estimativa = ler_sidra(est.corpo, ESTIMATIVA["variavel"], "Estimativa de população")
    fontes = {
        "dtb": fonte_dtb,
        "estimativa": _origem(url_est, est, coletado_em) | {
            "base": "ibge_estimativa", "periodo": periodo, "sha256_valores": sha256_valores(estimativa),
            "origem": "fonte", "ausentes": conferir_cobertura(codigos, estimativa, "Estimativa de população")},
    }
    censo, novo = _censo(codigos, pedir, release_censo, coletado_em)
    valores_censo = censo.pop("valores")
    fontes["censo"] = censo
    for chave, fonte in fontes.items():
        fonte["em_relacao_a_coleta_anterior"] = comparar(anterior, chave, fonte["periodo"], fonte["sha256_valores"])
    for m in municipios:
        m["populacao_estimada"] = estimativa.get(m["codigo"])
        m["populacao_censo"] = valores_censo.get(m["codigo"])
    resultado = {"coletado_em": coletado_em, "fontes": fontes, "municipios": municipios}
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "ibge.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    if novo is not None:
        (saida / "censo-2022.json").write_text(json.dumps(novo, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultado
