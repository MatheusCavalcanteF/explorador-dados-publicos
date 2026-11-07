"""Tabela-resumo dos agregados. Uso: python -I resumo.py <sih_agregados.json> [<caged_agregados.json>]"""
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print("tabela                          linhas  antiga:vis1a4 %cel_ant | %cel<5  %cel_ocult %intern_oc %aih_oc | dedut | MB")
pub = 0
for r in d["tabelas"]:
    print(f"{r['tabela']:<30} {r['linhas']:>8} {r['regra_antiga_visiveis_internacoes_1a4']:>9} {r['regra_antiga_pct_celulas_ocultas']:>7} | {r['pct_celulas_primarias']:>6} {r['pct_celulas_ocultas']:>7} {r['pct_internacoes_ocultas']:>9} {r['pct_aihs_ocultas']:>7} | {r['linhas_dedutiveis_depois']:>4} | {r['parquet_mb']:>5}")
print("visíveis 1a4 agora:", sum(r["visiveis_internacoes_1a4"] for r in d["tabelas"]))
print("ataque:", json.dumps(d.get("ataque_entre_tabelas"), ensure_ascii=False))
print("defasagem:", [(x["meses"], x["acumulado_pct"]) for x in d["fatos"]["defasagem_saida_competencia"]][:18], "... max", d["fatos"]["defasagem_saida_competencia"][-1])
if len(sys.argv) > 2:
    c = json.load(open(sys.argv[2], encoding="utf-8"))
    print("\nCAGED: tabela  linhas  antiga:vis  %cel_ant | %cel<5 %cel_oc %mov_oc | dedut | MB")
    for r in c["tabelas"]:
        print(f"{r['tabela']:<28} {r['linhas']:>8} {r['regra_antiga_visiveis_adm_ou_des_1a4']:>8} {r['regra_antiga_pct_celulas_ocultas']:>6} | {r['pct_celulas_primarias']:>6} {r['pct_celulas_ocultas']:>6} {r['pct_mov_ocultos']:>6} | {r['linhas_dedutiveis_depois']:>3} | {r['parquet_mb']:>5}")
