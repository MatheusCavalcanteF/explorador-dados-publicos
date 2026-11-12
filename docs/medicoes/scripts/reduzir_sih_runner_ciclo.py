"""Reduz o artefato `sih-medicao` do workflow `SIH (medição)` com `ciclo` ou com `regras` ao que o plano cita.

    gh run download <execução> -n sih-medicao -D <pasta>
    python docs/medicoes/scripts/reduzir_sih_runner_ciclo.py <pasta> <execução> docs/medicoes/resultados/sih_runner_ciclo.json

Por fase (a: primeira publicação; b: a seguinte, com os anos fechados copiados de a; c: a mesma, sem reaproveitar,
com os .dbc de a): tempo de relógio, memória, disco, coleta, o plano de reaproveitamento e, por ano, os tempos e o
ataque conjunto de cada motor e medida (tempo, contagens reveladas e o tamanho do problema). Só contagens e tempos.
Com `regras`, as fases d1, d2, ... são a versão seguinte depois de uma mudança de regra feita só na medição, com
tudo das fontes; cada uma leva a regra mudada, e cada ano diz se passou e virou partição.
"""
import json
import re
import sys
from pathlib import Path

PROBLEMA = ("livres", "igualdades", "alvos", "amostras", "resolucoes", "inconclusivas")


def _time(texto: str) -> dict:
    relogio = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", texto)
    memoria = re.search(r"Maximum resident set size \(kbytes\): (\d+)", texto)
    return {"tempo_de_relogio": relogio.group(1) if relogio else None,
            "maior_processo_kb": int(memoria.group(1)) if memoria else None}


def _ano(a: dict) -> dict:
    if a.get("reaproveitado_da_versao_no_ar"):
        return {"reaproveitado_da_versao_no_ar": True}
    saida = {"internacoes": a["internacoes"], "segundos": a["segundos"],
             "deducao": {"pequenas_reveladas": a["deducao_internacoes"]["pequenas_reveladas"],
                         "rodadas": len(a["deducao_internacoes"].get("rodadas", [])),
                         "obitos_passou": a["deducao_obitos"]["passou"]},
             "nao_publicados": sorted(a["nao_publicados"]), "particao_gravada": a.get("particao_gravada")}
    conjunto = a.get("ataque_conjunto", {})
    if not conjunto.get("rodou"):
        saida["ataque_conjunto"] = {"rodou": False, "motivo": conjunto.get("motivo")}
        return saida
    saida["ataque_conjunto"] = {"rodou": True, "passou": conjunto["passou"], "motivo": conjunto.get("motivo")}
    for medida in ("internacoes", "obitos"):
        saida["ataque_conjunto"][medida] = {
            motor: {"segundos": v["segundos"], "total": v["total"],
                    **{c: v["detalhe"][c] for c in PROBLEMA if c in v.get("detalhe", {})}}
            for motor, v in conjunto[medida]["motores"].items()}
    return saida


def reduzir(pasta: Path, execucao: str) -> dict:
    resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
    saida = {"execucao": execucao, "instalacao": (pasta / "instalacao.txt").read_text().strip(),
             "maquina_antes": (pasta / "maquina_antes.txt").read_text().split("\n")[:3],
             "pico_memoria_em_uso_na_maquina_mb": resumo["pico_memoria_em_uso_mb"], "fases": {}}
    for fase, r in resumo["fases"].items():
        m = json.loads((pasta / fase / "medicao.json").read_text(encoding="utf-8"))
        plano = m.get("reaproveitamento") or {}
        regra = pasta / fase / "regra.txt"
        saida["fases"][fase] = {
            **({"regras_mudadas_so_na_medicao": regra.read_text(encoding="utf-8").splitlines()} if regra.exists() else {}),
            "segundos": r["segundos"], "limite_s": r["limite_s"], "codigo_de_saida": r["codigo_de_saida"],
            "pico_memoria_em_uso_na_maquina_mb": r["pico_memoria_em_uso_mb"],
            **_time((pasta / fase / "time.txt").read_text(encoding="utf-8")),
            "disco_livre_antes": r["disco_livre_antes"], "disco_livre_depois": r["disco_livre_depois"],
            "total_s": m["etapas"]["total_s"],
            "janela": {c: m["janela"][c] for c in ("ultima_no_ftp", "ultima_completa", "ultimo_mes_fechado", "anos", "anos_abertos")},
            "coleta": {c: m["coleta"][c] for c in ("arquivos", "segundos", "bytes_dbc", "bytes_min", "maior_disco_bytes", "processos")},
            "disco": m["disco"],
            "reaproveitamento": {c: plano.get(c) for c in ("valido", "motivo", "reaproveitados", "anos", "avisos")},
            "anos": {ano: _ano(a) for ano, a in m["anos"].items()},
            "superficie": m.get("superficie"), "publicavel": m["publicavel"], "reprovados": m["reprovados"]}
    return saida


if __name__ == "__main__":
    pasta, execucao, destino = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    destino.write_text(json.dumps(reduzir(pasta, execucao), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{destino}: {destino.stat().st_size} bytes")
