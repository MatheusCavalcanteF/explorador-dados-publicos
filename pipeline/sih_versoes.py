"""Ataque conjunto: a versão no ar e a candidata, vistas por quem guardou as duas.

É uma etapa do pipeline, entre a supressão do ano e a gravação da partição. Se revelar alguma contagem, o
ano não é gravado e nada é publicado (bases.sih.versoes.ataque_conjunto_obrigatorio).

A etapa tem duas metades, para que o motor possa ser trocado sem mexer no resto:

1. `montar` descreve o problema sem dizer como resolvê-lo (Problema): as células de cada tabela, alinhadas
   nas mesmas chaves nas duas versões; o intervalo que cada versão deixa ver em cada célula; as somas que
   ligam as tabelas (arestas); e as células que quem lê sabe serem iguais nas duas versões, porque o período
   já tinha fechado. A versão no ar entra só com o que foi publicado, lido das partições dela; a candidata
   entra com o que a tela mostraria.
2. Um motor (Motor) recebe o Problema e devolve um Resultado: quantas contagens de 1 a k-1 ficam exatas em
   cada versão, e quantas diferenças exatas de 1 a k-1 aparecem entre elas. O motor de hoje aperta intervalos
   pelas somas, em cadeia (deducao.atacar_juntos e deducao.diferencas). Outro motor entra em MOTORES com o
   mesmo contrato.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from . import deducao, sih_deducao, sih_particoes, sih_tabelas as tab
from .contrato import ErroDeContrato

# Por medida: a coluna do valor, a da célula oculta e a do arredondamento, nos arquivos dos cruzamentos.
COLUNAS = {"internacoes": ("internacoes", "oculto", "arredondado"), "obitos": ("obitos", "obitos_oculto", "obitos_arredondado")}
MOTOR_PADRAO = "intervalos"


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

    @property
    def total(self) -> int:
        return (sum(sum(v.values()) for v in self.reveladas) + sum(sum(v.values()) for v in self.diferencas.values()))


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


MOTORES: dict[str, Motor] = {"intervalos": por_intervalos}


def atacar(problema: Problema, motor: str | None = None) -> Resultado:
    nome = motor or MOTOR_PADRAO
    if nome not in MOTORES:
        raise ErroDeVersoes(f"Motor do ataque conjunto desconhecido: {nome!r}; existem {sorted(MOTORES)}")
    return MOTORES[nome](problema)


# A versão no ar, lida das partições dela.

def ler_no_ar(pasta: Path, ano: int, catalogo: dict) -> dict:
    """Tudo o que a versão no ar mostrou de um ano: a situação, cada cruzamento publicado e as margens.

    Confere cada arquivo com a situação e recusa a versão que não poderia ter ido ao ar
    (sih_particoes.ler_publicada). O município volta aos 6 dígitos do pipeline.
    """
    situacao = sih_particoes.ler_publicada(pasta, ano)
    raiz = Path(pasta) / f"ano={ano}"
    cruzamentos = {}
    for c in catalogo["cruzamentos"]:
        if c["id"] not in situacao["publicados"]:
            continue
        nomes = sorted(n for n in situacao["arquivos"] if n.startswith(c["id"] + "/"))
        df = pd.concat([pd.read_parquet(raiz / n) for n in nomes], ignore_index=True)
        geo = "mun_res" if "mun_res" in df else "mun_hosp"
        df[geo] = df[geo].str[:6]
        cruzamentos[c["id"]] = df
    margens = {}
    nos_dos_cruzamentos = {tab.colunas_de(c, catalogo) for c in catalogo["cruzamentos"]}
    for medida, lista in catalogo["margens_publicadas"].items():
        for m in lista:
            n = tab.no(m)
            if n in nos_dos_cruzamentos:
                continue
            nome = f"margens/{medida}/{'-'.join(n) or 'brasil'}.parquet"
            if nome not in situacao["arquivos"]:
                raise ErroDeVersoes(f"{raiz}: a versão no ar não traz a margem publicada {nome}; sem ela não dá "
                                    "para refazer o que essa versão mostrava")
            margens[medida, n] = pd.read_parquet(raiz / nome)
    return {"situacao": situacao, "cruzamentos": cruzamentos, "margens": margens}


def _intervalos_publicados(df: pd.DataFrame, valor: str, oculto: str, arredondado: str, k: int, base: int, onde: str):
    """lo, hi e escondida de cada linha de um arquivo publicado."""
    if valor not in df or oculto not in df:
        raise ErroDeVersoes(f"{onde}: arquivo publicado sem as colunas {valor} e {oculto}")
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


def _incompleto(df: pd.DataFrame, n: tuple, ultimo_mes: int | None) -> np.ndarray:
    """Trimestre que ainda não tinha os três meses na base: fica fora do arquivo, e quem lê não vê nem a chave."""
    if "tri" not in n or ultimo_mes is None:
        return np.zeros(len(df), dtype=bool)
    fim = df["tri"].str[:4].astype(int) * 100 + df["tri"].str[5:].astype(int) * 3
    return (fim > int(ultimo_mes)).to_numpy()


def _posicoes(uniao: pd.DataFrame, df: pd.DataFrame, n: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Para cada chave da união, se a tabela a tem e em que linha."""
    chaves = df[list(n)].reset_index(drop=True).reset_index(names="_o")
    if chaves.duplicated(list(n)).any():
        raise ErroDeVersoes(f"Tabela {tab.nome(n)} com chave repetida")
    pos = uniao.reset_index(names="_u").merge(chaves, on=list(n), how="left").sort_values("_u")["_o"].to_numpy()
    tem = ~pd.isna(pos)
    return tem, np.where(tem, pos, 0).astype(np.int64)


