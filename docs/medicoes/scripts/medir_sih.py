"""Mede cada cruzamento do SIH 2025 no Brasil, com a regra de supressão por métrica.

A célula fica oculta quando as AIHs ou as internações estão entre 1 e 4. As AIHs não são
publicadas: diferença entre as duas medidas daria outra contagem pequena. Óbitos ficam em
medir_obitos.py.

Uso: python -I medir_sih.py <pasta_rd_sp> <pasta_outras_uf> <cid10.parquet> <sidra_6579.json> <saida> <db>
"""
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb
import numpy as np
import pandas as pd

from suprimir import K, chaves_de_linha, complementar, deducao_em_cadeia, faixa_pequena, linhas_dedutiveis

PASTA_SP, PASTA_UF, CID, POP, SAIDA, DB = sys.argv[1:7]
COM_FAMILIA = len(sys.argv) < 8 or sys.argv[7] != "sem-familia"
ARQ_SAIDA = "sih_agregados.json" if COM_FAMILIA else "sih_sem_familia.json"
SAIDA = Path(SAIDA)
(SAIDA / "parquet").mkdir(parents=True, exist_ok=True)

con = duckdb.connect(DB)
con.execute("SET threads=8; SET memory_limit='12GB'")

FAIXA12 = """CASE WHEN COD_IDADE IN ('2','3') THEN '00' WHEN COD_IDADE='5' THEN '80+'
  WHEN COD_IDADE='4' THEN CASE WHEN IDADE<1 THEN '00' WHEN IDADE<5 THEN '01-04' WHEN IDADE<10 THEN '05-09'
    WHEN IDADE<15 THEN '10-14' WHEN IDADE<20 THEN '15-19' WHEN IDADE<30 THEN '20-29' WHEN IDADE<40 THEN '30-39'
    WHEN IDADE<50 THEN '40-49' WHEN IDADE<60 THEN '50-59' WHEN IDADE<70 THEN '60-69' WHEN IDADE<80 THEN '70-79' ELSE '80+' END
  ELSE 'ign' END"""
FAIXA5 = """CASE WHEN COD_IDADE IN ('2','3') THEN '00-14' WHEN COD_IDADE='5' THEN '70+'
  WHEN COD_IDADE='4' THEN CASE WHEN IDADE<15 THEN '00-14' WHEN IDADE<30 THEN '15-29' WHEN IDADE<50 THEN '30-49'
    WHEN IDADE<70 THEN '50-69' ELSE '70+' END
  ELSE 'ign' END"""

inicio = time.perf_counter()
COL = "ANO_CMPT, MES_CMPT, IDENT, CNES, MUNIC_MOV, MUNIC_RES, DIAG_PRINC, DT_SAIDA, DIAS_PERM, VAL_TOT, MORTE, ESPEC, CAR_INT, SEXO, IDADE, COD_IDADE, COMPLEX, RACA_COR, PROC_REA"
con.execute(f"""
CREATE OR REPLACE TABLE aih AS
WITH cap AS (SELECT DISTINCT id_categoria, numero_capitulo FROM read_parquet('{CID}')),
bruto AS (
  SELECT {COL} FROM read_parquet('{PASTA_SP}/RDSP25*.parquet')
  UNION ALL BY NAME
  SELECT {COL} FROM read_parquet('{PASTA_UF}/RD*.parquet')
)
SELECT ANO_CMPT||MES_CMPT AS competencia, substr(DT_SAIDA,1,6) AS mes, substr(DT_SAIDA,1,4) AS ano,
  substr(DT_SAIDA,1,4)||'T'||((substr(DT_SAIDA,5,2)::INT+2)//3) AS tri, IDENT AS ident,
  CNES AS cnes, MUNIC_MOV AS mun_hosp, MUNIC_RES AS mun_res,
  substr(DIAG_PRINC,1,3) AS cid3, coalesce(cap.numero_capitulo::VARCHAR,'sem') AS capitulo,
  CASE SEXO WHEN '1' THEN 'M' WHEN '2' THEN 'F' WHEN '3' THEN 'F' ELSE 'I' END AS sexo,
  {FAIXA12} AS faixa12, {FAIXA5} AS faixa5,
  CASE CAR_INT WHEN '01' THEN 'eletivo' WHEN '02' THEN 'urgencia' ELSE 'outros' END AS carater,
  CASE CAR_INT WHEN '02' THEN 'urgencia' ELSE 'demais' END AS urgencia,
  ESPEC AS espec, RACA_COR AS raca, PROC_REA AS proc,
  DIAS_PERM AS dias, VAL_TOT AS valor, MORTE AS obito
FROM bruto b LEFT JOIN cap ON substr(b.DIAG_PRINC,1,3)=cap.id_categoria
""")
print("tabela base", round(time.perf_counter() - inicio, 1), "s", flush=True)

