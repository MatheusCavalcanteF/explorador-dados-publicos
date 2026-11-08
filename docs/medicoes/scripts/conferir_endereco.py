"""Endereço do site depois da renomeação do repositório, e o que os buscadores recebem no site publicado.

    python docs/medicoes/scripts/conferir_endereco.py <saida.json>

Roda da raiz do repositório. Nos dois endereços, pede a página inicial, a página de Santos e o
sitemap. No novo, também um caminho que não existe, a lista de municípios e o Parquet da
população: confere que o sitemap tem exatamente as páginas esperadas, valida o JSON-LD de Santos
com o validador do pipeline e compara os valores dele com o Parquet publicado. Mede ainda o
tamanho servido em gzip de 25 páginas de município, sorteadas pelo hash do código.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import buscadores, projeto, rede  # noqa: E402

# O endereço da época, antes da renomeação de 08/11/2026.
ANTIGO = "https://matheuscavalcantef.github.io/explorador-dados-publicos/"
NOVO = projeto.SITE
SANTOS = "municipio/3548500/"
SITEMAP = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def pedir(url: str) -> tuple[dict, bytes]:
    r = rede.pedir(url, cabecalhos={"Accept-Encoding": "gzip"}, descomprimir=False, tentativas=1)
    corpo = gzip.decompress(r.corpo) if r.cabecalho("Content-Encoding") == "gzip" else r.corpo
    return {"url": url, "status": r.status, "content_type": r.cabecalho("Content-Type"),
            "content_encoding": r.cabecalho("Content-Encoding"), "bytes_transferidos": len(r.corpo),
            "bytes": len(corpo), "sha256": hashlib.sha256(corpo).hexdigest()}, corpo


def main(saida: Path) -> None:
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    resultado = {"conferido_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "antigo": ANTIGO, "novo": NOVO, "pedidos": {}}
    corpos = {}
    for nome, base in (("antigo", ANTIGO), ("novo", NOVO)):
        for caminho in ["", SANTOS, "sitemap.xml", *(["nao-existe/"] if nome == "novo" else [])]:
            registro, corpo = pedir(f"{base}{caminho}?conferencia={marca}")
            resultado["pedidos"][f"{nome}:{caminho or 'inicio'}"] = registro
            corpos[(nome, caminho)] = corpo

    # Sitemap: exatamente a página inicial, as 27 UFs e um município por linha da lista publicada.
    _, lista = pedir(f"{NOVO}dados/municipios.json?conferencia={marca}")
    municipios = json.loads(lista)
    esperados = {NOVO} | {f"{NOVO}uf/{uf.lower()}/" for _, _, uf in municipios} | {f"{NOVO}municipio/{c}/" for c, _, _ in municipios}
    raiz = ET.fromstring(corpos[("novo", "sitemap.xml")])
    urls = {u.find("s:loc", SITEMAP).text: u.find("s:lastmod", SITEMAP).text for u in raiz.findall("s:url", SITEMAP)}
    resultado["sitemap"] = {"enderecos": len(urls), "esperados": len(esperados), "iguais_aos_esperados": set(urls) == esperados,
                            "lastmod": sorted(set(urls.values()))}

    # Santos: link canônico, Open Graph e JSON-LD válido, com os mesmos valores do Parquet publicado.
    html = corpos[("novo", SANTOS)].decode("utf-8")
    url = NOVO + SANTOS
    (bloco,) = JSONLD.findall(html)
    dado = json.loads(bloco)
    buscadores.validar(dado, url)
    _, corpo_parquet = pedir(f"{NOVO}dados/ibge/populacao.parquet?conferencia={marca}")
    linha = next(r for r in pq.read_table(io.BytesIO(corpo_parquet)).to_pylist() if r["codigo"] == "3548500")
    valores = {p["temporalCoverage"]: (p.get("variableMeasured") or {}).get("value") for p in dado["hasPart"]}
    resultado["santos"] = {
        "canonico": f'<link rel="canonical" href="{url}">' in html,
        "og_url": f'<meta property="og:url" content="{url}">' in html,
        "json_ld_valido": True, "json_ld_bytes": len(bloco.encode("utf-8")),
        "partes": sorted(valores), "date_modified": dado["dateModified"],
        "valores_iguais_ao_parquet": valores.get("2026") == linha["populacao_estimada"]
        and valores.get("2022") == linha["populacao_censo_2022"],
        "licenca": dado["license"], "fontes_oficiais": dado["isBasedOn"]}

    # Peso servido: 25 páginas de município, sorteadas pelo hash do código.
    amostra = sorted((c for c, _, _ in municipios), key=lambda c: hashlib.sha256(c.encode()).hexdigest())[:25]
    pesos = [pedir(f"{NOVO}municipio/{c}/?conferencia={marca}")[0] for c in amostra]
    resultado["paginas_amostra"] = {
        "codigos": amostra, "todas_200_em_gzip": all(p["status"] == 200 and p["content_encoding"] == "gzip" for p in pesos),
        "mediana_bytes": statistics.median(p["bytes"] for p in pesos),
        "mediana_bytes_transferidos": statistics.median(p["bytes_transferidos"] for p in pesos)}
    _, versao = pedir(f"{NOVO}versao.json?conferencia={marca}")
    resultado["versao_publicada"] = json.loads(versao)
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in resultado.items() if k != "pedidos"}, ensure_ascii=False, indent=1))
    for chave, registro in resultado["pedidos"].items():
        print(chave, registro["status"], registro["bytes_transferidos"])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