def montar(nos: dict, sup: dict, cat_ano: dict, catalogo: dict, no_ar: dict, ano: int, k: int, medida: str = "internacoes",
           arredondamento: tuple | None = None, ultimo_mes: int | None = None, fechado_ate: int | None = None) -> Problema:
    """O Problema de um ano e uma medida: a versão no ar (ler_no_ar) e a candidata.

    `nos` e `sup` são os de sih.construir_ano, e `cat_ano`, o catálogo só com o que a candidata publica no
    ano. `arredondamento` é (base, meses preliminares, ano), como no teste de cada versão. As células de
    período fechado até `fechado_ate` valem o mesmo nas duas versões: nenhum arquivo com altas daquele
    período foi republicado entre elas.
    """
    if catalogo["bases"]["sih"]["supressao"].get("motivo_por_celula"):
        raise ErroDeVersoes("O ataque conjunto supõe que o motivo da célula oculta não é publicado")
    col_valor, col_oculto, col_arred = COLUNAS[medida]
    situacao = no_ar["situacao"]
    base_antiga = int(situacao.get("arredondar_multiplo") or 0)
    publicados = sih_deducao.nos_publicados(catalogo, medida)
    fecho = tab.fechamento(publicados)

    # O que a versão no ar publicou, por nó: chaves e intervalo de cada linha.
    antigos: dict[tuple, pd.DataFrame] = {}
    for c in catalogo["cruzamentos"]:
        if c["id"] in no_ar["cruzamentos"] and (medida != "obitos" or "obitos" in c["metricas"]):
            n = tab.colunas_de(c, catalogo)
            df = no_ar["cruzamentos"][c["id"]]
            lo, hi, esc = _intervalos_publicados(df, col_valor, col_oculto, col_arred, k, base_antiga, f"{c['id']} de {ano}")
            antigos[n] = df[list(n)].assign(_lo=lo, _hi=hi, _esc=esc)
    for (med, n), df in no_ar["margens"].items():
        if med == medida and n not in antigos:
            lo, hi, esc = _intervalos_publicados(df, "valor", "oculto", "arredondado", k, base_antiga, f"margem {tab.nome(n)} de {ano}")
            antigos[n] = df[list(n)].assign(_lo=lo, _hi=hi, _esc=esc)

    # As mesmas chaves nas duas versões: as da candidata e as que saem de cada tabela publicada antes.
    alcance = {p: set(tab.fechamento([p])) for p in antigos}
    uniao: dict[tuple, pd.DataFrame] = {}
    for n in fecho:
        if not n:
            uniao[n] = pd.DataFrame(index=[0])
            continue
        partes = [nos[n][list(n)]] + [tab.chaves_acima(antigos[p], p, n) for p in antigos if n in alcance[p]]
        uniao[n] = pd.concat(partes).drop_duplicates().sort_values(list(n)).reset_index(drop=True)
    arestas = tab.arestas(uniao)

    # A candidata, como a tela a mostraria: o mesmo sistema do teste dela, nas chaves da união.
    estados = sih_deducao.sem_motivo(sih_deducao.estados_publicados(nos, sup, cat_ano, k, medida))
    nos_al, est_al = {}, {}
    for n in fecho:
        if not n:
            nos_al[n] = nos[n][[medida]].reset_index(drop=True)
            if n in estados:
                est_al[n] = estados[n]
            continue
        tem, idx = _posicoes(uniao[n], nos[n], n)
        nos_al[n] = uniao[n].assign(**{medida: np.where(tem, nos[n][medida].to_numpy(np.int64)[idx], 0)})
        if n in estados:
            # Chave que a candidata não tem vale zero, menos no trimestre que ainda não saiu.
            estado = np.where(tem, estados[n][idx], deducao.VISIVEL).astype(np.int8)
            estado[~tem & _incompleto(uniao[n], n, ultimo_mes)] = deducao.LIVRE
            est_al[n] = estado
    s = sih_deducao.sistema(nos_al, est_al, publicados, k, medida=medida, aresta_cache=arestas, arredondamento=arredondamento)
    candidata = Versao("candidata", {x: no.lo for x, no in s.nos.items()}, {x: no.hi for x, no in s.nos.items()},
                       {x: no.estado != deducao.VISIVEL for x, no in s.nos.items()},
                       frozenset(tab.nome(n) for n in est_al), {x: no.valor for x, no in s.nos.items()})

    # A versão no ar: só o que foi publicado. O resto é incógnita.
    lo, hi, esc = {}, {}, {}
    for n in fecho:
        tamanho = len(uniao[n])
        nome = tab.nome(n)
        if n not in antigos:
            lo[nome], hi[nome] = np.zeros(tamanho, np.int64), np.full(tamanho, deducao.INF, np.int64)
            esc[nome] = np.ones(tamanho, bool)
            continue
        antigo = antigos[n]
        if not n:
            tem, idx = np.ones(1, bool), np.zeros(1, np.int64)
        else:
            tem, idx = _posicoes(uniao[n], antigo, n)
        # Chave que a versão no ar não tinha valia zero lá, menos no trimestre que ela ainda não mostrava.
        fora = ~tem & _incompleto(uniao[n], n, situacao.get("ultimo_mes")) if n else np.zeros(1, bool)
        lo[nome] = np.where(tem, antigo["_lo"].to_numpy(np.int64)[idx], 0)
        hi[nome] = np.where(fora, deducao.INF, np.where(tem, antigo["_hi"].to_numpy(np.int64)[idx], 0))
        esc[nome] = np.where(tem, antigo["_esc"].to_numpy(bool)[idx], fora)
    no_ar_v = Versao("no ar", lo, hi, esc, frozenset(tab.nome(n) for n in antigos))

    iguais = []
    if fechado_ate:
        for n in fecho:
            iguais.append((0, 1, tab.nome(n), sih_deducao.periodo_fechado(uniao[n], n, ano, int(fechado_ate))))
    return Problema(k, medida, [no_ar_v, candidata], [(tab.nome(f), tab.nome(g), i) for f, g, i in arestas], iguais)


