"""Dedução entre duas versões publicadas do SIH, e o efeito de arredondar os meses preliminares.

Quem guarda a versão anterior do site e a nova conhece a diferença entre elas onde as duas são exatas,
e pode deduzir mais pelas mesmas somas (deducao.diferencas). Uma diferença exata de 1 a 4 revela um
grupo pequeno de AIHs que chegou ou saiu entre as versões.

Pares medidos, todos com as 27 UFs e a supressão do pipeline (motivo não publicado, reforço até passar):
- real: SP com os arquivos de setembro de 2026 (2509 a 2607, guardados no projeto de origem) contra os de
  outubro; as outras UFs iguais nas duas versões, porque só SP tem as duas guardadas;
- simulado: a versão com a última competência L contra a com L-1, tirando as AIHs das competências que
  ainda não teriam saído. Mede o processamento tardio, que é a maior parte do que muda de um mês para outro.

Políticas: exato; e valores visíveis dos períodos com mês preliminar arredondados para múltiplos de 5 ou 10.
Nada por município sai daqui: só contagens por nó e medidas de erro agregadas.

Uso: python medir_versoes_f1b.py <pasta_min> <pasta_min_sp_setembro> <saida.json> [par:ano ...]

Com pares na linha de comando, só eles são refeitos e substituídos no resultado que já existe.
O reforço usa o limite de rodadas do catálogo, o mesmo do pipeline.
"""
import json
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import catalogo, deducao, sih_deducao, sih_janela, sih_tabelas as tab  # noqa: E402

PASTA, SETEMBRO, SAIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
SO = {tuple(x.rsplit(":", 1)) for x in sys.argv[4:]}
CAT = catalogo.carregar()
K = 5
TEMPO = CAT["bases"]["sih"]["tempo"]
POLITICAS = {"exato": None, "arredondado_5": 5, "arredondado_10": 10}
PUB = sih_deducao.nos_publicados(CAT)
FECHO = tab.fechamento(PUB)
SP_REPUBLICADAS = [202509, 202510, 202511, 202512, 202601, 202602, 202603, 202604, 202605, 202606, 202607]


def preliminares(ultima_no_ftp, ano):
    jan = sih_janela.Janela(ultima_no_ftp, ultima_no_ftp, int(TEMPO["janela_republicada_meses"]),
                            int(TEMPO["defasagem_maxima_meses"]), 2021)
    return {str(m) for m in jan.meses_preliminares(ano)}


def arquivos(ate, setembro=False):
    lista = []
    for p in sorted(PASTA.glob("RD*.parquet")):
        comp = sih_janela.de_nome(p.stem[4:8])
        if comp > ate or comp < 202501:   # só 2025 e 2026 são medidos; altas deles começam em 2501
            continue
        if setembro and p.stem[2:4] == "SP" and comp in SP_REPUBLICADAS:
            p = SETEMBRO / p.name
        lista.append(p.as_posix())
    return lista


def versao(lista, ano, ultima_no_ftp, ate=None):
    con = duckdb.connect()
    con.execute("SET threads=8")
    filtro = f" WHERE competencia <= {ate}" if ate else ""
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({lista!r}){filtro}")
    nos = tab.montar(tab.calcular_base(con, "aih", ano, PUB, CAT), PUB)
    r = sih_deducao.suprimir_ate_passar(nos, CAT, K, motivo_publico=False)
    prelim = preliminares(ultima_no_ftp, ano)
    saida = {"nos": nos, "passou": r["passou"], "rodadas": len(r["historico"]), "prelim": prelim, "intervalos": {}}
    for nome_pol, base in POLITICAS.items():
        estados = sih_deducao.sem_motivo(r["estados"])
        arred = (base, prelim, ano) if base else None
        s = sih_deducao.sistema(nos, estados, PUB, K, aresta_cache=r["arestas"], arredondamento=arred)
        aud = sih_deducao.auditar(s)
        saida["intervalos"][nome_pol] = ({n: (s.nos[tab.nome(n)].lo.copy(), s.nos[tab.nome(n)].hi.copy()) for n in FECHO},
                                         aud["pequenas_reveladas"])
    saida["estados"] = r["estados"]
    return saida


def alinhar(a, b):
    """Chaves da união por nó, e lo/hi de cada versão nelas (0 exato onde a célula não existe)."""
    uniao, ia, ib = {}, {}, {}
    for n in FECHO:
        if not n:
            uniao[n] = pd.DataFrame(index=[0])
            continue
        u = pd.concat([a["nos"][n][list(n)], b["nos"][n][list(n)]]).drop_duplicates().sort_values(list(n)).reset_index(drop=True)
        uniao[n] = u
    for n in FECHO:
        for origem, destino in ((a, ia), (b, ib)):
            if not n:
                destino[n] = np.array([0])
                continue
            pos = uniao[n].reset_index(names="_u").merge(origem["nos"][n][list(n)].reset_index(names="_o"), on=list(n), how="left")
            destino[n] = pos.sort_values("_u")["_o"].to_numpy()
    arestas = tab.arestas(uniao)
    return uniao, ia, ib, arestas


