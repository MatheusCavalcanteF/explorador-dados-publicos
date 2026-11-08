import numpy as np
import pytest

pd = pytest.importorskip("pandas")
duckdb = pytest.importorskip("duckdb")

from pipeline import catalogo, deducao, sih_deducao, sih_tabelas as tab, supressao  # noqa: E402


@pytest.fixture(scope="module")
def cat():
    return catalogo.carregar()


def aihs_sinteticas(n=4000, semente=7, ano=2025):
    """AIHs inventadas no formato do Parquet mínimo: 2 UFs, municípios grandes e pequenos."""
    rng = np.random.default_rng(semente)
    municipios = [f"35{i:04d}" for i in range(10)] + [f"41{i:04d}" for i in range(6)]
    peso = np.array([60, 30, 10, 5, 3, 2, 1, 1, 1, 1, 40, 20, 5, 2, 1, 1], dtype=float)
    res = rng.choice(municipios, size=n, p=peso / peso.sum())
    hosp = np.where(rng.random(n) < 0.7, res, rng.choice(municipios[:2] + municipios[10:11], size=n))
    dia = rng.integers(1, 29, size=n)
    mes = rng.integers(1, 13, size=n)
    return pd.DataFrame({
        "competencia": ano * 100 + mes, "ident": np.where(rng.random(n) < 0.02, 5, 1).astype(np.int8),
        "cnes": "0000001", "mun_hosp": hosp, "mun_res": res,
        "cid3": rng.choice(["I10", "J18", "O80", "S72", "U07", "A09"], size=n),
        "dt_inter": ano * 10000 + mes * 100 + dia, "dt_saida": ano * 10000 + mes * 100 + dia,
        "dias": rng.integers(0, 10, size=n), "valor": rng.random(n) * 1000, "morte": (rng.random(n) < 0.04).astype(np.int8),
        "espec": rng.choice(["01", "02", "03"], size=n), "car_int": rng.choice(["01", "02", "02", "05"], size=n),
        "sexo": rng.choice(["1", "3"], size=n), "idade": rng.integers(0, 99, size=n),
        "cod_idade": rng.choice(["4", "4", "4", "2"], size=n), "raca": rng.choice(["01", "03", "99"], size=n),
    })


@pytest.fixture(scope="module")
def ano_montado(cat):
    con = duckdb.connect()
    con.register("aih", aihs_sinteticas())
    publicados = sih_deducao.nos_publicados(cat)
    base = tab.calcular_base(con, "aih", 2025, publicados, cat)
    nos = tab.montar(base, publicados)
    return nos, publicados


def test_fechamento_sobe_cada_nivel_e_junta_residencia_e_hospital_no_brasil():
    fecho = set(tab.fechamento([("mun_res", "mes", "sexo"), ("mun_hosp", "mes")]))
    for n in [("uf_res", "mes", "sexo"), ("mun_res", "tri", "sexo"), ("mun_res", "sexo"), ("mun_res", "mes"),
              ("sexo",), ("mes",), (), ("uf_hosp", "tri"), ("tri",)]:
        assert tab.no(n) in fecho
    assert ("uf_res", "uf_hosp") not in fecho
    assert len([n for n in fecho if n == ()]) == 1


def test_faixas_de_5_cabem_nas_de_12_e_carater_nas_de_urgencia(cat):
    faixa12 = cat["dimensoes"]["faixa_12"]["valores"]
    assert set(tab.FAIXA5_DE_FAIXA12) == set(faixa12)
    assert set(tab.FAIXA5_DE_FAIXA12.values()) == set(cat["dimensoes"]["faixa_5"]["valores"])
    assert set(tab.URGENCIA_DE_CARATER.values()) == set(cat["dimensoes"]["urgencia"]["valores"])
    # Os níveis do código são os do catálogo.
    for d in cat["dimensoes"].values():
        familia = tab.FAMILIA[d["niveis"][0]]
        assert tab.NIVEIS[familia][-len(d["niveis"]):] == d["niveis"] or tab.NIVEIS[familia][:len(d["niveis"])] == d["niveis"]


def test_mes_vira_trimestre_e_municipio_vira_uf():
    s = pd.Series(["202501", "202504", "202512"])
    assert list(tab.converter_coluna(s, "mes", "tri")) == ["2025T1", "2025T2", "2025T4"]
    assert list(tab.converter_coluna(pd.Series(["350010"]), "mun_res", "uf_res")) == ["35"]


