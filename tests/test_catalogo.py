import copy

import pytest

from pipeline import catalogo


@pytest.fixture(scope="module")
def _lido():
    return catalogo.carregar()


@pytest.fixture
def cat(_lido):
    """O catálogo do repositório, lido e validado uma vez; cada teste recebe uma cópia que pode alterar."""
    return copy.deepcopy(_lido)


def test_catalogo_do_repositorio_e_valido(cat):
    assert set(cat["metricas"]) == {"populacao_estimada", "populacao_censo", "internacoes", "dias_permanencia",
                                    "valor_total", "obitos", "taxa_internacao"}
    assert len(cat["temas"]) == 12


def test_catalogo_aponta_para_onde_o_pipeline_coleta(cat):
    from pipeline import dtb, ibge
    bases = cat["bases"]
    from pipeline import sih_coleta
    assert set(bases) == {"ibge_dtb", "ibge_estimativa", "ibge_censo_2022", "sih"}
    assert bases["ibge_dtb"]["coleta"]["origem"] == dtb.RAIZ
    assert bases["ibge_estimativa"]["coleta"]["origem"] == ibge.URL_SIDRA.format(**ibge.ESTIMATIVA)
    assert bases["ibge_censo_2022"]["coleta"]["origem"] == ibge.URL_SIDRA.format(**ibge.CENSO)
    assert bases["sih"]["coleta"]["origem"] == f"ftp://{sih_coleta.HOST}{sih_coleta.DIRETORIO}"
    assert all(b["mudanca"] == "hash_dos_valores" for n, b in bases.items() if n.startswith("ibge"))
    # Nenhuma base depende da API que não aceita o runner.
    assert "servicodados" not in str(bases)


def test_licenca_da_base_vai_para_o_json_ld_e_precisa_estar_completa(cat):
    sem = copy.deepcopy(cat)
    del sem["bases"]["ibge_dtb"]["licenca"]
    with pytest.raises(catalogo.ErroDeCatalogo, match="licenca precisa de id e atribuicao"):
        catalogo.validar(sem)
    declarada = copy.deepcopy(cat)
    declarada["bases"]["ibge_dtb"]["licenca"]["id"] = "cc-by-sa-4.0"
    with pytest.raises(catalogo.ErroDeCatalogo, match="precisa do endereço"):
        catalogo.validar(declarada)
    declarada["bases"]["ibge_dtb"]["licenca"]["url"] = "https://creativecommons.org/licenses/by-sa/4.0/"
    catalogo.validar(declarada)


def test_revisao_da_estimativa_e_regra_do_catalogo(cat):
    assert cat["bases"]["ibge_estimativa"]["revisao"] == {"acao": "marcar_revisado", "aviso_variacao_pct": 5}


def test_base_sem_origem_e_recusada(cat):
    novo = copy.deepcopy(cat)
    novo["bases"]["ibge_dtb"]["coleta"] = {}
    with pytest.raises(catalogo.ErroDeCatalogo, match="Base ibge_dtb"):
        catalogo.validar(novo)


def _estragar(cat, caminho, valor):
    novo = copy.deepcopy(cat)
    alvo = novo["metricas"]["populacao_estimada"]
    *pais, chave = caminho
    for p in pais:
        alvo = alvo[p]
    alvo[chave] = valor
    return novo


@pytest.mark.parametrize("caminho, valor, mensagem", [
    (("tema",), "esportes", "lista fixa"),
    (("etiquetas",), ["populacao"], "repetir"),
    (("etiquetas",), ["clima"], "etiquetas"),
    (("fonte", "acesso", "tipo"), "link", "acesso.tipo"),
    (("fonte", "acesso", "tipo"), "receita", "receita"),
    (("fonte", "acesso", "url"), "", "sem url"),
    (("ressalvas",), [], "ressalvas"),
    (("base",), "inexistente", "não existe"),
])
def test_catalogo_recusa_regra_quebrada(cat, caminho, valor, mensagem):
    with pytest.raises(catalogo.ErroDeCatalogo, match=mensagem):
        catalogo.validar(_estragar(cat, caminho, valor))


def test_metrica_calculada_lista_as_parcelas(cat):
    novo = copy.deepcopy(cat)
    novo["metricas"]["crescimento"] = {"tema": "populacao", "etiquetas": [], "rotulo": "Crescimento",
                                       "formula": "populacao_estimada / populacao_censo - 1",
                                       "fontes": ["populacao_estimada", "populacao_censo"]}
    catalogo.validar(novo)
    novo["metricas"]["crescimento"]["fontes"] = ["populacao_estimada", "inexistente"]
    with pytest.raises(catalogo.ErroDeCatalogo, match="calculada"):
        catalogo.validar(novo)


@pytest.mark.parametrize("valor", [None, 0, -1, "100", True])
def test_limite_de_pagina_precisa_ser_numero_positivo(cat, valor):
    novo = copy.deepcopy(cat)
    novo["limites"]["pagina_html_kb"] = valor
    with pytest.raises(catalogo.ErroDeCatalogo, match="limites.pagina_html_kb"):
        catalogo.validar(novo)


