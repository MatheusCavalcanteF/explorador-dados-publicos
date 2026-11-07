"""Supressão primária e complementar, compartilhada pelas medições.

O resultado só é determinístico se as linhas chegarem em ordem fixa: os empates na escolha da
complementar são resolvidos pela posição. Quem chama deve ordenar pelas dimensões.
"""
import numpy as np
import pandas as pd

K = 5


def faixa_pequena(valores: np.ndarray, k: int = K) -> np.ndarray:
    """Verdadeiro para contagens de 1 a k-1. Zero não é oculto."""
    return (valores >= 1) & (valores < k)


def chaves_de_linha(df: pd.DataFrame, conjuntos: list[list[str]]) -> list[np.ndarray]:
    """Um vetor de grupos por linha marginal. Cada conjunto lista as colunas mantidas fixas."""
    codigos: dict[str, np.ndarray] = {}
    saida = []
    for colunas in conjuntos:
        chave = np.zeros(len(df), dtype="int64")
        for c in colunas:
            if c not in codigos:
                codigos[c] = pd.factorize(df[c])[0].astype("int64")
            chave = pd.factorize(chave * (codigos[c].max() + 1) + codigos[c])[0].astype("int64")
        saida.append(chave)
    return saida


def _precisa(g: np.ndarray, oculto: np.ndarray, medidas: list[np.ndarray], k: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Linhas marginais em que ainda dá para deduzir alguma célula oculta.

    Uma margem de 1 a k-1 também é oculta, então não entrega nada nessa medida. Há risco quando a
    margem é visível e a linha tem uma só célula oculta, ou quando as ocultas somam de 1 a k-1.
    Linha de uma só célula não conta: a margem é a própria célula e fica oculta junto.
    """
    n = g.max() + 1
    n_ocultos = np.bincount(g, weights=oculto, minlength=n)
    total = np.bincount(g, minlength=n)
    risco = np.zeros(n, dtype=bool)
    for m in medidas:
        margem = np.bincount(g, weights=m, minlength=n)
        soma = np.bincount(g, weights=m * oculto, minlength=n)
        visivel = margem >= k
        risco = risco | (visivel & ((n_ocultos == 1) | ((soma > 0) & (soma < k))))
    return (n_ocultos >= 1) & risco & (total > n_ocultos), n_ocultos, total


def complementar(primaria: np.ndarray, linhas: list[np.ndarray], medidas: list[np.ndarray], k: int = K, max_voltas: int = 80, inelegivel: np.ndarray | None = None) -> tuple[np.ndarray, int, bool]:
    """Oculta o menor valor positivo visível em cada linha marginal que ainda permite dedução.

    Célula de valor zero só é escolhida quando não resta positivo na linha: ela cria incerteza sobre
    a posição, mas não aumenta a soma oculta. `inelegivel` marca células que não protegem nada, como
    a única filha de uma mãe visível, cujo valor já é público. Devolve a máscara, as voltas e se convergiu.
    """
    oculto = primaria.copy()
    bloqueada = np.zeros(len(oculto), dtype=bool) if inelegivel is None else inelegivel
    base = np.where(medidas[0] > 0, medidas[0], np.iinfo("int64").max)
    volta = 0
    convergiu = False
    for volta in range(1, max_voltas + 1):
        mudou = 0
        for g in linhas:
            precisa, _, _ = _precisa(g, oculto, medidas, k)
            cand = np.flatnonzero(precisa[g] & ~oculto & ~bloqueada)
            if cand.size == 0:
                continue
            ordem = cand[np.lexsort((base[cand], g[cand]))]
            _, primeiro = np.unique(g[ordem], return_index=True)
            oculto[ordem[primeiro]] = True
            mudou += primeiro.size
        if not mudou:
            convergiu = True
            break
    return oculto, volta, convergiu


def linhas_dedutiveis(oculto: np.ndarray, linhas: list[np.ndarray], medidas: list[np.ndarray], k: int = K) -> int:
    """Conta as linhas marginais que ainda permitem deduzir valor, para conferir a própria supressão."""
    return sum(int(_precisa(g, oculto, medidas, k)[0].sum()) for g in linhas)


def deducao_em_cadeia(conhecido: np.ndarray, valores: np.ndarray, linhas: list[np.ndarray], k: int = K) -> dict:
    """Parte das células conhecidas e deduz o que der pelas margens visíveis, até parar.

    Serve para medir a segunda ordem: uma célula complementar revelada por outra tabela pode
    desproteger a célula pequena que ela estava protegendo. Linha de uma só célula não entrega nada,
    porque a margem é a própria célula.
    """
    conhecido = conhecido.copy()
    inicial = conhecido.copy()
    while True:
        novos = 0
        for g in linhas:
            n = g.max() + 1
            margem = np.bincount(g, weights=valores, minlength=n)
            total = np.bincount(g, minlength=n)
            faltando = np.bincount(g, weights=~conhecido, minlength=n)
            alvo = (faltando == 1) & (margem >= k) & (total > 1)
            idx = np.flatnonzero(alvo[g] & ~conhecido)
            if idx.size:
                conhecido[idx] = True
                novos += idx.size
        if not novos:
            break
    deduzidas = conhecido & ~inicial
    return {"deduzidas": int(deduzidas.sum()), "deduzidas_de_1a4": int((deduzidas & faixa_pequena(valores, k)).sum())}
