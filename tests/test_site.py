import json
import re
import xml.etree.ElementTree as ET

import pyarrow.parquet as pq
import pytest

from pipeline import buscadores, catalogo, projeto, site

HASH_EST = "a" * 64
HASH_CENSO = "b" * 64
HASH_DTB = "c" * 64


def coleta(censo_origem="fonte"):
    municipios = [
        {"codigo": "3548500", "nome": "Santos", "uf": "SP", "uf_nome": "São Paulo",
         "populacao_estimada": 429528, "populacao_censo": 418608},
        {"codigo": "4206504", "nome": "Herval d'Oeste & <Teste>", "uf": "SC", "uf_nome": "Santa Catarina",
         "populacao_estimada": 22000, "populacao_censo": 21000},
        {"codigo": "5101837", "nome": "Boa Esperança do Norte", "uf": "MT", "uf_nome": "Mato Grosso",
         "populacao_estimada": 5983, "populacao_censo": None},
    ]
    comum = {"coletado_em": "2026-11-07T23:23:20Z", "bytes": 1508656, "origem": "fonte",
             "url": "https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/last%201"}
    censo = {**comum, "periodo": "2022", "sha256": HASH_CENSO, "bytes": 1447059, "origem": censo_origem,
             "url": "https://apisidra.ibge.gov.br/values/t/4714/n6/all/v/93/p/2022"}
    if censo_origem == "release":
        censo |= {"coletado_em": "2026-11-01T10:00:00Z", "conferido_com_a_fonte_em": "2026-11-07T23:23:20Z"}
    dtb = {"base": "ibge_dtb", "periodo": "2025", "data_base": "2025-12-31", "coletado_em": "2026-11-07T23:23:20Z",
           "url": "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip",
           "planilha": "RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods", "bytes": 1635600, "sha256": HASH_DTB}
    return {"coletado_em": "2026-11-07T23:23:20Z", "municipios": municipios,
            "fontes": {"dtb": dtb, "estimativa": {**comum, "periodo": "2026", "sha256": HASH_EST}, "censo": censo}}


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
    assert "<dt>Período de referência</dt><dd>2026</dd>" in html and "Atualização na origem" not in html
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


def test_data_base_da_dtb_no_rodape_de_todas_as_paginas_e_no_painel(construido):
    for caminho in ("index.html", "uf/sp/index.html", "municipio/3548500/index.html", "404.html"):
        assert ("Municípios da Divisão Territorial Brasileira 2025 do IBGE, com data-base em 31/12/2025."
                in ler(construido, caminho)), caminho
    html = ler(construido, "municipio/3548500/index.html")
    assert "<dt>Data-base</dt><dd>31/12/2025, como informa a própria planilha</dd>" in html
    assert 'href="https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip"' in html
    assert 'href="https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/"' in html
    assert HASH_DTB in html and "DTB_2025.zip, 1,6 MB" in html
    assert "só entra na edição seguinte" in html


# Buscadores: link canônico, Open Graph, JSON-LD e sitemap.

SITEMAP = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def jsonld(html):
    blocos = JSONLD.findall(html)
    assert len(blocos) == 1
    return json.loads(blocos[0])


def paginas(saida):
    return sorted(p.relative_to(saida).as_posix() for p in saida.rglob("index.html"))


def lastmods(saida):
    raiz = ET.fromstring(ler(saida, "sitemap.xml"))
    return {u.find("s:loc", SITEMAP).text: u.find("s:lastmod", SITEMAP).text for u in raiz.findall("s:url", SITEMAP)}


def coleta_com_historico(revisoes=None):
    """Valores da DTB e do Censo vistos desde 01/11; a estimativa de Santos revisada na coleta de 15/11 (UTC)."""
    dados = coleta()
    fontes = dados["fontes"]
    fontes["dtb"]["valores_desde"] = fontes["censo"]["valores_desde"] = "2026-11-01T00:47:00Z"
    if revisoes is None:
        revisoes = [{"detectada_em": "2026-11-15T00:47:00Z", "sem_detalhe_porque": None,
                     "municipios": [{"codigo": "3548500", "antes": 429000, "depois": 429528, "variacao_pct": 0.12}]}]
    fontes["estimativa"] |= {"valores_desde": "2026-11-15T00:47:00Z", "periodo_desde": "2026-11-01T00:47:00Z",
                             "revisoes": revisoes}
    return dados


