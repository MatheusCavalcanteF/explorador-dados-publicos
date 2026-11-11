"""Releases do repositório: a partição fechada do Censo 2022.

"Não existe" e "não consegui consultar" são respostas diferentes. A lista de Releases vem da API do GitHub,
e só uma resposta 200 com a lista diz o que existe: a Release que não está nela não existe, e a execução
segue (primeira coleta do Censo). Qualquer outra resposta, ou falha de rede, para com erro: seguir sem a
partição congelada trocaria, sem aviso, o dado publicado pelo da fonte.

O resultado da consulta fica em `consulta.json`, na pasta de destino.

Nada do SIH vai para Releases (decidido em 10/11/2026): a versão no ar do SIH é a superfície publicada com o
site, e a consulta a ela é sih_superficie.consultar.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import projeto, rede
from .contrato import ErroDeContrato

API = "https://api.github.com/repos/" + projeto.REPOSITORIO.split("github.com/", 1)[1]
CENSO_TAG, CENSO_ARQUIVO = "ibge-censo-2022", "censo-2022.json"
CONSULTA = "consulta.json"
POR_PAGINA = 100


class ErroDeRelease(ErroDeContrato):
    """Não deu para saber o que está nas Releases, ou o que está lá não confere."""


def listar(pedir=rede.pedir, token: str | None = None) -> dict[str, dict]:
    """Todas as Releases publicadas, por tag. Rascunho não conta: ninguém de fora o vê."""
    cabecalhos = {"Accept": "application/vnd.github+json"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    saida: dict[str, dict] = {}
    for pagina in range(1, 51):
        url = f"{API}/releases?per_page={POR_PAGINA}&page={pagina}"
        try:
            r = pedir(url, cabecalhos=cabecalhos)
        except rede.ErroDeRede as erro:
            raise ErroDeRelease(f"Não consegui consultar as Releases: {erro}") from None
        if r.status != 200:
            raise ErroDeRelease(f"Não consegui consultar as Releases: HTTP {r.status} em {url}")
        try:
            lista = json.loads(r.corpo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            lista = None
        if not isinstance(lista, list) or not all(isinstance(x, dict) and isinstance(x.get("tag_name"), str) for x in lista):
            raise ErroDeRelease(f"Não consegui consultar as Releases: resposta fora do formato em {url}")
        for item in lista:
            if not item.get("draft"):
                saida[item["tag_name"]] = item
        if len(lista) < POR_PAGINA:
            return saida
    raise ErroDeRelease("Não consegui consultar as Releases: mais páginas do que o esperado")


def baixar(release: dict, nome: str, pedir=rede.pedir) -> bytes:
    """Um arquivo de uma Release que existe. Faltar o arquivo, ou vir com outro tamanho ou hash, é erro."""
    tag = release["tag_name"]
    arquivo = next((a for a in release.get("assets") or [] if a.get("name") == nome), None)
    if arquivo is None or not arquivo.get("browser_download_url"):
        raise ErroDeRelease(f"A Release {tag} existe, mas não tem o arquivo {nome}")
    try:
        # Sem o token: o endereço de download redireciona para outro domínio, que não deve recebê-lo.
        r = pedir(arquivo["browser_download_url"], descomprimir=False)
    except rede.ErroDeRede as erro:
        raise ErroDeRelease(f"Não consegui baixar {nome} da Release {tag}: {erro}") from None
    if r.status != 200:
        raise ErroDeRelease(f"Não consegui baixar {nome} da Release {tag}: HTTP {r.status}")
    if "size" in arquivo and len(r.corpo) != arquivo["size"]:
        raise ErroDeRelease(f"{nome} da Release {tag}: {len(r.corpo)} bytes, e a Release registra {arquivo['size']}")
    digest = arquivo.get("digest") or ""
    if digest.startswith("sha256:") and hashlib.sha256(r.corpo).hexdigest() != digest[7:]:
        raise ErroDeRelease(f"{nome} da Release {tag}: SHA-256 diferente do que a Release registra")
    return r.corpo


def consultar(destino: Path, pedir=rede.pedir, token: str | None = None, agora=None) -> dict:
    """Lista as Releases uma vez, baixa o Censo se a Release existir e grava o resultado da consulta.

    `censo-2022.json` vai para `destino`, se a Release existir. A consulta só é gravada no fim: se algo falhar
    no caminho, a etapa seguinte não encontra `consulta.json` e para também.
    """
    destino.mkdir(parents=True, exist_ok=True)
    (destino / CONSULTA).unlink(missing_ok=True)
    releases = listar(pedir, token)
    censo = CENSO_TAG in releases
    if censo:
        (destino / CENSO_ARQUIVO).write_bytes(baixar(releases[CENSO_TAG], CENSO_ARQUIVO, pedir))
    else:
        (destino / CENSO_ARQUIVO).unlink(missing_ok=True)
    consulta = {"consultado_em": (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "releases": sorted(releases), "censo": censo}
    (destino / CONSULTA).write_text(json.dumps(consulta, ensure_ascii=False, indent=1), encoding="utf-8")
    return consulta
