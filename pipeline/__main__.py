"""Linha de comando do pipeline. Cada etapa grava em build/coleta, que o workflow passa adiante.

    python -m pipeline releases   --destino build/release   (partição fechada do Censo; falha ao consultar para)
    python -m pipeline no-ar      --destino build/no-ar     (versão no ar do SIH, a superfície no site; idem)
    python -m pipeline coletar    --saida build/coleta [--censo-release arquivo] [--anterior manifesto/ibge.json]
    python -m pipeline alcance    --saida build/coleta
    python -m pipeline diagnostico --saida build/diagnostico [--resumo arquivo.md] [--pular inep ...]
    python -m pipeline inep       --saida build/inep [--resumo arquivo.md]
    python -m pipeline construir  --coleta build/coleta --saida build/site [--links manifesto/links.json] [--execucao ID]
                                  [--sih-local PASTA]  (só local: SIH nas páginas sem mudar o catálogo; para no CI)
    python -m pipeline hospedagem --coleta build/coleta --site build/site --url URL --execucao ID
    python -m pipeline links      --coleta build/coleta
    python -m pipeline manifesto  --coleta build/coleta --saida manifesto
    python -m pipeline exigir     --coleta build/coleta
    python -m pipeline sih        --coleta build/coleta --trabalho build/sih --saida build/sih-medicao
                                  [--ufs RR SP] [--anos 2025 2026] [--processos 4] [--origem-local pasta]
                                  [--anterior superficie.parquet|particoes | --no-ar build/no-ar]
                                  (herda o padrão dos períodos fechados e roda o ataque conjunto com ela)
    python -m pipeline publicacao --base sih   (publicar=true ou false, pelo catálogo)

O SIH precisa de requirements-sih.txt e só é importado no próprio comando: o Publicar não depende dele.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import alcance, catalogo, diagnostico, hospedagem, ibge, links, manifesto, projeto, rede, release, site


def _estimativa_no_site():
    """O Parquet que está no ar, para achar os municípios revisados. Só é pedido quando a estimativa mudou."""
    url = f"{projeto.SITE}{site.PARQUET}?coleta={datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    resposta = rede.pedir(url)
    if resposta.status != 200:
        raise rede.ErroDeRede(f"HTTP {resposta.status} em {url}")
    return site.estimativa_publicada(resposta.corpo)


def _diagnostico(resultado: dict, saida: Path, nome: str, resumo: Path | None) -> None:
    _gravar(saida / f"{nome}.json", resultado)
    texto = diagnostico.resumo(resultado)
    (saida / "resumo.md").write_text(texto, encoding="utf-8")
    if resumo:
        # No GitHub é o $GITHUB_STEP_SUMMARY, que outros passos também escrevem.
        with resumo.open("a", encoding="utf-8") as arquivo:
            arquivo.write(texto)
    for chave, item in resultado["fontes"].items():
        print(f"{chave}: {'ok' if item['ok'] else 'FALHOU em ' + item['falhou_em']} ({item['ms_total']} ms)")


def _ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def _gravar(caminho: Path, valor) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("releases").add_argument("--destino", type=Path, required=True)
    sub.add_parser("no-ar").add_argument("--destino", type=Path, required=True)
    sub.add_parser("publicacao").add_argument("--base", required=True)
    p = sub.add_parser("coletar")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--censo-release", type=Path)
    # Manifesto da coleta anterior: a mudança é detectada pelo hash dos valores, comparado com ele.
    p.add_argument("--anterior", type=Path)
    sub.add_parser("alcance").add_argument("--saida", type=Path, required=True)
    p = sub.add_parser("diagnostico")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--resumo", type=Path)
    p.add_argument("--pular", nargs="*", default=[], choices=[a["nome"] for a in diagnostico.ALVOS])
    p = sub.add_parser("inep")
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--resumo", type=Path)
    p = sub.add_parser("construir")
    p.add_argument("--coleta", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--links", type=Path)
    p.add_argument("--execucao", default="local")
    # Partições de uma execução local do SIH (trabalho/particoes). Só para conferir no navegador: não muda o
    # catálogo, que segue com publicacao.site: false, e para com erro no CI.
    p.add_argument("--sih-local", type=Path)
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
    p = sub.add_parser("sih")
    p.add_argument("--coleta", type=Path, required=True)
    p.add_argument("--trabalho", type=Path, required=True)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--ufs", nargs="*")
    p.add_argument("--anos", nargs="*", type=int)
    p.add_argument("--processos", type=int, default=4)
    # Pasta com os .dbc já baixados, para medir sem baixar de novo. Só para uso local.
    p.add_argument("--origem-local", type=Path)
    p.add_argument("--manter-dbc", action="store_true")
    p.add_argument("--sem-deducao", action="store_true")
    # A versão publicada antes, como o site a mostrou (a superfície): nos períodos fechados, a nova herda o
    # padrão de células ocultas, e cada ano passa pelo ataque conjunto com ela. --anterior é um arquivo de
    # superfície ou uma pasta de partições escolhidos à mão, para uso local; --no-ar é a pasta de `no-ar`, com
    # a consulta ao site: sem versão no ar, é a primeira publicação.
    origem = p.add_mutually_exclusive_group()
    origem.add_argument("--anterior", type=Path)
    origem.add_argument("--no-ar", type=Path)
    args = parser.parse_args(argv)

    cat = catalogo.carregar()
    if args.comando == "releases":
        consulta = release.consultar(args.destino, token=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        print(f"Releases: {len(consulta['releases'])} publicadas. Censo 2022: "
              f"{'baixado da Release' if consulta['censo'] else 'ainda sem Release; a coleta vai à fonte'}")
    elif args.comando == "no-ar":
        from . import sih_superficie
        consulta = sih_superficie.consultar(args.destino, cat)
        print(f"SIH no ar: {'anos ' + ', '.join(map(str, consulta['anos'])) if consulta['existe'] else 'nenhuma versão; primeira publicação'}")
    elif args.comando == "publicacao":
        regra = cat["bases"][args.base].get("publicacao") or {}
        # Para o $GITHUB_OUTPUT: os passos do SIH no Publicar só rodam quando o catálogo manda publicar.
        print(f"publicar={'true' if regra.get('site') else 'false'}")
    elif args.comando == "coletar":
        censo = args.censo_release if args.censo_release and args.censo_release.exists() else None
        anterior = _ler(args.anterior)["fontes"] if args.anterior and args.anterior.exists() else None
        resultado = ibge.coletar(args.saida, censo, anterior, publicados=_estimativa_no_site)
        fontes = resultado["fontes"]
        print(f"IBGE: {len(resultado['municipios'])} municípios da DTB {fontes['dtb']['periodo']} "
              f"(data-base {fontes['dtb']['data_base']}); estimativa {fontes['estimativa']['periodo']}; "
              f"Censo 2022 da {fontes['censo']['origem']}")
        for nome, fonte in fontes.items():
            print(f"{nome}: em relação à coleta anterior, {fonte['em_relacao_a_coleta_anterior']}")
        # Revisão não bloqueia: aparece como aviso no workflow, além da ressalva na página.
        limite = cat["bases"]["ibge_estimativa"]["revisao"]["aviso_variacao_pct"]
        nomes = {m["codigo"]: m["nome"] for m in resultado["municipios"]}
        for evento in fontes["estimativa"]["revisoes"]:
            if evento["detectada_em"] != resultado["coletado_em"]:
                continue
            if evento["municipios"] is not None:
                print(f"Revisão do IBGE: {len(evento['municipios'])} municípios mudaram na estimativa "
                      f"{fontes['estimativa']['periodo']}; antes e depois vão para o manifesto")
            for linha in ibge.avisos_de_revisao(evento, limite, nomes):
                print(f"::warning title=Revisão da estimativa do IBGE::{linha}")
    elif args.comando == "alcance":
        resultado = alcance.executar()
        _gravar(args.saida / "alcance.json", resultado)
        for nome, item in resultado["fontes"].items():
            print(f"{nome}: {'ok' if item['ok'] else 'FALHOU ' + item['erro']}")
    elif args.comando == "diagnostico":
        alvos = [a for a in diagnostico.ALVOS if a["nome"] not in args.pular]
        _diagnostico(diagnostico.executar(alvos), args.saida, "diagnostico", args.resumo)
    elif args.comando == "inep":
        _diagnostico(diagnostico.inep_uma_vez(), args.saida, "inep", args.resumo)
    elif args.comando == "construir":
        anteriores = _ler(args.links) if args.links and args.links.exists() else None
        versao = site.construir(_ler(args.coleta / "ibge.json"), cat, args.saida, anteriores, args.execucao,
                                sih_local=args.sih_local)
        tamanho = versao["tamanho"]
        print(f"Site: {versao['municipios']} páginas de município em {args.saida}. Maior página: "
              f"{tamanho['maior_pagina']}, {tamanho['maior_pagina_bytes']} bytes, limite {tamanho['limite_pagina_bytes']}")
    elif args.comando == "hospedagem":
        resultado = hospedagem.conferir(args.url, args.site, args.execucao)
        _gravar(args.coleta / "hospedagem.json", resultado)
        for nome, item in resultado["testes"].items():
            print(f"{nome}: {item.get('status', '-')} {item.get('content_encoding') or '-'} bate={item['bate_com_o_plano']}")
    elif args.comando == "links":
        resultado = links.conferir(_ler(args.coleta / "ibge.json"), cat)
        _gravar(args.coleta / "links.json", resultado)
        print(f"Links quebrados: {resultado['quebrados']}")
    elif args.comando == "manifesto":
        print("Manifesto:", ", ".join(manifesto.gravar(args.coleta, args.saida)))
    elif args.comando == "sih":
        from . import sih, sih_superficie
        if args.no_ar:
            anterior = sih_superficie.versao_no_ar(args.no_ar, cat)
        else:
            anterior = sih_superficie.carregar(args.anterior, cat) if args.anterior else None
        medicao = sih.executar(_ler(args.coleta / "ibge.json"), cat, args.trabalho, args.saida, args.ufs, args.anos,
                               args.processos, args.origem_local, args.manter_dbc, not args.sem_deducao,
                               anterior=anterior, no_ar_consultada=bool(args.no_ar))
        print(f"SIH: {medicao['etapas']['total_s']} s no total; medição em {args.saida / 'medicao.json'}")
        # Um ano reprovado deixa a execução vermelha: nada dele foi gravado, e a versão não pode ser publicada.
        for ano, motivo in medicao["reprovados"].items():
            print(f"::error title=SIH {ano} sem partição::{motivo}")
        if medicao["reprovados"]:
            return 1
    elif args.comando == "exigir":
        problemas = manifesto.falhas(args.coleta)
        for problema in problemas:
            print(f"::error::{problema}")
        return 1 if problemas else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
