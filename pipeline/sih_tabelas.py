"""Tabelas do SIH por ano da alta: as publicáveis e todas as somas que se pode montar a partir delas.

Uma tabela é um nó, dado pelas colunas da chave. Cada coluna pertence a uma família com níveis, do
mais fino ao mais grosso (município, UF; mês, trimestre; faixa de 12, faixa de 5), e acima do último
nível está a soma inteira (o Brasil, o ano). Somar uma coluna é subir um nível. O fechamento de um
conjunto de nós é tudo o que se chega subindo níveis: é o que alguém com as tabelas publicadas pode
calcular, e é sobre ele que o teste de dedução trabalha.

Residência e hospital se encontram no Brasil: o total de internações do país num mês é o mesmo pelos
dois lados. Por isso o nó do Brasil não tem coluna de município, e as duas visões chegam nele.
"""
from __future__ import annotations

from itertools import chain

import numpy as np
import pandas as pd

# Família de cada coluna, e os níveis da família do mais fino ao mais grosso.
NIVEIS = {
    "res": ["mun_res", "uf_res"],
    "hosp": ["mun_hosp", "uf_hosp"],
    "tempo": ["mes", "tri"],
    "faixa": ["faixa12", "faixa5"],
    "carater": ["carater", "urgencia"],
    "sexo": ["sexo"],
    "capitulo": ["capitulo"],
    "raca": ["raca"],
    "espec": ["espec"],
}
FAMILIA = {coluna: familia for familia, niveis in NIVEIS.items() for coluna in niveis}
ORDEM = [c for niveis in NIVEIS.values() for c in niveis]
MEDIDAS = ["aihs", "internacoes", "dias", "valor", "obitos"]

FAIXA5_DE_FAIXA12 = {"00": "00-14", "01-04": "00-14", "05-09": "00-14", "10-14": "00-14", "15-19": "15-29",
                     "20-29": "15-29", "30-39": "30-49", "40-49": "30-49", "50-59": "50-69", "60-69": "50-69",
                     "70-79": "70+", "80+": "70+", "ign": "ign"}
URGENCIA_DE_CARATER = {"eletivo": "demais", "urgencia": "urgencia", "outros": "demais"}


def no(colunas) -> tuple[str, ...]:
    """Forma canônica de um nó: colunas na ordem fixa, sem repetir família."""
    colunas = list(colunas)
    familias = [FAMILIA[c] for c in colunas]
    if len(set(familias)) != len(familias):
        raise ValueError(f"Nó com duas colunas da mesma família: {colunas}")
    return tuple(sorted(colunas, key=ORDEM.index))


def nome(n: tuple[str, ...]) -> str:
    return "+".join(n) or "brasil"


def subir(coluna: str) -> str | None:
    """O nível acima, ou None quando acima está a soma inteira."""
    niveis = NIVEIS[FAMILIA[coluna]]
    i = niveis.index(coluna)
    return niveis[i + 1] if i + 1 < len(niveis) else None


def acima(n: tuple[str, ...]) -> list[tuple[str, tuple[str, ...]]]:
    """Os nós um nível acima, cada um com a coluna que subiu."""
    saida = []
    for c in n:
        novo = subir(c)
        resto = [x for x in n if x != c]
        saida.append((c, no(resto + ([novo] if novo else []))))
    return saida


def todos_acima(n: tuple[str, ...]) -> list[tuple[str, ...]]:
    """As margens de uma tabela para a complementar: cada coluna em cada nível acima dela, uma por vez."""
    saida = []
    for c in n:
        resto = [x for x in n if x != c]
        nivel = c
        while True:
            nivel = subir(nivel)
            saida.append(no(resto + ([nivel] if nivel else [])))
            if nivel is None:
                break
    return saida


def fechamento(nos) -> list[tuple[str, ...]]:
    """Todos os nós alcançáveis subindo níveis, dos mais finos para os mais grossos."""
    vistos, fila = set(), [no(n) for n in nos]
    while fila:
        n = fila.pop()
        if n in vistos:
            continue
        vistos.add(n)
        fila.extend(g for _, g in acima(n))
    # Mais colunas e níveis mais finos primeiro: cada nó é calculado a partir de um mais fino já pronto.
    return sorted(vistos, key=lambda n: (-len(n), sum(NIVEIS[FAMILIA[c]].index(c) for c in n), n))