def test_toda_pagina_tem_canonico_open_graph_e_json_ld_valido(construido):
    caminhos = paginas(construido)
    assert len(caminhos) == 1 + 3 + 3
    for caminho in caminhos:
        html = ler(construido, caminho)
        url = projeto.SITE + caminho.removesuffix("index.html")
        assert f'<link rel="canonical" href="{url}">' in html, caminho
        assert f'<meta property="og:url" content="{url}">' in html
        assert '<meta property="og:type" content="website">' in html and '<meta property="og:locale" content="pt_BR">' in html
        dado = jsonld(html)
        buscadores.validar(dado, url)
        assert dado["@context"] == "https://schema.org" and dado["@type"] == "Dataset" and dado["url"] == url


def test_json_ld_do_municipio_traz_fonte_licenca_periodo_e_municipio(construido):
    dado = jsonld(ler(construido, "municipio/3548500/index.html"))
    assert dado["name"] == "População de Santos (SP)"
    assert "código IBGE 3548500" in dado["description"]
    lugar = dado["spatialCoverage"]
    assert lugar["identifier"] == {"@type": "PropertyValue", "propertyID": "Código IBGE do município", "value": "3548500"}
    assert lugar["containedInPlace"]["name"] == "São Paulo"
    partes = {p["temporalCoverage"]: p for p in dado["hasPart"]}
    assert set(partes) == {"2025-12-31", "2026", "2022"}
    est = partes["2026"]
    assert est["creator"] == {"@type": "Organization", "name": "IBGE"}
    assert est["isBasedOn"] == "https://sidra.ibge.gov.br/tabela/6579"
    assert est["distribution"]["contentUrl"] == "https://apisidra.ibge.gov.br/values/t/6579/n6/3548500/v/9324/p/2026"
    assert est["variableMeasured"]["value"] == 429528 and est["variableMeasured"]["unitText"] == "pessoas"
    # A licença é a do catálogo: o IBGE não declara uma, e o JSON-LD não inventa.
    assert est["license"] == dado["license"] == {"@type": "CreativeWork", "name": "Licença não declarada na origem"}
    assert est["citation"] == "IBGE, Estimativas de População"
    assert partes["2022"]["variableMeasured"]["value"] == 418608
    assert partes["2025-12-31"]["distribution"]["contentUrl"].endswith("/2025/DTB_2025.zip")
    assert dado["dateModified"] == "2026-11-07T23:23:20Z"


def test_json_ld_sem_censo_nao_inventa_a_parte(construido):
    dado = jsonld(ler(construido, "municipio/5101837/index.html"))
    assert {p["temporalCoverage"] for p in dado["hasPart"]} == {"2025-12-31", "2026"}
    assert "Censo" not in dado["description"]


def test_json_ld_escapa_o_nome_dentro_do_script(construido):
    bloco = JSONLD.search(ler(construido, "municipio/4206504/index.html")).group(1)
    assert "<" not in bloco and ">" not in bloco and "&" not in bloco
    assert json.loads(bloco)["spatialCoverage"]["name"] == "Herval d'Oeste & <Teste>, Santa Catarina, Brasil"


def test_json_ld_da_uf_e_do_brasil(construido):
    uf = jsonld(ler(construido, "uf/sp/index.html"))
    assert uf["name"] == "Municípios de São Paulo" and uf["spatialCoverage"]["identifier"]["value"] == "35"
    assert uf["hasPart"][0]["temporalCoverage"] == "2025-12-31"
    brasil = jsonld(ler(construido, "index.html"))
    assert brasil["spatialCoverage"] == {"@type": "Country", "name": "Brasil"}
    assert {d["contentUrl"] for d in brasil["distribution"]} == {
        projeto.SITE + "dados/ibge/populacao.parquet", projeto.SITE + "dados/municipios.json"}
    assert {p["temporalCoverage"] for p in brasil["hasPart"]} == {"2025-12-31", "2026", "2022"}


def test_sitemap_tem_todas_as_paginas_e_so_elas(construido):
    urls = lastmods(construido)
    assert set(urls) == {projeto.SITE + c.removesuffix("index.html") for c in paginas(construido)}
    assert set(urls.values()) == {"2026-11-07T23:23:20Z"}
    assert ler(construido, "sitemap.xml").startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_lastmod_so_muda_onde_o_valor_mudou(tmp_path):
    saida = tmp_path / "site"
    site.construir(coleta_com_historico(), catalogo.carregar(), saida)
    urls = lastmods(saida)
    assert urls[projeto.SITE + "municipio/3548500/"] == "2026-11-15T00:47:00Z"
    assert urls[projeto.SITE + "municipio/4206504/"] == "2026-11-01T00:47:00Z"
    assert urls[projeto.SITE + "uf/sp/"] == "2026-11-01T00:47:00Z"
    assert urls[projeto.SITE] == "2026-11-15T00:47:00Z"
    assert jsonld(ler(saida, "municipio/3548500/index.html"))["dateModified"] == "2026-11-15T00:47:00Z"


