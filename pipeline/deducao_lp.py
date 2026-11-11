"""Ataque por programação linear: o menor e o maior valor de cada célula escondida, com todas as somas juntas.

O ataque por intervalos (deducao.py) aperta uma soma de cada vez, em cadeia. Ele não alcança o que só sai de
várias somas ao mesmo tempo: quatro células ocultas, as três partições delas em pares e o total, todos
visíveis, fixam as quatro em 3, e os intervalos ficam em 0 a 6. Aqui o sistema inteiro é um programa linear:
cada célula de cada versão é uma variável no intervalo que a tela deixa ver (o valor exato, a meia base do
arredondado ou de 0 ao infinito), cada aresta é uma igualdade (a célula grossa é a soma das finas), e a célula
que vale o mesmo nas duas versões é uma variável só.

Uma contagem está revelada quando o mínimo e o máximo, arredondados para dentro, coincidem num inteiro de 1 a
k-1, a mesma regra da auditoria independente. A diferença entre duas versões, do mesmo jeito, quando fica
exata entre 1 e k-1 em módulo.

Resolver dois programas por célula no Brasil inteiro levaria dias, e mesmo um programa só, com as duas versões
juntas, leva minutos. O ataque usa a forma do problema: as versões só se ligam pelas células que valem o mesmo
nas duas (período fechado). Cada versão sozinha é um bloco. Os passos:

1. Um ponto viável do conjunto, que já empurra as candidatas para baixo: uma versão resolvida sozinha, as
   células comuns presas no valor dela, e a outra resolvida em seguida. Se não der, o programa inteiro decide;
   se ele não tiver solução, as versões não fecham entre si.
2. Pontos de amostra do mesmo jeito, versão a versão, alternando qual vai primeiro: as candidatas para cima e,
   depois, em pares de direções sorteadas, uma e a oposta (semente fixa), para que cada candidata seja empurrada
   para os dois lados. Cada ponto montado assim é viável no programa inteiro. Um ponto com a célula em 0, ou em
   k ou mais, ou dois pontos com ela em inteiros diferentes provam que ela não está revelada.
3. O que sobra é conferido célula a célula, do mais barato ao mais caro: o bloco pequeno da célula sem as somas
   grandes (as de UF e do Brasil), um conjunto que contém o verdadeiro, que prova a revelação ou descarta; a
   versão com as células comuns presas (pontos viáveis, que só descartam); a versão dona de uma cópia livre das
   comuns (contém o verdadeiro); e o programa inteiro. Os passos que resolvem a versão inteira têm limite de
   células; o que passa dele, ou não termina, conta como inconclusivo, e inconclusivo conta contra a publicação.

Descartar com pontos viáveis é sempre seguro; revelação só se declara com um conjunto que contém o verdadeiro.
A relaxação é contínua: quando o intervalo contínuo não fixa um inteiro, o ataque não conclui nada, ainda que
só uma solução inteira exista.
"""
from __future__ import annotations

import time

import numpy as np

