import json
import re

import pyarrow.parquet as pq
import pytest

from pipeline import catalogo, site

HASH_EST = "a" * 64
HASH_CENSO = "b" * 64


def coleta(censo_origem="fonte"):
    municipios = [
        {"codigo": "3548500", "nome": "Santos", "uf": "SP", "uf_nome": "São Paulo",
         "populacao_estimada": 429528, "populacao_censo": 418608},
        {"codigo": "4206504", "nome": "Herval d'Oeste & <Teste>", "uf": "SC", "uf_nome": "Santa Catarina",
         "populacao_estimada": 22000, "populacao_censo": 21000},
        {"codigo": "5101837", "nome": "Boa Esperança do Norte", "uf": "MT", "uf_nome": "Mato Grosso",
         "populacao_estimada": 5983, "populacao_censo": None},
    ]
    comum = {"coletado_em": "2026-11-07T23:23:20Z", "bytes": 1508656, "origem": "fonte"}
    censo = {**comum, "periodo": "2022", "modificacao_na_origem": "2026-05-07", "sha256": HASH_CENSO,
             "bytes": 1447059, "origem": censo_origem}
    if censo_origem == "release":
        censo |= {"coletado_em": "2026-11-01T10:00:00Z", "conferido_com_a_fonte_em": "2026-11-07T23:23:20Z"}
    return {"coletado_em": "2026-11-07T23:23:20Z", "municipios": municipios,
            "fontes": {"estimativa": {**comum, "periodo": "2026", "modificacao_na_origem": "2026-08-28", "sha256": HASH_EST},
                       "censo": censo}}


@pytest.fixture
def construido(tmp_path):
    saida = tmp_path / "site"
    site.construir(coleta(), catalogo.carregar(), saida, execucao="123")
    return saida


def ler(saida, caminho):
    return (saida / caminho).read_text(encoding="utf-8")


def test_pagina_do_municipio_tem_numero_link_exato_e_coleta(construido):
    html = ler(construido, "municipio/3548500/index.html")
    assert "<h1 class=\"placa__nome\">Santos</h1>" in html
    assert '<data value="429528">429.528</data>' in html and '<data value="418608">418.608</data>' in html
    assert "https://apisidra.ibge.gov.br/values/t/6579/n6/3548500/v/9324/p/2026" in html
    assert "https://apisidra.ibge.gov.br/values/t/4714/n6/3548500/v/93/p/2022" in html
    assert "https://sidra.ibge.gov.br/tabela/6579" in html
    assert HASH_EST in html and HASH_CENSO in html
    # 23:23 UTC é 20:23 em Brasília
    assert "07/11/2026, 20:23 (Brasília)" in html
    assert "28/08/2026, segundo a SIDRA" in html
    assert "<summary>Fonte e método" in html
    assert "É estimativa do IBGE, não contagem." in html


def test_ausencia_nao_vira_zero(construido):
    html = ler(construido, "municipio/5101837/index.html")
    assert '<dd class="ausente">sem dado</dd>' in html
    assert "O Censo 2022 não traz dado para este município. A ausência não é zero." in html
    assert 'value="0"' not in html


def test_nome_e_escapado(construido):
    html = ler(construido, "municipio/4206504/index.html")
    assert "Herval d&#x27;Oeste &amp; &lt;Teste&gt;" in html
    assert "<Teste>" not in html


def test_caminhos_relativos_para_morar_em_subpasta(construido):
    for caminho in ("index.html", "uf/sp/index.html", "municipio/3548500/index.html"):
        html = ler(construido, caminho)
        internos = re.findall(r'(?:href|src)="(/[^"]*)"', html)
        assert internos == [], caminho


def test_listas_por_uf_e_indice_da_busca(construido):
    assert "Santos" in ler(construido, "uf/sp/index.html")
    assert "3 municípios" in ler(construido, "index.html")
    assert json.loads(ler(construido, "dados/municipios.json"))[0] == ["3548500", "Santos", "SP"]
    assert json.loads(ler(construido, "versao.json"))["execucao"] == "123"


def test_parquet_sem_compressao_com_os_valores_publicados(construido):
    arquivo = pq.ParquetFile(construido / "dados/ibge/populacao.parquet")
    colunas = arquivo.metadata.row_group(0)
    assert {colunas.column(i).compression for i in range(colunas.num_columns)} == {"UNCOMPRESSED"}
    tabela = arquivo.read().to_pylist()
    assert tabela[0] == {"codigo": "3548500", "nome": "Santos", "uf": "SP",
                         "populacao_estimada": 429528, "populacao_censo_2022": 418608}
    assert tabela[2]["populacao_censo_2022"] is None


def test_censo_da_release_diz_de_onde_veio(tmp_path):
    saida = tmp_path / "site"
    site.construir(coleta("release"), catalogo.carregar(), saida)
    html = ler(saida, "municipio/3548500/index.html")
    assert "releases/tag/ibge-censo-2022" in html
    assert "conferida de novo em 07/11/2026, 20:23 (Brasília), sem mudança" in html


def test_painel_mostra_a_ultima_conferencia_dos_links(tmp_path):
    amostra_ok = [{"codigo": "3548500", "ok": True}, {"codigo": "1100015", "ok": True}]
    links = {"conferido_em": "2026-11-07T23:40:00Z", "metricas": {
        "populacao_estimada": {"tabela": {"ok": True}, "amostra": amostra_ok},
        "populacao_censo": {"tabela": {"ok": False}, "amostra": [{"codigo": "3548500", "ok": False}]}}}
    saida = tmp_path / "site"
    site.construir(coleta(), catalogo.carregar(), saida, links)
    html = ler(saida, "municipio/3548500/index.html")
    assert "o link exato devolveu o valor publicado em 2 de 2 municípios sorteados" in html
    assert "Este município estava na amostra e conferiu." in html
    assert 'estado estado--falhou' in html and "a tabela não respondeu" in html


def test_sem_conferencia_registrada_diz_isso(construido):
    assert "Link ainda sem conferência registrada." in ler(construido, "municipio/3548500/index.html")