pop = {str(r["D1C"])[:6]: int(r["V"]) for r in json.load(open(POP, encoding="utf-8"))[1:]}


def porte(habitantes):
    if habitantes is None:
        return "sem"
    if habitantes < 5000:
        return "ate_5mil"
    if habitantes < 20000:
        return "5_a_20mil"
    if habitantes < 100000:
        return "20_a_100mil"
    if habitantes < 500000:
        return "100_a_500mil"
    return "mais_500mil"


fatos = {
    "linhas_total": con.execute("SELECT count(*) FROM aih").fetchone()[0],
    "internacoes": con.execute("SELECT count(*) FILTER (ident='1') FROM aih").fetchone()[0],
    "mun_hosp": con.execute("SELECT count(DISTINCT mun_hosp) FROM aih").fetchone()[0],
    "mun_hosp_com_alta_em_2025": con.execute("SELECT count(DISTINCT mun_hosp) FROM aih WHERE mes>='202501'").fetchone()[0],
    "mun_res": con.execute("SELECT count(DISTINCT mun_res) FROM aih").fetchone()[0],
    "res_fora_hosp_pct": con.execute("SELECT round(100.0*count(*) FILTER (mun_res<>mun_hosp)/count(*),1) FROM aih WHERE ident='1'").fetchone()[0],
    "amplitude_mes": con.execute("SELECT min(mes), max(mes), count(DISTINCT mes), count(*) FILTER (mes<'202501') FROM aih").fetchone(),
    "categorias_sem_capitulo_na_cid10": con.execute("SELECT cid3, count(*) FROM aih WHERE capitulo='sem' GROUP BY 1 ORDER BY 2 DESC").fetchall(),
}
# Defasagem entre o mês da saída e a competência, para definir quando um mês fica fechado
lag = con.execute("""SELECT (substr(competencia,1,4)::INT*12+substr(competencia,5,2)::INT)-(substr(mes,1,4)::INT*12+substr(mes,5,2)::INT) d, count(*) n
  FROM aih GROUP BY 1 ORDER BY 1""").fetchall()
total_lag = sum(n for _, n in lag)
acum = 0
fatos["defasagem_saida_competencia"] = []
for d, n in lag:
    acum += n
    fatos["defasagem_saida_competencia"].append({"meses": d, "linhas": n, "acumulado_pct": round(100 * acum / total_lag, 3)})
print(json.dumps(fatos, ensure_ascii=False, default=str)[:900], flush=True)

