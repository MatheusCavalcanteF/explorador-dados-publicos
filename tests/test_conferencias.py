"""Links, hospedagem e manifesto, com respostas simuladas no formato do GitHub Pages e da SIDRA."""
import gzip
import json
from datetime import datetime, timezone

import pytest

from pipeline import catalogo, hospedagem, links, manifesto, rede
from conftest import FonteFalsa, resposta, sidra
from test_site import coleta

AGORA = datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc)


def test_amostra_e_deterministica_e_muda_com_a_semente():
    municipios = [{"codigo": str(1100000 + i)} for i in range(200)]
    a = links.sortear(municipios, "2026-11-07", 30)
    assert a == links.sortear(municipios, "2026-11-07", 30) and len(a) == 30
    assert a != links.sortear(municipios, "2026-11-14", 30)


def test_links_marca_valor_divergente_e_tabela_fora():
    dados = coleta()
    respostas = {"https://sidra.ibge.gov.br/tabela/6579": resposta(b"<html>"),
                 "https://sidra.ibge.gov.br/tabela/4714": resposta(b"erro", status=404)}
    for m in dados["municipios"]:
        estimativa = m["populacao_estimada"] + (1 if m["codigo"] == "4206504" else 0)
        respostas[f"https://apisidra.ibge.gov.br/values/t/6579/n6/{m['codigo']}/v/9324/p/2026"] = \
            resposta(sidra({m["codigo"]: estimativa}, 9324, "2026"))
        if m["populacao_censo"]:
            respostas[f"https://apisidra.ibge.gov.br/values/t/4714/n6/{m['codigo']}/v/93/p/2022"] = \
                resposta(sidra({m["codigo"]: m["populacao_censo"]}, 93, "2022"))
    resultado = links.conferir(dados, catalogo.carregar(), FonteFalsa(respostas), AGORA)
    estimativa = resultado["metricas"]["populacao_estimada"]
    assert estimativa["tabela"]["ok"] is True
    assert {a["codigo"]: a["ok"] for a in estimativa["amostra"]} == {"3548500": True, "4206504": False, "5101837": True}
    censo = resultado["metricas"]["populacao_censo"]
    # Município sem valor publicado não entra na amostra do link exato.
    assert {a["codigo"] for a in censo["amostra"]} == {"3548500", "4206504"}
    assert censo["tabela"] == {"url": "https://sidra.ibge.gov.br/tabela/4714", "status": 404, "ok": False}
    assert resultado["quebrados"] == 2


class PagesFalso:
    """Imita o que o plano mediu no GitHub Pages: gzip, Range 206 com bytes crus e HEAD com tamanho comprimido."""

    def __init__(self, site, execucao, range_quebrado=False):
        self.site, self.execucao, self.range_quebrado = site, execucao, range_quebrado

    def __call__(self, url, metodo="GET", cabecalhos=None, descomprimir=True, tentativas=3):
        cabecalhos = cabecalhos or {}
        caminho = url.split("://", 1)[1].split("/", 2)[2].split("?")[0]
        if caminho == "versao.json":
            return resposta({"execucao": self.execucao})
        corpo = (self.site / (caminho + "index.html" if caminho.endswith("/") else caminho)).read_bytes()
        comprimido = gzip.compress(corpo)
        if "Range" in cabecalhos and not self.range_quebrado:
            inicio, fim = map(int, cabecalhos["Range"].removeprefix("bytes=").split("-"))
            return resposta(corpo[inicio:fim + 1], 206, {"Content-Range": f"bytes {inicio}-{fim}/{len(corpo)}"})
        if cabecalhos.get("Accept-Encoding") == "gzip":
            gz = {"Content-Encoding": "gzip", "Content-Length": str(len(comprimido))}
            return resposta(b"" if metodo == "HEAD" else comprimido, 200, gz)
        return resposta(corpo, 200, {"Content-Length": str(len(corpo))})


@pytest.fixture
def site_construido(tmp_path):
    from pipeline import site
    saida = tmp_path / "site"
    site.construir(coleta(), catalogo.carregar(), saida, execucao="77")
    return saida


