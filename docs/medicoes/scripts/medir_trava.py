"""Quantos pares município-competência acionariam a trava de queda entre duas versões do SIH?

Só SP tem as duas versões: a de setembro de 2026 está guardada no projeto de origem, a de outubro vem do FTP.
Com cada competência republicada (2509 a 2607), compara internações por município, por hospital e por residência.
Para separar alarme verdadeiro de falso, usa a mediana das competências 2501 a 2508, que não mudaram.

Uso: python -I medir_trava.py <pasta_rd_sp_antiga> <lib> <pasta_nova> <saida>
"""
import ftplib
import json
import sys
from pathlib import Path


import datasus_dbc
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ANT, LIB, NOVA, SAIDA = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, LIB)
from dbf_reader import read_dbf_bytes  # noqa: E402

NOVA.mkdir(parents=True, exist_ok=True)
COMPS = ["2509", "2510", "2511", "2512", "2601", "2602", "2603", "2604", "2605", "2606", "2607"]
ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=120)
ftp.login()
ftp.cwd("/dissemin/publicos/SIHSUS/200801_/Dados")
ftp.voidcmd("TYPE I")
versao = {}
for c in COMPS:
    nome = f"RDSP{c}.dbc"
    versao[c] = ftp.sendcmd(f"MDTM {nome}").split()[-1]
    alvo = NOVA / nome
    if not alvo.exists():
        with alvo.open("wb") as fh:
            ftp.retrbinary(f"RETR {nome}", fh.write)
    pq_novo = NOVA / f"RDSP{c}.parquet"
    if not pq_novo.exists():
        df = read_dbf_bytes(datasus_dbc.decompress_bytes(alvo.read_bytes()), nome, columns=["IDENT", "MUNIC_MOV", "MUNIC_RES", "VAL_TOT", "CNES", "DT_SAIDA"])
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), pq_novo, compression="zstd")
ftp.quit()
print("versões no FTP:", sorted(set(versao.values())), flush=True)

con = duckdb.connect()
antigos = [f"{ANT}/RDSP{c}.parquet" for c in COMPS]
novos = [(NOVA / f"RDSP{c}.parquet").as_posix() for c in COMPS]
for c, a, n in zip(COMPS, antigos, novos):
    con.execute(f"CREATE OR REPLACE VIEW a{c} AS SELECT '{c}' comp, IDENT, MUNIC_MOV, MUNIC_RES, CNES, substr(DT_SAIDA,1,6) saida FROM read_parquet('{a}')")
    con.execute(f"CREATE OR REPLACE VIEW n{c} AS SELECT '{c}' comp, IDENT, MUNIC_MOV, MUNIC_RES, CNES, substr(DT_SAIDA,1,6) saida FROM read_parquet('{n}')")
ant = " UNION ALL ".join(f"SELECT * FROM a{c}" for c in COMPS)
nov = " UNION ALL ".join(f"SELECT * FROM n{c}" for c in COMPS)
con.execute(f"CREATE TABLE ant AS {ant}")
con.execute(f"CREATE TABLE nov AS {nov}")
FROZEN = f"read_parquet({[f'{ANT}/RDSP25{m:02d}.parquet' for m in range(1, 9)]!r})"

