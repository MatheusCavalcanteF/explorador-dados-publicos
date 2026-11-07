"""Compara as duas opções para publicar óbitos, com a supressão aplicada.

A: óbitos por categoria nas tabelas anuais, com complementar própria e total municipal publicado.
B: só o total anual por município, com complementar na margem da UF e do país.

Uso: python -I medir_obitos.py <db_de_medir_sih> <sidra_6579.json> <saida>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb
import numpy as np
import pandas as pd

from suprimir import K, chaves_de_linha, complementar, faixa_pequena, linhas_dedutiveis

DB, POP, SAIDA = sys.argv[1], sys.argv[2], Path(sys.argv[3])
con = duckdb.connect(DB, read_only=True)
pop = {str(r["D1C"])[:6]: int(r["V"]) for r in json.load(open(POP, encoding="utf-8"))[1:]}
PORTES = [("ate_5mil", 0, 5000), ("5_a_20mil", 5000, 20000), ("20_a_100mil", 20000, 100000), ("100_a_500mil", 100000, 500000), ("mais_500mil", 500000, 10**9)]


def porte(m):
    h = pop.get(m)
    return "sem" if h is None else next(n for n, a, b in PORTES if a <= h < b)


def carregar(dims):
    d = ", ".join(dims)
    df = con.execute(f"""SELECT {d}, count(*) aihs, count(*) FILTER (ident='1') internacoes, sum(obito)::BIGINT obitos
        FROM aih WHERE mes>='202501' GROUP BY {d} ORDER BY {d}""").df()
    for c in dims:
        df[c] = df[c].astype(str)
    for c in ("aihs", "internacoes", "obitos"):
        df[c] = df[c].astype("int64")
    df["uf"] = df[dims[0]].str[:2]
    return df


res = {}
TABELAS_A = [("res_ano_capitulo", ["mun_res", "ano", "capitulo"]), ("res_ano_faixa12_sexo", ["mun_res", "ano", "faixa12", "sexo"]), ("res_ano_raca", ["mun_res", "ano", "raca"]), ("hosp_ano_espec", ["mun_hosp", "ano", "espec"])]
quadros = {}
estado = {}
for nome, dims in TABELAS_A:
    df = carregar(dims)
    geo = dims[0]
    aihs, intern = df["aihs"].to_numpy(), df["internacoes"].to_numpy()
    linhas = chaves_de_linha(df, [[x for x in dims if x != d] for d in dims] + [[x for x in dims if x != geo] + ["uf"]])
    oculto_base, _, _ = complementar((aihs < K) | faixa_pequena(intern), linhas, [aihs, intern])
    df["oculto_base"] = oculto_base
    quadros[nome] = (df, dims, linhas)
    nulo = oculto_base | faixa_pequena(df["obitos"].to_numpy())
    por_mun = pd.DataFrame({"m": df[geo], "nulo": nulo}).groupby("m", sort=False)["nulo"].sum()
    estado[nome] = {"municipios": int(df[geo].nunique()), "municipios_com_uma_unica_celula_nula": int((por_mun == 1).sum())}

# Estado anterior: 1 a 4 vira nulo, sem complementar. O total sai de qualquer tabela sem nulos;
# outra tabela da mesma visão com um só nulo fica exposta.
for visao, nomes in (("residencia", ["res_ano_capitulo", "res_ano_faixa12_sexo", "res_ano_raca"]), ("hospital", ["hosp_ano_espec"])):
    totais, resumos = {}, {}
    for nome in nomes:
        df, dims, _ = quadros[nome]
        nulo = df["oculto_base"].to_numpy() | faixa_pequena(df["obitos"].to_numpy())
        g = pd.DataFrame({"m": df[dims[0]], "vis": np.where(nulo, 0, df["obitos"]), "nulos": nulo.astype(int)}).groupby("m", sort=False).agg(vis=("vis", "sum"), nulos=("nulos", "sum"))
        resumos[nome] = g
        totais.update(g.loc[g["nulos"] == 0, "vis"].to_dict())
    for nome, g in resumos.items():
        um = g[(g["nulos"] == 1) & g.index.isin(list(totais))]
        valores = um.index.map(totais).to_numpy() - um["vis"].to_numpy() if len(um) else np.array([])
        estado[nome]["municipios_com_valor_deduzivel"] = int(len(um))
        estado[nome]["deduzidos_de_1a4"] = int(faixa_pequena(valores).sum()) if len(um) else 0
res["estado_anterior"] = estado
print("estado", json.dumps(estado, ensure_ascii=False), flush=True)

# Opção A
opcao_a = {}
for nome, (df, dims, linhas) in quadros.items():
    ob = df["obitos"].to_numpy()
    intern = df["internacoes"].to_numpy()
    oculto, voltas, convergiu = complementar(df["oculto_base"].to_numpy() | faixa_pequena(ob), linhas, [ob])
    faixas = df[dims[0]].map(porte).to_numpy()
    por_porte = {n: {"pct_celulas_com_obito_oculto": round(100 * oculto[faixas == n].mean(), 1), "pct_obitos_ocultos": round(100 * ob[(faixas == n) & oculto].sum() / max(ob[faixas == n].sum(), 1), 1)} for n, _, _ in PORTES}
    com_obito = ob > 0
    opcao_a[nome] = {"linhas": len(df), "pct_celulas_com_obito_oculto": round(100 * oculto.mean(), 1), "pct_celulas_com_obito_positivo_ocultas": round(100 * oculto[com_obito].mean(), 1),
                     "pct_obitos_ocultos": round(100 * ob[oculto].sum() / ob.sum(), 2), "linhas_dedutiveis_depois": linhas_dedutiveis(oculto, linhas, [ob]), "convergiu": convergiu, "voltas": voltas,
                     "sobreviventes_1a4_visiveis": int((~oculto & (ob > 0) & faixa_pequena(intern - ob)).sum()), "por_porte": por_porte}
    df["oculto_ob"] = oculto
    print("A", nome, json.dumps(opcao_a[nome], ensure_ascii=False), flush=True)
res["opcao_a"] = opcao_a

# Na opção A, quantos municípios têm óbito visível em ao menos metade das categorias com óbito?
utilidade = {}
for nome, (df, dims, _) in quadros.items():
    com = df[df["obitos"] > 0]
    g = com.assign(vis=~com["oculto_ob"]).groupby(dims[0], sort=False)["vis"].mean()
    fx = np.array([porte(m) for m in g.index])
    utilidade[nome] = {n: {"municipios": int((fx == n).sum()), "com_metade_ou_mais_visivel": int(((fx == n) & (g.to_numpy() >= 0.5)).sum())} for n, _, _ in PORTES}
res["opcao_a_utilidade"] = utilidade
print("utilidade A", json.dumps(utilidade, ensure_ascii=False), flush=True)

# Opção B
opcao_b = {}
for nome, dims in (("res_ano", ["mun_res", "ano"]), ("hosp_ano", ["mun_hosp", "ano"])):
    df = carregar(dims)
    geo = dims[0]
    ob, intern, aihs = df["obitos"].to_numpy(), df["internacoes"].to_numpy(), df["aihs"].to_numpy()
    linhas = chaves_de_linha(df, [["ano"], ["ano", "uf"]])
    oculto_i, _, _ = complementar((aihs < K) | faixa_pequena(intern), linhas, [aihs, intern])
    primaria = oculto_i | faixa_pequena(ob)
    oculto, voltas, convergiu = complementar(primaria, linhas, [ob])
    faixas = df[geo].map(porte).to_numpy()
    por_porte = {n: {"municipios": int((faixas == n).sum()), "municipios_com_obito_oculto": int(((faixas == n) & oculto).sum())} for n, _, _ in PORTES}
    opcao_b[nome] = {"municipios": len(df), "internacoes_ocultas": int(oculto_i.sum()), "obitos_ocultos_primarios": int(primaria.sum()), "obitos_ocultos_com_complementar": int(oculto.sum()), "pct_municipios_com_obito_oculto": round(100 * oculto.mean(), 1),
                     "pct_obitos_ocultos": round(100 * ob[oculto].sum() / ob.sum(), 2), "municipios_com_zero_obito_visivel": int((~oculto & (ob == 0)).sum()), "linhas_dedutiveis_depois": linhas_dedutiveis(oculto, linhas, [ob]), "convergiu": convergiu,
                     "sobreviventes_1a4_visiveis": int((~oculto & (ob > 0) & faixa_pequena(intern - ob)).sum()), "por_porte": por_porte}
    pub = df[dims].copy()
    pub["internacoes"] = pd.Series(intern, dtype="float64").where(~oculto_i)
    pub["obitos"] = pd.Series(ob, dtype="float64").where(~oculto)
    arq = SAIDA / "parquet" / f"BR_obitos_{nome}.parquet"
    c2 = duckdb.connect()
    c2.register("p", pub)
    c2.execute(f"COPY (SELECT * FROM p ORDER BY 1) TO '{arq.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)")
    opcao_b[nome]["parquet_mb"] = round(arq.stat().st_size / 1e6, 3)
    print("B", nome, json.dumps(opcao_b[nome], ensure_ascii=False), flush=True)
res["opcao_b"] = opcao_b

# Por mês, sem nenhuma complementar: é o piso do que ficaria oculto
mes = carregar(["mun_res", "mes"])
ob_mes = mes["obitos"].to_numpy()
pequeno = faixa_pequena(ob_mes)
series = pd.DataFrame({"m": mes["mun_res"], "p": pequeno}).groupby("m", sort=False)["p"].sum()
res["por_mes"] = {"descricao": "Óbitos por município de residência e mês da alta, se fossem publicados", "populacao": "Todas as AIHs com alta a partir de 01/2025, Brasil", "periodo": "Meses da alta de 2025",
                  "calculo": "Só a regra primária, sem complementar: célula oculta quando há de 1 a 4 óbitos. Série inteira visível: município sem nenhum mês de 1 a 4",
                  "celulas": len(mes), "com_zero_obito": int((ob_mes == 0).sum()), "com_1a4_obitos": int(pequeno.sum()), "com_5_ou_mais": int((ob_mes >= K).sum()),
                  "pct_celulas_com_1a4": round(100 * pequeno.mean(), 1), "municipios": len(series), "municipios_com_serie_inteira_visivel": int((series == 0).sum())}
print("por mês", json.dumps(res["por_mes"], ensure_ascii=False), flush=True)
(SAIDA / "obitos_opcoes.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("fim")
