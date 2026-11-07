"""Mede agregados do Novo CAGED 2025 com supressão por métrica, e a defasagem das declarações fora do prazo.

A célula fica oculta quando admissões, desligamentos ou o total de movimentos estão entre 1 e 4.
Saldo visível com admissões e desligamentos ocultos permitiria deduzir, por isso os três saem juntos.
As tabelas usam só o MOV: tamanho e supressão com FOR e EXC ainda não foram medidos.

Uso: python -I medir_caged.py <pasta_7z> <pasta_trabalho> <saida>
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb
import numpy as np
import py7zr

from suprimir import K, chaves_de_linha, complementar, faixa_pequena, linhas_dedutiveis

PASTA, TRAB, SAIDA = map(Path, sys.argv[1:4])
con = duckdb.connect()
con.execute("SET threads=8; SET memory_limit='10GB'")
TRAB.mkdir(parents=True, exist_ok=True)
(SAIDA / "parquet_caged").mkdir(parents=True, exist_ok=True)

ini = time.perf_counter()
for tipo in ("MOV", "FOR", "EXC"):
    partes = []
    for comp_dir in sorted(PASTA.iterdir()):
        arq = comp_dir / f"CAGED{tipo}{comp_dir.name}.7z"
        pasta_tmp = TRAB / f"x_{tipo}_{comp_dir.name}"
        parte = TRAB / f"{tipo}_{comp_dir.name}.parquet"
        if not parte.exists():
            pasta_tmp.mkdir(exist_ok=True)
            with py7zr.SevenZipFile(arq) as z:
                z.extractall(pasta_tmp)
            txt = next(pasta_tmp.glob("*.txt"))
            con.execute(f"""COPY (SELECT * FROM read_csv('{txt.as_posix()}', delim=';', header=true, all_varchar=true, sample_size=-1, normalize_names=true))
                TO '{parte.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
            shutil.rmtree(pasta_tmp)
        partes.append(parte.as_posix())
    con.execute(f"CREATE OR REPLACE VIEW v_{tipo.lower()} AS SELECT * FROM read_parquet({partes!r}, union_by_name=true)")
    print(tipo, "pronto", con.execute(f"SELECT count(*) FROM v_{tipo.lower()}").fetchone(), round(time.perf_counter() - ini), "s", flush=True)

nomes = [r[0] for r in con.execute("DESCRIBE SELECT * FROM v_mov").fetchall()]


def achar(*trechos):
    for n in nomes:
        if all(t in n for t in trechos):
            return n
    raise KeyError(trechos)


C_MUN, C_COMP, C_SALDO = achar("munic"), achar("compet", "mov"), achar("saldo")
C_SUB, C_SEXO, C_IDADE, C_INSTR, C_CBO, C_DEC = achar("subclasse"), achar("sexo"), achar("idade"), achar("instru"), achar("cbo"), achar("compet", "dec")
C_SECAO = next(n for n in nomes if n.startswith("se") and n != C_SEXO)

fatos = {}
fatos["linhas"] = {t: con.execute(f"SELECT count(*) FROM v_{t}").fetchone()[0] for t in ("mov", "for", "exc")}
fatos["municipios_mov"] = con.execute(f"SELECT count(DISTINCT {C_MUN}) FROM v_mov").fetchone()[0]
fatos["codigos_estranhos"] = con.execute(f"SELECT {C_MUN}, count(*) FROM v_mov WHERE NOT regexp_full_match({C_MUN},'[1-5][0-9]{{5}}') GROUP BY 1 ORDER BY 2 DESC LIMIT 6").fetchall()
fatos["saldo_mov_por_mes"] = con.execute(f"SELECT {C_COMP}, sum({C_SALDO}::INT), count(*) FROM v_mov GROUP BY 1 ORDER BY 1").fetchall()
for t in ("for", "exc"):
    fatos[f"defasagem_{t}_meses"] = con.execute(f"""SELECT (substr({C_DEC},1,4)::INT*12+substr({C_DEC},5,2)::INT)-(substr({C_COMP},1,4)::INT*12+substr({C_COMP},5,2)::INT) d, count(*) n
      FROM v_{t} GROUP BY 1 ORDER BY 1""").fetchall()
fatos["comp_for_min_max"] = con.execute(f"SELECT min({C_COMP}), max({C_COMP}), min({C_DEC}), max({C_DEC}) FROM v_for").fetchone()
fatos["saldo_2025_com_ajustes"] = con.execute(f"""
  SELECT (SELECT sum({C_SALDO}::INT) FROM v_mov WHERE {C_COMP} LIKE '2025%')
       + (SELECT sum({C_SALDO}::INT) FROM v_for WHERE {C_COMP} LIKE '2025%')
       - (SELECT sum({C_SALDO}::INT) FROM v_exc WHERE {C_COMP} LIKE '2025%')""").fetchone()[0]
fatos["saldo_2025_so_mov"] = con.execute(f"SELECT sum({C_SALDO}::INT) FROM v_mov WHERE {C_COMP} LIKE '2025%'").fetchone()[0]
fatos["base_das_tabelas"] = "Só MOV de 2025, sem FOR nem EXC e sem o código de município ignorado. FOR e EXC entram apenas no saldo nacional saldo_2025_com_ajustes."
tamanhos_mov = []
for comp_dir in sorted(PASTA.iterdir()):
    arq_mov = comp_dir / f"CAGEDMOV{comp_dir.name}.7z"
    with py7zr.SevenZipFile(arq_mov) as z:
        tamanhos_mov.append({"competencia": comp_dir.name, "comprimido_mb": round(arq_mov.stat().st_size / 1e6, 1), "aberto_mb": round(z.archiveinfo().uncompressed / 1e6, 1)})
