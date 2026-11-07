"""Estima o JSON por município com o conteúdo da v1 e 36 meses.

MEDIDO: um ano de SIH (2025), Censo 2024, toda a série do IDEB, IBGE. ESTIMADO: os outros dois anos do SIH e do
Censo, gerados a partir do ano medido com ruído de 5%, para o gzip não comprimir cópias idênticas. Os valores
ocultos continuam ocultos. Os arquivos servem para medir tamanho e carregamento, não como dado.

Uso: python -I gerar_json_municipios.py <parquet_sih> <educacao_por_municipio.json> <municipios.json> <sidra_6579.json> <sidra_5938.json> <sidra_4714.json> <destino> <saida>
"""
import gzip
import json
import random
import statistics
import sys
import time
from pathlib import Path

import duckdb

SIH, EDU, LOC, POP, PIB, CENSO, DEST, SAIDA = sys.argv[1:9]
DEST, SAIDA = Path(DEST), Path(SAIDA)
DEST.mkdir(parents=True, exist_ok=True)
con = duckdb.connect()
inicio = time.perf_counter()
random.seed(20261107)
municipios = json.load(open(LOC, encoding="utf-8"))


def uf_de(m):
    micro = m.get("microrregiao") or {}
    return micro["mesorregiao"]["UF"]["sigla"] if micro else m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]


pop = {int(r["D1C"]): int(r["V"]) for r in json.load(open(POP, encoding="utf-8"))[1:]}
pib = {int(r["D1C"]): int(r["V"]) for r in json.load(open(PIB, encoding="utf-8"))[1:]}
censo22 = {int(r["D1C"]): int(r["V"]) for r in json.load(open(CENSO, encoding="utf-8"))[1:]}
edu = json.load(open(EDU, encoding="utf-8"))


def carregar(arquivo, chave, colunas):
    caminho = Path(SIH) / f"{arquivo}.parquet"
    grupos = {}
    for linha in con.execute(f"SELECT {chave}, {', '.join(colunas)} FROM read_parquet('{caminho.as_posix()}') ORDER BY ALL").fetchall():
        grupos.setdefault(linha[0], []).append(list(linha[1:]))
    return grupos


