"""Dedução entre versões do SIH com a regra decidida em 08/11/2026: transição de fechamento e três versões.

Cada versão passa pela supressão do pipeline (sih.suprimir_publicaveis: reforço até o teste dar zero,
critério de publicação, trimestre só com os três meses na base, teste vendo os preliminares arredondados).
Quem guarda as versões ataca todas juntas:
- cada versão com o que a tela mostra: oculta sem motivo, preliminar visível arredondado para múltiplo de 5;
- as células de período já fechado na versão mais nova de um par são iguais nas duas, porque nenhum arquivo
  com altas daquele período foi republicado entre elas. É a transição: o mês que fecha sai exato na nova e
  devolve o valor que estava arredondado na anterior (deducao.atacar_juntos);
- a diferença de cada par respeita as somas, e em três versões d(1,3) = d(1,2) + d(2,3)
  (deducao.diferencas e deducao.diferencas_em_sequencia).
Uma contagem de 1 a 4 revelada em qualquer versão, ou uma diferença exata de 1 a 4 entre duas, conta.

Herança (decidida depois da primeira rodada desta medição): a versão nova herda da anterior o padrão das
células de período já fechado (sih.fixas_da_anterior). Sem ela, o fechamento de 2024 revelou 18 contagens;
com HERDAR=0 no ambiente, a medição roda sem herança e grava os grupos com o sufixo "_sem_heranca".

Grupos:
- real_sp: SP com os arquivos de setembro de 2026 (2509 a 2607, do projeto de origem) contra os de outubro;
  as outras UFs iguais. Em outubro, 2503 e o 1º trimestre de 2025 fecham.
- sequencia: versões simuladas com última competência 2605, 2606 e 2607, tirando as AIHs das competências que
  ainda não teriam saído. Em 2025, 2501 fecha na 2606 e 2502 na 2607; em 2026, só processamento tardio.
- fecha_2024: 2604 contra 2605. Na 2605, dezembro de 2024 fecha, e as tabelas anuais de 2024 saem exatas.
Nada por município sai daqui: só contagens por versão, por par e por nó.

Uso: python medir_versoes_transicao.py <pasta_min> <pasta_min_sp_setembro> <saida.json> [grupo:ano ...]
Com grupos na linha de comando, só eles são refeitos e substituídos no resultado que já existe.
"""
import json
import os
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import catalogo, deducao, sih, sih_deducao, sih_janela, sih_tabelas as tab  # noqa: E402

PASTA, SETEMBRO, SAIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
SO = {tuple(x.rsplit(":", 1)) for x in sys.argv[4:]}
CAT = catalogo.carregar()
SIH = CAT["bases"]["sih"]
K = int(SIH["supressao"]["k"])
BASE = int(SIH["preliminares"]["arredondar_multiplo"])
TEMPO = SIH["tempo"]
PUB = sih_deducao.nos_publicados(CAT)
FECHO = tab.fechamento(PUB)
HERDAR = os.environ.get("HERDAR", "1") != "0"
SUFIXO = "" if HERDAR else "_sem_heranca"
SP_REPUBLICADAS = [202509, 202510, 202511, 202512, 202601, 202602, 202603, 202604, 202605, 202606, 202607]


def janela(ultima_no_ftp: int, ultimo_mes: int) -> sih_janela.Janela:
    return sih_janela.Janela(ultima_no_ftp, ultimo_mes, int(TEMPO["janela_republicada_meses"]),
                             int(TEMPO["defasagem_maxima_meses"]), 2021)


def arquivos(ano: int, ate: int, setembro: bool = False) -> list[str]:
    lista = []
    for p in sorted(PASTA.glob("RD*.parquet")):
        comp = sih_janela.de_nome(p.stem[4:8])
        if comp > ate or comp < ano * 100 + 1:   # altas do ano só aparecem a partir da competência de janeiro
            continue
        if setembro and p.stem[2:4] == "SP" and comp in SP_REPUBLICADAS:
            p = SETEMBRO / p.name
        lista.append(p.as_posix())
    return lista


def publicado(v: dict) -> dict:
    """O que a versão mostrou, por cruzamento: chaves, oculta e arredondada, só nas linhas do arquivo."""
    saida = {}
    for c in v["r"]["catalogo"]["cruzamentos"]:
        df = v["r"]["suprimidas"][c["id"]]
        n = tab.colunas_de(c, CAT)
        aberto = sih_deducao.periodo_aberto(df, n, v["ano"], v["prelim"])
        arred = ~df["oculto"].to_numpy() & aberto & (df["internacoes"].to_numpy() >= K)
        linha = df["publicado"].to_numpy()
        saida[c["id"]] = df.loc[linha, list(n) + ["oculto"]].assign(arredondado=arred[linha])
    return saida


