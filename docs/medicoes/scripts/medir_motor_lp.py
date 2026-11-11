"""Tempo nacional dos dois motores do ataque conjunto, sobre a superfície, num ano e em duas versões juntas.

Duas versões do pipeline (sih.processar_anos) sobre o Parquet mínimo de uma coleta local, com as 27 UFs, só
para o ano da alta pedido e só com as competências que já teriam saído até a última de cada versão:

- A: última competência `primeira`. Nenhuma versão no ar; grava a superfície.
- B: última competência `seguinte`, com a superfície de A como versão no ar. Herança do padrão e ataque
  conjunto com os motores do catálogo, dentro do próprio pipeline.

O tempo das duas versões juntas é o do próprio pipeline, no ataque conjunto de B, com os dois motores. Depois,
fora do pipeline, cada motor ataca a superfície de B sozinha ("um ano, uma versão"). Daqui só saem contagens e
tempos: nenhum valor por município.

Uso: python medir_motor_lp.py <pasta_min> <ibge.json> <pasta_de_trabalho> <saida.json> <ano> <primeira> <seguinte>
"""
import json
import platform
import shutil
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import catalogo, sih, sih_janela, sih_superficie, sih_versoes  # noqa: E402

MIN, COLETA, TRABALHO, SAIDA = (Path(x) for x in sys.argv[1:5])
ANO, PRIMEIRA, SEGUINTE = (int(x) for x in sys.argv[5:8])
CAT = catalogo.carregar()
SIH = CAT["bases"]["sih"]
MUNICIPIOS7 = {m["codigo"][:6]: m["codigo"] for m in json.loads(COLETA.read_text(encoding="utf-8"))["municipios"]}
sih_versoes.REGISTRAR = lambda texto: print(f"  {texto}", flush=True)


def conexao(ultima: int):
    arquivos = [p.as_posix() for p in sorted(MIN.glob("RD*.parquet")) if sih_janela.de_nome(p.stem[4:8]) <= ultima]
    con = duckdb.connect()
    con.execute("SET threads = 8")
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({arquivos!r}) WHERE competencia <= {ultima}")
    return con, len(arquivos)


def versao(nome: str, ultima: int, anterior=None) -> dict:
    jan = sih_janela.Janela(ultima, ultima, int(SIH["tempo"]["janela_republicada_meses"]),
                            int(SIH["tempo"]["defasagem_maxima_meses"]), int(SIH["coleta"]["primeiro_ano"]))
    con, arquivos = conexao(ultima)
    trabalho = TRABALHO / nome
    shutil.rmtree(trabalho, ignore_errors=True)
    guardado = {}
    original = sih.construir_ano
    sih.construir_ano = lambda *a, **k: guardado.setdefault("ano", original(*a, **k))
    inicio = time.perf_counter()
    try:
        r = sih.processar_anos(con, "aih", jan, [ANO], CAT, trabalho, MUNICIPIOS7, f"medicao-{ultima}", f"ate-{ultima}",
                               anterior=anterior, no_ar_consultada=anterior is not None,
                               avisar=lambda texto: print(texto, flush=True))
    finally:
        sih.construir_ano = original
    m = r["anos"][str(ANO)]
    return {"resumo": {"versao": nome, "ultima_competencia": ultima, "arquivos_rd": arquivos,
                       "fechado_ate": jan.ultimo_mes_fechado, "meses_preliminares": len(m["preliminares"]),
                       "internacoes": m["internacoes"], "segundos": round(time.perf_counter() - inicio, 1),
                       "etapas_s": m["segundos"], "reprovados": r["reprovados"], "superficie": r["superficie"],
                       "ataque_conjunto": m["ataque_conjunto"]},
            "nos": guardado["ano"][0], "trabalho": trabalho, "jan": jan}


def atacar(problema, rotulo: str) -> dict:
    saida = {}
    for motor in sih_versoes.motores_do_catalogo(CAT):
        inicio = time.perf_counter()
        r = sih_versoes.atacar(problema, motor)
        saida[motor] = {"segundos": round(time.perf_counter() - inicio, 1), "total": r.total,
                        "reveladas": [sum(v.values()) for v in r.reveladas],
                        "diferencas": {par: sum(v.values()) for par, v in r.diferencas.items()},
                        "inconclusivas": r.inconclusivas, "detalhe": r.detalhe}
        print(json.dumps({"rotulo": rotulo, "motor": motor, **{c: v for c, v in saida[motor].items() if c != "detalhe"}}), flush=True)
    return saida


def tamanho(p) -> dict:
    return {"nos": len(p.versoes[0].lo), "celulas_por_versao": int(sum(v.size for v in p.versoes[0].lo.values())),
            "arestas": len(p.arestas), "escondidas": [int(sum(e.sum() for e in v.escondida.values())) for v in p.versoes]}


def main():
    a = versao("a", PRIMEIRA)
    no_ar = sih_superficie.ler(a["trabalho"] / sih_superficie.ARQUIVO, CAT)
    b = versao("b", SEGUINTE, no_ar)
    sup_b = sih_superficie.ler(b["trabalho"] / sih_superficie.ARQUIVO, CAT)
    k = int(SIH["supressao"]["k"])
    cand = (sup_b.anos[ANO], {cid: sup_b.tabelas[ANO, cid] for cid in sup_b.anos[ANO]["superficie"]})
    ar = (no_ar.anos[ANO], {cid: no_ar.tabelas[ANO, cid] for cid in no_ar.anos[ANO]["superficie"]})
    medidas = {}
    for medida in sih_versoes.COLUNAS:
        inicio = time.perf_counter()
        juntas = sih_versoes.montar(ar, cand, b["nos"], CAT, ANO, k, medida, b["jan"].ultimo_mes_fechado)
        montagem = round(time.perf_counter() - inicio, 1)
        sozinha = sih_versoes.Problema(k, medida, [juntas.versoes[1]], juntas.arestas, [])
        medidas[medida] = {"montagem_s": montagem,
                           "uma_versao": {"tamanho": tamanho(sozinha), "motores": atacar(sozinha, f"{medida}, uma versão")},
                           "duas_versoes": {"tamanho": tamanho(juntas), "celulas_iguais": int(sum(m.sum() for *_, m in juntas.iguais)),
                                            "motores": "no ataque conjunto do pipeline, em versoes[1]"}}
    resultado = {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ano": ANO,
                 "maquina": {"sistema": platform.platform(), "python": platform.python_version()},
                 "versoes": [a["resumo"], b["resumo"]], "ataque_fora_do_pipeline": medidas}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Gravado em {SAIDA}")


if __name__ == "__main__":
    main()