def test_hospedagem_igual_ao_plano(site_construido):
    resultado = hospedagem.conferir("https://exemplo.github.io/projeto", site_construido, "77",
                                    PagesFalso(site_construido, "77"), dormir=lambda s: None, agora=AGORA,
                                    esperado="https://exemplo.github.io/projeto/")
    assert {k: v["bate_com_o_plano"] for k, v in resultado["testes"].items()} == {
        "endereco": True, "gzip": True, "range": True, "head": True, "range_pedindo_gzip": None, "pagina": True,
        "sitemap": True}


def test_hospedagem_aponta_deploy_fora_do_endereco_configurado(site_construido, tmp_path):
    # Link canônico, sitemap e JSON-LD apontam para projeto.yaml: publicar em outro endereço deixa tudo errado.
    resultado = hospedagem.conferir("https://exemplo.github.io/nome-antigo/", site_construido, "77",
                                    PagesFalso(site_construido, "77"), dormir=lambda s: None)
    assert resultado["testes"]["endereco"]["bate_com_o_plano"] is False
    (tmp_path / "hospedagem.json").write_text(json.dumps(resultado), encoding="utf-8")
    assert "Hospedagem: endereco não bate com o plano" in manifesto.falhas(tmp_path)


def test_hospedagem_aponta_sitemap_diferente_do_build(site_construido, tmp_path):
    servido = tmp_path / "servido"
    import shutil
    shutil.copytree(site_construido, servido)
    (servido / "sitemap.xml").write_text("<urlset/>", encoding="utf-8")
    resultado = hospedagem.conferir("https://exemplo.github.io/projeto/", site_construido, "77",
                                    PagesFalso(servido, "77"), dormir=lambda s: None)
    assert resultado["testes"]["sitemap"]["bate_com_o_plano"] is False


def test_hospedagem_aponta_range_que_devolve_o_arquivo_inteiro(site_construido):
    resultado = hospedagem.conferir("https://exemplo.github.io/projeto/", site_construido, "77",
                                    PagesFalso(site_construido, "77", range_quebrado=True), dormir=lambda s: None)
    assert resultado["testes"]["range"]["bate_com_o_plano"] is False


def test_hospedagem_espera_a_versao_nova_e_desiste(site_construido):
    with pytest.raises(rede.ErroDeRede, match="não mostrou a execução 78"):
        hospedagem.conferir("https://exemplo.github.io/projeto", site_construido, "78",
                            PagesFalso(site_construido, "77"), limite=0, dormir=lambda s: None)


def test_manifesto_guarda_metadados_e_totais_sem_linhas_por_municipio(tmp_path):
    pasta = tmp_path / "coleta"
    pasta.mkdir()
    (pasta / "ibge.json").write_text(json.dumps(coleta()), encoding="utf-8")
    (pasta / "alcance.json").write_text(json.dumps({"fontes": {"datasus_ftp": {"ok": True}}}), encoding="utf-8")
    assert manifesto.gravar(pasta, tmp_path / "manifesto") == ["ibge.json", "alcance.json"]
    gravado = json.loads((tmp_path / "manifesto" / "ibge.json").read_text(encoding="utf-8"))
    assert gravado["municipios"] == 3 and gravado["por_uf"]["MT"]["populacao_censo_2022"] == 0
    assert "Santos" not in json.dumps(gravado)


def test_falhas_deixam_a_execucao_vermelha(tmp_path):
    def gravar(nome, valor):
        (tmp_path / f"{nome}.json").write_text(json.dumps(valor), encoding="utf-8")
    assert manifesto.falhas(tmp_path) == ["Teste de alcance não rodou", "Testes de hospedagem não rodaram",
                                          "Leitor em JavaScript não rodou"]
    gravar("alcance", {"fontes": {"datasus_ftp": {"ok": False, "erro": "timeout"}, "inep": {"ok": True}}})
    gravar("hospedagem", {"testes": {"range": {"bate_com_o_plano": False}, "range_pedindo_gzip": {"bate_com_o_plano": None}}})
    gravar("leitor", {"ok": False})
    assert manifesto.falhas(tmp_path) == ["Alcance: datasus_ftp falhou (timeout)", "Hospedagem: range não bate com o plano",
                                          "Leitor em JavaScript divergiu da coleta"]
