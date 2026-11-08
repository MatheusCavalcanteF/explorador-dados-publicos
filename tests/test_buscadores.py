"""Validação do JSON-LD e do sitemap: o que o pipeline recusa antes de publicar."""
import copy
import json

import pytest

from pipeline import buscadores, catalogo, projeto, site
from test_site import coleta, jsonld, ler

T = "2026-11-08T02:36:11Z"


@pytest.fixture
def municipio(tmp_path):
    saida = tmp_path / "site"
    site.construir(coleta(), catalogo.carregar(), saida)
    return jsonld(ler(saida, "municipio/3548500/index.html"))


@pytest.mark.parametrize("estrago, motivo", [
    (lambda d: d.update(description="Curta demais."), "raiz: description"),
    (lambda d: d.pop("license"), "raiz: license"),
    (lambda d: d.update(license={"@type": "CreativeWork"}), "raiz: license"),
    (lambda d: d.update(creator="IBGE"), "raiz: creator"),
    (lambda d: d.update(url=projeto.SITE + "outro/"), "raiz: url"),
    (lambda d: d.update(dateModified="2026-11-08"), "dateModified"),
    (lambda d: d.update(**{"@context": "http://schema.org"}), "@context"),
    (lambda d: d.update(hasPart=[]), "hasPart vazio"),
    (lambda d: d["hasPart"][1].pop("temporalCoverage"), r"hasPart\[1\]: temporalCoverage"),
    (lambda d: d["hasPart"][1].update(temporalCoverage="ano passado"), r"hasPart\[1\]: temporalCoverage"),
    (lambda d: d["hasPart"][1].update(isBasedOn="SIDRA"), r"hasPart\[1\]: isBasedOn"),
    (lambda d: d["hasPart"][1].pop("distribution"), r"hasPart\[1\]: sem distribution"),
    (lambda d: d["hasPart"][0].pop("license"), r"hasPart\[0\]: license"),
])
def test_validador_recusa_o_que_falta_ou_esta_fora_do_formato(municipio, estrago, motivo):
    url = projeto.SITE + "municipio/3548500/"
    buscadores.validar(municipio, url)
    estragado = copy.deepcopy(municipio)
    estrago(estragado)
    with pytest.raises(buscadores.ErroDeBuscadores, match=motivo):
        buscadores.validar(estragado, url)


def test_script_nao_fecha_antes_da_hora():
    texto = buscadores.script({"name": "</script><script>alert(1)</script> & cia"})
    abertura = '<script type="application/ld+json">'
    corpo = texto.removeprefix(abertura).removesuffix("</script>")
    assert "<" not in corpo and ">" not in corpo
    assert json.loads(corpo)["name"] == "</script><script>alert(1)</script> & cia"


def test_licenca_declarada_vai_como_endereco():
    base = {"licenca": {"id": "cc-by-sa-4.0", "atribuicao": "INPE", "url": "https://creativecommons.org/licenses/by-sa/4.0/"}}
    assert buscadores.licenca(base) == "https://creativecommons.org/licenses/by-sa/4.0/"


def test_sitemap_escapa_e_recusa_repetido_data_invalida_e_excesso(monkeypatch):
    texto = buscadores.sitemap([("a/?x=1&y=2", T)])
    assert f"<loc>{projeto.SITE}a/?x=1&amp;y=2</loc><lastmod>{T}</lastmod>" in texto
    with pytest.raises(buscadores.ErroDeBuscadores, match="repetido"):
        buscadores.sitemap([("a/", T), ("a/", T)])
    with pytest.raises(buscadores.ErroDeBuscadores, match="lastmod"):
        buscadores.sitemap([("a/", "2026-11-08")])
    monkeypatch.setattr(buscadores, "MAX_URLS", 2)
    with pytest.raises(buscadores.ErroDeBuscadores, match="acima do limite"):
        buscadores.sitemap([("a/", T), ("b/", T), ("c/", T)])


def test_desde_cai_na_coleta_quando_nao_ha_registro():
    assert buscadores.desde({"coletado_em": T}) == T
    assert buscadores.desde({"coletado_em": T, "valores_desde": "2026-11-01T00:47:00Z"}) == "2026-11-01T00:47:00Z"
