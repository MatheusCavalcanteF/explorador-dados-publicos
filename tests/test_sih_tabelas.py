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


def test_cada_aih_cai_no_mes_da_alta_e_os_tres_eixos_fecham(cat):
    # AIHs inventadas com processamento tardio: internação num mês, alta no seguinte, competência depois.
    linhas = aihs_sinteticas(600, semente=11)
    rng = np.random.default_rng(3)
    mes_alta = rng.integers(1, 13, size=len(linhas))
    atraso = rng.integers(0, 6, size=len(linhas))
    linhas["dt_saida"] = 2025 * 10000 + mes_alta * 100 + 15
    inter = [2025 * 12 + m - 1 - d for m, d in zip(mes_alta, rng.integers(0, 2, size=len(linhas)))]  # mesmo mês ou o anterior
    linhas["dt_inter"] = [(n // 12) * 10000 + (n % 12 + 1) * 100 + 10 for n in inter]
    linhas["competencia"] = [((2025 * 12 + m - 1 + a) // 12) * 100 + (2025 * 12 + m - 1 + a) % 12 + 1
                             for m, a in zip(mes_alta, atraso)]
    con = duckdb.connect()
    con.register("aih", linhas)
    por_mes = tab.calcular_base(con, "aih", 2025, [("mes",)], cat)[("mes",)]
    esperado = linhas[linhas["ident"] == 1].groupby(linhas["dt_saida"] // 100).size()
    assert dict(zip(por_mes["mes"].astype(int), por_mes["internacoes"])) == esperado.to_dict()
    # O mesmo conjunto de AIHs, contado pelos três eixos, dá o mesmo total.
    total = int(por_mes["internacoes"].sum())
    pela_competencia = con.execute("SELECT count(*) FILTER (WHERE ident = 1) FROM aih GROUP BY competencia").fetchall()
    pela_internacao = con.execute("SELECT count(*) FILTER (WHERE ident = 1) FROM aih GROUP BY dt_inter // 100").fetchall()
    assert total == sum(n for (n,) in pela_competencia) == sum(n for (n,) in pela_internacao)
    # E o eixo não é o da competência nem o da internação: os meses diferem.
    por_competencia = dict(con.execute("SELECT competencia, count(*) FILTER (WHERE ident = 1) FROM aih GROUP BY 1").fetchall())
    assert dict(zip(por_mes["mes"].astype(int), por_mes["internacoes"])) != por_competencia


def test_particao_leva_so_as_metricas_do_catalogo_e_oculta_como_nulo(cat, ano_montado, tmp_path):
    import pyarrow.parquet as pq

    from pipeline import sih
    nos, _ = ano_montado
    sup = supressao.suprimir(nos, cat, 5)
    for c in cat["cruzamentos"]:
        if "obitos" in c["metricas"]:
            n = tab.colunas_de(c, cat)
            sup[c["id"]]["estado_obitos"] = supressao.suprimir_obitos(nos[n], n, 5)
    municipios7 = {m: m + "0" for m in set(nos[("mun_res",)]["mun_res"]) | set(nos[("mun_hosp",)]["mun_hosp"])}
    # Julho a dezembro preliminares: o mês, o trimestre dele e o ano inteiro saem arredondados.
    prelim = {f"2025{m:02d}" for m in range(7, 13)}
    sih.gravar_particao(sup, 2025, tmp_path, municipios7, False, {c["id"]: c["metricas"] for c in cat["cruzamentos"]},
                        prelim, 5, 5, ("internacoes", "obitos"))
    filha = pq.read_table(tmp_path / "sih_res_mes_sexo" / "uf=35" / "ano=2025.parquet").to_pandas()
    assert set(filha.columns) == {"mun_res", "mes", "sexo", "internacoes", "oculto", "preliminar", "arredondado"}
    assert filha.loc[filha["oculto"], "internacoes"].isna().all() and filha["mun_res"].str.len().eq(7).all()
    mae = pq.read_table(tmp_path / "sih_res_ano" / "uf=35" / "ano=2025.parquet").to_pandas()
    assert {"internacoes", "dias", "valor", "obitos", "obitos_oculto", "obitos_arredondado"} <= set(mae.columns)
    assert "aihs" not in mae.columns and "motivo" not in mae.columns and "publicado" not in mae.columns
    # Preliminar visível sai em múltiplo de 5 e marcado; o mês fechado sai exato; oculta continua nula.
    mensal = pq.read_table(tmp_path / "sih_res_mes" / "uf=35" / "ano=2025.parquet").to_pandas()
    original = sup["sih_res_mes"].assign(mun_res=lambda d: d["mun_res"] + "0").set_index(["mun_res", "mes"])["internacoes"]
    mensal = mensal.join(original.rename("exato"), on=["mun_res", "mes"])
    aberto = mensal["mes"].isin(prelim)
    assert (mensal["preliminar"] == aberto).all()
    arred = mensal.loc[mensal["arredondado"]]
    assert len(arred) and (arred["internacoes"] % 5 == 0).all() and ((arred["internacoes"] - arred["exato"]).abs() <= 2).all()
    assert (mensal["arredondado"] == (aberto & ~mensal["oculto"] & (mensal["exato"] >= 5))).all()
    fechado = mensal.loc[~aberto & ~mensal["oculto"]]
    assert (fechado["internacoes"] == fechado["exato"]).all()
    assert mae["preliminar"].all() and (mae.loc[mae["arredondado"], "internacoes"] % 5 == 0).all()
    assert (mae.loc[mae["obitos_arredondado"], "obitos"] % 5 == 0).all()


def test_trimestre_sem_os_tres_meses_nao_sai_mas_e_protegido(cat, ano_montado, tmp_path):
    import pyarrow.parquet as pq

    from pipeline import sih
    nos, publicados = ano_montado
    # Base até agosto: o 3º trimestre tem só julho e agosto, e o 4º nenhum mês.
    sup = supressao.suprimir(nos, cat, 5, ultimo_mes=202508)
    tri = sup["sih_res_tri_capitulo"]
    assert (tri["publicado"] == tri["tri"].isin(["2025T1", "2025T2"])).all() and (~tri["publicado"]).any()
    # Fica de fora do arquivo e do resumo, e o teste o vê como incógnita.
    municipios7 = {m: m + "0" for m in set(nos[("mun_res",)]["mun_res"]) | set(nos[("mun_hosp",)]["mun_hosp"])}
    sih.gravar_particao({"sih_res_tri_capitulo": tri}, 2025, tmp_path, municipios7, False)
    lido = pq.read_table(tmp_path / "sih_res_tri_capitulo" / "uf=35" / "ano=2025.parquet").to_pandas()
    assert set(lido["tri"]) <= {"2025T1", "2025T2"}
    assert sih.resumo_supressao({"t": tri})["t"]["linhas"] == int(tri["publicado"].sum())
    estados = sih_deducao.estados_publicados(nos, sup, cat, 5)
    n = tab.colunas_de(next(c for c in cat["cruzamentos"] if c["id"] == "sih_res_tri_capitulo"), cat)
    assert (estados[n][~tri["publicado"].to_numpy()] == deducao.LIVRE).all()
    # A contagem pequena do trimestre incompleto continua oculta, e ele nunca serve de complementar.
    pequeno = ~tri["publicado"] & (tri["internacoes"].between(1, 4) | tri["aihs"].between(1, 4))
    assert tri.loc[pequeno, "oculto"].all()
    assert not (tri["estado"].eq(deducao.COMPLEMENTAR) & ~tri["publicado"]).any()


def test_criterio_tira_o_cruzamento_e_o_que_depende_dele(cat, ano_montado, monkeypatch):
    from pipeline import sih
    nos, _ = ano_montado
    chamadas = []

    def sem_teste(nos, catalogo, k, motivo, max_rodadas, arredondamento=None, ultimo_mes=None, fixas=None):
        # Só a supressão: aqui interessa o critério, não o reforço, que tem testes próprios.
        chamadas.append([c["id"] for c in catalogo["cruzamentos"]])
        return {"suprimidas": supressao.suprimir(nos, catalogo, k, ultimo_mes=ultimo_mes), "auditoria": {}, "passou": True}
    monkeypatch.setattr(sih_deducao, "suprimir_ate_passar", sem_teste)
    limite = cat["bases"]["sih"]["supressao"] | {"criterio_publicacao": {"internacoes_ocultas_pct_max": 100,
                                                                        "celulas_ocultas_pct_max": 10}}
    estrito = cat | {"bases": cat["bases"] | {"sih": cat["bases"]["sih"] | {"supressao": limite}}}
    r = sih.suprimir_publicaveis(nos, estrito, 5)
    fora = r["nao_publicados"]
    reprovados = {cid for cid, v in fora.items() if not v["motivo"].startswith("depende de")}
    assert reprovados and all("das células ficariam ocultas (limite: 10%)" in fora[c]["motivo"] for c in reprovados)
    assert set(r["suprimidas"]) == {c["id"] for c in r["catalogo"]["cruzamentos"]} and not set(fora) & set(r["suprimidas"])
    # A segunda volta refaz a supressão sem os reprovados, e o que depende deles sai junto.
    assert len(chamadas) >= 2 and not set(chamadas[-1]) & set(fora)
    for cid in fora:
        assert set(sih.dependentes(cat, cid)) <= set(fora)
    assert set(sih.dependentes(cat, "sih_res_mes")) == {"sih_res_mes_sexo", "sih_res_mes_urgencia", "sih_res_mes_faixa5",
                                                         "sih_res_tri_capitulo"}


def test_sexo_fora_do_dicionario_vai_para_ignorado_como_no_tabwin(cat):
    con = duckdb.connect()
    linhas = aihs_sinteticas(40)
    linhas["sexo"] = ["1", "2", "3", "4", "0"] * 8
    con.register("aih", linhas)
    sexo = tab.calcular_base(con, "aih", 2025, [("sexo",)], cat)[("sexo",)]
    assert dict(zip(sexo["sexo"], sexo["aihs"])) == {"M": 8, "F": 16, "I": 16}
    assert set(cat["dimensoes"]["sexo"]["fora_do_dicionario"]["4"]) == {"visto", "documentacao", "tratamento"}


def test_periodo_fechado_herda_o_padrao_da_versao_anterior(cat, ano_montado):
    from pipeline import sih
    nos, _ = ano_montado
    antes = supressao.suprimir(nos, cat, 5)
    # A versão anterior mostrou janeiro a junho exatos e o resto arredondado. Fecha até junho.
    anterior = {}
    for c in cat["cruzamentos"]:
        df = antes[c["id"]]
        n = tab.colunas_de(c, cat)
        aberto = sih_deducao.periodo_aberto(df, n, 2025, {f"2025{m:02d}" for m in range(7, 13)})
        anterior[c["id"]] = df[list(n) + ["oculto"]].assign(arredondado=~df["oculto"].to_numpy() & aberto)
    # Uma célula fechada que estava oculta lá e não seria oculta agora: a herança a mantém oculta.
    mensal = anterior["sih_res_mes"]
    alvo = mensal.index[(~mensal["oculto"]) & (mensal["mes"] <= "202506")][0]
    anterior["sih_res_mes"].loc[alvo, "oculto"] = True
    fixas = sih.fixas_da_anterior(nos, cat, anterior, 2025, 202506)
    depois = supressao.suprimir(nos, cat, 5, fixas=fixas)
    assert depois["sih_res_mes"].loc[alvo, "oculto"]
    for cid, (ocultas, travadas) in fixas.items():
        assert depois[cid]["oculto"].to_numpy()[ocultas].all(), cid
        # Visível e exata na anterior, num período fechado: nunca vira complementar.
        assert not (depois[cid]["estado"].to_numpy()[travadas] == deducao.COMPLEMENTAR).any(), cid
    # Período aberto não herda nada.
    aberto = sih_deducao.periodo_aberto(antes["sih_res_mes"], ("mun_res", "mes"), 2025, {f"2025{m:02d}" for m in range(7, 13)})
    assert not (fixas["sih_res_mes"][0] | fixas["sih_res_mes"][1])[aberto].any()
