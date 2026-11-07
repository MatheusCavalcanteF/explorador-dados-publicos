"""Tamanho real, sem compressão, de todas as tabelas publicáveis por UF, e o que a transferência com gzip custa.

Também grava os arquivos de SP sem compressão, para o teste do formato.

Uso: python -I tamanho_sem_compressao.py <pasta_parquet> <sih_agregados.json> <pasta_site_dados> <saida>
"""
import gzip
import json
import sys
from pathlib import Path

import duckdb

PASTA, AGREG, SITE, SAIDA = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
TMP = SITE / "_tmp_sem"
TMP.mkdir(exist_ok=True)
con = duckdb.connect()
ag = json.load(open(AGREG, encoding="utf-8"))
por_tabela = {r["tabela"]: r for r in ag["tabelas"]}
total, total_gz, total_zstd = 0, 0, 0
maior = (0, "", "")
maior_gz = 0
detalhe = {}
for nome in ag["publicar"]:
    geo = por_tabela[nome]["dims"][0]
    base = (PASTA / f"BR_{nome}.parquet").as_posix()
    soma = soma_gz = 0
    for (uf,) in con.execute(f"SELECT DISTINCT substr({geo},1,2) FROM '{base}' ORDER BY 1").fetchall():
        arq = TMP / f"{nome}_{uf}.parquet"
        con.execute(f"COPY (SELECT * FROM '{base}' WHERE substr({geo},1,2)='{uf}' ORDER BY ALL) TO '{arq.as_posix()}' (FORMAT parquet, COMPRESSION uncompressed, ROW_GROUP_SIZE 50000)")
        b = arq.read_bytes()
        g = len(gzip.compress(b, 6))
        soma += len(b)
        soma_gz += g
        if len(b) > maior[0]:
            maior = (len(b), nome, uf)
            maior_gz = g
        arq.unlink()
    detalhe[nome] = {"soma_mb": round(soma / 1e6, 2), "soma_gzip_mb": round(soma_gz / 1e6, 2)}
    total += soma
    total_gz += soma_gz
    print(nome, detalhe[nome], flush=True)
TMP.rmdir()
for nome in ("res_mes", "res_tri_capitulo", "res_ano_faixa12_sexo", "hosp_tri_capitulo"):
    geo = por_tabela[nome]["dims"][0]
    base = (PASTA / f"BR_{nome}.parquet").as_posix()
    con.execute(f"COPY (SELECT * FROM '{base}' WHERE substr({geo},1,2)='35' ORDER BY ALL) TO '{(SITE / f'uf35_{nome}_sem.parquet').as_posix()}' (FORMAT parquet, COMPRESSION uncompressed, ROW_GROUP_SIZE 50000)")
p = SAIDA / "particoes.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["sem_compressao"] = {"soma_por_uf_mb": round(total / 1e6, 2), "soma_gzip_mb": round(total_gz / 1e6, 2), "maior_arquivo_kb": round(maior[0] / 1e3), "maior_arquivo_gzip_kb": round(maior_gz / 1e3), "maior_tabela": maior[1], "maior_uf": maior[2], "tabelas": detalhe}
p.write_text(json.dumps(d, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in d["sem_compressao"].items() if k != "tabelas"}), "| zstd por UF:", d["soma_por_uf_mb"], d["maior_arquivo_por_uf"])