fatos["arquivos_mov"] = tamanhos_mov
print(json.dumps({k: fatos[k] for k in ("linhas", "municipios_mov", "saldo_2025_com_ajustes", "saldo_2025_so_mov")}, ensure_ascii=False, default=str), flush=True)

FAIXA = f"""CASE WHEN try_cast({C_IDADE} AS INT) IS NULL THEN 'ign' WHEN {C_IDADE}::INT<18 THEN '<18' WHEN {C_IDADE}::INT<25 THEN '18-24' WHEN {C_IDADE}::INT<40 THEN '25-39'
  WHEN {C_IDADE}::INT<50 THEN '40-49' WHEN {C_IDADE}::INT<65 THEN '50-64' ELSE '65+' END"""
con.execute(f"""CREATE OR REPLACE TABLE c AS
  SELECT {C_MUN} mun, {C_COMP} mes, substr({C_COMP},1,4) ano, {C_SECAO} secao, substr({C_SUB},1,2) divisao, {C_SUB} subclasse,
    {C_SEXO} sexo, {FAIXA} faixa, {C_INSTR} instrucao, substr({C_CBO},1,1) cbo1, {C_CBO} cbo, {C_SALDO}::INT saldo
  FROM v_mov WHERE {C_MUN} NOT LIKE '%9999%'""")
TABELAS = [
    ("mun_mes", ["mun", "mes"]), ("mun_mes_sexo", ["mun", "mes", "sexo"]), ("mun_mes_faixa", ["mun", "mes", "faixa"]),
    ("mun_mes_cbo1", ["mun", "mes", "cbo1"]), ("mun_mes_secao", ["mun", "mes", "secao"]), ("mun_mes_instrucao", ["mun", "mes", "instrucao"]),
    ("mun_ano_secao", ["mun", "ano", "secao"]), ("mun_ano_subclasse", ["mun", "ano", "subclasse"]), ("mun_mes_divisao", ["mun", "mes", "divisao"]),
    ("mun_ano_cbo", ["mun", "ano", "cbo"]), ("mun_mes_secao_sexo", ["mun", "mes", "secao", "sexo"]), ("mun_ano_secao_sexo_faixa", ["mun", "ano", "secao", "sexo", "faixa"]),
]
res = []
mascara_mae = None
for nome, dims in TABELAS:
    t0 = time.perf_counter()
    d_sql = ", ".join(dims)
    df = con.execute(f"SELECT {d_sql}, count(*) mov, count(*) FILTER (saldo=1) adm, count(*) FILTER (saldo=-1) des, sum(saldo) saldo FROM c GROUP BY {d_sql} ORDER BY {d_sql}").df()
    for c in dims:
        df[c] = df[c].astype(str)
    for c in ("mov", "adm", "des", "saldo"):
        df[c] = df[c].astype("int64")
    df["uf"] = df["mun"].str[:2]
    mov, adm, des = df["mov"].to_numpy(), df["adm"].to_numpy(), df["des"].to_numpy()

    # Regra anterior: só o total de movimentos, sem margem por UF
    antigas = chaves_de_linha(df, [[x for x in dims if x != d] for d in dims])
    oculto_antigo, _, _ = complementar(mov < K, antigas, [mov])
    vazou = int(((faixa_pequena(adm) | faixa_pequena(des)) & ~oculto_antigo).sum())

    linhas = chaves_de_linha(df, [[x for x in dims if x != d] for d in dims] + [[x for x in dims if x != "mun"] + ["uf"]])
    primaria = (mov < K) | faixa_pequena(adm) | faixa_pequena(des)
    if nome != "mun_mes" and dims[:2] == ["mun", "mes"]:
        # Família: oculta na mãe esconde as filhas da mesma chave
        primaria = primaria | df[["mun", "mes"]].merge(mascara_mae, on=["mun", "mes"], how="left")["h"].fillna(False).to_numpy(dtype=bool)
    oculto, voltas, convergiu = complementar(primaria, linhas, [mov, adm, des])
    if nome == "mun_mes":
        mascara_mae = df.loc[oculto, ["mun", "mes"]].assign(h=True)
    r = {"tabela": nome, "linhas": len(df), "regra_antiga_visiveis_adm_ou_des_1a4": vazou, "regra_antiga_pct_celulas_ocultas": round(100 * oculto_antigo.mean(), 1),
         "pct_celulas_primarias": round(100 * primaria.mean(), 1), "pct_celulas_ocultas": round(100 * oculto.mean(), 1),
         "pct_mov_ocultos": round(100 * mov[oculto].sum() / mov.sum(), 2), "linhas_dedutiveis_depois": linhas_dedutiveis(oculto, linhas, [mov, adm, des]), "voltas": voltas, "convergiu": convergiu, "municipios": int(df["mun"].nunique())}
    pub = df[dims].copy()
    for c in ("adm", "des", "saldo"):
        pub[c] = df[c].astype("float64")
        pub.loc[oculto, c] = np.nan
    pub["oculto"] = oculto
    con.register("pub_df", pub)
    arq = SAIDA / "parquet_caged" / f"BR_{nome}.parquet"
    con.execute(f"COPY (SELECT * FROM pub_df ORDER BY {d_sql}) TO '{arq.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, ROW_GROUP_SIZE 50000)")
    con.unregister("pub_df")
    r["parquet_mb"] = round(arq.stat().st_size / 1e6, 2)
    r["segundos"] = round(time.perf_counter() - t0, 1)
    res.append(r)
    print(json.dumps(r, ensure_ascii=False), flush=True)
    (SAIDA / "caged_agregados.json").write_text(json.dumps({"fatos": fatos, "tabelas": res}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("fim", round(time.perf_counter() - ini), "s")
