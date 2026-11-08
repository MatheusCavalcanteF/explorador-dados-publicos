"""Manifesto no git: o que foi baixado, de onde, quando e com que hash, e o resultado das conferências.

Só metadados e totais. Os valores por município ficam no site e na Release, não aqui. A exceção são
as revisões da estimativa do IBGE: para cada município revisado, o valor antes e depois, por código.
"""
from __future__ import annotations

import json
from pathlib import Path

CONFERENCIAS = ("alcance", "hospedagem", "links", "leitor")


def _gravar(caminho: Path, valor) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def resumo_ibge(coleta: dict) -> dict:
    por_uf: dict[str, dict] = {}
    for m in coleta["municipios"]:
        uf = por_uf.setdefault(m["uf"], {"municipios": 0, "populacao_estimada": 0, "populacao_censo_2022": 0})
        uf["municipios"] += 1
        uf["populacao_estimada"] += m["populacao_estimada"] or 0
        uf["populacao_censo_2022"] += m["populacao_censo"] or 0
    return {"coletado_em": coleta["coletado_em"], "fontes": coleta["fontes"], "municipios": len(coleta["municipios"]),
            "por_uf": dict(sorted(por_uf.items()))}


def gravar(coleta_dir: Path, destino: Path) -> list[str]:
    coleta = json.loads((coleta_dir / "ibge.json").read_text(encoding="utf-8"))
    _gravar(destino / "ibge.json", resumo_ibge(coleta))
    gravados = ["ibge.json"]
    for nome in CONFERENCIAS:
        origem = coleta_dir / f"{nome}.json"
        if origem.exists():
            _gravar(destino / f"{nome}.json", json.loads(origem.read_text(encoding="utf-8")))
            gravados.append(f"{nome}.json")
    return gravados


def falhas(coleta_dir: Path) -> list[str]:
    """O que deve deixar a execução vermelha: fonte sem alcance, hospedagem fora do plano, leitor divergente."""
    problemas = []
    ler = lambda nome: json.loads((coleta_dir / f"{nome}.json").read_text(encoding="utf-8"))
    if not (coleta_dir / "alcance.json").exists():
        problemas.append("Teste de alcance não rodou")
    else:
        problemas += [f"Alcance: {nome} falhou ({item.get('erro')})"
                      for nome, item in ler("alcance")["fontes"].items() if not item["ok"]]
    if not (coleta_dir / "hospedagem.json").exists():
        problemas.append("Testes de hospedagem não rodaram")
    else:
        problemas += [f"Hospedagem: {nome} não bate com o plano"
                      for nome, item in ler("hospedagem")["testes"].items() if item["bate_com_o_plano"] is False]
    if not (coleta_dir / "leitor.json").exists():
        problemas.append("Leitor em JavaScript não rodou")
    elif not ler("leitor").get("ok"):
        problemas.append("Leitor em JavaScript divergiu da coleta")
    return problemas