TABELAS = [
    ("res_mes", ["mun_res", "mes"]),
    ("hosp_mes", ["mun_hosp", "mes"]),
    ("res_ano", ["mun_res", "ano"]),
    ("hosp_ano", ["mun_hosp", "ano"]),
    ("hosp_cnes_mes", ["cnes", "mes"]),
    ("res_mes_sexo", ["mun_res", "mes", "sexo"]),
    ("res_mes_urgencia", ["mun_res", "mes", "urgencia"]),
    ("res_ano_capitulo", ["mun_res", "ano", "capitulo"]),
    ("res_ano_faixa12_sexo", ["mun_res", "ano", "faixa12", "sexo"]),
    ("res_ano_raca", ["mun_res", "ano", "raca"]),
    ("hosp_cnes_ano_capitulo", ["cnes", "ano", "capitulo"]),
    ("hosp_ano_espec", ["mun_hosp", "ano", "espec"]),
    ("hosp_mes_espec", ["mun_hosp", "mes", "espec"]),
    ("res_mes_faixa5", ["mun_res", "mes", "faixa5"]),
    ("res_tri_capitulo", ["mun_res", "tri", "capitulo"]),
    ("hosp_tri_capitulo", ["mun_hosp", "tri", "capitulo"]),
    ("hosp_mes_capitulo", ["mun_hosp", "mes", "capitulo"]),
    ("hosp_mes_carater", ["mun_hosp", "mes", "carater"]),
    ("fluxo_res_hosp_ano", ["mun_res", "mun_hosp", "ano"]),
    ("res_mes_carater", ["mun_res", "mes", "carater"]),
    ("res_mes_capitulo", ["mun_res", "mes", "capitulo"]),
    ("fluxo_res_hosp_mes", ["mun_res", "mun_hosp", "mes"]),
    ("res_ano_proc", ["mun_res", "ano", "proc"]),
    ("res_ano_cid3", ["mun_res", "ano", "cid3"]),
    ("res_ano_capitulo_faixa5_sexo", ["mun_res", "ano", "capitulo", "faixa5", "sexo"]),
    ("res_mes_cid3", ["mun_res", "mes", "cid3"]),
    ("res_mes_capitulo_faixa5_sexo", ["mun_res", "mes", "capitulo", "faixa5", "sexo"]),
]
# Tabelas que entram no ataque entre tabelas: chave comum e, quando existe, a tabela-mãe
GRUPOS_ATAQUE = {
    "residencia_mes": {"chave": ["mun_res", "mes"], "mae": "res_mes", "filhas": ["res_mes_sexo", "res_mes_urgencia", "res_mes_faixa5"]},
    "residencia_ano": {"chave": ["mun_res", "ano"], "mae": "res_ano", "filhas": ["res_ano_capitulo", "res_ano_faixa12_sexo", "res_ano_raca"]},
    "hospital_mes": {"chave": ["mun_hosp", "mes"], "mae": "hosp_mes", "filhas": ["hosp_mes_espec", "hosp_mes_capitulo", "hosp_mes_carater"]},
    "hospital_ano": {"chave": ["mun_hosp", "ano"], "mae": "hosp_ano", "filhas": ["hosp_ano_espec"]},
    "residencia_capitulo": {"chave": ["mun_res", "capitulo"], "mae": "res_ano_capitulo", "filhas": ["res_tri_capitulo"]},
}
# Família: uma célula oculta na mãe esconde todas as filhas da mesma chave, senão a soma das filhas a revelaria
MAES = {
    "res_mes_sexo": "res_mes", "res_mes_urgencia": "res_mes", "res_mes_faixa5": "res_mes", "res_mes_carater": "res_mes",
    "res_mes_capitulo": "res_mes", "res_mes_cid3": "res_mes", "res_mes_capitulo_faixa5_sexo": "res_mes",
    "hosp_mes_espec": "hosp_mes", "hosp_mes_capitulo": "hosp_mes", "hosp_mes_carater": "hosp_mes", "hosp_cnes_mes": "hosp_mes",
    "res_ano_capitulo": "res_ano", "res_ano_faixa12_sexo": "res_ano", "res_ano_raca": "res_ano", "res_ano_proc": "res_ano", "res_ano_cid3": "res_ano", "res_ano_capitulo_faixa5_sexo": "res_ano",
    "hosp_ano_espec": "hosp_ano", "hosp_cnes_ano_capitulo": "hosp_ano",
    "res_tri_capitulo": "res_ano_capitulo",
}
PUBLICAR = ["res_mes", "hosp_mes", "res_ano", "hosp_ano", "res_mes_sexo", "res_mes_urgencia", "res_ano_capitulo", "res_ano_faixa12_sexo", "res_ano_raca",
            "hosp_ano_espec", "res_mes_faixa5", "res_tri_capitulo", "hosp_tri_capitulo", "hosp_mes_carater", "fluxo_res_hosp_ano"]
GUARDAR = {"res_tri_capitulo", "hosp_tri_capitulo"} | {t for g in GRUPOS_ATAQUE.values() for t in g["filhas"] + ([g["mae"]] if g["mae"] else [])}


def conjuntos_de_linha(dims: list[str]) -> list[list[str]]:
    """Margens que o site pode publicar: cada dimensão somada, e o município somado dentro da UF."""
    conj = [[x for x in dims if x != d] for d in dims]
    if dims[0].startswith("mun_"):
        conj.append([x for x in dims if x != dims[0]] + ["uf"])
    if dims[0] == "cnes":
        conj.append([x for x in dims if x != "cnes"] + ["mun_hosp"])
    return conj


