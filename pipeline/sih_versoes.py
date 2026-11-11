"""Ataque conjunto: a versão no ar e a candidata, vistas por quem guardou as duas.

É uma etapa do pipeline, entre a supressão do ano e a gravação da partição. Se revelar alguma contagem, o
ano não é gravado e nada é publicado (bases.sih.versoes.ataque_conjunto_obrigatorio).

As duas versões entram como a superfície as mostra (bases.sih.superficie, decidido em 10/11/2026): a versão no
ar, lida do arquivo publicado com o site; a candidata, montada das mesmas tabelas que vão para a página. Nada
além da superfície é público, então nada além dela entra no ataque.

A etapa tem duas metades, para que o motor possa ser trocado sem mexer no resto:

1. `montar` descreve o problema sem dizer como resolvê-lo (Problema): as células de cada tabela, alinhadas
   nas mesmas chaves nas duas versões; o intervalo que cada versão deixa ver em cada célula; as somas que
   ligam as tabelas (arestas), inclusive as que ninguém publica e qualquer um pode montar; e as células que
   quem lê sabe serem iguais nas duas versões, porque o período já tinha fechado.
2. Um motor (Motor) recebe o Problema e devolve um Resultado: quantas contagens de 1 a k-1 ficam exatas em
   cada versão, e quantas diferenças exatas de 1 a k-1 aparecem entre elas. Há dois em MOTORES, e o catálogo
   manda rodar os dois (versoes.motores); todos precisam dar zero. "intervalos" aperta intervalos pelas
   somas, em cadeia (deducao.atacar_juntos e deducao.diferencas); "programacao_linear" acha o mínimo e o
   máximo de cada célula com todas as somas juntas (deducao_lp).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import deducao, sih_deducao, sih_superficie, sih_tabelas as tab
from .contrato import ErroDeContrato

# Por medida: a coluna do valor, a da célula oculta e a do arredondamento, nas tabelas da superfície.
COLUNAS = sih_superficie.COLUNAS
MOTOR_PADRAO = "intervalos"
# Quem mede pode ligar aqui o registro do progresso do motor por programação linear (uma linha por etapa).
REGISTRAR = None


class ErroDeVersoes(ErroDeContrato):
    """A versão no ar e a candidata não podem ser as duas verdadeiras, ou a versão no ar não pode ser refeita."""


@dataclass
class Versao:
    """O que uma versão deixa ver, por nó (nome da tabela), nas chaves comuns às versões.

    `lo` e `hi` são o intervalo de cada célula para quem lê: iguais no valor exato, meia base para cada lado
    no arredondado, de 0 ao infinito (deducao.INF) na oculta e na soma que ninguém publica. `escondida` marca
    as que não aparecem com valor. `valor` é o verdadeiro, quando o pipeline o tem: só para o motor conferir
    que nunca o tira do intervalo.
    """
    rotulo: str
    lo: dict[str, np.ndarray]
    hi: dict[str, np.ndarray]
    escondida: dict[str, np.ndarray]
    publicados: frozenset[str]
    valor: dict[str, np.ndarray] | None = None


@dataclass
class Problema:
    k: int
    medida: str
    versoes: list[Versao]
    # (nó fino, nó grosso, posição da célula grossa de cada fina): a grossa é a soma das finas.
    arestas: list[tuple[str, str, np.ndarray]]
    # (versão i, versão j, nó, máscara): células que valem o mesmo nas duas.
    iguais: list[tuple[int, int, str, np.ndarray]]


@dataclass
class Resultado:
    motor: str
    reveladas: list[dict[str, int]]            # por versão: nó -> contagens de 1 a k-1 que ficaram exatas
    diferencas: dict[str, dict[str, int]]      # por par "i-j": nó -> diferenças exatas de 1 a k-1, em módulo
    detalhe: dict = field(default_factory=dict)
    inconclusivas: int = 0                     # células que o motor não conseguiu decidir: contam contra

    @property
    def total(self) -> int:
        return (sum(sum(v.values()) for v in self.reveladas) + sum(sum(v.values()) for v in self.diferencas.values())
                + self.inconclusivas)


Motor = Callable[[Problema], Resultado]


def por_intervalos(p: Problema) -> Resultado:
    """Aperta os intervalos de cada versão pelas somas, cruza as células iguais e repete até nada mudar."""
    sistemas = []
    try:
        for v in p.versoes:
            s = deducao.Sistema(p.k)
            for nome in v.lo:
                estado = np.where(v.escondida[nome], deducao.LIVRE, deducao.VISIVEL)
                s.no(nome, estado, None if v.valor is None else v.valor[nome], nome in v.publicados, lo=v.lo[nome], hi=v.hi[nome])
            for fino, grosso, indice in p.arestas:
                s.aresta(fino, grosso, indice)
            sistemas.append(s)
        voltas = deducao.atacar_juntos(sistemas, p.iguais)
        intervalos = [{nome: (no.lo, no.hi) for nome, no in s.nos.items()} for s in sistemas]
        pares = {f"{i}-{i + 1}": deducao.diferencas(intervalos[i], intervalos[i + 1], p.arestas, p.k)
                 for i in range(len(sistemas) - 1)}
    except ValueError as erro:
        # Intervalo vazio: o que as versões mostram não fecha, sozinhas ou juntas.
        raise ErroDeVersoes(f"As versões não fecham entre si ({p.medida}): {erro}") from None
    for s in sistemas:
        s.conferir_solidez()
    reveladas = [{nome: r["pequenas_reveladas"] for nome, r in s.reveladas().items() if r["pequenas_reveladas"]}
                 for s in sistemas]
    diferencas = {par: {nome: r["pequenas_diretas"] + r["pequenas_pela_cadeia"] for nome, r in nos.items()
                        if r["pequenas_diretas"] + r["pequenas_pela_cadeia"]} for par, nos in pares.items()}
    return Resultado("intervalos", reveladas, diferencas, {"voltas": voltas})


def conferir_valores(p: Problema) -> None:
    """O valor verdadeiro, onde o pipeline o tem, satisfaz o que o Problema diz: fica no intervalo da tela e
    fecha cada soma. Se não satisfizer, o Problema está errado, e nenhum motor deve rodar sobre ele."""
    for v in p.versoes:
        if v.valor is None:
            continue
        for nome, valor in v.valor.items():
            fora = (valor < v.lo[nome]) | ((valor > v.hi[nome]) & (v.hi[nome] < deducao.INF // 2))
            if fora.any():
                raise AssertionError(f"{v.rotulo}, {nome}: {int(fora.sum())} célula(s) com o valor fora do intervalo da tela")
        for fino, grosso, indice in p.arestas:
            soma = np.bincount(indice, weights=v.valor[fino], minlength=v.valor[grosso].size)
            if not np.array_equal(np.rint(soma).astype(np.int64), v.valor[grosso]):
                raise AssertionError(f"{v.rotulo}: {grosso} não é a soma de {fino}")


def por_programacao_linear(p: Problema) -> Resultado:
    """Mínimo e máximo de cada célula escondida, e de cada diferença entre versões, com todas as somas juntas."""
    from . import deducao_lp
    conferir_valores(p)
    try:
        r = deducao_lp.atacar([(v.lo, v.hi) for v in p.versoes], p.arestas, p.iguais,
                              [v.escondida for v in p.versoes], p.k, [(i, i + 1) for i in range(len(p.versoes) - 1)],
                              registrar=REGISTRAR)
    except deducao_lp.SemSolucao as erro:
        raise ErroDeVersoes(f"As versões não fecham entre si ({p.medida}): {erro}") from None
    return Resultado("programacao_linear", r["reveladas"], r["diferencas"], r["detalhe"], r["detalhe"]["inconclusivas"])


MOTORES: dict[str, Motor] = {"intervalos": por_intervalos, "programacao_linear": por_programacao_linear}


def atacar(problema: Problema, motor: str | None = None) -> Resultado:
    nome = motor or MOTOR_PADRAO
    if nome not in MOTORES:
        raise ErroDeVersoes(f"Motor do ataque conjunto desconhecido: {nome!r}; existem {sorted(MOTORES)}")
    try:
        return MOTORES[nome](problema)
    except ImportError as erro:
        # Sem a dependência do motor (scipy), o ataque não rodou: isso nunca conta como aprovado.
        raise ErroDeVersoes(f"O motor {nome} não pôde rodar: {erro}") from None


def motores_do_catalogo(catalogo: dict) -> list[str]:
    return list((catalogo["bases"]["sih"].get("versoes") or {}).get("motores") or [MOTOR_PADRAO])


def _intervalos_publicados(df: pd.DataFrame, valor: str, oculto: str, arredondado: str, k: int, base: int, onde: str):
    """lo, hi e escondida de cada linha de uma tabela da superfície."""
    if valor not in df or oculto not in df:
        raise ErroDeVersoes(f"{onde}: tabela publicada sem as colunas {valor} e {oculto}")
    escondida = df[oculto].to_numpy(bool)
    v = df[valor].fillna(0).to_numpy(np.int64)
    if (df[valor].isna().to_numpy() != escondida).any():
        raise ErroDeVersoes(f"{onde}: valor nulo e marca de oculta não coincidem")
    arred = df[arredondado].to_numpy(bool) if arredondado in df else np.zeros(len(df), bool)
    if arred.any() and (base < 2 or (v[arred] % base).any()):
        raise ErroDeVersoes(f"{onde}: valor marcado como arredondado fora do múltiplo de {base} da situação")
    lo, hi = v.copy(), v.copy()
    lo[arred] = np.maximum(v[arred] - base // 2, k)
    hi[arred] = v[arred] - base // 2 + base - 1
    lo[escondida], hi[escondida] = 0, deducao.INF
    return lo, hi, escondida


def _posicoes(uniao: pd.DataFrame, df: pd.DataFrame, n: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Para cada chave da união, se a tabela a tem e em que linha."""
    chaves = df[list(n)].reset_index(drop=True).reset_index(names="_o")
    if chaves.duplicated(list(n)).any():
        raise ErroDeVersoes(f"Tabela {tab.nome(n)} com chave repetida")
    pos = uniao.reset_index(names="_u").merge(chaves, on=list(n), how="left").sort_values("_u")["_o"].to_numpy()
    tem = ~pd.isna(pos)
    return tem, np.where(tem, pos, 0).astype(np.int64)