def versao(rotulo: str, lista: list[str], ano: int, ultima_no_ftp: int, ate: int, anterior: dict | None = None) -> dict:
    inicio = time.perf_counter()
    con = duckdb.connect()
    con.execute("SET threads=8")
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({lista!r}) WHERE competencia <= {ate}")
    nos = tab.montar(tab.calcular_base(con, "aih", ano, PUB, CAT), PUB)
    j = janela(ultima_no_ftp, ate)
    prelim = {str(m) for m in j.meses_preliminares(ano)}
    fixas = sih.fixas_da_anterior(nos, CAT, publicado(anterior), ano, j.ultimo_mes_fechado) if anterior and HERDAR else None
    r = sih.suprimir_publicaveis(nos, CAT, K, ultimo_mes=ate, arredondamento=(BASE, prelim, ano) if prelim else None,
                                 fixas=fixas)
    estados = sih_deducao.sem_motivo(sih_deducao.estados_publicados(nos, r["suprimidas"], r["catalogo"], K))
    print(f"{rotulo} {ano}: teste sozinha {r['auditoria']['pequenas_reveladas']}, rodadas {len(r['historico'])}, "
          f"fora {sorted(r['nao_publicados'])}, {time.perf_counter() - inicio:.0f} s", flush=True)
    return {"rotulo": rotulo, "ano": ano, "nos": nos, "estados": estados, "prelim": prelim, "ultimo_mes": ate,
            "fechado": j.ultimo_mes_fechado, "ultima_no_ftp": ultima_no_ftp, "r": r}


def fechado(df: pd.DataFrame, n: tuple, ano: int, ate_mes: int) -> np.ndarray:
    """Células cujo período inteiro já fechou: o mês, os três meses do trimestre ou o ano."""
    if "mes" in n:
        return (df["mes"].astype(int) <= ate_mes).to_numpy()
    if "tri" in n:
        fim = df["tri"].str[:4].astype(int) * 100 + df["tri"].str[5:].astype(int) * 3
        return (fim <= ate_mes).to_numpy()
    return np.full(len(df), ano * 100 + 12 <= ate_mes)


def incompleto(df: pd.DataFrame, n: tuple, ultimo_mes: int) -> np.ndarray:
    if "tri" not in n:
        return np.zeros(len(df), dtype=bool)
    fim = df["tri"].str[:4].astype(int) * 100 + df["tri"].str[5:].astype(int) * 3
    return (fim > ultimo_mes).to_numpy()


def atacar(versoes: list[dict]) -> dict:
    """Alinha as versões nas mesmas chaves, ataca juntas e mede as diferenças."""
    ano = versoes[0]["ano"]
    uniao = {}
    for n in FECHO:
        if not n:
            uniao[n] = pd.DataFrame(index=[0])
            continue
        uniao[n] = (pd.concat([v["nos"][n][list(n)] for v in versoes]).drop_duplicates()
                    .sort_values(list(n)).reset_index(drop=True))
    arestas = tab.arestas(uniao)
    sistemas = []
    for v in versoes:
        nos_al, est_al = {}, {}
        for n in FECHO:
            if not n:
                nos_al[n] = v["nos"][n][["internacoes"]].reset_index(drop=True)
                if n in v["estados"]:
                    est_al[n] = v["estados"][n]
                continue
            pos = (uniao[n].reset_index(names="_u").merge(v["nos"][n][list(n)].reset_index(names="_o"), on=list(n), how="left")
                   .sort_values("_u")["_o"].to_numpy())
            tem = ~pd.isna(pos)
            idx = np.where(tem, pos, 0).astype(int)
            valores = np.where(tem, v["nos"][n]["internacoes"].to_numpy(np.int64)[idx], 0)
            nos_al[n] = uniao[n].assign(internacoes=valores)
            if n in v["estados"]:
                # Chave que não está na tabela publicada vale zero, menos no trimestre que ainda não saiu.
                estado = np.where(tem, v["estados"][n][idx], deducao.VISIVEL).astype(np.int8)
                estado[~tem & incompleto(uniao[n], n, v["ultimo_mes"])] = deducao.LIVRE
                est_al[n] = estado
        arred = (BASE, v["prelim"], ano) if v["prelim"] else None
        sistemas.append(sih_deducao.sistema(nos_al, est_al, PUB, K, aresta_cache=arestas, arredondamento=arred))
    iguais, fecharam = [], {}
    for i in range(len(versoes)):
        for j in range(i + 1, len(versoes)):
            for n in FECHO:
                mascara = fechado(uniao[n], n, ano, versoes[j]["fechado"]) if n else np.array([ano * 100 + 12 <= versoes[j]["fechado"]])
                iguais.append((i, j, tab.nome(n), mascara))
                if n in PUB and j == i + 1:
                    antes = fechado(uniao[n], n, ano, versoes[i]["fechado"]) if n else np.array([ano * 100 + 12 <= versoes[i]["fechado"]])
                    fecharam[f"{i}-{j}"] = fecharam.get(f"{i}-{j}", 0) + int((mascara & ~antes).sum())
    voltas = deducao.atacar_juntos(sistemas, iguais)
    for s in sistemas:
        s.conferir_solidez()
    intervalos = [{tab.nome(n): (s.nos[tab.nome(n)].lo.copy(), s.nos[tab.nome(n)].hi.copy()) for n in FECHO} for s in sistemas]
    nomes = [(tab.nome(f), tab.nome(g), idx) for f, g, idx in arestas]
    publicados = {tab.nome(n) for n in PUB}
    if len(versoes) == 3:
        pares = deducao.diferencas_em_sequencia(intervalos, nomes, K)
    else:
        pares = {"0-1": deducao.diferencas(intervalos[0], intervalos[1], nomes, K)}
    saida = {"ano": ano, "voltas_do_ataque_conjunto": voltas, "celulas_publicadas_que_fecharam": fecharam,
             "versoes": [], "pares": {}}
    for v, s in zip(versoes, sistemas):
        rev = s.reveladas()
        saida["versoes"].append({
            "rotulo": v["rotulo"], "ultima_no_ftp": v["ultima_no_ftp"], "ultimo_mes": v["ultimo_mes"],
            "fechado_ate": v["fechado"], "meses_preliminares": len(v["prelim"]),
            "nao_publicados": sorted(v["r"]["nao_publicados"]), "rodadas": len(v["r"]["historico"]),
            "teste_sozinha": v["r"]["auditoria"]["pequenas_reveladas"],
            "teste_com_as_outras": sum(x["pequenas_reveladas"] for x in rev.values()),
            "por_no": {nome: x["pequenas_reveladas"] for nome, x in rev.items() if x["pequenas_reveladas"]}})
    for par, r in pares.items():
        saida["pares"][par] = {
            "diferencas_pequenas_diretas": sum(x["pequenas_diretas"] for x in r.values()),
            "diferencas_pequenas_pela_cadeia": sum(x["pequenas_pela_cadeia"] for x in r.values()),
            "em_nos_publicados": sum(x["pequenas_diretas"] + x["pequenas_pela_cadeia"] for n, x in r.items() if n in publicados),
            "celulas_que_mudaram": sum(x["mudaram"] for x in r.values()),
            "por_no": {n: x["pequenas_diretas"] + x["pequenas_pela_cadeia"] for n, x in r.items()
                       if x["pequenas_diretas"] + x["pequenas_pela_cadeia"]}}
    return saida


