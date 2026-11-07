"""Conferência agendada dos links oficiais. Roda no CI depois da publicação, nunca nos testes.

Abre a tabela de cada métrica e o link exato numa amostra de municípios, e confere se o
link exato devolve o valor publicado. Link quebrado é marcado no manifesto, sem impedir a publicação.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import ibge, rede

AMOSTRA = 30
METRICAS = {
    "populacao_estimada": ("estimativa", "populacao_estimada", ibge.ESTIMATIVA["variavel"]),
    "populacao_censo": ("censo", "populacao_censo", ibge.CENSO["variavel"]),
}


def sortear(municipios: list[dict], semente: str, n: int = AMOSTRA) -> list[dict]:
    """Amostra determinística que muda com a semente, para cobrir municípios diferentes a cada semana."""
    return sorted(municipios, key=lambda m: rede.sha256(f"{semente}:{m['codigo']}".encode()))[:n]


def _abrir(url: str, pedir) -> dict:
    try:
        r = pedir(url)
        return {"url": url, "status": r.status, "ok": r.status == 200}
    except rede.ErroDeRede as e:
        return {"url": url, "ok": False, "erro": str(e)[:300]}


def conferir(coleta: dict, catalogo: dict, pedir=rede.pedir, agora=None, n: int = AMOSTRA) -> dict:
    quando = (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resultado = {"conferido_em": quando, "metricas": {}}
    for nome, (chave, campo, variavel) in METRICAS.items():
        fonte_catalogo = catalogo["metricas"][nome]["fonte"]
        periodo = coleta["fontes"][chave]["periodo"]
        amostra = []
        for m in sortear([m for m in coleta["municipios"] if m[campo]], f"{quando[:10]}:{nome}", n):
            url = fonte_catalogo["acesso"]["url"].format(municipio=m["codigo"], periodo=periodo)
            item = {"codigo": m["codigo"], "url": url, "publicado": m[campo]}
            try:
                r = pedir(url)
                _, valores = ibge.ler_sidra(r.corpo, variavel, f"Link exato de {m['codigo']}")
                item |= {"status": r.status, "na_origem": valores.get(m["codigo"]),
                         "ok": r.status == 200 and valores.get(m["codigo"]) == m[campo]}
            except (rede.ErroDeRede, ibge.ErroDeContrato) as e:
                item |= {"ok": False, "erro": str(e)[:300]}
            amostra.append(item)
        resultado["metricas"][nome] = {"tabela": _abrir(fonte_catalogo["tabela"], pedir), "amostra": amostra}
    resultado["quebrados"] = sum(
        (0 if item["tabela"]["ok"] else 1) + sum(1 for a in item["amostra"] if not a["ok"])
        for item in resultado["metricas"].values())
    return resultado
