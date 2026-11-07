"""Recalcula contra os valores do TabNet já coletados, agora com os RD das 27 UFs na visão de residência.

Também mede o que se perde na visão de residência ao ler só o arquivo da própria UF, e grava só os agregados.
O resultado por comparação tem contagens pequenas e fica fora do repositório; o que é publicado é o resumo.

Uso: python -I conferir_tabnet2.py <pasta_rdsp> <pasta_outras_uf> <entrada_tabnet.json> <saida.json> <sih_perda_so_uf.json> <conferencia_tabnet_resumo.json>
"""
import json, sys
import duckdb
sp, uf, entrada, saida, saida_perda, saida_resumo = sys.argv[1:7]
col = "ANO_CMPT,MES_CMPT,IDENT,MUNIC_MOV,MUNIC_RES,DIAS_PERM,VAL_TOT,MORTE"
con = duckdb.connect()
con.execute(f"CREATE VIEW br AS SELECT {col} FROM read_parquet('{sp}/RDSP25*.parquet') UNION ALL BY NAME SELECT {col} FROM read_parquet('{uf}/RD*.parquet')")
con.execute(f"CREATE VIEW sp AS SELECT {col} FROM read_parquet('{sp}/RDSP25*.parquet')")
EXPR = {"Internações":"count(*) FILTER (IDENT='1')","AIH_aprovadas":"count(*)","Valor_total":"round(sum(VAL_TOT),2)","Óbitos":"sum(MORTE)","Dias_permanência":"sum(DIAS_PERM)"}
dados = json.load(open(entrada, encoding="utf-8"))
res = []
for r in dados:
    coluna = "MUNIC_MOV" if r["visao"]=="nisp" else "MUNIC_RES"
    base = "sp" if r["visao"]=="nisp" else "br"
    calc = con.execute(f"SELECT {EXPR[r['medida']]} FROM {base} WHERE {coluna}='{r['mun']}' AND ANO_CMPT||MES_CMPT='20{r['comp']}'").fetchone()[0]
    calc = float(calc) if calc is not None else 0.0
    igual = abs(calc - r["tabnet"]) < 0.011
    res.append({**r, "calculado": calc, "igual": igual})
    if not igual: print("DIF", r["visao"], r["mun"], r["comp"], ascii(r["medida"]), calc, r["tabnet"], f"{100*(calc-r['tabnet'])/max(r['tabnet'],1):+.2f}%")
json.dump(res, open(saida,"w",encoding="utf-8"), ensure_ascii=False, indent=0)
print("total", len(res), "iguais", sum(x["igual"] for x in res))
for v in ("nisp","nrsp"):
    print(v, sum(x["igual"] for x in res if x["visao"]==v), "/", sum(1 for x in res if x["visao"]==v))
por_medida = {}
for x in res:
    placar = por_medida.setdefault(f"{x['visao']}/{x['medida']}", {"identicas": 0, "total": 0})
    placar["identicas"] += x["igual"]
    placar["total"] += 1
diferencas = [{k: x[k] for k in ("visao", "mun", "comp", "medida", "calculado", "tabnet")} for x in res if not x["igual"]]
if any(d["mun"] != "355030" for d in diferencas):
    sys.exit("Há diferença fora da capital: o resumo só pode listar valores da capital, que são grandes")
json.dump({"comparacoes": len(res), "identicas": sum(x["igual"] for x in res), "municipios": sorted({x["mun"] for x in res}), "competencias": sorted({x["comp"] for x in res}), "por_medida": por_medida, "diferencas_capital": diferencas},
          open(saida_resumo, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# Tamanho do erro ao usar só o RD da própria UF na visão de residência (SP, 2025)
q = con.execute("""WITH a AS (SELECT MUNIC_RES m, count(*) FILTER (IDENT='1') n FROM sp WHERE substr(MUNIC_RES,1,2)='35' GROUP BY 1),
 b AS (SELECT MUNIC_RES m, count(*) FILTER (IDENT='1') n FROM br WHERE substr(MUNIC_RES,1,2)='35' GROUP BY 1)
 SELECT sum(a.n), sum(b.n), round(100.0*(sum(b.n)-sum(a.n))/sum(b.n),2), max(round(100.0*(b.n-a.n)/nullif(b.n,0),1)), count(*) FILTER (b.n<>a.n), count(*) FROM b JOIN a USING(m)""").fetchone()
sem = con.execute("SELECT count(*) FILTER (IDENT='1') FROM br WHERE substr(MUNIC_RES,1,2)='35' AND substr(MUNIC_MOV,1,2)<>'35'").fetchone()
perda = {"descricao": "Internações de moradores de SP que somem ao ler só o arquivo de SP, em vez dos arquivos das 27 UFs",
         "populacao": "AIHs com IDENT=1 e município de residência em SP",
         "periodo": "Competências de 2025 (RD??25*), por competência, não por data da alta",
         "calculo": "perda_pct = (internacoes_27_ufs - internacoes_so_rdsp) / internacoes_27_ufs; pior_municipio_pct é o mesmo cálculo por município; o município não é identificado aqui",
         "internacoes_so_rdsp": int(q[0]), "internacoes_27_ufs": int(q[1]), "internados_fora_de_sp": int(sem[0]), "perda_pct": float(q[2]), "pior_municipio_pct": float(q[3]),
         "municipios_afetados": int(q[4]), "municipios_com_residentes": int(q[5])}
json.dump(perda, open(saida_perda, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(perda)