def num(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return int(v) if float(v) == int(v) else round(float(v), 2)


def linha_limpa(l):
    return [num(x) if isinstance(x, float) else x for x in l]


MED = ["internacoes", "dias", "valor"]
tab = {
    "res_mes": carregar("BR_res_mes", "mun_res", ["mes", *MED]),
    "hosp_mes": carregar("BR_hosp_mes", "mun_hosp", ["mes", *MED]),
    "res_mes_sexo": carregar("BR_res_mes_sexo", "mun_res", ["mes", "sexo", "internacoes"]),
    "res_mes_urgencia": carregar("BR_res_mes_urgencia", "mun_res", ["mes", "urgencia", "internacoes"]),
    "res_mes_faixa5": carregar("BR_res_mes_faixa5", "mun_res", ["mes", "faixa5", "internacoes"]),
    "res_tri_capitulo": carregar("BR_res_tri_capitulo", "mun_res", ["tri", "capitulo", "internacoes"]),
    "hosp_tri_capitulo": carregar("BR_hosp_tri_capitulo", "mun_hosp", ["tri", "capitulo", "internacoes"]),
    "res_ano_capitulo": carregar("BR_res_ano_capitulo", "mun_res", ["ano", "capitulo", *MED]),
    "res_ano_faixa12_sexo": carregar("BR_res_ano_faixa12_sexo", "mun_res", ["ano", "faixa12", "sexo", "internacoes"]),
    "res_ano_raca": carregar("BR_res_ano_raca", "mun_res", ["ano", "raca", "internacoes"]),
    "hosp_ano_espec": carregar("BR_hosp_ano_espec", "mun_hosp", ["ano", "espec", "internacoes"]),
    "obitos_res_ano": carregar("BR_obitos_res_ano", "mun_res", ["ano", "internacoes", "obitos"]),
    "obitos_hosp_ano": carregar("BR_obitos_hosp_ano", "mun_hosp", ["ano", "internacoes", "obitos"]),
}
fluxo = carregar("BR_fluxo_res_hosp_ano", "mun_res", ["mun_hosp", "internacoes"])


def anos_estimados(linhas, ano_coluna=0):
    """Gera 2023 e 2024 a partir de 2025, trocando o período e variando os valores em 5%."""
    saida = [linha_limpa(l) for l in linhas]
    for delta in (1, 2):
        for l in linhas:
            nova = linha_limpa(l)
            p = str(nova[ano_coluna])
            nova[ano_coluna] = str(int(p[:4]) - delta) + p[4:]
            nova = [round(x * random.uniform(0.95, 1.05)) if isinstance(x, int) and i != ano_coluna else x for i, x in enumerate(nova)]
            saida.append(nova)
    return saida


tamanhos, comprimidos = {}, {}
partes_medias = {"sih": [], "educacao": [], "ibge": []}
amostras = {}
for m in municipios:
    id7 = m["id"]
    id6 = str(id7)[:6]
    sih = {k: anos_estimados(v.get(id6, [])) for k, v in tab.items()}
    sih["fluxo_destinos"] = [linha_limpa(l) for l in sorted(fluxo.get(id6, []), key=lambda l: -(l[1] if l[1] == l[1] and l[1] is not None else 0))[:12]]
    e = edu.get(str(id7), {"matriculas": [], "geral": [], "ideb": {}})
    educacao = {
        "matriculas": [[a] + l for a in (2024, 2023, 2022) for l in e["matriculas"]],
        "geral": [[a] + l for a in (2024, 2023, 2022) for l in e["geral"]],
        "ideb": e["ideb"],
    }
    ibge = {"populacao": [[2026, pop.get(id7)], [2022, censo22.get(id7)]], "pib_mil_reais": [[2023, pib.get(id7)]]}
    doc = {"id": id7, "nome": m["nome"], "uf": uf_de(m), "versao": "2026-11", "sih": sih, "educacao": educacao, "ibge": ibge}
    corpo = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (DEST / f"{id7}.json").write_bytes(corpo)
    tamanhos[id7] = len(corpo)
    comprimidos[id7] = len(gzip.compress(corpo, 6))
    for k, v in (("sih", sih), ("educacao", educacao), ("ibge", ibge)):
        partes_medias[k].append(len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))))
    if id7 in (3548500, 3550308, 3506359, 3500105, 5300108, 3304557):
        amostras[str(id7)] = {"nome": m["nome"], "bytes": len(corpo), "gzip": comprimidos[id7]}

v = sorted(tamanhos.values())
g = sorted(comprimidos.values())
top = sorted(tamanhos, key=tamanhos.get, reverse=True)[:5]
nomes = {m["id"]: m["nome"] for m in municipios}
res = {
    "natureza": "estimativa: um ano medido e dois gerados, com o conteúdo da v1",
    "arquivos": len(v), "total_mb": round(sum(v) / 1e6, 1), "total_gzip_mb": round(sum(g) / 1e6, 1),
    "p50_kb": round(statistics.median(v) / 1e3, 1), "p95_kb": round(v[int(len(v) * 0.95)] / 1e3, 1), "p99_kb": round(v[int(len(v) * 0.99)] / 1e3, 1), "max_kb": round(v[-1] / 1e3, 1),
    "p50_gzip_kb": round(statistics.median(g) / 1e3, 1), "p95_gzip_kb": round(g[int(len(g) * 0.95)] / 1e3, 1), "p99_gzip_kb": round(g[int(len(g) * 0.99)] / 1e3, 1), "max_gzip_kb": round(g[-1] / 1e3, 1),
    "maiores": [{"nome": nomes[i], "kb": round(tamanhos[i] / 1e3, 1), "gzip_kb": round(comprimidos[i] / 1e3, 1)} for i in top],
    "amostras": amostras,
    "mediana_por_parte_kb": {k: round(statistics.median(x) / 1e3, 1) for k, x in partes_medias.items()},
}
indice = [[m["id"], m["nome"], uf_de(m)] for m in municipios]
corpo = json.dumps(indice, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
(DEST / "indice.json").write_bytes(corpo)
res["indice_kb"] = round(len(corpo) / 1e3, 1)
res["indice_gzip_kb"] = round(len(gzip.compress(corpo, 6)) / 1e3, 1)
(SAIDA / "json_municipios.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(ascii(json.dumps(res, ensure_ascii=False)))
print("fim", round(time.perf_counter() - inicio, 1), "s")