resultado = {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "k": K, "arredondar_multiplo": BASE,
             "reforco_max_rodadas": SIH["supressao"]["reforco_max_rodadas"], "grupos": []}
if SO and SAIDA.exists():
    resultado = json.loads(SAIDA.read_text(encoding="utf-8")) | {"medido_em": resultado["medido_em"]}


def guardar(grupo: str, linha: dict) -> None:
    grupo += SUFIXO
    linha = {"grupo": grupo, "herda_da_anterior": HERDAR} | linha
    resultado["grupos"] = [g for g in resultado["grupos"] if (g["grupo"], g["ano"]) != (grupo, linha["ano"])] + [linha]
    resultado["grupos"].sort(key=lambda g: (g["grupo"], g["ano"]))
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"grupo": grupo, "ano": linha["ano"], "pares": {p: {c: v for c, v in d.items() if c != "por_no"}
                                                                     for p, d in linha["pares"].items()},
                      "versoes": [(v["rotulo"], v["teste_sozinha"], v["teste_com_as_outras"]) for v in linha["versoes"]]},
                     ensure_ascii=False), flush=True)


def pedido(grupo: str, ano: int) -> bool:
    return not SO or (grupo, str(ano)) in SO


for ano in (2025, 2026):
    if pedido("real_sp", ano):
        trocados = sorted(set(arquivos(ano, 202607, setembro=True)) - set(arquivos(ano, 202607)))
        esperados = [c for c in SP_REPUBLICADAS if c >= ano * 100 + 1]
        assert len(trocados) == len(esperados), f"esperava trocar {len(esperados)} arquivos de SP, troquei {len(trocados)}"
        a = versao("setembro", arquivos(ano, 202607, setembro=True), ano, 202607, 202607)
        b = versao("outubro", arquivos(ano, 202607), ano, 202608, 202607, anterior=a)
        guardar("real_sp", atacar([a, b]))
    if pedido("sequencia", ano):
        seq = []
        for L in (202605, 202606, 202607):
            seq.append(versao(f"L={L}", arquivos(ano, L), ano, L, L, anterior=seq[-1] if seq else None))
        guardar("sequencia", atacar(seq))
if pedido("fecha_2024", 2024):
    a = versao("L=202604", arquivos(2024, 202604), 2024, 202604, 202604)
    guardar("fecha_2024", atacar([a, versao("L=202605", arquivos(2024, 202605), 2024, 202605, 202605, anterior=a)]))
print("fim")
