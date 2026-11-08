"""Testes de hospedagem no site publicado: endereço, gzip, Range, HEAD, uma página e o sitemap, comparados com o plano.

O plano mediu no GitHub Pages, em sites de terceiros: `Range` volta 206 com bytes crus e o
tamanho real em Content-Range; `HEAD` informa o tamanho comprimido; `.parquet` sai em gzip.
O endereço em que o deploy publicou precisa ser o de projeto.yaml, porque o link canônico,
o sitemap e o JSON-LD apontam para ele.
"""
from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import projeto, rede
from .site import PARQUET

PAGINA = "municipio/3548500/index.html"
SITEMAP = "sitemap.xml"


def _sem_gzip(r: rede.Resposta) -> bytes:
    return gzip.decompress(r.corpo) if r.cabecalho("Content-Encoding") == "gzip" else r.corpo


def _registro(r: rede.Resposta) -> dict:
    return {"status": r.status, "content_encoding": r.cabecalho("Content-Encoding"),
            "content_length": r.cabecalho("Content-Length"), "content_range": r.cabecalho("Content-Range"),
            "cache_control": r.cabecalho("Cache-Control"), "bytes_recebidos": len(r.corpo)}


def esperar_versao(base: str, execucao: str, pedir, limite: float, dormir) -> float:
    """O deploy termina antes de o site servir a versão nova em todos os pontos; espera por ela."""
    inicio = time.monotonic()
    while True:
        try:
            r = pedir(f"{base}versao.json?conferencia={execucao}", tentativas=1)
            if r.status == 200 and json.loads(r.corpo).get("execucao") == execucao:
                return round(time.monotonic() - inicio, 1)
        except (rede.ErroDeRede, json.JSONDecodeError):
            pass
        if time.monotonic() - inicio > limite:
            raise rede.ErroDeRede(f"O site não mostrou a execução {execucao} em {limite:.0f} s")
        dormir(10)


def conferir(url_base: str, site: Path, execucao: str, pedir=rede.pedir, limite: float = 300,
             dormir=time.sleep, agora=None, esperado: str = projeto.SITE) -> dict:
    base = url_base.rstrip("/") + "/"
    espera = esperar_versao(base, execucao, pedir, limite, dormir)
    # A consulta muda a chave de cache do CDN, para não medir a versão anterior.
    url = f"{base}{PARQUET}?conferencia={execucao}"
    local = (site / PARQUET).read_bytes()
    testes = {"endereco": {"publicado_em": base, "esperado": f"o endereço de projeto.yaml, {esperado}",
                           "bate_com_o_plano": base == esperado}}

    r = pedir(url, cabecalhos={"Accept-Encoding": "gzip"}, descomprimir=False)
    comprimido = len(r.corpo)
    testes["gzip"] = _registro(r) | {
        "esperado": "200 em gzip, com o mesmo conteúdo do build",
        "bate_com_o_plano": r.status == 200 and r.cabecalho("Content-Encoding") == "gzip" and _sem_gzip(r) == local}

    r = pedir(url, cabecalhos={"Range": "bytes=0-1023", "Accept-Encoding": "identity"}, descomprimir=False)
    testes["range"] = _registro(r) | {
        "esperado": f"206, bytes crus, Content-Range bytes 0-1023/{len(local)}",
        "bate_com_o_plano": r.status == 206 and r.cabecalho("Content-Range") == f"bytes 0-1023/{len(local)}"
        and not r.cabecalho("Content-Encoding") and r.corpo == local[:1024]}

    r = pedir(url, metodo="HEAD", cabecalhos={"Accept-Encoding": "gzip"}, descomprimir=False)
    testes["head"] = _registro(r) | {
        "esperado": f"Content-Length com o tamanho comprimido ({comprimido}), não o real ({len(local)})",
        "bate_com_o_plano": r.status == 200 and r.cabecalho("Content-Length") == str(comprimido) != str(len(local))}

    # O plano não mediu este caso: o navegador pede identity quando manda Range. Fica registrado.
    r = pedir(url, cabecalhos={"Range": "bytes=0-1023", "Accept-Encoding": "gzip"}, descomprimir=False)
    testes["range_pedindo_gzip"] = _registro(r) | {"esperado": "não medido no plano", "bate_com_o_plano": None}

    pagina = (site / PAGINA).read_bytes()
    r = pedir(f"{base}{PAGINA.removesuffix('index.html')}?conferencia={execucao}",
              cabecalhos={"Accept-Encoding": "gzip"}, descomprimir=False)
    testes["pagina"] = _registro(r) | {
        "esperado": "200 em gzip, igual ao HTML do build",
        "bate_com_o_plano": r.status == 200 and r.cabecalho("Content-Encoding") == "gzip" and _sem_gzip(r) == pagina}

    mapa = (site / SITEMAP).read_bytes()
    r = pedir(f"{base}{SITEMAP}?conferencia={execucao}", cabecalhos={"Accept-Encoding": "gzip"}, descomprimir=False)
    testes["sitemap"] = _registro(r) | {
        "esperado": "200, igual ao sitemap do build",
        "bate_com_o_plano": r.status == 200 and _sem_gzip(r) == mapa}

    return {"conferido_em": (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "site": base, "execucao": execucao, "segundos_ate_a_versao_nova": espera,
            "parquet_bytes_reais": len(local), "testes": testes}
