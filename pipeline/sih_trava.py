"""Trava de queda entre a versão publicada e a candidata, nos dois níveis do plano.

Município e mês da alta: queda de `queda_pct` ou mais, partindo de pelo menos `minimo_internacoes`,
marca a célula como "em revisão". O site publica o valor novo, que é o do arquivo oficial mais recente,
com o anterior ao lado e fora de variações e comparações. Não bloqueia.

Publicação inteira: queda de `queda_uf_competencia_pct` ou mais no total de internações de uma UF numa
competência, ou competência que sumiu, é falha estrutural. O site anterior continua no ar.

Só compara células visíveis nas duas versões: uma célula oculta não tem valor publicado para comparar.
"""
from __future__ import annotations

import pandas as pd


def municipio(anterior: pd.DataFrame, nova: pd.DataFrame, chaves: list[str], regra: dict) -> pd.DataFrame:
    """Células que acionam a trava: chaves, valor anterior, valor novo e a queda em %."""
    a = anterior.loc[~anterior["oculto"], chaves + ["internacoes"]].rename(columns={"internacoes": "anterior"})
    b = nova.loc[~nova["oculto"], chaves + ["internacoes"]].rename(columns={"internacoes": "nova"})
    junto = a.merge(b, on=chaves, how="inner")
    junto["queda_pct"] = 100 * (junto["anterior"] - junto["nova"]) / junto["anterior"]
    aciona = (junto["anterior"] >= regra["minimo_internacoes"]) & (junto["queda_pct"] >= regra["queda_pct"])
    return junto.loc[aciona].sort_values(chaves).reset_index(drop=True)


def publicacao(anteriores: dict[str, int], novos: dict[str, int], regra: dict) -> list[str]:
    """Falhas estruturais por UF e competência. As chaves são "UF/AAAAMM", os valores, internações."""
    falhas = []
    for chave, antes in sorted(anteriores.items()):
        if not isinstance(antes, int) or antes <= 0:
            continue
        depois = novos.get(chave)
        if depois is None:
            falhas.append(f"{chave}: competência publicada antes não está na versão nova")
            continue
        queda = 100 * (antes - depois) / antes
        if queda >= regra["queda_uf_competencia_pct"]:
            falhas.append(f"{chave}: internações caíram {queda:.1f}% ({antes} para {depois}), "
                          f"limite {regra['queda_uf_competencia_pct']}%")
    return falhas