resultados = []
guardados = {}
mascaras_mae = {}
for nome, dims in TABELAS:
    t0 = time.perf_counter()
    d_sql = ", ".join(dims)
    extra = ", any_value(mun_hosp) mun_hosp" if dims[0] == "cnes" else ""
    df = con.execute(f"""SELECT {d_sql}{extra}, count(*) aihs, count(*) FILTER (ident='1') internacoes, sum(dias) dias, round(sum(valor),2) valor
        FROM aih WHERE mes>='202501' GROUP BY {d_sql} ORDER BY {d_sql}""").df()
    for c in dims:
        df[c] = df[c].astype(str)
    for c in ("aihs", "internacoes", "dias"):
        df[c] = df[c].astype("int64")
    if dims[0].startswith("mun_"):
        df["uf"] = df[dims[0]].str[:2]
    aihs, intern = df["aihs"].to_numpy(), df["internacoes"].to_numpy()

    # Regra anterior, para medir o que ela deixava passar: só AIHs, sem margem por UF
    linhas_antigas = chaves_de_linha(df, [[x for x in dims if x != d] for d in dims])
    oculto_antigo, _, _ = complementar(aihs < K, linhas_antigas, [aihs])
    vazou = int((faixa_pequena(intern) & ~oculto_antigo).sum())

    linhas = chaves_de_linha(df, conjuntos_de_linha(dims))
    primaria = (aihs < K) | faixa_pequena(intern)
    herdadas = 0
    inelegivel = None
    if COM_FAMILIA and nome in MAES:
        chave = ["mun_hosp", dims[1]] if dims[0] == "cnes" else (["mun_res", "capitulo"] if nome == "res_tri_capitulo" else dims[:2])
        herda = df[chave].merge(mascaras_mae[MAES[nome]][chave + ["h"]], on=chave, how="left")["h"].fillna(False).to_numpy(dtype=bool)
        herdadas = int((herda & ~primaria).sum())
        primaria = primaria | herda
        # A única filha de uma mãe visível tem valor público: escondê-la não protege nada
        tamanho = df.groupby(chave, sort=False)[chave[0]].transform("size").to_numpy()
        inelegivel = (tamanho == 1) & ~herda
    if COM_FAMILIA and nome in ("res_tri_capitulo", "hosp_tri_capitulo"):
        m = mascaras_mae["res_mes" if nome.startswith("res") else "hosp_mes"].copy()
        m["tri"] = m["mes"].str[:4] + "T" + ((m["mes"].str[4:6].astype(int) + 2) // 3).astype(str)
        chave_t = [dims[0], "tri"]
        herda_t = df[chave_t].merge(m[chave_t].drop_duplicates().assign(h2=True), on=chave_t, how="left")["h2"].fillna(False).to_numpy(dtype=bool)
        herdadas += int((herda_t & ~primaria).sum())
        primaria = primaria | herda_t
    oculto, voltas, convergiu = complementar(primaria, linhas, [aihs, intern], inelegivel=inelegivel)
    if nome in set(MAES.values()):
        mascaras_mae[nome] = df.loc[oculto, dims].assign(h=True)

    r = {
        "tabela": nome, "dims": dims, "linhas": len(df),
        "regra_antiga_visiveis_internacoes_1a4": vazou,
        "regra_antiga_pct_celulas_ocultas": round(100 * oculto_antigo.mean(), 1),
        "pct_celulas_primarias": round(100 * primaria.mean(), 1),
        "pct_celulas_ocultas": round(100 * oculto.mean(), 1),
        "pct_internacoes_ocultas": round(100 * intern[oculto].sum() / intern.sum(), 2),
        "pct_aihs_ocultas": round(100 * aihs[oculto].sum() / aihs.sum(), 2),
        "visiveis_internacoes_1a4": int((faixa_pequena(intern) & ~oculto).sum()),
        "linhas_dedutiveis_depois": linhas_dedutiveis(oculto, linhas, [aihs, intern]),
        "linhas_dedutiveis_por_margem": {"+".join(c): linhas_dedutiveis(oculto, [g], [aihs, intern]) for c, g in zip(conjuntos_de_linha(dims), linhas)},
        "voltas": voltas, "convergiu": convergiu, "celulas_herdadas_da_mae": herdadas,
        "hash_oculto": hashlib.sha256(oculto.tobytes()).hexdigest()[:16],
    }
    if dims[0].startswith("mun_"):
        faixas = df[dims[0]].map(lambda m: porte(pop.get(m)))
        r["por_porte"] = {}
        for f in ("ate_5mil", "5_a_20mil", "20_a_100mil", "100_a_500mil", "mais_500mil"):
            m = (faixas == f).to_numpy()
            if m.any():
                r["por_porte"][f] = {"pct_celulas_ocultas": round(100 * oculto[m].mean(), 1), "pct_internacoes_ocultas": round(100 * intern[m & oculto].sum() / max(intern[m].sum(), 1), 2)}

    if nome in GUARDAR:
        guardados[nome] = df[dims + ["internacoes"] + (["uf"] if "uf" in df else [])].assign(oculto=oculto)

    pub = df[dims].copy()
    for c in ("internacoes", "dias", "valor"):
        pub[c] = df[c].astype("float64")
        pub.loc[oculto, c] = np.nan
    pub["oculto"] = oculto
    con.register("pub_df", pub)
    arq = SAIDA / ("parquet" if COM_FAMILIA else "parquet_sem_familia") / f"BR_{nome}.parquet"
    arq.parent.mkdir(exist_ok=True)
    con.execute(f"COPY (SELECT * FROM pub_df ORDER BY {d_sql}) TO '{arq.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, ROW_GROUP_SIZE 50000)")
    con.unregister("pub_df")
    r["parquet_mb"] = round(arq.stat().st_size / 1e6, 2)
    r["segundos"] = round(time.perf_counter() - t0, 1)
    resultados.append(r)
    print(json.dumps({k: v for k, v in r.items() if k not in ("por_porte", "dims")}, ensure_ascii=False), flush=True)
    (SAIDA / ARQ_SAIDA).write_text(json.dumps({"fatos": fatos, "tabelas": resultados}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

# Ataque entre tabelas, de primeira ordem: uma tabela sem células ocultas revela o total da chave;
# com o total em mãos, qualquer outra tabela com uma só célula oculta na mesma chave fica exposta.
ataque = {}
for grupo, cfg in GRUPOS_ATAQUE.items():
    chave = cfg["chave"]
    totais = None
    if cfg["mae"]:
        mae = guardados[cfg["mae"]]
        totais = mae.loc[~mae["oculto"], chave + ["internacoes"]].rename(columns={"internacoes": "total"})
    resumos = {}
    for f in cfg["filhas"]:
        t = guardados[f]
        g = t.assign(vis=t["internacoes"].where(~t["oculto"], 0), oc=t["oculto"].astype(int)).groupby(chave, sort=False).agg(soma=("vis", "sum"), ocultas=("oc", "sum")).reset_index()
        resumos[f] = g
        completos = g.loc[g["ocultas"] == 0, chave + ["soma"]].rename(columns={"soma": "total"})
        totais = completos if totais is None else pd.concat([totais, completos], ignore_index=True)
    totais = totais.drop_duplicates(chave)
    det = {}
    for f, g in resumos.items():
        um = g[g["ocultas"] == 1].merge(totais, on=chave)
        valor = um["total"] - um["soma"]
        det[f] = {"chaves_com_uma_oculta_e_total_conhecido": len(um), "valor_deduzido_1a4": int(faixa_pequena(valor.to_numpy()).sum())}
    if cfg["mae"]:
        mae = guardados[cfg["mae"]]
        escondidas = mae.loc[mae["oculto"], chave + ["internacoes"]].merge(totais, on=chave)
        det["mae_oculta_revelada_por_filha"] = {"chaves": len(escondidas), "valor_1a4": int(faixa_pequena(escondidas["total"].to_numpy()).sum())}
    for f in cfg["filhas"]:
        # Segunda ordem na filha: chave com uma só oculta e total conhecido entrega a célula
        t_f = guardados[f]
        chaves = t_f[chave].merge(resumos[f].assign(uma=resumos[f]["ocultas"] == 1)[chave + ["uma"]], on=chave, how="left").merge(totais.assign(tem=True)[chave + ["tem"]], on=chave, how="left")
        revelada_f = chaves["uma"].fillna(False).to_numpy(dtype=bool) & chaves["tem"].fillna(False).to_numpy(dtype=bool) & t_f["oculto"].to_numpy()
        cats = [c for c in t_f.columns if c not in chave + ["internacoes", "oculto", "uf"]]
        conj = [chave] + [[chave[0]] + cats, [chave[1]] + cats, [chave[1], "uf"] + cats]
        det[f]["segunda_ordem"] = deducao_em_cadeia((~t_f["oculto"].to_numpy()) | revelada_f, t_f["internacoes"].to_numpy(), chaves_de_linha(t_f, conj))
        declaradas = [chave]
        if f in ("hosp_mes_espec", "res_mes_sexo", "res_mes_faixa5"):
            declaradas.append([chave[0]] + cats)
        det[f]["segunda_ordem_margens_publicadas"] = deducao_em_cadeia((~t_f["oculto"].to_numpy()) | revelada_f, t_f["internacoes"].to_numpy(), chaves_de_linha(t_f, declaradas))
    if cfg["mae"]:
        # Segunda ordem: as mães reveladas entram como conhecidas e as margens da própria tabela fazem o resto
        mae = guardados[cfg["mae"]]
        revelada = mae[chave].merge(totais.assign(rev=True), on=chave, how="left")["rev"].fillna(False).to_numpy(dtype=bool)
        conhecido = (~mae["oculto"].to_numpy()) | revelada
        linhas_mae = chaves_de_linha(mae, [[chave[0]], [chave[1]], [chave[1], "uf"]])
        det["segunda_ordem_na_mae"] = deducao_em_cadeia(conhecido, mae["internacoes"].to_numpy(), linhas_mae)
    ataque[grupo] = det
    print(grupo, json.dumps(det, ensure_ascii=False), flush=True)

trimestre = {}
for filha, mae, geo in (("res_tri_capitulo", "res_mes", "mun_res"), ("hosp_tri_capitulo", "hosp_mes", "mun_hosp")):
    f = guardados[filha]
    g = f.assign(vis=f["internacoes"].where(~f["oculto"], 0), oc=f["oculto"].astype(int)).groupby([geo, "tri"], sort=False).agg(soma=("vis", "sum"), ocultas=("oc", "sum")).reset_index()
    conhecidos = g.loc[g["ocultas"] == 0, [geo, "tri", "soma"]]
    m = guardados[mae].copy()
    m["tri"] = m["mes"].str[:4] + "T" + ((m["mes"].str[4:6].astype(int) + 2) // 3).astype(str)
    ocultos_por_tri = m.assign(o=m["oculto"].astype(int), vis=m["internacoes"].where(~m["oculto"], 0)).groupby([geo, "tri"], sort=False).agg(o=("o", "sum"), vis=("vis", "sum")).reset_index()
    um = ocultos_por_tri[ocultos_por_tri["o"] == 1].merge(conhecidos, on=[geo, "tri"])
    valor = um["soma"] - um["vis"]
    trimestre[filha] = {"mes_oculto_deduzido": len(um), "valor_1a4": int(faixa_pequena(valor.to_numpy()).sum())}
print("trimestre x mes", json.dumps(trimestre, ensure_ascii=False), flush=True)
pub_ataque = 0
for grupo, det in ataque.items():
    for k, v in det.items():
        if k == "segunda_ordem_na_mae":
            pub_ataque += v["deduzidas_de_1a4"]
        elif "segunda_ordem_margens_publicadas" in v and k in PUBLICAR:
            pub_ataque += v["segunda_ordem_margens_publicadas"]["deduzidas_de_1a4"]
pub_ataque += sum(v["valor_1a4"] for v in trimestre.values())
print("contagens 1 a 4 dedutiveis nas tabelas publicaveis, com as margens publicadas:", pub_ataque, flush=True)
soma_mb = round(sum(r["parquet_mb"] for r in resultados if r["tabela"] in PUBLICAR), 2)
print("MB publicaveis por ano:", soma_mb, flush=True)
(SAIDA / ARQ_SAIDA).write_text(json.dumps({"fatos": fatos, "publicar": PUBLICAR, "mb_publicaveis_por_ano": soma_mb, "tabelas": resultados, "ataque_entre_tabelas": ataque, "ataque_trimestre_mes": trimestre, "dedutiveis_publicaveis": pub_ataque}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("fim", round(time.perf_counter() - inicio), "s")