INF = 1 << 40
_METADE = INF // 2
# Teto só para os pontos de amostra, que precisam de objetivo limitado: maior que qualquer contagem do SIH.
TETO = float(2 ** 31)
EPS = 1e-6
OPCOES = {"presolve": True, "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9}
PARES_SORTEADOS = 3      # pares de amostras com sinais opostos
LINHA_GRANDE = 64        # soma com mais parcelas liga blocos pequenos: UF e Brasil
LIMITE_INTEIRO = 20      # células conferidas nas versões inteiras; o que passar disso é inconclusivo
TEMPO_INTEIRO = 1800.0   # segundos por resolução do programa inteiro


class SemSolucao(ValueError):
    """Nenhum valor satisfaz o que as versões mostram: elas não fecham entre si."""


def _abaixo(x: np.ndarray) -> np.ndarray:
    """Maior inteiro <= x, tolerando o erro numérico perto de um inteiro. Infinito continua infinito."""
    with np.errstate(invalid="ignore"):
        r = np.rint(x)
        return np.where(np.abs(x - r) < EPS, r, np.floor(x))


def _acima(x: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        r = np.rint(x)
        return np.where(np.abs(x - r) < EPS, r, np.ceil(x))


def _possivel(baixo: np.ndarray, alto: np.ndarray, k: int, diferenca) -> np.ndarray:
    """Se algum inteiro entre `baixo` e `alto` ainda pode ser uma revelação: de 1 a k-1, ou, nas diferenças
    (`diferenca` verdadeiro, por alvo), também de -(k-1) a -1."""
    positivo = np.maximum(baixo, 1) <= np.minimum(alto, k - 1)
    negativo = np.maximum(baixo, -(k - 1)) <= np.minimum(alto, -1)
    return positivo | (np.asarray(diferenca, bool) & negativo)


def _linprog(c, a, b, lo, hi, tempo=None):
    from scipy.optimize import linprog
    tem = a is not None and a.shape[0] > 0
    opcoes = OPCOES | ({"time_limit": tempo} if tempo else {})
    r = linprog(c, A_eq=a if tem else None, b_eq=b if tem else None, bounds=np.column_stack([lo, hi]),
                method="highs", options=opcoes)
    return (r.x if r.status == 0 else None), r.status


class Programa:
    """As igualdades e os limites de todas as versões, com as células iguais unidas e as fixas tiradas."""

    def __init__(self, versoes, arestas, iguais):
        """`versoes`: lista de (lo, hi), cada um {nó: array}, com os mesmos nós e tamanhos em todas.
        `arestas`: (nó fino, nó grosso, célula grossa de cada fina). `iguais`: (versão i, versão j, nó, máscara)."""
        from scipy import sparse
        nomes = list(versoes[0][0])
        self.tam = {n: int(versoes[0][0][n].size) for n in nomes}
        self.base, total = {}, 0
        for v in range(len(versoes)):
            for n in nomes:
                self.base[v, n] = total
                total += self.tam[n]
        lo = np.concatenate([np.asarray(versoes[v][0][n], np.float64) for v in range(len(versoes)) for n in nomes])
        hi = np.concatenate([np.asarray(versoes[v][1][n], np.float64) for v in range(len(versoes)) for n in nomes])
        hi[hi >= _METADE] = np.inf
        # Célula igual nas duas versões: uma variável só, no menor intervalo comum.
        rep = np.arange(total)
        for i, j, n, mascara in iguais:
            c = np.flatnonzero(mascara)
            rep[self.base[j, n] + c] = self.base[i, n] + c
        while not np.array_equal(rep[rep], rep):
            rep = rep[rep]
        np.maximum.at(lo, rep, lo.copy())
        np.minimum.at(hi, rep, hi.copy())
        lo, hi = lo[rep], hi[rep]
        if (lo > hi + EPS).any():
            raise SemSolucao(f"{int((lo > hi + EPS).sum())} célula(s) sem valor comum às versões")
        versao = np.repeat(np.arange(len(versoes)), sum(self.tam.values()))
        linhas, colunas, valores, r = [], [], [], 0
        versao_da_linha = []
        for v in range(len(versoes)):
            for fino, grosso, indice in arestas:
                g, f = self.tam[grosso], self.tam[fino]
                linhas += [r + np.arange(g), r + np.asarray(indice, np.int64)]
                colunas += [self.base[v, grosso] + np.arange(g), self.base[v, fino] + np.arange(f)]
                valores += [np.ones(g), -np.ones(f)]
                versao_da_linha.append(np.full(g, v))
                r += g
        cols = rep[np.concatenate(colunas)] if colunas else np.zeros(0, np.int64)
        a = sparse.csr_matrix((np.concatenate(valores) if valores else np.zeros(0),
                               (np.concatenate(linhas) if linhas else np.zeros(0, np.int64), cols)), shape=(r, total))
        a.sum_duplicates()
        # Variáveis representantes; as fixas (lo == hi) viram constante do lado direito.
        ativa = np.zeros(total, bool)
        ativa[rep] = True
        fixa = ativa & (hi - lo <= EPS)
        livre = np.flatnonzero(ativa & ~fixa)
        b = -(a @ np.where(fixa, lo, 0.0))
        a = a.tocsc()[:, livre].tocsr()
        a.eliminate_zeros()
        vazia = np.diff(a.indptr) == 0
        if (np.abs(b[vazia]) > EPS).any():
            raise SemSolucao(f"{int((np.abs(b[vazia]) > EPS).sum())} soma(s) de células exatas que não fecham")
        self.a, self.b = a[~vazia], b[~vazia]
        self.versao_da_linha = (np.concatenate(versao_da_linha) if versao_da_linha else np.zeros(0, np.int64))[~vazia]
        # Variável comum: representa células de mais de uma versão. As outras são de uma versão só.
        comum = np.zeros(total, bool)
        comum[rep[versao != versao[rep]]] = True
        self.versao, self.comum = versao[livre], comum[livre]
        self.lo, self.hi = lo[livre], hi[livre]
        self.mapa = np.full(total, -1, np.int64)
        self.mapa[livre] = np.arange(livre.size)
        self.rep, self.fixo = rep, np.where(fixa, lo, np.nan)
        self.variaveis, self.livres, self.resolucoes = total, int(livre.size), 0

    def termo(self, v: int, n: str, celulas: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(índice da variável livre ou -1, constante) de cada célula pedida."""
        g = self.rep[self.base[v, n] + celulas]
        idx = self.mapa[g]
        return idx, np.where(idx >= 0, 0.0, self.fixo[g])

    def resolver(self, c: np.ndarray, maximizar: bool = False, teto: bool = False):
        """Um ponto ótimo do programa inteiro (x) e o status do HiGHS: 0 ótimo, 2 inviável, 3 ilimitado,
        outro inconclusivo."""
        self.resolucoes += 1
        if not self.livres:
            return np.zeros(0), 0
        alto = np.minimum(self.hi, TETO) if teto else self.hi
        return _linprog(-c if maximizar else c, self.a, self.b, self.lo, alto, TEMPO_INTEIRO)

    def componentes(self) -> np.ndarray:
        """O bloco pequeno de cada variável: ligadas só pelas somas de até LINHA_GRANDE parcelas (quase sempre,
        um município). Sem as somas grandes, cada bloco é um conjunto que contém a projeção do verdadeiro."""
        if getattr(self, "_comp", None) is None:
            from scipy import sparse
            from scipy.sparse.csgraph import connected_components
            n = self.livres
            self._grande = np.diff(self.a.indptr) > LINHA_GRANDE
            pequenas = self.a[~self._grande].tocoo()
            grafo = sparse.coo_matrix((np.ones(pequenas.nnz), (pequenas.col, n + pequenas.row)),
                                      shape=(n + pequenas.shape[0],) * 2)
            self._comp = connected_components(grafo, directed=False)[1][:n]
            self._pequenas = self.a[~self._grande].tocsr()
            self._b_pequenas = self.b[~self._grande]
            self._linha_comp = self._comp[self._pequenas.indices[self._pequenas.indptr[:-1]]] if self._pequenas.shape[0] else np.zeros(0, np.int64)
        return self._comp

    def no_componente(self, c: np.ndarray, maximizar: bool):
        """O ótimo de `c` nos blocos pequenos das variáveis que ele usa, sem as somas grandes: um limite que vale
        para o verdadeiro. None se ilimitado ou não resolvido."""
        comp = self.componentes()
        usados = np.unique(comp[np.flatnonzero(c)])
        idx = np.flatnonzero(np.isin(comp, usados))
        linhas = np.isin(self._linha_comp, usados)
        self.resolucoes += 1
        xk, _ = _linprog(-c[idx] if maximizar else c[idx], self._pequenas[linhas][:, idx], self._b_pequenas[linhas],
                         self.lo[idx], self.hi[idx])
        return None if xk is None else float(c[idx] @ xk)

    def blocos(self):
        """Por versão: as variáveis só dela, as comuns que aparecem nas somas dela e as somas."""
        saida = []
        for v in np.unique(self.versao_da_linha):
            linhas = self.versao_da_linha == v
            a = self.a[linhas]
            proprias = np.flatnonzero((self.versao == v) & ~self.comum)
            usadas = np.zeros(self.livres, bool)
            usadas[a.indices] = True
            comuns = np.flatnonzero(usadas & self.comum)
            saida.append({"versao": int(v), "proprias": proprias, "comuns": comuns, "b": self.b[linhas],
                          "a_proprias": a[:, proprias], "a_comuns": a[:, comuns]})
        return saida

    def no_bloco(self, bloco, c: np.ndarray, x: np.ndarray, maximizar: bool, teto: bool, comuns_livres: bool):
        """Resolve um bloco com o objetivo `c` (indexado no programa todo) e escreve o resultado em `x`.

        Com `comuns_livres`, as células comuns são variáveis do bloco: o conjunto do bloco sozinho, que contém
        a projeção do verdadeiro. Sem, elas ficam no valor que `x` já tem. Devolve (o ótimo do objetivo, status);
        o ótimo é None quando o bloco não resolve ou o objetivo é ilimitado."""
        from scipy import sparse
        alto = np.minimum(self.hi, TETO) if teto else self.hi
        self.resolucoes += 1
        if comuns_livres:
            idx = np.concatenate([bloco["proprias"], bloco["comuns"]])
            a = sparse.hstack([bloco["a_proprias"], bloco["a_comuns"]]).tocsr()
            b = bloco["b"]
        else:
            idx, a = bloco["proprias"], bloco["a_proprias"]
            b = bloco["b"] - bloco["a_comuns"] @ x[bloco["comuns"]]
        if not idx.size:
            # Sem variável: o bloco só confere que as somas fecham.
            return (0.0, 0) if not (np.abs(b) > EPS).any() else (None, 2)
        # O teto só entra se o objetivo for ilimitado sem ele: limites finitos enormes deixam o HiGHS lento.
        xk, st = _linprog(-c[idx] if maximizar else c[idx], a, b, self.lo[idx], self.hi[idx])
        if st == 3 and teto:
            xk, st = _linprog(-c[idx] if maximizar else c[idx], a, b, self.lo[idx], alto[idx])
        if xk is None:
            return None, st
        x[idx] = xk
        return float(c[idx] @ xk), st


def atacar(versoes, arestas, iguais, escondidas, k: int, pares, registrar=None) -> dict:
    """Contagens reveladas por versão e diferenças reveladas por par, nó a nó.

    `escondidas`: por versão, {nó: máscara} das células sem valor à vista. `pares`: [(i, j)] de versões
    comparadas. `registrar`, se dado, recebe uma linha de texto a cada etapa, com o tempo e quantas candidatas
    sobram. Devolve {"reveladas": [{nó: n}], "diferencas": {"i-j": {nó: n}}, "detalhe": {...}}.
    """
    inicio = time.perf_counter()
    registrar = registrar or (lambda texto: None)
    prog = Programa(versoes, arestas, iguais)
    # Alvos: valor = constante + x[b] - x[a] (índices -1 quando a parcela é fixa ou não existe).
    a_idx, b_idx, const, tipo, rotulo = [], [], [], [], []
    for v, mascaras in enumerate(escondidas):
        for n, m in mascaras.items():
            c = np.flatnonzero(m)
            idx, k0 = prog.termo(v, n, c)
            a_idx.append(np.full(c.size, -1))
            b_idx.append(idx)
            const.append(k0)
            tipo.append(np.zeros(c.size, bool))
            rotulo += [("v", v, n)] * c.size
    for i, j in pares:
        for n in versoes[0][0]:
            c = np.arange(prog.tam[n])
            ia, ca = prog.termo(i, n, c)
            ib, cb = prog.termo(j, n, c)
            a_idx.append(ia)
            b_idx.append(ib)
            const.append(cb - ca)
            tipo.append(np.ones(c.size, bool))
            rotulo += [("d", f"{i}-{j}", n)] * c.size
    ia, ib = np.concatenate(a_idx).astype(np.int64), np.concatenate(b_idx).astype(np.int64)
    const, dif = np.concatenate(const), np.concatenate(tipo)
    # Mesma variável dos dois lados (célula igual nas duas versões): a diferença é a constante.
    mesma = (ia == ib) & (ia >= 0)
    ia[mesma], ib[mesma] = -1, -1

    def valor(x):
        # O índice -1 cai no zero acrescentado no fim: parcela fixa ou ausente.
        xx = np.append(x, 0.0)
        return const + xx[ib] - xx[ia]

    # Limites que já vêm das variáveis, sem resolver nada.
    lo_v, hi_v = np.append(prog.lo, 0.0), np.append(prog.hi, 0.0)
    vivo = _possivel(_acima(const + lo_v[ib] - hi_v[ia]), _abaixo(const + hi_v[ib] - lo_v[ia]), k, dif)
    fixo = vivo & (ia < 0) & (ib < 0)
    revelado = fixo & _possivel(np.rint(const), np.rint(const), k, dif)
    vivo &= ~fixo
    minimo, maximo = np.full(const.size, np.inf), np.full(const.size, -np.inf)
    detalhe = {"variaveis": prog.variaveis, "variaveis_livres": prog.livres, "igualdades": int(prog.a.shape[0]),
               "alvos": int(const.size), "amostras": 0, "conferidas_uma_a_uma": 0, "conferidas_nas_versoes": 0,
               "conferidas_no_programa_inteiro": 0,
               "inconclusivas": 0}

    def anotar(val):
        nonlocal vivo
        minimo[vivo] = np.minimum(minimo[vivo], val[vivo])
        maximo[vivo] = np.maximum(maximo[vivo], val[vivo])
        # Revelada exige um inteiro entre o maior inteiro abaixo do máximo visto e o menor acima do mínimo visto.
        vivo &= _possivel(_abaixo(maximo), _acima(minimo), k, dif)

    def resumo():
        detalhe["resolucoes"] = prog.resolucoes
        detalhe["segundos"] = round(time.perf_counter() - inicio, 2)
        reveladas, diferencas = [dict() for _ in versoes], {f"{i}-{j}": {} for i, j in pares}
        for t in np.flatnonzero(revelado):
            quem, onde, n = rotulo[t]
            alvo = reveladas[onde] if quem == "v" else diferencas[onde]
            alvo[n] = alvo.get(n, 0) + 1
        return {"reveladas": reveladas, "diferencas": diferencas, "detalhe": detalhe}

    if not prog.livres:
        return resumo()
    blocos = prog.blocos()
    detalhe["blocos"] = len(blocos)
    dono = {int(b["versao"]): i for i, b in enumerate(blocos)}

    def ponto(c, maximizar, primeiro, base):
        """Um ponto viável do programa inteiro: o bloco `primeiro` com as células comuns livres, os outros com
        elas presas no valor que ele deu. Se um bloco seguinte não fecha com esse valor, todos ficam presos no de
        `base`. Devolve None se nem assim der."""
        x = base.copy()
        for n_, i in enumerate([primeiro] + [j for j in range(len(blocos)) if j != primeiro]):
            otimo, _ = prog.no_bloco(blocos[i], c, x, maximizar, teto=True, comuns_livres=n_ == 0)
            if otimo is None:
                if n_ == 0 or base is None:
                    return None
                x = base.copy()
                for b in blocos:
                    if prog.no_bloco(b, c, x, maximizar, teto=True, comuns_livres=False)[0] is None:
                        return None
                return x
        return x

    def objetivo(pesos, quais):
        c = np.zeros(prog.livres)
        np.add.at(c, ib[quais & (ib >= 0)], pesos[quais & (ib >= 0)])
        np.add.at(c, ia[quais & (ia >= 0)], -pesos[quais & (ia >= 0)])
        return c

    # 1. Um ponto viável, que já é a primeira amostra (as candidatas o mais baixo possível): versão a versão; se
    # não der, o programa inteiro decide.
    t0 = time.perf_counter()
    inicial = np.clip(np.zeros(prog.livres), prog.lo, np.minimum(prog.hi, TETO))
    x0 = ponto(objetivo(np.ones(const.size), vivo), False, 0, inicial)
    if x0 is None:
        x0, status = prog.resolver(np.zeros(prog.livres))
        if status == 2:
            raise SemSolucao("o programa linear não tem solução")
        if x0 is None:
            detalhe["inconclusivas"] = int(vivo.sum())
            return resumo()
    anotar(valor(x0))
    detalhe["amostras"] = 1
    registrar(f"ponto viável: {time.perf_counter() - t0:.1f} s, {prog.livres} variáveis livres em {len(blocos)} bloco(s), "
              f"{int(vivo.sum())} candidata(s) de {const.size}")

    # 2. Pontos de amostra: as candidatas para cima e em direções sorteadas, alternando o primeiro bloco.
    # Nos pares, o mesmo sorteio de sinais e o oposto: cada candidata é empurrada para os dois lados.
    rng = np.random.default_rng(20261110)
    sinais = None
    for rodada in range(1, 2 + 2 * PARES_SORTEADOS):
        if not vivo.any():
            break
        t0 = time.perf_counter()
        if rodada == 1:
            pesos = np.ones(const.size)
        elif rodada % 2 == 0:
            sinais = rng.choice([-1.0, 1.0], size=const.size)
            pesos = sinais
        else:
            pesos = -sinais
        x = ponto(objetivo(pesos, vivo), True, rodada % len(blocos), x0)
        detalhe["amostras"] += 1
        if x is not None:
            anotar(valor(x))
        registrar(f"amostra {detalhe['amostras']}: {time.perf_counter() - t0:.1f} s, {int(vivo.sum())} candidata(s) de {const.size}")

    # 3. Célula a célula, do mais barato ao mais caro: o bloco pequeno sem as somas grandes (contém o verdadeiro:
    # prova revelação ou descarta); a versão com as comuns presas (pontos viáveis: só descarta); a versão com as
    # comuns soltas (contém o verdadeiro); e o programa inteiro. Os passos caros têm limite: além dele, inconclusiva.
    def decidir(menor, maior, t):
        baixo, alto = _acima(np.array([menor + const[t]])), _abaixo(np.array([maior + const[t]]))
        if not _possivel(baixo, alto, k, dif[t])[0]:
            vivo[t] = False
        elif baixo[0] == alto[0]:
            revelado[t], vivo[t] = True, False
        return not vivo[t]

    for t in np.flatnonzero(vivo):
        detalhe["conferidas_uma_a_uma"] += 1
        so = np.zeros(const.size, bool)
        so[t] = True
        c = objetivo(np.ones(const.size), so)
        menor, maior = prog.no_componente(c, False), prog.no_componente(c, True)
        if decidir(-np.inf if menor is None else menor, np.inf if maior is None else maior, t):
            continue
        if detalhe["conferidas_nas_versoes"] >= LIMITE_INTEIRO:
            detalhe["inconclusivas"] += 1
            continue
        detalhe["conferidas_nas_versoes"] += 1
        # Cada parcela do alvo fica com o bloco dono dela: a célula comum entra uma vez só.
        partes = {}
        for v, sinal in ((ib[t], 1.0), (ia[t], -1.0)):
            if v >= 0:
                parte = partes.setdefault(dono[int(prog.versao[v])], np.zeros(prog.livres))
                parte[v] += sinal
        t0 = time.perf_counter()
        for maximizar in (False, True):
            x = x0.copy()
            if all(prog.no_bloco(blocos[i], parte, x, maximizar, teto=True, comuns_livres=False)[0] is not None
                   for i, parte in partes.items()):
                anotar(valor(x))
        if not vivo[t]:
            registrar(f"{rotulo[t]}: descartada nas versões em {time.perf_counter() - t0:.1f} s")
            continue
        extremos = []
        for maximizar in (False, True):
            soma = 0.0
            for i, parte in partes.items():
                otimo, _ = prog.no_bloco(blocos[i], parte, x0.copy(), maximizar, teto=False, comuns_livres=True)
                if otimo is None:
                    soma = np.inf if maximizar else -np.inf
                    break
                soma += otimo
            extremos.append(soma)
        if decidir(extremos[0], extremos[1], t):
            registrar(f"{rotulo[t]}: decidida nas versões em {time.perf_counter() - t0:.1f} s")
            continue
        detalhe["conferidas_no_programa_inteiro"] += 1
        xmin, s1 = prog.resolver(c)
        xmax, s2 = prog.resolver(c, maximizar=True)
        registrar(f"programa inteiro para {rotulo[t]}: {time.perf_counter() - t0:.1f} s, status {s1} e {s2}")
        if s1 not in (0, 3) or s2 not in (0, 3):
            detalhe["inconclusivas"] += 1
        elif s1 == 0 and s2 == 0:
            menor, maior = _acima(np.array([c @ xmin + const[t]])), _abaixo(np.array([c @ xmax + const[t]]))
            if menor[0] == maior[0] and _possivel(menor, maior, k, dif[t])[0]:
                revelado[t] = True
    return resumo()