def test_soma_derivada_bate_com_a_contagem_direta(cat, ano_montado):
    nos, _ = ano_montado
    con = duckdb.connect()
    con.register("aih", aihs_sinteticas())
    direto = tab.calcular_base(con, "aih", 2025, [("mun_res", "tri"), ("uf_hosp",), ()], cat)
    for n, df in direto.items():
        pd.testing.assert_frame_equal(nos[n][df.columns].reset_index(drop=True), df.reset_index(drop=True),
                                      check_dtype=False, check_exact=False)


def test_capitulo_da_cid_sai_das_faixas_do_catalogo(cat):
    con = duckdb.connect()
    linhas = aihs_sinteticas(50)
    linhas["cid3"] = ["U07", "U02", "A09", "Z99", "V01"] * 10
    con.register("aih", linhas)
    cap = tab.calcular_base(con, "aih", 2025, [("capitulo",)], cat)[("capitulo",)]
    assert dict(zip(cap["capitulo"], cap["aihs"])) == {"00": 10, "01": 10, "20": 10, "21": 10, "22": 10}


def test_familia_esconde_as_filhas_e_o_trimestre(cat, ano_montado):
    nos, _ = ano_montado
    sup = supressao.suprimir(nos, cat, 5)
    mae = sup["sih_res_mes"].set_index(["mun_res", "mes"])["oculto"]
    filha = sup["sih_res_mes_sexo"]
    herda = filha.join(mae.rename("mae_oculta"), on=["mun_res", "mes"])
    assert herda.loc[herda["mae_oculta"], "oculto"].all()
    assert (herda.loc[herda["mae_oculta"], "estado"] != deducao.VISIVEL).all()
    # Trimestre: se um mês do município está oculto, os capítulos daquele trimestre também.
    mensal = sup["sih_res_mes"]
    tri_oculto = set(zip(mensal.loc[mensal["oculto"], "mun_res"],
                         tab.converter_coluna(mensal.loc[mensal["oculto"], "mes"], "mes", "tri")))
    tri = sup["sih_res_tri_capitulo"]
    marcado = [(m, t) in tri_oculto for m, t in zip(tri["mun_res"], tri["tri"])]
    assert tri.loc[marcado, "oculto"].all() and any(marcado)


def test_nenhuma_contagem_pequena_fica_visivel(cat, ano_montado):
    nos, _ = ano_montado
    for nome, df in supressao.suprimir(nos, cat, 5).items():
        pequena = supressao.pequena(df["internacoes"].to_numpy(), 5) | supressao.pequena(df["aihs"].to_numpy(), 5)
        assert df.loc[pequena, "oculto"].all(), nome
        assert set(df.loc[pequena, "estado"]) <= {deducao.PEQUENA}, nome


def test_filha_unica_de_mae_visivel_nao_vira_complementar():
    primaria = np.array([True, False, False])
    linhas = [np.array([0, 0, 1])]          # a terceira célula é sozinha na linha
    medidas = [np.array([3, 9, 20]), np.array([3, 9, 20])]
    oculto = supressao.complementar(primaria, linhas, medidas, 5, inelegivel=np.array([False, True, False]))
    assert not oculto[1]                    # a única candidata está bloqueada; a linha segue arriscada


def test_complementar_esconde_a_menor_visivel_da_linha():
    oculto = supressao.complementar(np.array([True, False, False, False]), [np.zeros(4, dtype=int)],
                                    [np.array([2, 50, 7, 9])], 5)
    assert list(oculto) == [True, False, True, False]


def test_teste_de_deducao_do_ano_sintetico_e_solido(cat, ano_montado):
    nos, publicados = ano_montado
    sup = supressao.suprimir(nos, cat, 5)
    estados = sih_deducao.estados_publicados(nos, sup, cat, 5)
    r = sih_deducao.auditar(sih_deducao.sistema(nos, estados, publicados, 5))
    assert r["voltas"] >= 1 and set(r) >= {"pequenas_reveladas", "pequenas_estreitadas"}


def test_arredondamento_esconde_meia_base_para_cada_lado():
    valores = np.array([5, 7, 8, 12, 13, 3])
    estado = np.array([0, 0, 0, 0, 0, deducao.PEQUENA])
    lo, hi = sih_deducao.dominio_arredondado(valores, estado, np.ones(6, dtype=bool), 5, 5)
    assert list(sih_deducao.arredondar(valores[:5], 5)) == [5, 5, 10, 10, 15]
    assert list(lo[:5]) == [5, 5, 8, 8, 13] and list(hi[:5]) == [7, 7, 12, 12, 17]
    assert (lo[:5] <= valores[:5]).all() and (valores[:5] <= hi[:5]).all()
    assert (lo[5], hi[5]) == (0, 4)
