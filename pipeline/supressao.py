"""Supressão por família, para os cruzamentos de um ano, na ordem do catálogo.

Quatro camadas, cada uma porque a anterior deixou passar algo medido (ver o plano):
1. Primária: oculta a célula quando as AIHs ou as internações estão entre 1 e k-1.
2. Família: uma célula oculta na mãe esconde as filhas da mesma chave, e o trimestre herda a ocultação
   de qualquer mês dele. A única filha de uma mãe visível não serve de complementar: o valor já é público.
3. Complementar: em cada margem que alguém pode montar (cada coluna em cada nível acima), oculta o menor
   valor visível onde ainda daria para deduzir: uma só oculta com margem visível, ou ocultas somando
   de 1 a k-1. A margem conta como visível se a soma for de k para cima, mesmo quando não é publicada.
4. O teste de dedução, em deducao.py, confere o resultado agindo como quem tenta deduzir.

Cada célula oculta leva o motivo, que é público: contagem pequena, família ou complementar. O resultado
só é determinístico com as linhas em ordem fixa, porque os empates na complementar saem pela posição.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import sih_tabelas as tab
from .deducao import COMPLEMENTAR, PEQUENA, VISIVEL

FAMILIA = 4
MOTIVOS = {VISIVEL: "", PEQUENA: "contagem_pequena", COMPLEMENTAR: "complementar", FAMILIA: "familia"}


def pequena(valores: np.ndarray, k: int) -> np.ndarray:
    """De 1 a k-1. Zero não é oculto."""
    return (valores >= 1) & (valores < k)


def _arriscadas(g: np.ndarray, oculto: np.ndarray, medidas: list[np.ndarray], k: int) -> np.ndarray:
    """Linhas marginais em que ainda dá para deduzir alguma célula oculta, por grupo.

    Linha de uma só célula não conta: a margem é a própria célula e fica oculta junto.
    """
    n = int(g.max()) + 1
    n_ocultos = np.bincount(g, weights=oculto, minlength=n)
    total = np.bincount(g, minlength=n)
    risco = np.zeros(n, dtype=bool)
    for m in medidas:
        margem = np.bincount(g, weights=m, minlength=n)
        soma = np.bincount(g, weights=m * oculto, minlength=n)
        risco |= (margem >= k) & ((n_ocultos == 1) | ((soma > 0) & (soma < k)))
    return (n_ocultos >= 1) & risco & (total > n_ocultos)


def complementar(primaria: np.ndarray, linhas: list[np.ndarray], medidas: list[np.ndarray], k: int,
                 inelegivel: np.ndarray | None = None, max_voltas: int = 100) -> np.ndarray:
    """Oculta o menor valor positivo visível de cada linha marginal arriscada, até nenhuma restar.

    Zero só é escolhido quando não resta positivo na linha: cria incerteza na posição sem aumentar a
    soma oculta. A ordem do menor usa a primeira medida (as AIHs), e o empate, a posição.
    """
    oculto = primaria.copy()
    bloqueada = np.zeros(oculto.size, dtype=bool) if inelegivel is None else inelegivel
    base = np.where(medidas[0] > 0, medidas[0], np.iinfo(np.int64).max)
    for _ in range(max_voltas):
        mudou = False
        for g in linhas:
            if not g.size:
                continue
            arriscada = _arriscadas(g, oculto, medidas, k)
            candidatas = np.flatnonzero(arriscada[g] & ~oculto & ~bloqueada)
            if not candidatas.size:
                continue
            ordem = candidatas[np.lexsort((base[candidatas], g[candidatas]))]
            _, primeira = np.unique(g[ordem], return_index=True)
            oculto[ordem[primeira]] = True
            mudou = True
        if not mudou:
            return oculto
    raise RuntimeError(f"Complementar não convergiu em {max_voltas} voltas")


def estados(primaria: np.ndarray, herdada: np.ndarray, oculto: np.ndarray) -> np.ndarray:
    estado = np.full(oculto.size, VISIVEL, dtype=np.int8)
    estado[oculto] = COMPLEMENTAR
    estado[herdada & oculto] = FAMILIA
    estado[primaria] = PEQUENA
    return estado


def nos_publicados(catalogo: dict, medida: str = "internacoes") -> list[tuple]:
    """Cruzamentos do catálogo e margens publicadas da medida, como nós."""
    margens = [tab.no(m) for m in catalogo["margens_publicadas"][medida]]
    cruz = [tab.colunas_de(c, catalogo) for c in catalogo["cruzamentos"]
            if medida != "obitos" or "obitos" in c["metricas"]]
    return list(dict.fromkeys(cruz + margens))


def margens_conhecidas(catalogo: dict) -> dict[str, list[tuple]]:
    """As margens que a complementar protege em cada cruzamento: as publicadas e as que dá para calcular
    a partir de outra tabela publicada. Uma soma que só sai da própria tabela, como eletivo mais outros
    num hospital e mês, ninguém conhece, e protegê-la só esconde mais. O teste de dedução confere o
    resultado e o reforço cobre o que a cadeia ainda revelar.
    """
    publicados = nos_publicados(catalogo)
    saida = {}
    for c in catalogo["cruzamentos"]:
        n = tab.colunas_de(c, catalogo)
        alcance = set(tab.fechamento([p for p in publicados if p != n])) | set(publicados)
        saida[c["id"]] = [m for m in tab.todos_acima(n) if m in alcance]
    return saida


def suprimir(nos: dict[tuple, pd.DataFrame], catalogo: dict, k: int, forcadas: dict[str, np.ndarray] | None = None,
             cache: dict | None = None) -> dict[str, pd.DataFrame]:
    """Cada cruzamento do catálogo com as colunas `oculto` e `estado`. Não altera os valores.

    `forcadas` traz, por cruzamento, células que o teste de dedução mandou ocultar a mais; entram como
    complementares, antes da complementar normal, e a família as leva para as filhas. `cache` guarda os
    grupos das margens entre uma rodada e outra.
    """
    forcadas = forcadas or {}
    cache = {} if cache is None else cache
    saida: dict[str, pd.DataFrame] = {}
    por_id = {c["id"]: c for c in catalogo["cruzamentos"]}
    for c in catalogo["cruzamentos"]:
        n = tab.colunas_de(c, catalogo)
        df = nos[n].copy()
        aihs, intern = df["aihs"].to_numpy(np.int64), df["internacoes"].to_numpy(np.int64)
        primaria = pequena(aihs, k) | pequena(intern, k)
        herdada = np.zeros(len(df), dtype=bool)
        inelegivel = None
        if "mae" in c:
            mae = saida[c["mae"]]
            n_mae = tab.colunas_de(por_id[c["mae"]], catalogo)
            idx = tab.indice_acima(df, n, mae, n_mae)
            herdada |= mae["oculto"].to_numpy()[idx]
            tamanho = np.bincount(idx, minlength=len(mae))[idx]
            inelegivel = (tamanho == 1) & ~herdada
        if "herda_trimestre_de" in c:
            mensal = saida[c["herda_trimestre_de"]]
            n_mensal = tab.colunas_de(por_id[c["herda_trimestre_de"]], catalogo)
            n_tri = tab.no([x if x != "mes" else "tri" for x in n_mensal])
            chave_mensal = tab.chaves_acima(mensal, n_mensal, n_tri)[mensal["oculto"].to_numpy()]
            ocultos = set(map(tuple, chave_mensal.to_numpy()))
            chave = tab.chaves_acima(df, n, n_tri)
            herdada |= np.fromiter((tuple(x) in ocultos for x in chave.to_numpy()), dtype=bool, count=len(df))
        if c["id"] not in cache:
            # Todas as margens servem ao reforço; a complementar usa só as do catálogo.
            cache[c["id"]] = [tab.grupos(df, n, m) for m in tab.todos_acima(n)]
            if catalogo["bases"]["sih"]["supressao"].get("margens_complementar", "todas") == "conhecidas":
                conhecidas = set(margens_conhecidas(catalogo)[c["id"]])
                cache[("complementar", c["id"])] = [g for g, m in zip(cache[c["id"]], tab.todos_acima(n)) if m in conhecidas]
            else:
                cache[("complementar", c["id"])] = cache[c["id"]]
        inicial = primaria | herdada
        if c["id"] in forcadas:
            inicial = inicial | forcadas[c["id"]]
        oculto = complementar(inicial, cache[("complementar", c["id"])], [aihs, intern], k, inelegivel)
        df["oculto"] = oculto
        df["estado"] = estados(primaria, herdada, oculto)
        saida[c["id"]] = df
    return saida


def suprimir_obitos(df: pd.DataFrame, n: tuple, k: int) -> np.ndarray:
    """Óbitos têm máscara própria, só no total anual por município: primária e complementar."""
    obitos = df["obitos"].to_numpy(np.int64)
    primaria = pequena(obitos, k)
    linhas = [tab.grupos(df, n, m) for m in tab.todos_acima(n)]
    oculto = complementar(primaria, linhas, [obitos], k)
    return estados(primaria, np.zeros(len(df), dtype=bool), oculto)


def margem_publicada(df: pd.DataFrame, k: int, medida: str = "internacoes") -> np.ndarray:
    """Margens de UF e do Brasil: só a primária. Na prática nenhuma fica oculta."""
    valores = df[medida].to_numpy(np.int64)
    primaria = pequena(valores, k) | (pequena(df["aihs"].to_numpy(np.int64), k) if medida == "internacoes" else False)
    return np.where(primaria, PEQUENA, VISIVEL).astype(np.int8)
