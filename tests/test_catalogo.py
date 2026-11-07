import copy

import pytest

from pipeline import catalogo


@pytest.fixture
def cat():
    return catalogo.carregar()


def test_catalogo_do_repositorio_e_valido(cat):
    assert set(cat["metricas"]) == {"populacao_estimada", "populacao_censo"}
    assert len(cat["temas"]) == 12


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
