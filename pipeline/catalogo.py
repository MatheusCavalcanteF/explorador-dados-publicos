"""Leitura e validação do catálogo. Um catálogo inconsistente para o pipeline antes de qualquer coleta."""
from __future__ import annotations

from pathlib import Path

import yaml

CAMINHO = Path(__file__).resolve().parent.parent / "catalogo" / "catalogo.yaml"
TIPOS_DE_ACESSO = {"exato", "tabela", "arquivo", "receita"}


class ErroDeCatalogo(ValueError):
    """O catálogo contradiz as próprias regras."""


def carregar(caminho: Path = CAMINHO) -> dict:
    catalogo = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    validar(catalogo)
    return catalogo


def validar(catalogo: dict) -> None:
    if not isinstance(catalogo, dict) or catalogo.get("versao") != 1:
        raise ErroDeCatalogo("Catálogo sem versão 1")
    temas = catalogo.get("temas") or {}
    bases = catalogo.get("bases") or {}
    metricas = catalogo.get("metricas") or {}
    if not temas or not metricas:
        raise ErroDeCatalogo("Catálogo sem temas ou sem métricas")
    for nome, base in bases.items():
        origem = str((base.get("coleta") or {}).get("origem", ""))
        if not base.get("nome") or not base.get("orgao") or not origem.startswith(("https://", "http://", "ftp://")):
            raise ErroDeCatalogo(f"Base {nome}: sem nome, órgão ou coleta.origem")
    for nome, metrica in metricas.items():
        onde = f"Métrica {nome}"
        if metrica.get("tema") not in temas:
            raise ErroDeCatalogo(f"{onde}: tema {metrica.get('tema')!r} fora da lista fixa")
        etiquetas = metrica.get("etiquetas")
        if not isinstance(etiquetas, list) or not set(etiquetas) <= set(temas):
            raise ErroDeCatalogo(f"{onde}: etiquetas ausentes ou fora da lista fixa")
        if metrica["tema"] in etiquetas:
            raise ErroDeCatalogo(f"{onde}: o tema principal não pode repetir nas etiquetas")
        if "formula" in metrica:
            # Calculada: cada parcela é outra métrica do catálogo, com a própria fonte.
            parcelas = metrica.get("fontes") or []
            if not parcelas or any(p not in metricas or p == nome for p in parcelas):
                raise ErroDeCatalogo(f"{onde}: métrica calculada precisa listar as métricas de que depende")
            continue
        if metrica.get("base") not in bases:
            raise ErroDeCatalogo(f"{onde}: base {metrica.get('base')!r} não existe")
        fonte = metrica.get("fonte") or {}
        acesso = fonte.get("acesso") or {}
        if acesso.get("tipo") not in TIPOS_DE_ACESSO:
            raise ErroDeCatalogo(f"{onde}: acesso.tipo deve ser um de {sorted(TIPOS_DE_ACESSO)}")
        if not str(acesso.get("url", "")).startswith("https://") and not str(acesso.get("url", "")).startswith("http://"):
            raise ErroDeCatalogo(f"{onde}: acesso sem url")
        if acesso["tipo"] == "receita" and not acesso.get("receita"):
            raise ErroDeCatalogo(f"{onde}: acesso por receita precisa dos passos em 'receita'")
        if not fonte.get("orgao") or not fonte.get("pesquisa"):
            raise ErroDeCatalogo(f"{onde}: fonte sem órgão ou pesquisa")
        if not metrica.get("ressalvas"):
            raise ErroDeCatalogo(f"{onde}: toda métrica publicada diz suas ressalvas")