def _visivel(versao: tuple[dict, dict], catalogo: dict, k: int, medida: str, ano: int) -> dict[tuple, pd.DataFrame]:
    """O que uma versão mostra de uma medida, por nó: as chaves (município com 6 dígitos, como no pipeline) e o
    intervalo de cada célula. `versao` é (situação do ano, {cruzamento: tabela da superfície})."""
    meta, tabelas = versao
    base = int(meta.get("arredondar_multiplo") or 0)
    col_valor, col_oculto, col_arred = COLUNAS[medida]
    cruzamentos = {c["id"]: c for c in catalogo["cruzamentos"]}
    saida = {}
    for cid, medidas in meta["superficie"].items():
        if medida not in medidas:
            continue
        n = tab.colunas_de(cruzamentos[cid], catalogo)
        df = tabelas[cid]
        df = df.to_pandas() if not isinstance(df, pd.DataFrame) else df.copy()
        geo = "mun_res" if "mun_res" in df else "mun_hosp"
        df[geo] = df[geo].astype(str).str[:6]
        lo, hi, esc = _intervalos_publicados(df, col_valor, col_oculto, col_arred, k, base, f"{cid} de {ano}")
        saida[n] = df[list(n)].assign(_lo=lo, _hi=hi, _esc=esc)
    return saida


