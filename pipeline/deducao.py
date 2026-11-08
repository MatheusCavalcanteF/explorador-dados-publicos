"""Teste de dedução em cadeia: age como quem tenta descobrir uma contagem pequena a partir do publicado.

O sistema é um conjunto de nós, cada um uma tabela de contagens por chave, e de arestas, cada uma
dizendo que uma célula de um nó grosso é a soma de células de um nó fino (o mês é a soma dos dias,
a UF é a soma dos municípios). Os nós publicados entram com o que a tela mostra; os outros, que
ninguém publica mas qualquer um pode somar, entram como incógnitas.

Cada célula tem um intervalo [lo, hi] do que ela pode valer. O ataque aperta os intervalos pelas
somas, em cadeia, até nada mudar: numa aresta, a célula grossa fica entre a soma dos mínimos e a dos
máximos das finas, e cada fina fica entre o total menos o máximo das outras e o total menos o mínimo
delas. Isso generaliza a dedução de uma incógnita por linha, e é sólido: o valor verdadeiro sempre
fica dentro do intervalo, o que os testes conferem.

Quando o motivo da célula oculta é publicado, ele entra no domínio: a contagem pequena está entre 0 e
k-1 (0 quando a regra oculta pelas AIHs e não há internação), e a complementar está fora de 1 a k-1.
Numa margem com uma oculta de cada tipo e soma 6, a complementar só pode ser 5 ou 6, e a pequena, 0 ou
1; com soma 5, as duas ficam exatas (5 e 0). O site não publica o motivo (decidido em 08/11/2026): a
oculta entra como LIVRE, de 0 ao infinito, e o estado PEQUENA serve para medir o efeito do motivo.

Uma contagem pequena é revelada quando o intervalo vira um ponto entre 1 e k-1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

INF = 1 << 40
_METADE = INF // 2

VISIVEL, PEQUENA, COMPLEMENTAR, LIVRE = 0, 1, 2, 3


@dataclass
class No:
    nome: str
    lo: np.ndarray
    hi: np.ndarray
    lacuna: np.ndarray            # o valor não pode estar entre 1 e k-1
    publicado: bool
    estado: np.ndarray | None = None   # VISIVEL, PEQUENA, COMPLEMENTAR ou LIVRE, por célula
    valor: np.ndarray | None = None    # o verdadeiro, quando se conhece: só para medir e conferir


@dataclass
class Sistema:
    k: int
    nos: dict[str, No] = field(default_factory=dict)
    arestas: list[tuple[str, str, np.ndarray]] = field(default_factory=list)  # (fino, grosso, célula grossa de cada fina)

    def no(self, nome: str, estado: np.ndarray, valor: np.ndarray | None, publicado: bool,
           lo: np.ndarray | None = None, hi: np.ndarray | None = None) -> No:
        """Domínio inicial pelo estado da célula. `lo` e `hi` explícitos servem a valores arredondados."""
        estado = np.asarray(estado, dtype=np.int8)
        n = estado.size
        if lo is None:
            lo = np.zeros(n, dtype=np.int64)
            hi = np.full(n, INF, dtype=np.int64)
            visivel = estado == VISIVEL
            if visivel.any():
                lo[visivel] = valor[visivel]
                hi[visivel] = valor[visivel]
            hi[estado == PEQUENA] = self.k - 1
        no = No(nome, np.asarray(lo, dtype=np.int64).copy(), np.asarray(hi, dtype=np.int64).copy(),
                estado == COMPLEMENTAR, publicado, estado,
                None if valor is None else np.asarray(valor, dtype=np.int64))
        self._normalizar(no)
        self.nos[nome] = no
        return no

    def aresta(self, fino: str, grosso: str, indice: np.ndarray) -> None:
        indice = np.asarray(indice, dtype=np.int64)
        if indice.size != self.nos[fino].lo.size:
            raise ValueError(f"Aresta {fino} -> {grosso}: índice com tamanho errado")
        if indice.size and (indice.min() < 0 or indice.max() >= self.nos[grosso].lo.size):
            raise ValueError(f"Aresta {fino} -> {grosso}: célula grossa inexistente")
        self.arestas.append((fino, grosso, indice))

    def _normalizar(self, no: No) -> bool:
        """Aplica a lacuna e confere que o intervalo não ficou vazio. Devolve se algo mudou."""
        lo, hi = no.lo, no.hi
        antes = (lo.copy(), hi.copy())
        np.minimum(hi, INF, out=hi)
        hi[hi >= _METADE] = INF
        if no.lacuna.any():
            sobe = no.lacuna & (lo >= 1) & (lo <= self.k - 1)
            lo[sobe] = self.k
            desce = no.lacuna & (hi >= 1) & (hi <= self.k - 1)
            hi[desce] = 0
        vazio = lo > hi
        if vazio.any():
            raise ValueError(f"Nó {no.nome}: {int(vazio.sum())} célula(s) sem valor possível; o domínio está errado")
        return not (np.array_equal(antes[0], lo) and np.array_equal(antes[1], hi))

    def propagar(self, max_voltas: int = 200) -> int:
        """Aperta os intervalos até parar. Devolve o número de voltas."""
        for volta in range(1, max_voltas + 1):
            mudou = False
            for fino, grosso, indice in self.arestas:
                f, g = self.nos[fino], self.nos[grosso]
                if not indice.size:
                    continue
                n = g.lo.size
                s_lo = np.rint(np.bincount(indice, weights=f.lo, minlength=n)).astype(np.int64)
                s_hi = np.rint(np.bincount(indice, weights=f.hi, minlength=n)).astype(np.int64)
                g_lo = np.maximum(g.lo, s_lo)
                g_hi = np.minimum(g.hi, s_hi)
                f_lo = np.maximum(f.lo, g_lo[indice] - (s_hi[indice] - f.hi))
                f_hi = np.minimum(f.hi, g_hi[indice] - (s_lo[indice] - f.lo))
                # Um máximo infinito não aperta nada: a conta acima daria um número enorme, não infinito.
                f_hi[(g_hi[indice] >= _METADE)] = f.hi[(g_hi[indice] >= _METADE)]
                f_lo[(s_hi[indice] - f.hi) >= _METADE] = f.lo[(s_hi[indice] - f.hi) >= _METADE]
                for no, lo, hi in ((g, g_lo, g_hi), (f, f_lo, f_hi)):
                    if not (np.array_equal(lo, no.lo) and np.array_equal(hi, no.hi)):
                        no.lo[:], no.hi[:] = lo, hi
                        mudou = True
                    mudou |= self._normalizar(no)
            if not mudou:
                return volta
        raise RuntimeError(f"Propagação não parou em {max_voltas} voltas")

    def conferir_solidez(self) -> None:
        """O valor verdadeiro tem de estar dentro do intervalo. Se não estiver, o ataque está errado."""
        for no in self.nos.values():
            if no.valor is None:
                continue
            fora = (no.valor < no.lo) | (no.valor > no.hi)
            if fora.any():
                raise AssertionError(f"Nó {no.nome}: {int(fora.sum())} célula(s) com o valor fora do intervalo deduzido")

    def reveladas(self) -> dict[str, dict]:
        """Por nó: células ocultas ou não publicadas cujo valor exato foi descoberto, e quantas são de 1 a k-1."""
        saida = {}
        for nome, no in self.nos.items():
            escondida = no.estado != VISIVEL
            exata = escondida & (no.lo == no.hi)
            pequena = exata & (no.lo >= 1) & (no.lo <= self.k - 1)
            # Sem chegar ao valor exato, o ataque ainda pode estreitar uma oculta pequena para dois valores
            # possíveis, como 0 ou 1. Não é o critério do plano, mas fica medido.
            estreitada = (no.estado == PEQUENA) & ~exata & (no.hi - no.lo <= 1)
            saida[nome] = {"celulas": int(no.lo.size), "escondidas": int(escondida.sum()),
                           "exatas": int(exata.sum()), "pequenas_reveladas": int(pequena.sum()),
                           "pequenas_estreitadas": int(estreitada.sum())}
        return saida

    def total_pequenas_reveladas(self) -> int:
        return sum(r["pequenas_reveladas"] for r in self.reveladas().values())


def atacar_juntos(sistemas: list[Sistema], iguais: list[tuple[int, int, str, np.ndarray]], max_voltas: int = 50) -> int:
    """Quem guarda várias versões sabe que algumas células não mudaram entre elas: as de período que já
    tinha fechado na versão mais nova do par, porque nenhum arquivo com altas daquele período foi
    republicado. Alterna o aperto de cada versão com a interseção dos intervalos dessas células, até nada
    mudar. Os sistemas têm as mesmas chaves, na mesma ordem; `iguais` traz (versão i, versão j, nó,
    máscara das células iguais). Se a interseção ficar vazia, a premissa de igualdade estava errada, e o
    erro diz onde. Devolve o número de voltas.
    """
    for volta in range(1, max_voltas + 1):
        for s in sistemas:
            s.propagar()
        mudou = False
        for i, j, nome, mascara in iguais:
            if not mascara.any():
                continue
            a, b = sistemas[i].nos[nome], sistemas[j].nos[nome]
            lo = np.maximum(a.lo[mascara], b.lo[mascara])
            hi = np.minimum(a.hi[mascara], b.hi[mascara])
            for s, no in ((sistemas[i], a), (sistemas[j], b)):
                if not (np.array_equal(no.lo[mascara], lo) and np.array_equal(no.hi[mascara], hi)):
                    no.lo[mascara], no.hi[mascara] = lo, hi
                    s._normalizar(no)
                    mudou = True
        if not mudou:
            return volta
    raise RuntimeError(f"Ataque entre versões não parou em {max_voltas} voltas")


def _intervalos_da_diferenca(a, b) -> tuple[dict, dict, dict]:
    lo, hi, direta = {}, {}, {}
    for nome in b:
        a_lo, a_hi = a[nome]
        b_lo, b_hi = b[nome]
        lo[nome] = np.where((a_hi >= _METADE), -INF, b_lo - a_hi)
        hi[nome] = np.where((b_hi >= _METADE), INF, b_hi - a_lo)
        direta[nome] = (a_lo == a_hi) & (b_lo == b_hi)
    return lo, hi, direta


def _contar_diferencas(lo: dict, hi: dict, direta: dict, k: int) -> dict[str, dict]:
    saida = {}
    for nome in lo:
        exata = lo[nome] == hi[nome]
        pequena = exata & (np.abs(lo[nome]) >= 1) & (np.abs(lo[nome]) <= k - 1)
        saida[nome] = {"celulas": int(exata.size), "diferencas_exatas": int(exata.sum()),
                       "pequenas_diretas": int((pequena & direta[nome]).sum()),
                       "pequenas_pela_cadeia": int((pequena & ~direta[nome]).sum()),
                       "mudaram": int((exata & (lo[nome] != 0)).sum())}
    return saida


def diferencas(a: dict[str, tuple[np.ndarray, np.ndarray]], b: dict[str, tuple[np.ndarray, np.ndarray]],
               arestas: list[tuple[str, str, np.ndarray]], k: int, max_voltas: int = 200) -> dict[str, dict]:
    """Quem guarda duas versões publicadas conhece a diferença entre elas onde as duas são exatas, e pode
    deduzir o resto pelas mesmas somas, porque a diferença também respeita as arestas.

    `a` e `b` dão, por nó, (lo, hi) já propagados de cada versão, alinhados nas mesmas chaves (a célula
    que não existe numa versão vale 0 nela). Devolve, por nó, quantas diferenças exatas de 1 a k-1 em
    módulo aparecem, separando as que vêm direto de duas células exatas das que a cadeia revelou.
    """
    lo, hi, direta = _intervalos_da_diferenca(a, b)
    _propagar_diferencas(lo, hi, arestas, max_voltas)
    return _contar_diferencas(lo, hi, direta, k)


def _somar(a_lo, a_hi, b_lo, b_hi, sinal: int):
    """Intervalo de a + sinal*b, com os infinitos tratados como infinitos."""
    if sinal < 0:
        b_lo, b_hi = -b_hi, -b_lo
    lo = np.where((a_lo <= -_METADE) | (b_lo <= -_METADE), -INF, a_lo + b_lo)
    hi = np.where((a_hi >= _METADE) | (b_hi >= _METADE), INF, a_hi + b_hi)
    return lo, hi


def diferencas_em_sequencia(versoes: list[dict[str, tuple[np.ndarray, np.ndarray]]],
                            arestas: list[tuple[str, str, np.ndarray]], k: int, max_voltas: int = 50) -> dict:
    """Três versões seguidas, guardadas por quem tenta deduzir: as diferenças de cada par respeitam as
    arestas, e também d(1,3) = d(1,2) + d(2,3). Aperta os três pares juntos, pelas somas e por essa
    identidade, até nada mudar. Devolve, por par ("0-1", "1-2", "0-2"), a contagem de diferenças por nó.
    """
    pares = [(0, 1), (1, 2), (0, 2)]
    estado = {p: _intervalos_da_diferenca(versoes[p[0]], versoes[p[1]]) for p in pares}
    for _ in range(max_voltas):
        for p in pares:
            _propagar_diferencas(estado[p][0], estado[p][1], arestas)
        mudou = False
        for nome in versoes[0]:
            (l01, h01), (l12, h12), (l02, h02) = ((estado[p][0][nome], estado[p][1][nome]) for p in pares)
            for alvo, (lo, hi) in (((0, 2), _somar(l01, h01, l12, h12, 1)), ((0, 1), _somar(l02, h02, l12, h12, -1)),
                                   ((1, 2), _somar(l02, h02, l01, h01, -1))):
                novo_lo = np.maximum(estado[alvo][0][nome], lo)
                novo_hi = np.minimum(estado[alvo][1][nome], hi)
                if (novo_lo > novo_hi).any():
                    raise ValueError(f"Nó {nome}: diferenças sem valor possível; as versões estão desalinhadas")
                if not (np.array_equal(novo_lo, estado[alvo][0][nome]) and np.array_equal(novo_hi, estado[alvo][1][nome])):
                    estado[alvo][0][nome], estado[alvo][1][nome] = novo_lo, novo_hi
                    mudou = True
        if not mudou:
            return {f"{p[0]}-{p[1]}": _contar_diferencas(*estado[p], k) for p in pares}
    raise RuntimeError(f"Diferenças em sequência não pararam em {max_voltas} voltas")


def _propagar_diferencas(lo: dict, hi: dict, arestas: list[tuple[str, str, np.ndarray]], max_voltas: int = 200) -> int:
    """Aperta os intervalos das diferenças pelas somas, em cadeia. Altera `lo` e `hi` no lugar."""
    for volta in range(1, max_voltas + 1):
        mudou = False
        for fino, grosso, indice in arestas:
            if not indice.size:
                continue
            n = lo[grosso].size
            fl, fh, gl, gh = lo[fino], hi[fino], lo[grosso], hi[grosso]
            inf_lo = np.bincount(indice, weights=(fl <= -_METADE), minlength=n)
            inf_hi = np.bincount(indice, weights=(fh >= _METADE), minlength=n)
            s_lo = np.rint(np.bincount(indice, weights=np.where(fl <= -_METADE, 0, fl), minlength=n)).astype(np.int64)
            s_hi = np.rint(np.bincount(indice, weights=np.where(fh >= _METADE, 0, fh), minlength=n)).astype(np.int64)
            n_gl = np.where(inf_lo > 0, gl, np.maximum(gl, s_lo))
            n_gh = np.where(inf_hi > 0, gh, np.minimum(gh, s_hi))
            # Para cada fina: total menos as outras, só quando as outras são todas finitas.
            outras_hi_inf = inf_hi[indice] - (fh >= _METADE)
            outras_lo_inf = inf_lo[indice] - (fl <= -_METADE)
            outras_hi = s_hi[indice] - np.where(fh >= _METADE, 0, fh)
            outras_lo = s_lo[indice] - np.where(fl <= -_METADE, 0, fl)
            pode_lo = (outras_hi_inf == 0) & (n_gl[indice] > -_METADE)
            pode_hi = (outras_lo_inf == 0) & (n_gh[indice] < _METADE)
            n_fl = np.where(pode_lo, np.maximum(fl, n_gl[indice] - outras_hi), fl)
            n_fh = np.where(pode_hi, np.minimum(fh, n_gh[indice] - outras_lo), fh)
            for nome, novo_lo, novo_hi in ((grosso, n_gl, n_gh), (fino, n_fl, n_fh)):
                if (novo_lo > novo_hi).any():
                    raise ValueError(f"Nó {nome}: diferença sem valor possível; as versões estão desalinhadas")
                if not (np.array_equal(novo_lo, lo[nome]) and np.array_equal(novo_hi, hi[nome])):
                    lo[nome], hi[nome] = novo_lo, novo_hi
                    mudou = True
        if not mudou:
            return volta
    raise RuntimeError(f"Propagação das diferenças não parou em {max_voltas} voltas")
