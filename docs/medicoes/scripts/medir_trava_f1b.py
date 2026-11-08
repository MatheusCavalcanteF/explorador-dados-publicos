"""Trava de queda do pipeline no único par de versões reais guardado: SP de setembro contra outubro de 2026.

Município e mês da alta, por residência e por hospital, nas tabelas já suprimidas; e o total de
internações por UF e competência. As outras UFs entram iguais nas duas versões.

Uso: python medir_trava_f1b.py <pasta_min> <pasta_min_sp_setembro> <saida.json>
"""
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import catalogo, sih_deducao, sih_tabelas as tab, sih_trava  # noqa: E402

PASTA, SETEMBRO, SAIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CAT = catalogo.carregar()
REGRA = CAT["bases"]["sih"]["revisao"]
REPUBLICADAS = {202509, 202510, 202511, 202512, 202601, 202602, 202603, 202604, 202605, 202606, 202607}


def arquivos(setembro):
    lista = []
    for p in sorted(PASTA.glob("RD*.parquet")):
        comp = 200000 + int(p.stem[4:8])
        if 202501 <= comp <= 202607:
            lista.append((SETEMBRO / p.name if setembro and p.stem[2:4] == "SP" and comp in REPUBLICADAS else p).as_posix())
    return lista


def suprimidas(lista, ano):
    con = duckdb.connect()
    con.execute("SET threads=8")
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({lista!r})")
    pub = sih_deducao.nos_publicados(CAT)
    nos = tab.montar(tab.calcular_base(con, "aih", ano, pub, CAT), pub)
    return sih_deducao.suprimir_ate_passar(nos, CAT, 5, False)["suprimidas"]


def totais(lista):
    con = duckdb.connect()
    linhas = con.execute(f"SELECT substr(filename, -14, 2) uf, competencia, count(*) FILTER (WHERE ident = 1) "
                         f"FROM read_parquet({lista!r}, filename = true) GROUP BY 1, 2").fetchall()
    return {f"{uf}/{c}": n for uf, c, n in linhas}


resultado = {"regra": REGRA, "municipio": {}}
for ano in (2025, 2026):
    a, b = suprimidas(arquivos(True), ano), suprimidas(arquivos(False), ano)
    for cid, geo in (("sih_res_mes", "mun_res"), ("sih_hosp_mes", "mun_hosp")):
        visiveis = a[cid].loc[~a[cid]["oculto"], [geo, "mes", "internacoes"]].merge(
            b[cid].loc[~b[cid]["oculto"], [geo, "mes", "internacoes"]], on=[geo, "mes"])
        mudaram = visiveis[visiveis["internacoes_x"] != visiveis["internacoes_y"]]
        marcadas = sih_trava.municipio(a[cid], b[cid], [geo, "mes"], REGRA["municipio"])
        resultado["municipio"][f"{cid}/{ano}"] = {
            "pares_visiveis_nas_duas": len(visiveis), "mudaram": len(mudaram), "acionaram": len(marcadas),
            # Só municípios e meses com pelo menos 100 internações na versão anterior: é a própria regra.
            "acionamentos": [{"municipio": r[geo], "mes": r["mes"], "anterior": int(r["anterior"]), "nova": int(r["nova"]),
                              "queda_pct": round(float(r["queda_pct"]), 1)} for _, r in marcadas.iterrows()]}
        print(cid, ano, resultado["municipio"][f"{cid}/{ano}"], flush=True)
ta, tb = totais(arquivos(True)), totais(arquivos(False))
resultado["publicacao"] = {"falhas": sih_trava.publicacao(ta, tb, REGRA["publicacao"]),
                           "maior_queda_pct_uf_competencia": round(max(100 * (ta[c] - tb.get(c, 0)) / ta[c] for c in ta), 2)}
print(resultado["publicacao"], flush=True)
SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