def montar(no_ar: tuple[dict, dict], candidata: tuple[dict, dict], nos: dict | None, catalogo: dict, ano: int, k: int,
           medida: str = "internacoes", fechado_ate: int | None = None) -> Problema:
    """O Problema de um ano e uma medida, com as duas versões como a superfície as mostra.

    `no_ar` e `candidata` são (situação do ano, {cruzamento: tabela da superfície}). `nos` são os da candidata
    (sih.construir_ano), com os valores verdadeiros: só servem para conferir a solidez do ataque. As células de
    período fechado até `fechado_ate` valem o mesmo nas duas versões: nenhum arquivo com altas daquele período
    foi republicado entre elas.
    """
    if catalogo["bases"]["sih"]["supressao"].get("motivo_por_celula"):
        raise ErroDeVersoes("O ataque conjunto supõe que o motivo da célula oculta não é publicado")
    vistas = [_visivel(v, catalogo, k, medida, ano) for v in (no_ar, candidata)]
    visiveis = list(dict.fromkeys(n for v in vistas for n in v))
    fecho = tab.fechamento(visiveis)
    alcance = {p: set(tab.fechamento([p])) for p in visiveis}

    # As mesmas chaves nas duas versões: as que cada uma mostra e as que saem delas, nível a nível.
    uniao: dict[tuple, pd.DataFrame] = {}
    for n in fecho:
        if not n:
            uniao[n] = pd.DataFrame(index=[0])
            continue
        partes = [tab.chaves_acima(v[p], p, n) if p != n else v[p][list(n)] for v in vistas for p in v if n in alcance[p]]
        if nos is not None and n in nos:
            partes.append(nos[n][list(n)])
        uniao[n] = pd.concat(partes).drop_duplicates().sort_values(list(n)).reset_index(drop=True)
    arestas = tab.arestas(uniao)

    versoes = []
    for rotulo, vista in zip(("no ar", "candidata"), vistas):
        lo, hi, esc = {}, {}, {}
        for n in fecho:
            nome, tamanho = tab.nome(n), len(uniao[n])
            if n not in vista:
                # Ninguém publica: incógnita, de 0 ao infinito.
                lo[nome], hi[nome], esc[nome] = np.zeros(tamanho, np.int64), np.full(tamanho, deducao.INF, np.int64), np.ones(tamanho, bool)
                continue
            # Chave que a versão não mostra numa tabela que ela publica vale zero nela.
            tem, idx = _posicoes(uniao[n], vista[n], n)
            lo[nome] = np.where(tem, vista[n]["_lo"].to_numpy(np.int64)[idx], 0)
            hi[nome] = np.where(tem, vista[n]["_hi"].to_numpy(np.int64)[idx], 0)
            esc[nome] = np.where(tem, vista[n]["_esc"].to_numpy(bool)[idx], False)
        versoes.append(Versao(rotulo, lo, hi, esc, frozenset(tab.nome(n) for n in vista)))
    if nos is not None:
        valor = {}
        for n in fecho:
            if not n:
                valor[tab.nome(n)] = nos[n][medida].to_numpy(np.int64)[:1]
                continue
            tem, idx = _posicoes(uniao[n], nos[n], n)
            valor[tab.nome(n)] = np.where(tem, nos[n][medida].to_numpy(np.int64)[idx], 0)
        versoes[1].valor = valor

    iguais = []
    if fechado_ate:
        for n in fecho:
            iguais.append((0, 1, tab.nome(n), sih_deducao.periodo_fechado(uniao[n], n, ano, int(fechado_ate))))
    return Problema(k, medida, versoes, [(tab.nome(f), tab.nome(g), i) for f, g, i in arestas], iguais)


