import pytest

pd = pytest.importorskip("pandas")

from pipeline import catalogo, sih_trava  # noqa: E402

REVISAO = catalogo.carregar()["bases"]["sih"]["revisao"]


def tabela(linhas):
    return pd.DataFrame(linhas, columns=["mun_res", "mes", "internacoes", "oculto"])


def test_queda_grande_em_municipio_grande_marca_em_revisao():
    antes = tabela([("354780", "202605", 3616, False), ("354850", "202605", 900, False), ("350010", "202605", 120, False)])
    depois = tabela([("354780", "202605", 1269, False), ("354850", "202605", 880, False), ("350010", "202605", 60, False)])
    marcadas = sih_trava.municipio(antes, depois, ["mun_res", "mes"], REVISAO["municipio"])
    assert list(marcadas["mun_res"]) == ["350010", "354780"]
    assert round(marcadas.loc[marcadas["mun_res"] == "354780", "queda_pct"].iloc[0], 1) == 64.9


def test_municipio_pequeno_ou_celula_oculta_nao_aciona():
    antes = tabela([("350020", "202605", 99, False), ("350030", "202605", 500, True)])
    depois = tabela([("350020", "202605", 10, False), ("350030", "202605", 10, False)])
    assert sih_trava.municipio(antes, depois, ["mun_res", "mes"], REVISAO["municipio"]).empty


def test_queda_de_5_por_cento_numa_uf_e_falha_estrutural():
    antes = {"SP/202605": 250_000, "RR/202605": 3000, "AC/202604": 4000}
    depois = {"SP/202605": 249_000, "RR/202605": 2800}
    falhas = sih_trava.publicacao(antes, depois, REVISAO["publicacao"])
    assert any(f.startswith("RR/202605: internações caíram 6.7%") for f in falhas)
    assert any(f.startswith("AC/202604: competência publicada antes não está") for f in falhas)
    assert not any(f.startswith("SP/") for f in falhas)