def conferir_com_a_no_ar(nos: dict, sup: dict, cat_ano: dict, catalogo: dict, pasta: Path, ano: int, k: int,
                         arredondamento: tuple | None, ultimo_mes: int | None, fechado_ate: int | None,
                         motor: str | None = None) -> dict:
    """A etapa: ataca a versão no ar e a candidata juntas, em internações e em óbitos, e resume.

    O resumo vai para a situação do ano (deducao.conjunto). Só contagens de células, nunca valores.
    Versão no ar ilegível, incoerente ou incompatível com a candidata vira `passou` falso, com o motivo.
    """
    resumo = {"obrigatorio": True, "rodou": False, "passou": False, "motor": motor or MOTOR_PADRAO}
    try:
        no_ar = ler_no_ar(pasta, ano, catalogo)
        medidas = {}
        for medida in COLUNAS:
            r = atacar(montar(nos, sup, cat_ano, catalogo, no_ar, ano, k, medida, arredondamento, ultimo_mes, fechado_ate), motor)
            medidas[medida] = {"reveladas_na_versao_no_ar": sum(r.reveladas[0].values()),
                               "reveladas_na_candidata": sum(r.reveladas[1].values()),
                               "diferencas_de_1_a_k-1": sum(r.diferencas["0-1"].values()),
                               "por_no": {"no_ar": r.reveladas[0], "candidata": r.reveladas[1], "diferencas": r.diferencas["0-1"]},
                               "motor": r.motor, "detalhe": r.detalhe, "total": r.total}
    except ErroDeContrato as erro:
        return resumo | {"motivo": str(erro)}
    total = sum(m["total"] for m in medidas.values())
    resumo |= {"rodou": True, "passou": total == 0, "versao_no_ar_coletada_em": no_ar["situacao"].get("coletado_em"), **medidas}
    if total:
        resumo["motivo"] = f"{total} contagem(ns) de 1 a {k - 1} revelada(s) com as duas versões juntas"
    return resumo
