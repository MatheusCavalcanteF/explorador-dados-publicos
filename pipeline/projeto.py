"""Endereços do projeto, lidos de projeto.yaml. Configuração errada para o pipeline antes de qualquer coleta."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import yaml

CAMINHO = Path(__file__).resolve().parent.parent / "projeto.yaml"
NOME = "Explorador de Dados Públicos"
# Só letras, números, _ e -: o código vira nome de arquivo na raiz do site.
CODIGO_GOOGLE = re.compile(r"google[0-9A-Za-z_-]{6,64}")


class ErroDeConfiguracao(ValueError):
    """projeto.yaml fora do formato esperado."""


def carregar(caminho: Path = CAMINHO) -> dict:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    repositorio, site = str(dados.get("repositorio") or ""), str(dados.get("site") or "")
    if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", repositorio):
        raise ErroDeConfiguracao(f"{caminho.name}: repositorio deve ser https://github.com/dono/nome, veio {repositorio!r}")
    partes = urlsplit(site)
    if partes.scheme != "https" or not partes.netloc or not partes.path.endswith("/") or partes.query or partes.fragment:
        raise ErroDeConfiguracao(f"{caminho.name}: site deve ser https e terminar em /, veio {site!r}")
    codigo = dados.get("google_search_console")
    if codigo is not None:
        codigo = str(codigo).strip().removesuffix(".html")
        if not CODIGO_GOOGLE.fullmatch(codigo):
            raise ErroDeConfiguracao(f"{caminho.name}: google_search_console deve ser o nome do arquivo que o "
                                     f"Search Console mostra, como google0123456789abcdef; veio {codigo!r}")
    return {"repositorio": repositorio, "site": site, "caminho_do_site": partes.path,
            "nome_curto": repositorio.rsplit("/", 1)[1], "google_search_console": codigo or None}


_CONFIGURACAO = carregar()
REPOSITORIO = _CONFIGURACAO["repositorio"]
SITE = _CONFIGURACAO["site"]
# Caminho do site no host, como /nome-do-repositorio/: a página 404 precisa de caminhos absolutos.
CAMINHO_DO_SITE = _CONFIGURACAO["caminho_do_site"]
NOME_CURTO = _CONFIGURACAO["nome_curto"]
GOOGLE_SEARCH_CONSOLE = _CONFIGURACAO["google_search_console"]