def expandir(intervalos, idx):
    saida = {}
    for n, (lo, hi) in intervalos.items():
        i = idx[n]
        tem = ~pd.isna(i)
        lo_u = np.zeros(len(i), dtype=np.int64)
        hi_u = np.zeros(len(i), dtype=np.int64)
        lo_u[tem] = lo[i[tem].astype(int)]
        hi_u[tem] = hi[i[tem].astype(int)]
        saida[tab.nome(n)] = (lo_u, hi_u)
    return saida


def perda(v, base, ano):
    """Erro do arredondamento nas células visíveis dos períodos preliminares, nos nós publicados."""
    erros, relativos, celulas, visiveis = [], [], 0, 0
    for n, estado in v["estados"].items():
        df = v["nos"][n]
        valores = df["internacoes"].to_numpy(np.int64)
        aberto = sih_deducao.periodo_aberto(df, n, ano, v["prelim"])
        alvo = (estado == deducao.VISIVEL) & aberto & (valores >= K)
        visiveis += int((estado == deducao.VISIVEL).sum())
        celulas += int(alvo.sum())
        e = np.abs(sih_deducao.arredondar(valores[alvo], base) - valores[alvo])
        erros.append(e)
        relativos.append(e / valores[alvo])
    e, r = np.concatenate(erros), np.concatenate(relativos)
    return {"celulas_arredondadas": celulas, "pct_das_visiveis": round(100 * celulas / visiveis, 1),
            "erro_medio": round(float(e.mean()), 2), "pct_com_erro_acima_de_10pct": round(100 * float((r > 0.10).mean()), 1),
            "pct_com_erro_acima_de_20pct": round(100 * float((r > 0.20).mean()), 1)}


def comparar(nome_par, ano, a, b):
    uniao, ia, ib, arestas = alinhar(a, b)
    linha = {"par": nome_par, "ano": ano, "passou_a": a["passou"], "passou_b": b["passou"],
             "meses_preliminares_b": len(b["prelim"]), "politicas": {}}
    for pol in POLITICAS:
        ia_int, ib_int = expandir(a["intervalos"][pol][0], ia), expandir(b["intervalos"][pol][0], ib)
        r = deducao.diferencas(ia_int, ib_int, [(f, g, i) for f, g, i in ((tab.nome(f), tab.nome(g), i) for f, g, i in arestas)], K)
        pub = {tab.nome(n) for n in PUB}
        linha["politicas"][pol] = {
            "reveladas_na_versao_b": b["intervalos"][pol][1],
            "diferencas_pequenas_diretas": sum(v["pequenas_diretas"] for v in r.values()),
            "diferencas_pequenas_pela_cadeia": sum(v["pequenas_pela_cadeia"] for v in r.values()),
            "em_nos_publicados": sum(v["pequenas_diretas"] + v["pequenas_pela_cadeia"] for n, v in r.items() if n in pub),
            "celulas_que_mudaram": sum(v["mudaram"] for v in r.values() if True),
            "por_no": {n: v["pequenas_diretas"] + v["pequenas_pela_cadeia"] for n, v in r.items()
                       if v["pequenas_diretas"] + v["pequenas_pela_cadeia"]},
        }
        if POLITICAS[pol]:
            linha["politicas"][pol]["perda"] = perda(b, POLITICAS[pol], ano)
    print(json.dumps({x: linha[x] for x in ("par", "ano")} | {p: {k: v for k, v in d.items() if k != "por_no"}
                                                               for p, d in linha["politicas"].items()}, ensure_ascii=False), flush=True)
    return linha


resultado = {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "k": K,
             "reforco_max_rodadas": CAT["bases"]["sih"]["supressao"]["reforco_max_rodadas"], "pares": []}
if SO:
    resultado = json.loads(SAIDA.read_text(encoding="utf-8")) | {"reforco_max_rodadas": resultado["reforco_max_rodadas"]}


def guardar(linha):
    chave = (linha["par"], linha["ano"])
    resultado["pares"] = [p for p in resultado["pares"] if (p["par"], p["ano"]) != chave] + [linha]
    resultado["pares"].sort(key=lambda p: (not p["par"].startswith("real"), p["par"], p["ano"]))
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")


def pedido(par, ano):
    return not SO or (par, str(ano)) in SO
# Par real: SP de setembro (última competência 2607) contra outubro (última 2608, mas 2608 sem AC e RR).
trocados = sorted(set(arquivos(202607, setembro=True)) - set(arquivos(202607)))
assert len(trocados) == len(SP_REPUBLICADAS), f"esperava trocar {len(SP_REPUBLICADAS)} arquivos de SP, troquei {len(trocados)}"
for ano in (2025, 2026):
    if not pedido("real_sp_setembro_outubro", ano):
        continue
    a = versao(arquivos(202607, setembro=True), ano, 202607)
    b = versao(arquivos(202607), ano, 202608)
    guardar(comparar("real_sp_setembro_outubro", ano, a, b))
# Pares simulados: a versão com L contra a com L-1.
for ultima in (202604, 202605, 202606, 202607):
    anterior = sih_janela.somar(ultima, -1)
    for ano in (2025, 2026):
        if ano == 2025 and ultima > 202605:
            continue  # as altas de 2025 só chegam até a competência 2605
        if not pedido(f"simulado_{anterior}_{ultima}", ano):
            continue
        a = versao(arquivos(anterior), ano, anterior, ate=anterior)
        b = versao(arquivos(ultima), ano, ultima, ate=ultima)
        guardar(comparar(f"simulado_{anterior}_{ultima}", ano, a, b))
print("fim")