def test_limite_de_pagina_e_100_kb(cat):
    assert cat["limites"] == {"pagina_html_kb": 100, "arquivo_mib": 25}


def test_sih_fica_fora_do_site_ate_o_ok_e_nunca_vai_para_releases(cat):
    assert cat["bases"]["sih"]["publicacao"] == {"site": False}
    novo = copy.deepcopy(cat)
    novo["bases"]["sih"]["publicacao"]["releases"] = False
    with pytest.raises(catalogo.ErroDeCatalogo, match="publicacao só aceita site"):
        catalogo.validar(novo)


def test_superficie_e_o_que_a_pagina_mostra(cat):
    sup = cat["bases"]["sih"]["superficie"]
    assert sup["arquivo"] == "dados/sih/superficie.parquet"
    assert sup["cruzamentos"] == {
        "sih_res_ano": {"medidas": ["internacoes", "obitos"]}, "sih_hosp_ano": {"medidas": ["internacoes"]},
        "sih_res_mes": {"medidas": ["internacoes"]},
        "sih_res_ano_capitulo": {"medidas": ["internacoes"], "anos_recentes": 2},
        "sih_res_ano_faixa12_sexo": {"medidas": ["internacoes"], "anos_recentes": 2}}
    assert cat["bases"]["sih"]["versoes"]["motores"] == ["intervalos", "programacao_linear"]


@pytest.mark.parametrize("mudanca, mensagem", [
    (lambda s: s.update(arquivo="/dados/sih.parquet"), "caminho .parquet relativo"),
    (lambda s: s.update(arquivo="../fora.parquet"), "caminho .parquet relativo"),
    (lambda s: s["cruzamentos"].update(sih_inventado={"medidas": ["internacoes"]}), "fora do catálogo"),
    (lambda s: s["cruzamentos"]["sih_res_mes"].update(medidas=["obitos"]), "só mostra contagens"),
    (lambda s: s["cruzamentos"]["sih_res_ano"].update(medidas=["dias_permanencia"]), "só mostra contagens"),
    (lambda s: s["cruzamentos"]["sih_res_ano_capitulo"].update(anos_recentes=0), "anos_recentes"),
    (lambda s: s["cruzamentos"]["sih_res_ano"].update(cor="verde"), "só aceita medidas"),
])
def test_superficie_quebrada_e_recusada(cat, mudanca, mensagem):
    novo = copy.deepcopy(cat)
    mudanca(novo["bases"]["sih"]["superficie"])
    with pytest.raises(catalogo.ErroDeCatalogo, match=mensagem):
        catalogo.validar(novo)


@pytest.mark.parametrize("motores", [[], ["intervalos", "intervalos"], ["outro"], "intervalos"])
def test_motor_do_ataque_conjunto_fora_da_lista_e_recusado(cat, motores):
    novo = copy.deepcopy(cat)
    novo["bases"]["sih"]["versoes"]["motores"] = motores
    with pytest.raises(catalogo.ErroDeCatalogo, match="versoes.motores"):
        catalogo.validar(novo)


def test_capitulos_da_cid_cobrem_as_categorias_sem_sobrepor(cat):
    faixas = cat["referencias"]["cid10_capitulos"]["faixas"]
    assert [f[0] for f in faixas] == list(range(1, 23))
    novo = copy.deepcopy(cat)
    novo["referencias"]["cid10_capitulos"]["faixas"][1][1] = "B50"   # capítulo II começando dentro do I
    with pytest.raises(catalogo.ErroDeCatalogo, match="Capítulo 2"):
        catalogo.validar(novo)


@pytest.mark.parametrize("mudanca, mensagem", [
    (lambda c: c["cruzamentos"][4].update(mae="sih_res_mes_faixa5"), "precisa vir antes"),
    (lambda c: c["cruzamentos"][4].update(mae="sih_hosp_mes"), "precisa ser uma soma"),
    (lambda c: c["cruzamentos"][4].update(tempo="semana"), "tempo deve ser"),
    (lambda c: c["cruzamentos"][4].update(dimensoes=["municipio_residencia", "escolaridade"]), "dimensão fora"),
    (lambda c: c["cruzamentos"][10].update(herda_trimestre_de="sih_hosp_mes"), "mesmo município"),
    (lambda c: c["cruzamentos"].append(dict(c["cruzamentos"][0])), "repetido"),
    (lambda c: c["margens_publicadas"]["internacoes"].append(["uf_res", "escolaridade"]), "fora das dimensões"),
    (lambda c: c["bases"]["sih"]["revisao"]["municipio"].update(queda_pct=0), "trava de queda"),
    (lambda c: c["bases"]["sih"]["supressao"].update(k=1), "supressao.k"),
])
def test_cruzamento_quebrado_e_recusado(cat, mudanca, mensagem):
    novo = copy.deepcopy(cat)
    mudanca(novo)
    with pytest.raises(catalogo.ErroDeCatalogo, match=mensagem):
        catalogo.validar(novo)
