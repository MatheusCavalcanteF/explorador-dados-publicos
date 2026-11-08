"""Linha de comando do pipeline. Cada etapa grava em build/coleta, que o workflow passa adiante.

    python -m pipeline coletar    --saida build/coleta [--censo-release arquivo]
    python -m pipeline alcance    --saida build/coleta
    python -m pipeline diagnostico --saida build/diagnostico [--resumo arquivo.md]
    python -m pipeline construir  --coleta build/coleta --saida build/site [--links manifesto/links.json] [--execucao ID]
    python -m pipeline hospedagem --coleta build/coleta --site build/site --url URL --execucao ID
    python -m pipeline links      --coleta build/coleta
    python -m pipeline manifesto  --coleta build/coleta --saida manifesto
    python -m pipeline exigir     --coleta build/coleta
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import alcance, catalogo, diagnostico, hospedagem, ibge, links, manifesto, site


def _ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def _gravar(caminho: Path, valor) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("coletar")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--censo-release", type=Path)
    sub.add_parser("alcance").add_argument("--saida", type=Path, required=True)
    p = sub.add_parser("diagnostico")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--resumo", type=Path)
    p = sub.add_parser("construir")
    p.add_argument("--coleta", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--links", type=Path)
    p.add_argument("--execucao", default="local")
    p = sub.add_parser("hospedagem")
    p.add_argument("--coleta", type=Path, required=True)
    p.add_argument("--site", type=Path, required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--execucao", required=True)
    sub.add_parser("links").add_argument("--coleta", type=Path, required=True)
    p = sub.add_parser("manifesto")
    p.add_argument("--coleta", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    sub.add_parser("exigir").add_argument("--coleta", type=Path, required=True)
    args = parser.parse_args(argv)

    cat = catalogo.carregar()
    if args.comando == "coletar":
        release = args.censo_release if args.censo_release and args.censo_release.exists() else None
        resultado = ibge.coletar(args.saida, release)
        fontes = resultado["fontes"]
        print(f"IBGE: {len(resultado['municipios'])} municípios; estimativa {fontes['estimativa']['periodo']}; "
              f"Censo 2022 da {fontes['censo']['origem']}")
    elif args.comando == "alcance":
        resultado = alcance.executar()
        _gravar(args.saida / "alcance.json", resultado)
        for nome, item in resultado["fontes"].items():
            print(f"{nome}: {'ok' if item['ok'] else 'FALHOU ' + item['erro']}")
    elif args.comando == "diagnostico":
        resultado = diagnostico.executar()
        _gravar(args.saida / "diagnostico.json", resultado)
        texto = diagnostico.resumo(resultado)
        # No GitHub, --resumo é o $GITHUB_STEP_SUMMARY, que outros passos também escrevem.
        with (args.resumo or args.saida / "resumo.md").open("a", encoding="utf-8") as arquivo:
            arquivo.write(texto)
        for nome, item in resultado["fontes"].items():
            print(f"{nome}: {'ok' if item['ok'] else 'FALHOU em ' + item['falhou_em']} ({item['ms_total']} ms)")
    elif args.comando == "construir":
        anteriores = _ler(args.links) if args.links and args.links.exists() else None
        versao = site.construir(_ler(args.coleta / "ibge.json"), cat, args.saida, anteriores, args.execucao)
        print(f"Site: {versao['municipios']} páginas de município em {args.saida}")
    elif args.comando == "hospedagem":
        resultado = hospedagem.conferir(args.url, args.site, args.execucao)
        _gravar(args.coleta / "hospedagem.json", resultado)
        for nome, item in resultado["testes"].items():
            print(f"{nome}: {item['status']} {item['content_encoding'] or '-'} bate={item['bate_com_o_plano']}")
    elif args.comando == "links":
        resultado = links.conferir(_ler(args.coleta / "ibge.json"), cat)
        _gravar(args.coleta / "links.json", resultado)
        print(f"Links quebrados: {resultado['quebrados']}")
    elif args.comando == "manifesto":
        print("Manifesto:", ", ".join(manifesto.gravar(args.coleta, args.saida)))
    elif args.comando == "exigir":
        problemas = manifesto.falhas(args.coleta)
        for problema in problemas:
            print(f"::error::{problema}")
        return 1 if problemas else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
