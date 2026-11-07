"""Tamanho por UF de cada tabela publicável, e os arquivos para o teste do leitor.

Também compara os formatos de compressão do Parquet: arquivo, transferência com gzip e código do leitor.

Uso: python -I particoes.py <pasta_parquet> <sih_agregados.json> <pasta_site_dados> <saida>
"""
import gzip
import json
import sys
from pathlib import Path

import duckdb

PASTA, AGREG, SITE, SAIDA = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
SITE.mkdir(parents=True, exist_ok=True)
TMP = SITE / "_tmp"
TMP.mkdir(exist_ok=True)
con = duckdb.connect()
ag = json.load(open(AGREG, encoding="utf-8"))
por_tabela = {r["tabela"]: r for r in ag["tabelas"]}
res = {"tabelas": {}}
maior_global = (0, "", "")
soma_uf_total = 0
for nome in ag["publicar"]:
    dims = por_tabela[nome]["dims"]
    geo = dims[0]
    base = (PASTA / f"BR_{nome}.parquet").as_posix()
    tam = {}
    for (uf,) in con.execute(f"SELECT DISTINCT substr({geo},1,2) FROM '{base}' ORDER BY 1").fetchall():
        arq = TMP / f"{nome}_{uf}.parquet"
        con.execute(f"COPY (SELECT * FROM '{base}' WHERE substr({geo},1,2)='{uf}' ORDER BY ALL) TO '{arq.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)")
        tam[uf] = arq.stat().st_size
        if tam[uf] > maior_global[0]:
            maior_global = (tam[uf], nome, uf)
        arq.unlink()
    res["tabelas"][nome] = {"soma_mb": round(sum(tam.values()) / 1e6, 2), "maior_uf": max(tam, key=tam.get), "maior_kb": round(max(tam.values()) / 1e3), "menor_kb": round(min(tam.values()) / 1e3)}
    soma_uf_total += sum(tam.values())
    print(nome, res["tabelas"][nome], flush=True)
res["soma_por_uf_mb"] = round(soma_uf_total / 1e6, 2)
res["maior_arquivo_por_uf"] = {"kb": round(maior_global[0] / 1e3), "tabela": maior_global[1], "uf": maior_global[2]}

# Formatos: a maior tabela publicável, recortada em SP
ALVO = "res_tri_capitulo"
base = (PASTA / f"BR_{ALVO}.parquet").as_posix()
formatos = {}
for rot, opt in (("zstd", "COMPRESSION zstd, COMPRESSION_LEVEL 9"), ("snappy", "COMPRESSION snappy"), ("sem", "COMPRESSION uncompressed")):
    arq = SITE / f"uf35_{ALVO}_{rot}.parquet"
    con.execute(f"COPY (SELECT * FROM '{base}' WHERE substr(mun_res,1,2)='35' ORDER BY ALL) TO '{arq.as_posix()}' (FORMAT parquet, {opt}, ROW_GROUP_SIZE 50000)")
    b = arq.read_bytes()
    formatos[rot] = {"arquivo_kb": round(len(b) / 1e3, 1), "transferencia_gzip_kb": round(len(gzip.compress(b, 6)) / 1e3, 1)}
res["formatos_sp"] = formatos
print(json.dumps(formatos), flush=True)

# Arquivos usados no teste do leitor
for nome in ("res_mes", "res_tri_capitulo", "res_ano_faixa12_sexo", "hosp_tri_capitulo", "res_ano_capitulo"):
    origem = PASTA / f"BR_{nome}.parquet"
    (SITE / origem.name).write_bytes(origem.read_bytes())
    geo = por_tabela[nome]["dims"][0]
    con.execute(f"COPY (SELECT * FROM '{origem.as_posix()}' WHERE substr({geo},1,2)='35' ORDER BY ALL) TO '{(SITE / f'uf35_{nome}.parquet').as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9)")

TMP.rmdir()
(SAIDA / "particoes.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print("fim", res["soma_por_uf_mb"], res["maior_arquivo_por_uf"])