res = {"versoes_ftp": sorted(set(versao.values())), "competencias": COMPS, "visoes": {}}
for visao, col in (("hospital", "MUNIC_MOV"), ("residencia", "MUNIC_RES")):
    con.execute(f"""CREATE OR REPLACE TABLE pares AS
      WITH a AS (SELECT comp, {col} m, count(*) FILTER (IDENT='1') n FROM ant GROUP BY 1,2),
           b AS (SELECT comp, {col} m, count(*) FILTER (IDENT='1') n FROM nov GROUP BY 1,2)
      SELECT coalesce(a.comp,b.comp) comp, coalesce(a.m,b.m) m, coalesce(a.n,0) antes, coalesce(b.n,0) depois
      FROM a FULL JOIN b ON a.comp=b.comp AND a.m=b.m""")
    con.execute(f"""CREATE OR REPLACE TABLE hist AS
      SELECT m, median(n) mediana FROM (SELECT ANO_CMPT||MES_CMPT c, {col} m, count(*) FILTER (IDENT='1') n FROM {FROZEN} GROUP BY 1,2) GROUP BY 1""")
    total = con.execute("SELECT count(*), count(*) FILTER (antes<>depois) FROM pares").fetchone()
    por_comp = con.execute("SELECT comp, count(*) FILTER (antes<>depois) mudaram, sum(antes), sum(depois) FROM pares GROUP BY 1 ORDER BY 1").fetchall()
    linhas = {}
    for base in (100, 50, 20):
        for lim in (30, 50):
            linhas[f"base{base}_queda{lim}"] = con.execute(f"SELECT count(*) FROM pares WHERE antes>={base} AND depois<antes*(1-{lim}/100.0)").fetchone()[0]
    acionados = con.execute("""SELECT p.comp, p.m, p.antes, p.depois, round(100.0*(p.depois-p.antes)/p.antes,1) pct, h.mediana,
        CASE WHEN h.mediana IS NULL THEN 'sem historico'
             WHEN p.depois>=0.7*h.mediana AND p.depois<=1.3*h.mediana THEN 'alarme falso: valor novo condiz com o historico'
             WHEN p.depois<0.7*h.mediana THEN 'alarme verdadeiro: valor novo abaixo do historico'
             ELSE 'indefinido' END classe
      FROM pares p LEFT JOIN hist h USING (m) WHERE p.antes>=100 AND p.depois<p.antes*0.7 ORDER BY pct""").fetchall()
    # O mesmo critério na direção contrária: alta grande entre versões
    altas = con.execute("""SELECT p.comp, p.m, p.antes, p.depois, round(100.0*(p.depois-p.antes)/p.antes,1), h.mediana
      FROM pares p LEFT JOIN hist h USING (m) WHERE p.antes>=100 AND p.depois>p.antes*1.3 ORDER BY 5 DESC""").fetchall()
    # Teste do limite: pares que nunca mudaram servem para ver quantos cairiam só por ruído do mês
    ruido = con.execute("""SELECT count(*) FROM (SELECT p.m FROM pares p JOIN hist h USING (m) WHERE p.antes>=100 AND p.antes=p.depois AND p.depois<0.7*h.mediana)""").fetchone()[0]
    # Subtração entre versões: visível nas duas, e a diferença é uma contagem de 1 a 4
    subtracao = con.execute("""SELECT count(*), count(DISTINCT m) FROM pares WHERE antes>=5 AND depois>=5 AND abs(depois-antes) BETWEEN 1 AND 4""").fetchone()
    subtracao_primeira_vez = con.execute("""SELECT count(*) FROM pares WHERE (antes BETWEEN 1 AND 4 AND depois>=5) OR (depois BETWEEN 1 AND 4 AND antes>=5)""").fetchone()[0]
    uf = con.execute("""SELECT comp, sum(antes), sum(depois), round(100.0*(sum(depois)-sum(antes))/sum(antes),2) FROM pares GROUP BY 1 ORDER BY 4""").fetchall()
    classes = {}
    for a in acionados:
        classes[a[6]] = classes.get(a[6], 0) + 1
    # Municípios por competência acionados: agrupa para saber a concentração
    res["visoes"][visao] = {
        "pares": total[0], "pares_que_mudaram": total[1], "por_competencia": por_comp,
        "acionados_por_limite": linhas, "acionados_base100_queda30": [dict(zip(("comp", "municipio", "antes", "depois", "pct", "mediana_2501_2508", "classe"), a)) for a in acionados],
        "classes": classes, "altas_acima_30pct_base100": len(altas), "altas_exemplos": altas[:6], "pares_inalterados_abaixo_de_70pct_da_mediana": ruido,
        "subtracao_pares_visiveis_dif_1a4": subtracao[0], "subtracao_municipios": subtracao[1], "subtracao_entrou_ou_saiu_de_oculto": subtracao_primeira_vez,
        "variacao_total_sp_por_competencia": uf,
    }
    print(visao, json.dumps({k: v for k, v in res["visoes"][visao].items() if k not in ("por_competencia", "altas_exemplos")}, ensure_ascii=False, default=str), flush=True)
    print("  por competência", por_comp, flush=True)


# O mesmo teste no eixo publicado: município e mês de saída, somando as competências republicadas
eixo = {}
for visao, col in (("hospital", "MUNIC_MOV"), ("residencia", "MUNIC_RES")):
    con.execute(f"""CREATE OR REPLACE TABLE ps AS
      WITH a AS (SELECT saida, {col} m, count(*) FILTER (IDENT='1') n FROM ant GROUP BY 1,2),
           b AS (SELECT saida, {col} m, count(*) FILTER (IDENT='1') n FROM nov GROUP BY 1,2)
      SELECT coalesce(a.saida,b.saida) saida, coalesce(a.m,b.m) m, coalesce(a.n,0) antes, coalesce(b.n,0) depois FROM a FULL JOIN b ON a.saida=b.saida AND a.m=b.m""")
    acion = con.execute("SELECT saida, m, antes, depois, round(100.0*(depois-antes)/antes,1) FROM ps WHERE antes>=100 AND depois<antes*0.7 ORDER BY 1").fetchall()
    subt = con.execute("SELECT count(*), count(DISTINCT m) FROM ps WHERE antes>=5 AND depois>=5 AND abs(depois-antes) BETWEEN 1 AND 4").fetchone()
    mudou = con.execute("SELECT count(*), count(*) FILTER (antes<>depois) FROM ps").fetchone()
    entrou = con.execute("SELECT count(*) FROM ps WHERE (antes BETWEEN 1 AND 4 AND depois>=5) OR (depois BETWEEN 1 AND 4 AND antes>=5)").fetchone()[0]
    eixo[visao] = {"pares": mudou[0], "pares_que_mudaram": mudou[1], "acionados": acion, "subtracao_pares_visiveis_dif_1a4": subt[0], "subtracao_municipios": subt[1], "entrou_ou_saiu_de_oculto": entrou}
    print("mes de saida", visao, json.dumps(eixo[visao], ensure_ascii=False, default=str), flush=True)
res["eixo_mes_de_saida"] = eixo

# Hospitais que somem ou caem entre versões, para mostrar o que aciona a trava
hosp = con.execute("""WITH a AS (SELECT comp, MUNIC_MOV m, CNES c, count(*) n FROM ant GROUP BY 1,2,3), b AS (SELECT comp, MUNIC_MOV m, CNES c, count(*) n FROM nov GROUP BY 1,2,3)
  SELECT a.comp, a.m, count(*) FILTER (b.n IS NULL AND a.n>=50), sum(a.n) FILTER (b.n IS NULL AND a.n>=50) FROM a LEFT JOIN b ON a.comp=b.comp AND a.m=b.m AND a.c=b.c
  GROUP BY 1,2 HAVING count(*) FILTER (b.n IS NULL AND a.n>=50)>0 ORDER BY 1,2""").fetchall()
res["hospitais_que_sumiram"] = hosp
print("hospitais que sumiram, com 50 AIHs ou mais:", hosp, flush=True)
(SAIDA / "trava_versoes.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("fim")