def converter_coluna(serie: pd.Series, de: str, para: str | None) -> pd.Series | None:
    """Valores de `de` levados ao nível `para`. None quando a coluna some (soma inteira)."""
    if para is None:
        return None
    if (de, para) in (("mun_res", "uf_res"), ("mun_hosp", "uf_hosp")):
        return serie.str[:2]
    if (de, para) == ("mes", "tri"):
        return serie.str[:4] + "T" + ((serie.str[4:6].astype(int) + 2) // 3).astype(str)
    if (de, para) == ("faixa12", "faixa5"):
        return serie.map(FAIXA5_DE_FAIXA12)
    if (de, para) == ("carater", "urgencia"):
        return serie.map(URGENCIA_DE_CARATER)
    raise ValueError(f"Sem conversão de {de} para {para}")


def chaves_acima(df: pd.DataFrame, fino: tuple[str, ...], grosso: tuple[str, ...]) -> pd.DataFrame:
    """As colunas de `grosso` calculadas a partir das chaves de `fino`, linha a linha."""
    saida = {}
    for c in grosso:
        if c in fino:
            saida[c] = df[c]
            continue
        origem = next(x for x in fino if FAMILIA[x] == FAMILIA[c])
        serie, nivel = df[origem], origem
        while nivel != c:
            proximo = subir(nivel)
            serie, nivel = converter_coluna(serie, nivel, proximo), proximo
        saida[c] = serie
    return pd.DataFrame(saida, index=df.index)


def grupos(df: pd.DataFrame, fino: tuple[str, ...], grosso: tuple[str, ...]) -> np.ndarray:
    """Para cada linha de `fino`, o número do grupo em `grosso`, em ordem de chave."""
    if not grosso:
        return np.zeros(len(df), dtype=np.int64)
    chaves = chaves_acima(df, fino, grosso)
    return chaves.groupby(list(grosso), sort=True).ngroup().to_numpy(dtype=np.int64)


def agregar(fino_df: pd.DataFrame, fino: tuple[str, ...], grosso: tuple[str, ...]) -> pd.DataFrame:
    chaves = chaves_acima(fino_df, fino, grosso)
    medidas = fino_df[[m for m in MEDIDAS if m in fino_df]]
    junto = pd.concat([chaves, medidas], axis=1)
    if not grosso:
        return medidas.sum().to_frame().T.reset_index(drop=True)
    return junto.groupby(list(grosso), sort=True, as_index=False).sum()


def indice_acima(fino_df: pd.DataFrame, fino: tuple[str, ...], grosso_df: pd.DataFrame,
                 grosso: tuple[str, ...]) -> np.ndarray:
    """Para cada célula de `fino`, a posição da célula de `grosso` que a contém."""
    if not grosso:
        return np.zeros(len(fino_df), dtype=np.int64)
    chaves = chaves_acima(fino_df, fino, grosso)
    alvo = grosso_df[list(grosso)].reset_index(drop=True).reset_index(names="_pos")
    junto = chaves.reset_index(drop=True).merge(alvo, on=list(grosso), how="left", validate="many_to_one")
    if junto["_pos"].isna().any():
        raise ValueError(f"{nome(fino)} -> {nome(grosso)}: célula fina sem célula grossa correspondente")
    return junto["_pos"].to_numpy(dtype=np.int64)


def montar(base: dict[tuple[str, ...], pd.DataFrame], nos_publicados) -> dict[tuple[str, ...], pd.DataFrame]:
    """Calcula o fechamento dos nós publicados. `base` traz os nós que vêm direto das AIHs."""
    feitos = dict(base)
    for n in fechamento(nos_publicados):
        if n in feitos:
            continue
        fino = next((f for f in feitos if n in [g for _, g in acima(f)]), None)
        if fino is None:
            raise ValueError(f"Nó {nome(n)} sem nó mais fino calculado")
        feitos[n] = agregar(feitos[fino], fino, n)
    return feitos


def arestas(nos: dict[tuple[str, ...], pd.DataFrame]) -> list[tuple[tuple, tuple, np.ndarray]]:
    """Uma aresta de cada nó para cada nó um nível acima que esteja no conjunto."""
    saida = []
    for fino, df in nos.items():
        for _, grosso in acima(fino):
            if grosso in nos:
                saida.append((fino, grosso, indice_acima(df, fino, nos[grosso], grosso)))
    return saida


def colunas_de(cruzamento: dict, catalogo: dict) -> tuple[str, ...]:
    dims = [catalogo["dimensoes"][d]["niveis"][0] for d in cruzamento["dimensoes"]]
    tempo = {"mes": ["mes"], "tri": ["tri"], "ano": []}[cruzamento["tempo"]]
    return no(chain(dims, tempo))


def faixas_sql(faixas: list) -> str:
    """CASE do capítulo da CID-10 pela categoria de 3 caracteres, a partir das faixas do catálogo."""
    casos = " ".join(f"WHEN cid3 BETWEEN '{ini}' AND '{fim}' THEN '{num:02d}'" for num, ini, fim, _ in faixas)
    return f"CASE {casos} ELSE '00' END"


FAIXA12_SQL = """CASE WHEN cod_idade IN ('2','3') THEN '00' WHEN cod_idade = '5' THEN '80+'
  WHEN cod_idade = '4' THEN CASE WHEN idade < 1 THEN '00' WHEN idade < 5 THEN '01-04' WHEN idade < 10 THEN '05-09'
    WHEN idade < 15 THEN '10-14' WHEN idade < 20 THEN '15-19' WHEN idade < 30 THEN '20-29' WHEN idade < 40 THEN '30-39'
    WHEN idade < 50 THEN '40-49' WHEN idade < 60 THEN '50-59' WHEN idade < 70 THEN '60-69' WHEN idade < 80 THEN '70-79'
    ELSE '80+' END
  ELSE 'ign' END"""


def sexo_sql(dimensao: dict) -> str:
    """CASE do sexo pelos códigos do catálogo; o que não estiver lá vai para `outros`, como no TabWin."""
    casos = " ".join(f"WHEN '{codigo}' THEN '{valor}'" for codigo, valor in sorted(dimensao["codigos"].items()))
    return f"CASE sexo {casos} ELSE '{dimensao['outros']}' END"


def derivadas_sql(catalogo: dict) -> str:
    """Colunas das tabelas, calculadas de cada AIH do Parquet mínimo."""
    faixas = catalogo["referencias"]["cid10_capitulos"]["faixas"]
    return f"""
      mun_res, mun_hosp, substr(mun_res, 1, 2) AS uf_res, substr(mun_hosp, 1, 2) AS uf_hosp,
      CAST(dt_saida // 100 AS VARCHAR) AS mes,
      CAST(dt_saida // 10000 AS VARCHAR) || 'T' || CAST(((dt_saida // 100) % 100 + 2) // 3 AS VARCHAR) AS tri,
      {sexo_sql(catalogo["dimensoes"]["sexo"])} AS sexo,
      {FAIXA12_SQL} AS faixa12,
      {faixas_sql(faixas)} AS capitulo,
      CASE car_int WHEN '01' THEN 'eletivo' WHEN '02' THEN 'urgencia' ELSE 'outros' END AS carater,
      CASE car_int WHEN '02' THEN 'urgencia' ELSE 'demais' END AS urgencia,
      raca, espec,
      ident, dias, valor, morte"""


def calcular_base(con, tabela: str, ano: int, nos, catalogo: dict) -> dict[tuple[str, ...], pd.DataFrame]:
    """Cada nó pedido direto das AIHs com alta no ano. `tabela` é uma tabela ou view do DuckDB."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE _ano AS SELECT {derivadas_sql(catalogo)} FROM {tabela} "
                f"WHERE dt_saida // 10000 = {int(ano)}")
    saida = {}
    faixa5 = "CASE faixa12 " + " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in FAIXA5_DE_FAIXA12.items()) + " END"
    for n in nos:
        colunas_sql = [f"{faixa5} AS faixa5" if c == "faixa5" else c for c in n]
        grupo = ", ".join(str(i + 1) for i in range(len(n)))
        sql = (f"SELECT {', '.join(colunas_sql) + ', ' if n else ''}count(*)::BIGINT AS aihs, "
               "count(*) FILTER (WHERE ident = 1)::BIGINT AS internacoes, sum(dias)::BIGINT AS dias, "
               "round(sum(valor), 2) AS valor, sum(morte)::BIGINT AS obitos FROM _ano"
               + (f" GROUP BY {grupo} ORDER BY {grupo}" if n else ""))
        saida[no(n)] = con.execute(sql).df()
    return saida