def test_revisao_do_ibge_vira_ressalva_so_no_municipio_revisado(tmp_path):
    saida = tmp_path / "site"
    site.construir(coleta_com_historico(), catalogo.carregar(), saida)
    html = ler(saida, "municipio/3548500/index.html")
    # 00:47 UTC de 15/11 ainda é 14/11 em Brasília.
    assert ("Revisado pelo IBGE. A coleta de 14/11/2026 encontrou, para a estimativa de 2026, um valor diferente "
            "do que a SIDRA informava antes.") in html
    assert f'href="{projeto.REPOSITORIO}/blob/main/manifesto/ibge.json"' in html
    assert "<li>Revisado pelo IBGE: a mudança foi detectada na coleta de 14/11/2026.</li>" in html
    assert "Revisado pelo IBGE" not in ler(saida, "municipio/4206504/index.html")


def test_revisao_sem_detalhe_por_municipio_avisa_em_todas_as_paginas(tmp_path):
    geral = [{"detectada_em": "2026-11-15T00:47:00Z", "municipios": None, "sem_detalhe_porque": "o site anterior não respondeu"}]
    saida = tmp_path / "site"
    site.construir(coleta_com_historico(geral), catalogo.carregar(), saida)
    for codigo in ("3548500", "4206504", "5101837"):
        assert "não conseguiu identificar quais municípios mudaram" in ler(saida, f"municipio/{codigo}/index.html")
    assert {lastmods(saida)[projeto.SITE + f"municipio/{c}/"] for c in ("3548500", "4206504")} == {"2026-11-15T00:47:00Z"}


def test_estimativa_retirada_no_mesmo_periodo_avisa_e_muda_o_lastmod(tmp_path):
    retirada = [{"detectada_em": "2026-11-15T00:47:00Z", "sem_detalhe_porque": None,
                 "municipios": [{"codigo": "4206504", "antes": 22000, "depois": None, "variacao_pct": None}]}]
    dados = coleta_com_historico(retirada)
    next(m for m in dados["municipios"] if m["codigo"] == "4206504")["populacao_estimada"] = None
    saida = tmp_path / "site"
    site.construir(dados, catalogo.carregar(), saida)
    html = ler(saida, "municipio/4206504/index.html")
    assert "A estimativa de 2026 não traz dado para este município. A ausência não é zero." in html
    assert ("Revisado pelo IBGE. Na coleta de 14/11/2026, a SIDRA deixou de trazer este município na estimativa "
            "de 2026, que antes tinha valor.") in html
    assert lastmods(saida)[projeto.SITE + "municipio/4206504/"] == "2026-11-15T00:47:00Z"
    dado = jsonld(html)
    assert dado["dateModified"] == "2026-11-15T00:47:00Z"
    assert {p["temporalCoverage"] for p in dado["hasPart"]} == {"2025-12-31", "2022"}
    # Os outros municípios não mudaram.
    assert "Revisado pelo IBGE" not in ler(saida, "municipio/3548500/index.html")
    assert lastmods(saida)[projeto.SITE + "municipio/3548500/"] == "2026-11-01T00:47:00Z"


def test_arquivo_do_search_console_so_com_codigo(tmp_path):
    sem = tmp_path / "sem"
    site.construir(coleta(), catalogo.carregar(), sem, google=None)
    assert not list(sem.glob("google*.html"))
    com = tmp_path / "com"
    site.construir(coleta(), catalogo.carregar(), com, google="google0123456789abcdef")
    assert ler(com, "google0123456789abcdef.html") == "google-site-verification: google0123456789abcdef.html"
    assert "google0123456789abcdef" not in ler(com, "sitemap.xml")


def test_404_usa_o_caminho_do_site_e_fica_fora_dos_buscadores(construido):
    html = ler(construido, "404.html")
    assert f'<a href="{projeto.CAMINHO_DO_SITE}">página inicial</a>' in html
    assert f'href="{projeto.CAMINHO_DO_SITE}estilo.css"' in html
    assert 'rel="canonical"' not in html and "ld+json" not in html


def test_estimativa_publicada_le_o_parquet_do_site(construido):
    corpo = (construido / site.PARQUET).read_bytes()
    assert site.estimativa_publicada(corpo) == {"3548500": 429528, "4206504": 22000, "5101837": 5983}
