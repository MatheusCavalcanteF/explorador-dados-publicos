"""Censo Escolar e IDEB por município: supressão, tamanho e os dados para a página.

Uso: python -I medir_educacao.py <censo.zip> <pasta_ideb> <trabalho> <saida>
"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb
import numpy as np
import openpyxl
import pandas as pd

from suprimir import K, chaves_de_linha, complementar, faixa_pequena, linhas_dedutiveis

ZIP, IDEB, TRAB, SAIDA = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
TRAB.mkdir(parents=True, exist_ok=True)
(SAIDA / "parquet").mkdir(exist_ok=True)
z = zipfile.ZipFile(ZIP)
info = next(i for i in z.infolist() if i.filename.lower().endswith("microdados_ed_basica_2024.csv"))
destino = TRAB / "censo2024.csv"
if not destino.exists():
    with z.open(info) as a, destino.open("wb") as b:
        while True:
            pedaco = a.read(1 << 20)
            if not pedaco:
                break
            b.write(pedaco)

con = duckdb.connect()
q = f"read_csv('{destino.as_posix()}', delim=';', header=true, encoding='latin-1', all_varchar=true, sample_size=-1)"
ETAPAS = {"infantil": "QT_MAT_INF", "fund_iniciais": "QT_MAT_FUND_AI", "fund_finais": "QT_MAT_FUND_AF", "medio": "QT_MAT_MED", "eja": "QT_MAT_EJA"}  # sem especial e profissional, que se sobrepõem a estas
REDE = "CASE TP_DEPENDENCIA WHEN '1' THEN 'federal' WHEN '2' THEN 'estadual' WHEN '3' THEN 'municipal' WHEN '4' THEN 'privada' END"
blocos = " UNION ALL ".join(f"SELECT CO_MUNICIPIO mun, {REDE} rede, '{e}' etapa, sum(try_cast({c} AS BIGINT)) n FROM {q} GROUP BY 1,2" for e, c in ETAPAS.items())
df = con.execute(f"SELECT mun, rede, etapa, n::BIGINT n FROM ({blocos}) WHERE n>0 ORDER BY 1,2,3").df()
df["uf"] = df["mun"].str[:2]
print("matriculas por municipio, rede e etapa:", len(df), "soma", int(df["n"].sum()), "| QT_MAT_BAS", con.execute(f"SELECT sum(try_cast(QT_MAT_BAS AS BIGINT)) FROM {q}").fetchone()[0], flush=True)
n = df["n"].to_numpy()
dims = ["mun", "rede", "etapa"]
linhas = chaves_de_linha(df, [[x for x in dims if x != d] for d in dims] + [["rede", "etapa", "uf"]])
primaria = faixa_pequena(n)
oculto, voltas, convergiu = complementar(primaria, linhas, [n])
res = {"censo": {"linhas": len(df), "municipios": int(df["mun"].nunique()), "pct_celulas_primarias": round(100 * primaria.mean(), 1), "pct_celulas_ocultas": round(100 * oculto.mean(), 1), "pct_matriculas_ocultas": round(100 * n[oculto].sum() / n.sum(), 3), "convergiu": convergiu, "linhas_dedutiveis_depois": linhas_dedutiveis(oculto, linhas, [n])}}

# Conferência do arquivo com o que o INEP divulga, e o efeito de somar etapas que se sobrepõem
soma_col = lambda c: f"sum(try_cast({c} AS BIGINT))"
conf = con.execute(f"""SELECT count(*), count(*) FILTER (try_cast(QT_MAT_BAS AS BIGINT)>0), {soma_col('QT_MAT_BAS')}, {soma_col('QT_MAT_ESP')}, {soma_col('QT_MAT_PROF')} FROM {q}""").fetchone()
md5_declarado = next(z.read(i).decode("latin-1") for i in z.infolist() if i.filename.lower().endswith("md5_microdados_ed_basica_2024.txt"))
md5 = hashlib.md5()
with z.open(info) as a:
    for pedaco in iter(lambda: a.read(1 << 20), b""):
        md5.update(pedaco)
soma_etapas = int(df["n"].sum())
res["conferencia"] = {"periodo": "Censo Escolar 2024", "colunas": len(con.execute(f"DESCRIBE SELECT * FROM {q}").fetchall()), "linhas_do_arquivo": conf[0], "escolas_com_matricula": conf[1], "matriculas_qt_mat_bas": int(conf[2]),
                      "divulgado": {"matriculas": "47,1 milhões", "escolas": "179,3 mil", "fonte": "https://www.gov.br/mec/pt-br/centrais-de-conteudo/infograficos/censo-escolar/documentos/censo-escolar-2024.pdf"},
                      "soma_etapas_sem_sobreposicao": soma_etapas, "qt_mat_esp": int(conf[3]), "qt_mat_prof": int(conf[4]), "soma_com_especial_e_profissional": soma_etapas + int(conf[3]) + int(conf[4]),
                      "md5_calculado": md5.hexdigest(), "md5_confere_com_o_declarado_no_zip": md5.hexdigest().upper() in md5_declarado.upper()}
print(json.dumps(res["conferencia"], ensure_ascii=False), flush=True)

# Docentes, turmas e escolas por município e rede
geral = con.execute(f"""SELECT CO_MUNICIPIO mun, {REDE} rede, count(*) FILTER (try_cast(QT_MAT_BAS AS BIGINT)>0)::BIGINT escolas, sum(try_cast(QT_MAT_BAS AS BIGINT))::BIGINT matriculas,
    sum(try_cast(QT_DOC_BAS AS BIGINT))::BIGINT docentes, sum(try_cast(QT_TUR_BAS AS BIGINT))::BIGINT turmas FROM {q} GROUP BY 1,2 HAVING sum(try_cast(QT_MAT_BAS AS BIGINT))>0 ORDER BY 1,2""").df()
geral["uf"] = geral["mun"].str[:2]
g_dims = ["mun", "rede"]
g_linhas = chaves_de_linha(geral, [["mun"], ["rede"], ["rede", "uf"]])
ocultos_g = {}
for c in ("matriculas", "docentes", "turmas"):
    v = geral[c].fillna(0).to_numpy().astype("int64")
    o, _, _ = complementar(faixa_pequena(v), g_linhas, [v])
    ocultos_g[c] = o
    res.setdefault("geral", {})[c] = {"linhas": len(geral), "pct_ocultas": round(100 * o.mean(), 1), "pct_valor_oculto": round(100 * v[o].sum() / max(v.sum(), 1), 3)}
print(json.dumps(res, ensure_ascii=False), flush=True)

pub = df[dims].copy()
pub["matriculas"] = pd.Series(n, dtype="float64").where(~oculto)
arq = SAIDA / "parquet" / "BR_censo_mun_rede_etapa.parquet"
c2 = duckdb.connect()
c2.register("p", pub)
c2.execute(f"COPY (SELECT * FROM p ORDER BY 1,2,3) TO '{arq.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)")
res["censo"]["parquet_mb"] = round(arq.stat().st_size / 1e6, 3)
pub2 = geral[["mun", "rede", "escolas"]].copy()
for c in ("matriculas", "docentes", "turmas"):
    pub2[c] = pd.Series(geral[c].fillna(0).to_numpy(), dtype="float64").where(~ocultos_g[c])
arq2 = SAIDA / "parquet" / "BR_censo_mun_rede.parquet"
c2.register("p2", pub2)
c2.execute(f"COPY (SELECT * FROM p2 ORDER BY 1,2) TO '{arq2.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)")
res["geral"]["parquet_mb"] = round(arq2.stat().st_size / 1e6, 3)

# IDEB: as três planilhas
ideb = {}
por_etapa = {}
for etapa, nome in (("anos_iniciais", "anos_iniciais.xlsx"), ("anos_finais", "anos_finais.xlsx"), ("ensino_medio", "ensino_medio.xlsx")):
    linhas_x = list(openpyxl.load_workbook(IDEB / nome, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
    cab = next(i for i, l in enumerate(linhas_x) if l and l[0] == "SG_UF")
    h = linhas_x[cab]
    idx = {v: i for i, v in enumerate(h)}
    colunas = [v for v in h if v and str(v).startswith("VL_OBSERVADO")]
    dados = [l for l in linhas_x[cab + 1 :] if l and l[0] and re.fullmatch("[A-Z]{2}", str(l[0]))]
    com_nota = set()
    nao_numericos = {}
    for l in dados:
        m = str(l[idx["CO_MUNICIPIO"]])
        serie = []
        for c in colunas:
            v = l[idx[c]]
            if isinstance(v, (int, float)):
                serie.append([int(c[-4:]), round(float(v), 1)])
            else:
                nao_numericos[str(v)] = nao_numericos.get(str(v), 0) + 1
        if serie:
            ideb.setdefault(m, {}).setdefault(etapa, {})[str(l[idx["REDE"]])] = serie
            if serie[-1][0] == 2023:
                com_nota.add(m)
    por_etapa[etapa] = {"linhas": len(dados), "municipios": len({str(l[idx["CO_MUNICIPIO"]]) for l in dados}), "com_nota_2023": len(com_nota), "colunas_serie": len(colunas), "valores_nao_numericos": nao_numericos}
    print(etapa, json.dumps(por_etapa[etapa], ensure_ascii=False), flush=True)
res["ideb"] = por_etapa
(SAIDA / "educacao.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

# Dados por município para a página, já com a supressão
pagina = {}
for (m, rede, etapa), v in zip(df[["mun", "rede", "etapa"]].itertuples(index=False, name=None), np.where(oculto, -1, n)):
    pagina.setdefault(m, {"matriculas": [], "geral": [], "ideb": ideb.get(m, {})})["matriculas"].append([rede, etapa, None if v < 0 else int(v)])
for i, l in enumerate(geral.itertuples(index=False)):
    pagina.setdefault(l.mun, {"matriculas": [], "geral": [], "ideb": ideb.get(l.mun, {})})["geral"].append([l.rede, int(l.escolas), *[None if ocultos_g[c][i] else (0 if pd.isna(getattr(l, c)) else int(getattr(l, c))) for c in ("matriculas", "docentes", "turmas")]])
(TRAB / "educacao_por_municipio.json").write_text(json.dumps(pagina, ensure_ascii=False), encoding="utf-8")
print("fim", json.dumps({k: res[k].get("parquet_mb") for k in ("censo", "geral")}), flush=True)
