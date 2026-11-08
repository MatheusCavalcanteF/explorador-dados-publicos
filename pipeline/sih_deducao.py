"""Teste de dedução do SIH: tudo o que é publicável num ano, mais as somas que se pode montar com isso.

Os nós publicados são os cruzamentos do catálogo e as margens de UF e do Brasil. Os outros nós do
fechamento entram como incógnitas. Internações e óbitos são sistemas separados, porque cada medida tem
a própria máscara; dias e valor seguem a máscara das internações, com a mesma estrutura de somas.

Meses preliminares (decidido em 08/11/2026): a célula visível de um período que ainda pode mudar aparece
em múltiplo de `base` (bases.sih.preliminares), e quem lê só sabe que o valor está a menos de meia base.
O teste de cada versão vê os valores como a tela os mostra.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import deducao, sih_tabelas as tab, supressao

LIVRE = deducao.LIVRE


nos_publicados = supressao.nos_publicados


def estados_publicados(nos: dict[tuple, pd.DataFrame], suprimidas: dict[str, pd.DataFrame], catalogo: dict,
                       k: int, medida: str = "internacoes") -> dict[tuple, np.ndarray]:
    """Estado de cada célula publicada: o da supressão nos cruzamentos e a primária nas margens."""
    saida = {}
    for c in catalogo["cruzamentos"]:
        n = tab.colunas_de(c, catalogo)
        if medida == "obitos":
            if "obitos" in c["metricas"]:
                saida[n] = supressao.suprimir_obitos(nos[n], n, k)
        else:
            estado = suprimidas[c["id"]]["estado"].to_numpy().copy()
            # Linha que não vai para o arquivo (trimestre incompleto): quem lê não vê nem a chave.
            if "publicado" in suprimidas[c["id"]]:
                estado[~suprimidas[c["id"]]["publicado"].to_numpy()] = LIVRE
            saida[n] = estado
    for m in catalogo["margens_publicadas"][medida]:
        n = tab.no(m)
        if n not in saida:
            saida[n] = supressao.margem_publicada(nos[n], k, medida)
    return saida


def periodo_aberto(df: pd.DataFrame, n: tuple, ano: int, preliminares: set[str]) -> np.ndarray:
    """Células cujo período inclui um mês preliminar: o mês, o trimestre dele, ou o ano inteiro."""
    if not preliminares:
        return np.zeros(len(df), dtype=bool)
    if "mes" in n:
        return df["mes"].isin(preliminares).to_numpy()
    if "tri" in n:
        tris = {f"{m[:4]}T{(int(m[4:]) + 2) // 3}" for m in preliminares}
        return df["tri"].isin(tris).to_numpy()
    return np.ones(len(df), dtype=bool)


def periodo_fechado(df: pd.DataFrame, n: tuple, ano: int, ate_mes: int) -> np.ndarray:
    """Células cujo período inteiro já fechou até `ate_mes` (AAAAMM): o mês, os três do trimestre ou o ano."""
    if "mes" in n:
        return (df["mes"].astype(int) <= ate_mes).to_numpy()
    if "tri" in n:
        fim = df["tri"].str[:4].astype(int) * 100 + df["tri"].str[5:].astype(int) * 3
        return (fim <= ate_mes).to_numpy()
    return np.full(len(df), ano * 100 + 12 <= ate_mes)


def arredondar(valores: np.ndarray, base: int) -> np.ndarray:
    return (valores + base // 2) // base * base


def dominio_arredondado(valores: np.ndarray, estado: np.ndarray, aberto: np.ndarray, k: int, base: int):
    """lo e hi de quem lê o valor arredondado. Fora do período aberto, ou oculta, o domínio é o de sempre."""
    lo = np.zeros(valores.size, dtype=np.int64)
    hi = np.full(valores.size, deducao.INF, dtype=np.int64)
    visivel = estado == deducao.VISIVEL
    lo[visivel] = hi[visivel] = valores[visivel]
    hi[estado == deducao.PEQUENA] = k - 1
    alvo = visivel & aberto & (valores >= k)
    # r = (v + base//2) // base * base, então v fica entre r - base//2 e r - base//2 + base - 1;
    # e, sendo visível, não é menor que k.
    r = arredondar(valores[alvo], base)
    lo[alvo] = np.maximum(r - base // 2, k)
    hi[alvo] = r - base // 2 + base - 1
    return lo, hi


def sistema(nos: dict[tuple, pd.DataFrame], estados: dict[tuple, np.ndarray], publicados: list[tuple], k: int,
            medida: str = "internacoes", aresta_cache: list | None = None,
            arredondamento: tuple[int, set[str], int] | None = None) -> deducao.Sistema:
    """Monta o sistema do fechamento dos nós publicados. `arredondamento` é (base, meses preliminares, ano)."""
    fecho = tab.fechamento(publicados)
    s = deducao.Sistema(k)
    for n in fecho:
        df = nos[n]
        valores = df[medida].to_numpy(np.int64)
        if n in estados:
            estado = estados[n]
            if arredondamento:
                base, prelim, ano = arredondamento
                aberto = periodo_aberto(df, n, ano, prelim)
                lo, hi = dominio_arredondado(valores, estado, aberto, k, base)
                s.no(tab.nome(n), estado, valores, publicado=True, lo=lo, hi=hi)
            else:
                s.no(tab.nome(n), estado, valores, publicado=True)
        else:
            s.no(tab.nome(n), np.full(len(df), LIVRE, dtype=np.int8), valores, publicado=False)
    arestas = aresta_cache if aresta_cache is not None else tab.arestas({n: nos[n] for n in fecho})
    for fino, grosso, idx in arestas:
        s.aresta(tab.nome(fino), tab.nome(grosso), idx)
    return s


def auditar(s: deducao.Sistema) -> dict:
    voltas = s.propagar()
    s.conferir_solidez()
    por_no = s.reveladas()
    return {"voltas": voltas,
            "pequenas_reveladas": sum(r["pequenas_reveladas"] for r in por_no.values()),
            "pequenas_reveladas_em_publicados": sum(r["pequenas_reveladas"] for n, r in por_no.items() if s.nos[n].publicado),
            "pequenas_estreitadas": sum(r["pequenas_estreitadas"] for r in por_no.values()),
            "ocultas_exatas": sum(r["exatas"] for n, r in por_no.items() if s.nos[n].publicado),
            "por_no": {n: r for n, r in por_no.items() if r["pequenas_reveladas"] or r["pequenas_estreitadas"]}}


def reforcar(s: deducao.Sistema, sup: dict[str, pd.DataFrame], catalogo: dict, k: int, cache: dict,
             arestas: list, forcadas: dict[str, np.ndarray],
             travadas: dict[str, np.ndarray] | None = None) -> tuple[dict[str, np.ndarray], int]:
    """O que ocultar a mais depois de um ataque que revelou algo. Devolve as forçadas e quantas são novas.

    Uma célula oculta que o ataque deixou exata está exposta, e as somas que ninguém publica, quando
    reveladas, expõem as células ocultas das tabelas publicadas que as compõem. Em cada margem da
    tabela que contém uma célula exposta, a menor célula visível e positiva passa a ser complementar.
    """
    ids = {tab.nome(tab.colunas_de(c, catalogo)): c["id"] for c in catalogo["cruzamentos"]}
    expostas = {}
    # Exposta é a célula que a supressão ocultou e o ataque deixou exata. A linha visível que não vai para o
    # arquivo (trimestre incompleto) também é incógnita para quem lê, mas não protege nada: não conta.
    for nome_no, cid in ids.items():
        no = s.nos[nome_no]
        expostas[cid] = sup[cid]["oculto"].to_numpy() & (no.lo == no.hi)
    for fino, grosso, idx in arestas:
        g = s.nos[tab.nome(grosso)]
        if g.publicado or tab.nome(fino) not in ids:
            continue
        revelada = (g.lo == g.hi) & (g.lo >= 1) & (g.lo <= k - 1)
        if revelada.any():
            expostas[ids[tab.nome(fino)]] |= revelada[idx] & sup[ids[tab.nome(fino)]]["oculto"].to_numpy()
    novas = 0
    saida = {cid: m.copy() for cid, m in forcadas.items()}
    for cid, exposta in expostas.items():
        if not exposta.any():
            continue
        df = sup[cid]
        visivel = ~df["oculto"].to_numpy() & _publicado(df) & ~_travada(travadas, cid, df)
        aihs = df["aihs"].to_numpy()
        base = np.where(aihs > 0, aihs, np.iinfo(np.int64).max)
        marca = saida.setdefault(cid, np.zeros(len(df), dtype=bool))
        for g in cache[cid]:
            precisa = np.zeros(int(g.max()) + 1, dtype=bool)
            precisa[g[exposta]] = True
            candidatas = np.flatnonzero(precisa[g] & visivel & ~marca)
            if not candidatas.size:
                continue
            ordem = candidatas[np.lexsort((base[candidatas], g[candidatas]))]
            _, primeira = np.unique(g[ordem], return_index=True)
            marca[ordem[primeira]] = True
            novas += primeira.size
    novas += _quebrar_vizinhas(s, sup, ids, arestas, k, saida, travadas)
    return saida, novas


def _quebrar_vizinhas(s: deducao.Sistema, sup: dict, ids: dict, arestas: list, k: int, saida: dict,
                      travadas: dict[str, np.ndarray] | None = None) -> int:
    """Uma soma não publicada revelada costuma sair de um total menos as vizinhas exatas: o trimestre da UF
    menos os trimestres dos outros municípios, por exemplo. Ocultar mais células da própria soma não
    adianta; é preciso tirar a exatidão de uma vizinha. Para cada revelada, a vizinha exata de menor valor
    perde a menor célula visível que a compõe, em cada tabela publicada abaixo dela, e a complementar da
    rodada seguinte completa a proteção na linha dessa célula.
    """
    abaixo: dict[str, list] = {}
    acima_de: dict[str, list] = {}
    for fino, grosso, idx in arestas:
        if tab.nome(fino) in ids:
            abaixo.setdefault(tab.nome(grosso), []).append((ids[tab.nome(fino)], idx))
        acima_de.setdefault(tab.nome(fino), []).append(idx)
    novas = 0

    def quebrar(no_nome: str, celula: int) -> int:
        """Oculta, em cada tabela publicada abaixo da célula, a menor visível que a compõe."""
        feitas = 0
        for cid, idx_pub in abaixo.get(no_nome, []):
            df = sup[cid]
            marca = saida.setdefault(cid, np.zeros(len(df), dtype=bool))
            candidatas = np.flatnonzero((idx_pub == celula) & ~df["oculto"].to_numpy() & _publicado(df)
                                        & ~_travada(travadas, cid, df) & (df["aihs"].to_numpy() > 0) & ~marca)
            if candidatas.size:
                marca[candidatas[np.argmin(df["aihs"].to_numpy()[candidatas])]] = True
                feitas += 1
        return feitas

    for nome_no, grupos in acima_de.items():
        f = s.nos[nome_no]
        if f.publicado or len(grupos) < 2:
            continue
        exata = f.lo == f.hi
        for c in np.flatnonzero(exata & (f.lo >= 1) & (f.lo <= k - 1)):
            # Retângulo: c e uma vizinha c1 numa soma (g1), c e outra célula c2 noutra soma (g2), e a célula
            # que fecha o retângulo, c3, na soma g2 de c1 e na g1 de c2. Ocultar algo sob c1 e sob c3 deixa
            # as quatro sem valor exato, mesmo com os dois totais conhecidos.
            feito = False
            for i, g1 in enumerate(grupos):
                for g2 in grupos[i + 1:] + grupos[:i]:
                    vizinhas = np.flatnonzero((g1 == g1[c]) & exata & (f.lo >= 1))
                    vizinhas = vizinhas[(vizinhas != c) & (g2[vizinhas] != g2[c])]
                    outras = np.flatnonzero((g2 == g2[c]) & (g1 != g1[c]))
                    for c1 in vizinhas[np.argsort(f.lo[vizinhas], kind="stable")]:
                        for c2 in outras[np.argsort(exata[outras], kind="stable")]:
                            c3 = np.flatnonzero((g2 == g2[c1]) & (g1 == g1[c2]))
                            if c3.size:
                                novas_aqui = quebrar(nome_no, c1) + quebrar(nome_no, int(c3[0]))
                                if novas_aqui:
                                    novas_feitas = novas_aqui
                                    feito = True
                                    break
                        if feito:
                            break
                    if feito:
                        break
                if feito:
                    break
            if feito:
                novas += novas_feitas
    return novas


def _travada(travadas: dict | None, cid: str, df: pd.DataFrame) -> np.ndarray:
    """Visível e exata na versão publicada antes, num período fechado: escondê-la agora não adianta."""
    return travadas[cid] if travadas and cid in travadas else np.zeros(len(df), dtype=bool)


def _publicado(df: pd.DataFrame) -> np.ndarray:
    return df["publicado"].to_numpy() if "publicado" in df else np.ones(len(df), dtype=bool)


def sem_motivo(estados: dict[tuple, np.ndarray]) -> dict[tuple, np.ndarray]:
    """Quando o motivo não é publicado, quem lê só sabe que a célula está oculta: de 0 ao infinito."""
    return {n: np.where(e == deducao.VISIVEL, deducao.VISIVEL, LIVRE).astype(np.int8) for n, e in estados.items()}


def suprimir_ate_passar(nos: dict, catalogo: dict, k: int, motivo_publico: bool, max_rodadas: int | None = None,
                        arestas: list | None = None, arredondamento=None, ultimo_mes: int | None = None,
                        fixas: dict | None = None) -> dict:
    """Supressão, teste de dedução e reforço, até o teste dar zero ou o reforço não ter mais o que ocultar.

    Sem `max_rodadas`, vale o limite do catálogo (supressao.reforco_max_rodadas), o mesmo do pipeline.
    `arredondamento` é (base, meses preliminares, ano): o teste vê os valores como a tela os mostra.
    `ultimo_mes` (AAAAMM) tira do arquivo o trimestre que ainda não tem os três meses na base.
    `fixas` é o padrão herdado da versão publicada antes (supressao.suprimir); o reforço não oculta as travadas.
    Devolve os cruzamentos suprimidos, a auditoria final, o histórico por rodada e se passou. Quem chama
    decide o que fazer quando não passa; o pipeline não publica.
    """
    if max_rodadas is None:
        max_rodadas = int(catalogo["bases"]["sih"]["supressao"]["reforco_max_rodadas"])
    publicados = nos_publicados(catalogo)
    fecho = tab.fechamento(publicados)
    arestas = arestas if arestas is not None else tab.arestas({n: nos[n] for n in fecho})
    forcadas, cache, historico = {}, {}, []
    for rodada in range(max_rodadas + 1):
        sup = supressao.suprimir(nos, catalogo, k, forcadas, cache, ultimo_mes, fixas)
        estados = estados_publicados(nos, sup, catalogo, k)
        vistos = estados if motivo_publico else sem_motivo(estados)
        s = sistema(nos, vistos, publicados, k, aresta_cache=arestas, arredondamento=arredondamento)
        auditoria = auditar(s)
        historico.append({"rodada": rodada, "pequenas_reveladas": auditoria["pequenas_reveladas"],
                          "celulas_ocultas": int(sum(df["oculto"].sum() for df in sup.values()))})
        if auditoria["pequenas_reveladas"] == 0 or rodada == max_rodadas:
            break
        forcadas, novas = reforcar(s, sup, catalogo, k, cache, arestas, forcadas,
                                   {cid: f[1] for cid, f in (fixas or {}).items()})
        if not novas:
            break
    return {"suprimidas": sup, "estados": estados, "sistema": s, "auditoria": auditoria, "historico": historico,
            "passou": auditoria["pequenas_reveladas"] == 0, "arestas": arestas}
