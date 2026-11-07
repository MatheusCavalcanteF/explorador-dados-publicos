"""Regras do catálogo medidas nos dados: maturação por UF, revisão entre versões e qualidade dos códigos.

Uso: python -I qualidade_sih.py <pasta_rd_sp> <pasta_outras_uf> <municipios.json> <lib> <pasta_rev> <saida>
"""
import ftplib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import datasus_dbc
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

SP, UF, LOC, LIB, REV, SAIDA = sys.argv[1:7]
REV, SAIDA = Path(REV), Path(SAIDA)
REV.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, LIB)
from dbf_reader import read_dbf_bytes  # noqa: E402

COL = "ANO_CMPT,MES_CMPT,IDENT,CNES,MUNIC_MOV,MUNIC_RES,DIAG_PRINC,DT_INTER,DT_SAIDA,DIAS_PERM,VAL_TOT,MORTE,ESPEC,CAR_INT,SEXO,IDADE,COD_IDADE,COMPLEX,RACA_COR"
con = duckdb.connect()
con.execute("SET threads=6")
con.execute(f"CREATE VIEW br AS SELECT {COL} FROM read_parquet('{SP}/RDSP25*.parquet') UNION ALL BY NAME SELECT {COL} FROM read_parquet('{UF}/RD*.parquet')")
validos = [str(m["id"])[:6] for m in json.load(open(LOC, encoding="utf-8"))]
con.execute("CREATE TABLE ibge AS SELECT unnest(?) AS cod", [validos])
res = {}

# Maturação: quanto das altas de jan-jun/2025 chegou em cada defasagem, por UF do hospital
mat = con.execute("""
WITH a AS (
  SELECT substr(MUNIC_MOV,1,2) uf,
    (ANO_CMPT::INT*12+MES_CMPT::INT)-(substr(DT_SAIDA,1,4)::INT*12+substr(DT_SAIDA,5,2)::INT) lag
  FROM br WHERE IDENT='1' AND substr(DT_SAIDA,1,6) BETWEEN '202501' AND '202506'
), t AS (SELECT uf, count(*) n FROM a GROUP BY 1)
SELECT a.uf, t.n,
  round(100.0*count(*) FILTER (lag<=0)/t.n,1) d0,
  round(100.0*count(*) FILTER (lag<=1)/t.n,1) d1,
  round(100.0*count(*) FILTER (lag<=2)/t.n,1) d2,
  round(100.0*count(*) FILTER (lag<=3)/t.n,1) d3,
  round(100.0*count(*) FILTER (lag<=4)/t.n,1) d4,
  round(100.0*count(*) FILTER (lag<=6)/t.n,1) d6
FROM a JOIN t USING(uf) GROUP BY a.uf, t.n ORDER BY d3, a.uf
""").fetchall()
res["maturacao_por_uf"] = [dict(zip(["uf", "altas", "ate0", "ate1", "ate2", "ate3", "ate4", "ate6"], m)) for m in mat]
nac = con.execute("""
WITH a AS (SELECT (ANO_CMPT::INT*12+MES_CMPT::INT)-(substr(DT_SAIDA,1,4)::INT*12+substr(DT_SAIDA,5,2)::INT) lag
  FROM br WHERE IDENT='1' AND substr(DT_SAIDA,1,6) BETWEEN '202501' AND '202506')
SELECT count(*), round(100.0*count(*) FILTER (lag<=0)/count(*),1), round(100.0*count(*) FILTER (lag<=1)/count(*),1),
  round(100.0*count(*) FILTER (lag<=2)/count(*),1), round(100.0*count(*) FILTER (lag<=3)/count(*),1), round(100.0*count(*) FILTER (lag<=4)/count(*),1), round(100.0*count(*) FILTER (lag<=6)/count(*),1) FROM a""").fetchone()
res["maturacao_brasil"] = dict(zip(["altas", "ate0", "ate1", "ate2", "ate3", "ate4", "ate6"], nac))
print("maturação Brasil", res["maturacao_brasil"], flush=True)
print("piores d3:", [(m[0], m[5]) for m in mat[:6]], "melhores d3:", [(m[0], m[5]) for m in mat[-3:]], flush=True)