def conferir_com_a_no_ar(nos: dict, candidata: tuple[dict, dict], no_ar: sih_superficie.Superficie, catalogo: dict,
                         ano: int, k: int, fechado_ate: int | None, motores: list[str] | None = None) -> dict:
    """A etapa: ataca a versão no ar e a candidata juntas, em internações e em óbitos, com cada motor, e resume.

    O resumo vai para a situação do ano (deducao.conjunto). Só contagens de células, nunca valores. Versão no ar
    ilegível, incoerente ou incompatível com a candidata, ou motor que não roda, vira `passou` falso, com o motivo.
    """
    nomes = list(motores or motores_do_catalogo(catalogo))
    resumo = {"obrigatorio": True, "rodou": False, "passou": False, "motores": nomes}
    try:
        if ano not in no_ar.anos:
            raise ErroDeVersoes(f"A versão no ar não tem o ano {ano}")
        meta = no_ar.anos[ano]
        no_ar_ano = (meta, {cid: no_ar.tabelas[ano, cid] for cid in meta["superficie"]})
        medidas = {}
        for medida in COLUNAS:
            p = montar(no_ar_ano, candidata, nos, catalogo, ano, k, medida, fechado_ate)
            por_motor = {}
            for nome in nomes:
                inicio = time.perf_counter()
                r = atacar(p, nome)
                por_motor[nome] = {"reveladas_na_versao_no_ar": sum(r.reveladas[0].values()),
                                   "reveladas_na_candidata": sum(r.reveladas[1].values()),
                                   "diferencas_de_1_a_k-1": sum(r.diferencas["0-1"].values()),
                                   "inconclusivas": r.inconclusivas, "total": r.total,
                                   "por_no": {"no_ar": r.reveladas[0], "candidata": r.reveladas[1], "diferencas": r.diferencas["0-1"]},
                                   "detalhe": r.detalhe, "segundos": round(time.perf_counter() - inicio, 2)}
            medidas[medida] = {"motores": por_motor, "total": sum(m["total"] for m in por_motor.values())}
    except ErroDeContrato as erro:
        return resumo | {"motivo": str(erro)}
    total = sum(m["total"] for m in medidas.values())
    resumo |= {"rodou": True, "passou": total == 0, "versao_no_ar_coletada_em": no_ar.anos[ano].get("coletado_em"), **medidas}
    if total:
        resumo["motivo"] = f"{total} contagem(ns) de 1 a {k - 1} revelada(s) com as duas versões juntas"
    return resumo