# Qualidade
q = {}
q["linhas"] = con.execute("SELECT count(*) FROM br").fetchone()[0]
q["ident"] = con.execute("SELECT IDENT, count(*) FROM br GROUP BY 1 ORDER BY 2 DESC").fetchall()
q["sexo"] = con.execute("SELECT SEXO, count(*) FROM br GROUP BY 1 ORDER BY 2 DESC").fetchall()
q["cod_idade"] = con.execute("SELECT COD_IDADE, count(*) FROM br GROUP BY 1 ORDER BY 2 DESC").fetchall()
q["car_int"] = con.execute("SELECT CAR_INT, count(*) FROM br GROUP BY 1 ORDER BY 2 DESC").fetchall()
q["raca"] = con.execute("SELECT RACA_COR, count(*) FROM br GROUP BY 1 ORDER BY 2 DESC").fetchall()
q["mov_fora_ibge"] = con.execute("SELECT MUNIC_MOV, count(*) FROM br WHERE MUNIC_MOV NOT IN (SELECT cod FROM ibge) GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall()
q["res_fora_ibge"] = con.execute("SELECT MUNIC_RES, count(*) FROM br WHERE MUNIC_RES NOT IN (SELECT cod FROM ibge) GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall()
q["ibge_sem_res"] = con.execute("SELECT cod FROM ibge WHERE cod NOT IN (SELECT DISTINCT MUNIC_RES FROM br)").fetchall()
q["cid_invalido"] = con.execute("SELECT count(*) FROM br WHERE NOT regexp_full_match(DIAG_PRINC,'[A-Z][0-9]{2}[0-9A-Z]?')").fetchone()[0]
q["saida_invalida"] = con.execute("SELECT count(*) FROM br WHERE try_strptime(DT_SAIDA,'%Y%m%d') IS NULL").fetchone()[0]
q["saida_antes_entrada"] = con.execute("SELECT count(*) FROM br WHERE DT_SAIDA<DT_INTER").fetchone()[0]
q["dias_negativos"] = con.execute("SELECT count(*) FROM br WHERE DIAS_PERM<0").fetchone()[0]
q["valor_zero_ou_nulo"] = con.execute("SELECT count(*) FILTER (VAL_TOT=0), count(*) FILTER (VAL_TOT IS NULL), count(*) FILTER (VAL_TOT<0) FROM br").fetchone()
q["chave_duplicada_em_uma_uf"] = None
q["aih_valor_zero_por_espec"] = con.execute("SELECT ESPEC, count(*) FROM br WHERE VAL_TOT=0 GROUP BY 1 ORDER BY 2 DESC LIMIT 5").fetchall()
q["hospital_em_mais_de_um_municipio"] = con.execute("SELECT count(*) FROM (SELECT CNES FROM br GROUP BY 1 HAVING count(DISTINCT MUNIC_MOV)>1)").fetchone()[0]
q["hospitais"] = con.execute("SELECT count(DISTINCT CNES) FROM br").fetchone()[0]


def sem_categoria_pequena(pares, k=5):
    """Soma à menor categoria seguinte as que têm menos de k. Só mascarar não basta: o total revelaria o valor por subtração."""
    pares = sorted(pares, key=lambda p: p[1], reverse=True)
    while len(pares) > 1 and pares[-1][1] < k:
        menor, seguinte = pares.pop(), pares.pop()
        pares.append((f"{seguinte[0]} + {menor[0]}", seguinte[1] + menor[1]))
        pares.sort(key=lambda p: p[1], reverse=True)
    return pares


for chave in ("ident", "sexo", "cod_idade", "car_int", "raca", "aih_valor_zero_por_espec"):
    q[chave] = sem_categoria_pequena(q[chave])
res["qualidade"] = q
print(json.dumps(q, ensure_ascii=False, default=str)[:1800], flush=True)

# Revisão: versão local de set/2026 x versão atual do FTP (out/2026)
ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=120)
ftp.login()
ftp.cwd("/dissemin/publicos/SIHSUS/200801_/Dados")
ftp.voidcmd("TYPE I")
rev = []
for comp in ("2509", "2601", "2603", "2605", "2607"):
    nome = f"RDSP{comp}.dbc"
    alvo = REV / nome
    if not alvo.exists():
        with alvo.open("wb") as fh:
            ftp.retrbinary(f"RETR {nome}", fh.write)
    novo = REV / f"RDSP{comp}.parquet"
    if not novo.exists():
        df = read_dbf_bytes(datasus_dbc.decompress_bytes(alvo.read_bytes()), nome, columns=["N_AIH", "IDENT", "MUNIC_MOV", "MUNIC_RES", "DIAG_PRINC", "VAL_TOT", "MORTE", "DT_SAIDA", "CNES"])
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), novo, compression="zstd")
    ant = f"read_parquet('{SP}/RDSP{comp}.parquet')"
    atu = f"read_parquet('{novo.as_posix()}')"
    a = con.execute(f"SELECT count(*), count(*) FILTER (IDENT='1'), round(sum(VAL_TOT),2), sum(MORTE) FROM {ant}").fetchone()
    b = con.execute(f"SELECT count(*), count(*) FILTER (IDENT='1'), round(sum(VAL_TOT),2), sum(MORTE) FROM {atu}").fetchone()
    k = "N_AIH, IDENT, DT_SAIDA"
    saiu = con.execute(f"SELECT count(*) FROM (SELECT {k} FROM {ant} EXCEPT SELECT {k} FROM {atu})").fetchone()[0]
    entrou = con.execute(f"SELECT count(*) FROM (SELECT {k} FROM {atu} EXCEPT SELECT {k} FROM {ant})").fetchone()[0]
    mudou_mun = con.execute(f"""SELECT count(*) FROM (
        SELECT MUNIC_MOV m, count(*) FILTER (IDENT='1') n FROM {ant} GROUP BY 1) x FULL JOIN (
        SELECT MUNIC_MOV m, count(*) FILTER (IDENT='1') n FROM {atu} GROUP BY 1) y USING(m) WHERE coalesce(x.n,0)<>coalesce(y.n,0)""").fetchone()[0]
    maior = con.execute(f"""SELECT m, x.n, y.n, round(100.0*(y.n-x.n)/x.n,1) FROM (
        SELECT MUNIC_MOV m, count(*) FILTER (IDENT='1') n FROM {ant} GROUP BY 1) x JOIN (
        SELECT MUNIC_MOV m, count(*) FILTER (IDENT='1') n FROM {atu} GROUP BY 1) y USING(m) WHERE x.n>=100 ORDER BY abs(y.n-x.n)*1.0/x.n DESC, m LIMIT 1""").fetchone()
    linha = {"comp": comp, "linhas_ant": a[0], "linhas_atu": b[0], "intern_ant": a[1], "intern_atu": b[1], "valor_ant": a[2], "valor_atu": b[2], "obitos_ant": a[3], "obitos_atu": b[3],
             "saiu": saiu, "entrou": entrou, "municipios_mudaram": mudou_mun, "maior_mudanca_ge100": maior}
    rev.append(linha)
    print(json.dumps(linha, ensure_ascii=False, default=str), flush=True)
ftp.quit()
res["revisao_set_para_out_2026"] = rev
(SAIDA / "sih_regras.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("fim")
