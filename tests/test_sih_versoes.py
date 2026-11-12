"""Ataque conjunto com a versão no ar e o ciclo de publicação do SIH, com AIHs inventadas."""
import copy
import json
import re
import shutil
import sys

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
duckdb = pytest.importorskip("duckdb")
pytest.importorskip("scipy")

import pyarrow as pa  # noqa: E402
from conftest import site_falso  # noqa: E402
from test_sih_tabelas import aihs_sinteticas  # noqa: E402

from pipeline import __main__ as cli  # noqa: E402
from pipeline import catalogo, deducao, projeto, sih, sih_janela, sih_superficie, sih_versoes  # noqa: E402

INF = deducao.INF
CRUZAMENTOS = ("sih_res_ano", "sih_res_mes", "sih_res_mes_sexo")
# Os dois da superfície entre os três acima: mês x sexo não aparece na página.
NA_TELA = ["sih_res_ano", "sih_res_mes"]
MOTORES = ["intervalos", "programacao_linear"]


def versao(rotulo, celulas, total, publicados=("celulas", "total")):
    """Uma tabela de duas células e o total dela. None é célula sem valor à vista."""
    def lados(valores):
        return (np.array([0 if v is None else v for v in valores], np.int64),
                np.array([INF if v is None else v for v in valores], np.int64), np.array([v is None for v in valores]))
    (lo_c, hi_c, esc_c), (lo_t, hi_t, esc_t) = lados(celulas), lados([total])
    return sih_versoes.Versao(rotulo, {"celulas": lo_c, "total": lo_t}, {"celulas": hi_c, "total": hi_t},
                              {"celulas": esc_c, "total": esc_t}, frozenset(publicados))


def problema(no_ar, candidata, iguais=True):
    mascaras = [(0, 1, "celulas", np.ones(2, bool)), (0, 1, "total", np.ones(1, bool))] if iguais else []
    return sih_versoes.Problema(5, "internacoes", [no_ar, candidata], [("celulas", "total", np.zeros(2, np.int64))], mascaras)


@pytest.mark.parametrize("motor", MOTORES)
def test_duas_versoes_juntas_revelam_o_que_nenhuma_revela_sozinha(motor):
    # No ar: as duas células ocultas e o total 12. Candidata: uma célula vira 9, e o total deixa de aparecer.
    no_ar, candidata = versao("no ar", [None, None], 12), versao("candidata", [None, 9], None)
    sozinhas = sih_versoes.atacar(problema(no_ar, candidata, iguais=False), motor)
    assert sozinhas.total == 0 and sozinhas.reveladas == [{}, {}]
    # O período já fechou, então as células valem o mesmo nas duas: 12 - 9 = 3, em qualquer das versões.
    juntas = sih_versoes.atacar(problema(no_ar, candidata), motor)
    assert juntas.reveladas == [{"celulas": 1}, {"celulas": 1}] and juntas.total == 2 and juntas.motor == motor


@pytest.mark.parametrize("motor", MOTORES)
def test_diferenca_exata_de_1_a_4_entre_as_versoes_conta(motor):
    # Período aberto, valores exatos nas duas: quem guardou as versões vê que a célula subiu 2.
    r = sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [9, 20], 29), iguais=False), motor)
    assert r.reveladas == [{}, {}] and r.diferencas == {"0-1": {"celulas": 1, "total": 1}} and r.total == 2
    # Subir 13 não é contagem pequena.
    assert sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [20, 20], 40), iguais=False), motor).total == 0


@pytest.mark.parametrize("motor", MOTORES)
def test_versoes_que_nao_fecham_entre_si_param_com_erro(motor):
    # Período fechado com valores diferentes nas duas versões: uma delas não é verdadeira.
    with pytest.raises(sih_versoes.ErroDeVersoes, match="não fecham entre si"):
        sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [9, 20], 29)), motor)


def test_motor_desconhecido_ou_sem_dependencia_nao_conta_como_aprovado(monkeypatch):
    p = problema(versao("no ar", [7, 20], 27), versao("candidata", [7, 20], 27))
    with pytest.raises(sih_versoes.ErroDeVersoes, match="Motor do ataque conjunto desconhecido: 'outro'"):
        sih_versoes.atacar(p, motor="outro")
    monkeypatch.setitem(sys.modules, "scipy", None)
    with pytest.raises(sih_versoes.ErroDeVersoes, match="programacao_linear não pôde rodar"):
        sih_versoes.atacar(p, motor="programacao_linear")
    assert set(sih_versoes.MOTORES) == catalogo.MOTORES_DO_ATAQUE


def quatro_contagens_de_3():
    """Quatro células ocultas, as três partições delas em pares (cada par soma 6) e o total 12, tudo visível.

    Só há uma solução: as quatro valem 3. Cada soma sozinha deixa cada célula entre 0 e 6."""
    nos = {"celulas": ([None] * 4, None), "a": ([6, 6], [0, 0, 1, 1]), "b": ([6, 6], [0, 1, 0, 1]),
           "c": ([6, 6], [0, 1, 1, 0]), "total": ([12], [0, 0, 0, 0])}
    lo = {n: np.array([0 if x is None else x for x in v], np.int64) for n, (v, _) in nos.items()}
    hi = {n: np.array([INF if x is None else x for x in v], np.int64) for n, (v, _) in nos.items()}
    esc = {n: np.array([x is None for x in v]) for n, (v, _) in nos.items()}
    arestas = [("celulas", n, np.array(idx, np.int64)) for n, (_, idx) in nos.items() if idx is not None]
    valor = {"celulas": np.full(4, 3), "a": np.array([6, 6]), "b": np.array([6, 6]), "c": np.array([6, 6]), "total": np.array([12])}
    return sih_versoes.Problema(5, "internacoes", [sih_versoes.Versao("no ar", lo, hi, esc, frozenset(nos) - {"celulas"}, valor)],
                                arestas, [])


def test_quatro_contagens_de_3_so_a_programacao_linear_acha():
    p = quatro_contagens_de_3()
    # Os intervalos ficam em 0 a 6 e não revelam nada; a programação linear fixa as quatro em 3.
    assert sih_versoes.atacar(p, "intervalos").total == 0
    r = sih_versoes.atacar(p, "programacao_linear")
    assert r.reveladas == [{"celulas": 4}] and r.total == 4 and r.inconclusivas == 0
    # Com uma das somas em pares oculta, há outras soluções, e nenhum dos dois motores revela nada.
    p.versoes[0].lo["c"][:] = 0
    p.versoes[0].hi["c"][:] = INF
    p.versoes[0].escondida["c"][:] = True
    assert sih_versoes.atacar(p, "programacao_linear").total == 0 == sih_versoes.atacar(p, "intervalos").total


def test_programacao_linear_confere_que_o_valor_verdadeiro_cabe_no_problema():
    p = quatro_contagens_de_3()
    p.versoes[0].valor["total"] = np.array([13])
    with pytest.raises(AssertionError, match="fora do intervalo da tela"):
        sih_versoes.atacar(p, "programacao_linear")
    p = quatro_contagens_de_3()
    p.versoes[0].valor["celulas"] = np.array([3, 3, 3, 4])
    with pytest.raises(AssertionError, match="a não é a soma de celulas"):
        sih_versoes.atacar(p, "programacao_linear")


def test_amostra_fracionaria_nao_descarta_o_que_os_extremos_revelam():
    """Regressão do apontamento da revisão de 11/11/2026: x+y=2, x+z=2 e y+z+w=3, com 0<=w<=1 e o resto >= 0.

    Minimizar x+y+z+w dá a amostra (0,5; 1,5; 1,5; 0). No contínuo, x fica em [0,5; 1] e y e z em [1; 1,5]:
    arredondados para dentro, os três ficam em 1, revelados. w fica em [0; 1] e não é revelado."""
    from pipeline import deducao_lp
    amostra = np.array([0.5, 1.5, 1.5, 0.0])
    # A amostra só descarta quando não sobra inteiro de 1 a k-1 entre o abaixo do máximo e o acima do mínimo:
    # x tem 1 entre 0 e 1, y e z têm 1 e 2 entre 1 e 2; w, entre 0 e 0, nenhum.
    vivas = deducao_lp._possivel(deducao_lp._abaixo(amostra), deducao_lp._acima(amostra), 5, np.zeros(4, bool))
    assert vivas.tolist() == [True, True, True, False]
    # As três somas como partições das células x, y, z, w; a outra parte de cada partição fica escondida.
    inf = deducao_lp.INF
    lo = {"celulas": np.zeros(4, np.int64), "a": np.array([2, 0]), "b": np.array([2, 0]), "c": np.array([3, 0])}
    hi = {"celulas": np.array([inf, inf, inf, 1]), "a": np.array([2, inf]), "b": np.array([2, inf]),
          "c": np.array([3, inf])}
    arestas = [("celulas", "a", np.array([0, 0, 1, 1])), ("celulas", "b", np.array([0, 1, 0, 1])),
               ("celulas", "c", np.array([1, 0, 0, 0]))]
    linhas = []
    r = deducao_lp.atacar([(lo, hi)], arestas, [], [{"celulas": np.ones(4, bool)}], 5, [], registrar=linhas.append)
    assert r["reveladas"] == [{"celulas": 3}] and r["detalhe"]["inconclusivas"] == 0
    # O primeiro ponto minimiza a soma das quatro, a amostra do apontamento; depois dele sobram três candidatas.
    assert linhas[0].startswith("ponto viável") and "3 candidata(s) de 4" in linhas[0]
    # Célula a célula, com k = 2, em que só o 1 é revelação: x, y e z revelados em 1, w não.
    for celula, esperado in zip("xyzw", (1, 1, 1, 0)):
        alvo = np.array([c == celula for c in "xyzw"])
        r = deducao_lp.atacar([(lo, hi)], arestas, [], [{"celulas": alvo}], 2, [])
        assert r["reveladas"][0].get("celulas", 0) == esperado, celula


# O ciclo: primeira publicação, a superfície no site, a versão seguinte com a versão no ar, e versões reprovadas.

@pytest.fixture(scope="module")
def cat():
    cat = catalogo.carregar()
    # Com poucas AIHs inventadas, o critério de publicação tiraria quase tudo; aqui interessa o ciclo.
    regras = cat["bases"]["sih"]["supressao"] | {"criterio_publicacao": {"internacoes_ocultas_pct_max": 100,
                                                                        "celulas_ocultas_pct_max": 100}}
    return cat | {"cruzamentos": [c for c in cat["cruzamentos"] if c["id"] in CRUZAMENTOS],
                  "bases": cat["bases"] | {"sih": cat["bases"]["sih"] | {"supressao": regras}}}


def processar(cat, ciclo, trabalho, ultima, anterior=None, **opcoes):
    """Uma execução do ano de 2025 com a última competência `ultima` (AAAAMM)."""
    jan = sih_janela.Janela(ultima, ultima, 12, 5, 2025)
    return sih.processar_anos(ciclo["con"], "aih", jan, [2025], cat, trabalho, ciclo["municipios7"], "2027-06-01T00:00:00Z",
                              "2027-05-20", anterior=anterior, avisar=lambda texto: None, **opcoes)


@pytest.fixture(scope="module")
def ciclo(cat, tmp_path_factory):
    """Primeira publicação (2704: dezembro de 2025 ainda preliminar), a superfície dela no site e a versão
    seguinte (2705: o ano fecha), que recebe a versão no ar pela consulta ao site."""
    raiz = tmp_path_factory.mktemp("ciclo")
    aihs = aihs_sinteticas(1500)
    con = duckdb.connect()
    con.execute("CREATE TABLE aih AS SELECT * FROM aihs")
    ciclo = {"con": con, "raiz": raiz, "municipios7": {m: m + "0" for m in set(aihs["mun_res"]) | set(aihs["mun_hosp"])}}
    ciclo["primeira"] = processar(cat, ciclo, raiz / "primeira", 202704)
    # A superfície da primeira vai para o site; a seguinte a baixa e confere, como no Publicar.
    endereco = projeto.SITE + cat["bases"]["sih"]["superficie"]["arquivo"]
    consulta = sih_superficie.consultar(raiz / "no-ar", cat, site_falso(endereco, raiz / "primeira" / sih_superficie.ARQUIVO))
    assert consulta["existe"] and consulta["anos"] == [2025]
    ciclo["no_ar"] = sih_superficie.versao_no_ar(raiz / "no-ar", cat)
    # A segunda guarda o que construir_ano devolveu, para os testes de reprovação não refazerem o ano.
    original, guardado = sih.construir_ano, {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sih, "construir_ano", lambda *a, **k: guardado.setdefault("ano", original(*a, **k)))
        ciclo["segunda"] = processar(cat, ciclo, raiz / "segunda", 202705, ciclo["no_ar"], no_ar_consultada=True)
    ciclo["construido"] = guardado["ano"]
    return ciclo


def test_primeira_publicacao_grava_a_superficie_como_a_tela_mostra(ciclo):
    assert ciclo["primeira"]["reprovados"] == {}
    s = sih.ler_situacao(ciclo["raiz"] / "primeira" / "particoes", 2025)
    assert s["deducao"]["conjunto"] == {"obrigatorio": False, "rodou": False, "motivo": "nenhuma versão anterior informada"}
    assert s["versao_no_ar"] == {"consultada": False, "tinha_o_ano": False}
    assert set(s["publicados"]) == set(CRUZAMENTOS) and s["preliminares"] == ["202512"]
    # Nenhuma margem nem mês x sexo vai para a superfície: a página não os mostra.
    assert not any(n.startswith("margens/") for n in s["arquivos"])
    sup = sih_superficie.ler(ciclo["raiz"] / "primeira" / sih_superficie.ARQUIVO, catalogo_do_ciclo())
    assert sorted(sup.anos) == [2025] and sup.anos[2025]["superficie"] == {"sih_res_ano": ["internacoes", "obitos"],
                                                                          "sih_res_mes": ["internacoes"]}
    assert ciclo["primeira"]["superficie"]["linhas"] == sum(t.num_rows for t in sup.tabelas.values())
    # Dezembro, preliminar, em múltiplo de 5; os meses fechados, exatos. O ano, aberto, arredondado.
    mes = sup.tabela(2025, "sih_res_mes")
    grandes = mes[~mes["oculto"] & (mes["internacoes"] >= 5)]
    assert (grandes["arredondado"] == grandes["mes"].eq("202512")).all()
    verdade = ciclo["construido"][0][("mun_res", "mes")].assign(mun_res=lambda d: d["mun_res"] + "0")
    junto = mes.merge(verdade, on=["mun_res", "mes"], suffixes=("", "_v"))
    exatas = junto[~junto["oculto"] & (junto["mes"] != "202512")]
    assert len(exatas) and (exatas["internacoes"] == exatas["internacoes_v"]).all()
    dezembro = junto[~junto["oculto"] & junto["arredondado"]]
    assert len(dezembro) and (dezembro["internacoes"] % 5 == 0).all()
    assert ((dezembro["internacoes"] - dezembro["internacoes_v"]).abs() <= 2).all()


def catalogo_do_ciclo():
    cat = catalogo.carregar()
    return cat | {"cruzamentos": [c for c in cat["cruzamentos"] if c["id"] in CRUZAMENTOS]}


def test_versao_seguinte_herda_passa_pelos_dois_motores_e_so_entao_e_gravada(ciclo):
    assert ciclo["segunda"]["reprovados"] == {} and ciclo["segunda"]["superficie"]["linhas"] > 0
    s = sih.ler_situacao(ciclo["raiz"] / "segunda" / "particoes", 2025)
    conjunto = s["deducao"]["conjunto"]
    assert conjunto["obrigatorio"] and conjunto["rodou"] and conjunto["passou"] and conjunto["motores"] == MOTORES
    assert conjunto["versao_no_ar_coletada_em"] == "2027-06-01T00:00:00Z"
    for medida in ("internacoes", "obitos"):
        assert conjunto[medida]["total"] == 0 and set(conjunto[medida]["motores"]) == set(MOTORES)
        for motor in MOTORES:
            assert conjunto[medida]["motores"][motor]["total"] == 0 and "por_no" not in conjunto[medida]["motores"][motor]
    lp = conjunto["internacoes"]["motores"]["programacao_linear"]["detalhe"]
    assert lp["inconclusivas"] == 0 and lp["alvos"] > 0 and lp["resolucoes"] >= 1
    assert s["versao_no_ar"] == {"consultada": True, "tinha_o_ano": True} and s["preliminares"] == []
    medicao = ciclo["segunda"]["anos"]["2025"]
    # A herança vem da superfície: só o que a página mostrou.
    assert medicao["particao_gravada"] and medicao["herdou_da_anterior"] == NA_TELA
    depois = sih_superficie.ler(ciclo["raiz"] / "segunda" / sih_superficie.ARQUIVO, catalogo_do_ciclo())
    # O ano fechou: o que estava oculto na versão no ar continua oculto, e nada mais sai arredondado.
    for cid in NA_TELA:
        antes, agora = ciclo["no_ar"].tabela(2025, cid), depois.tabela(2025, cid)
        chaves = [c for c in antes.columns if c in ("mun_res", "mes")]
        junto = antes.merge(agora, on=chaves, suffixes=("_antes", "_depois"))
        assert len(junto) == len(antes) == len(agora)
        assert junto.loc[junto["oculto_antes"], "oculto_depois"].all() and not junto["arredondado_depois"].any(), cid


def refazer(cat, ciclo, monkeypatch, trabalho="segunda", medicao=None, **opcoes):
    """A segunda versão outra vez, na mesma pasta de trabalho, sem recalcular o ano."""
    nos, sup, m = ciclo["construido"]
    monkeypatch.setattr(sih, "construir_ano", lambda *a, **k: (nos, sup, copy.deepcopy(m) | (medicao or {})))
    return processar(cat, ciclo, ciclo["raiz"] / trabalho, 202705, ciclo["no_ar"], no_ar_consultada=True, **opcoes)


@pytest.fixture
def com_particao_aprovada(ciclo, tmp_path):
    """Devolve a partição aprovada e a superfície da segunda versão ao lugar depois de cada teste que as apaga."""
    pasta = ciclo["raiz"] / "segunda"
    shutil.copytree(pasta, tmp_path / "copia")
    yield pasta / "particoes"
    shutil.rmtree(pasta)
    shutil.copytree(tmp_path / "copia", pasta)


def test_ano_que_reprova_no_teste_de_deducao_nao_grava_particao(cat, ciclo, monkeypatch, com_particao_aprovada):
    assert (com_particao_aprovada / "ano=2025" / "situacao.json").exists()
    _, _, m = ciclo["construido"]
    reprovado = {"deducao_internacoes": m["deducao_internacoes"] | {"passou": False, "pequenas_reveladas": 3}}
    r = refazer(cat, ciclo, monkeypatch, medicao=reprovado)
    assert r["reprovados"] == {"2025": "o teste de dedução revelou 3 contagem(ns) de internações"}
    assert r["particoes"]["2025"]["arquivos"] == 0 and not r["anos"]["2025"]["particao_gravada"]
    # Nem a partição nova, nem a que a execução anterior tinha deixado ali, nem sobra da troca, nem superfície.
    assert list(com_particao_aprovada.iterdir()) == [] and r["superficie"] is None
    assert not (com_particao_aprovada.parent / sih_superficie.ARQUIVO).exists()
    assert r["anos"]["2025"]["ataque_conjunto"]["motivo"] == "a candidata não passou no teste dela"
    # Óbitos reprovam do mesmo jeito.
    r = refazer(cat, ciclo, monkeypatch, medicao={"deducao_obitos": m["deducao_obitos"] | {"passou": False}})
    assert r["reprovados"] == {"2025": "o teste de dedução revelou contagens de óbitos"} and list(com_particao_aprovada.iterdir()) == []


def test_ataque_conjunto_que_revela_algo_nao_grava_particao(cat, ciclo, monkeypatch, com_particao_aprovada):
    # Outro motor, com o mesmo contrato, que acha uma contagem revelada na candidata.
    recebidos = []

    def revela(p):
        recebidos.append(p)
        achou = {"mun_res+mes": 1} if p.medida == "internacoes" else {}
        return sih_versoes.Resultado("de teste", [{}, achou], {"0-1": {}})
    monkeypatch.setitem(sih_versoes.MOTORES, "de teste", revela)
    r = refazer(cat, ciclo, monkeypatch, motores=["intervalos", "de teste"])
    motivo = "o ataque conjunto com a versão no ar não passou: 1 contagem(ns) de 1 a 4 revelada(s) com as duas versões juntas"
    assert r["reprovados"] == {"2025": motivo} and list(com_particao_aprovada.iterdir()) == []
    conjunto = r["anos"]["2025"]["ataque_conjunto"]
    assert conjunto["rodou"] and not conjunto["passou"]
    assert conjunto["internacoes"]["motores"]["de teste"]["por_no"]["candidata"] == {"mun_res+mes": 1}
    assert conjunto["internacoes"]["motores"]["intervalos"]["total"] == 0
    # O motor recebeu o problema inteiro, só com a superfície das duas versões.
    p = recebidos[0]
    assert [v.rotulo for v in p.versoes] == ["no ar", "candidata"] and p.versoes[0].valor is None
    assert p.versoes[1].valor is not None
    assert {"mun_res+mes", "uf_res+mes", "brasil"} <= set(p.versoes[0].lo) == set(p.versoes[1].lo)
    assert set(p.versoes[0].publicados) == {"mun_res", "mun_res+mes"} == set(p.versoes[1].publicados)
    assert all(v.lo[n].shape == v.hi[n].shape == v.escondida[n].shape for v in p.versoes for n in v.lo)
    assert {(f, g) for f, g, _ in p.arestas} >= {("mun_res+mes", "uf_res+mes"), ("uf_res", "brasil")}
    # O ano fechou na candidata: todas as células valem o mesmo nas duas versões.
    assert all(mascara.all() for _, _, _, mascara in p.iguais) and len(p.iguais) == len(p.versoes[0].lo)
    # A versão no ar entra como foi publicada: só dezembro é um intervalo; os meses fechados, exatos.
    no_ar = p.versoes[0]
    largura = no_ar.hi["mun_res+mes"] - no_ar.lo["mun_res+mes"]
    assert (largura[~no_ar.escondida["mun_res+mes"]] <= 4).all() and (largura[~no_ar.escondida["mun_res+mes"]] > 0).sum() > 0


def test_versao_no_ar_adulterada_ou_incoerente_nao_deixa_publicar(cat, ciclo, monkeypatch, com_particao_aprovada):
    # Um valor de período fechado diferente do que a candidata tem: as versões não fecham entre si.
    trocada = copy.copy(ciclo["no_ar"])
    trocada.tabelas = dict(trocada.tabelas)
    mes = trocada.tabela(2025, "sih_res_mes")
    alvo = mes.index[~mes["oculto"] & (mes["mes"] == "202503")][0]
    mes.loc[alvo, "internacoes"] += 7
    trocada.tabelas[2025, "sih_res_mes"] = pa.Table.from_pandas(mes, schema=ciclo["no_ar"].tabelas[2025, "sih_res_mes"].schema,
                                                                 preserve_index=False)
    nos, sup, m = ciclo["construido"]
    monkeypatch.setattr(sih, "construir_ano", lambda *a, **k: (nos, sup, copy.deepcopy(m)))
    r = processar(cat, ciclo, ciclo["raiz"] / "segunda", 202705, trocada, no_ar_consultada=True)
    assert "não rodou: As versões não fecham entre si (internacoes)" in r["reprovados"]["2025"]
    assert list(com_particao_aprovada.iterdir()) == []
    # Arquivo da versão no ar diferente do que a consulta baixou: a leitura para antes de qualquer ano.
    arquivo = ciclo["raiz"] / "adulterada" / sih_superficie.ARQUIVO
    shutil.copytree(ciclo["raiz"] / "no-ar", arquivo.parent)
    arquivo.write_bytes(arquivo.read_bytes() + b"x")
    with pytest.raises(sih_superficie.ErroDeSuperficie, match="diferente do que a consulta baixou"):
        sih_superficie.versao_no_ar(arquivo.parent, cat)


def test_sem_teste_de_deducao_nada_e_gravado(cat, ciclo, monkeypatch, com_particao_aprovada):
    r = refazer(cat, ciclo, monkeypatch, deduzir=False)
    # Não é reprovação, é medição: mas sem teste não há partição publicável, nem superfície.
    assert r["reprovados"] == {} and r["particoes"]["2025"]["nao_gravada"] == "o teste de dedução não rodou"
    assert list(com_particao_aprovada.iterdir()) == [] and r["superficie"] is None


def test_comando_sih_fica_vermelho_com_ano_reprovado(tmp_path, monkeypatch, capsys):
    (tmp_path / "ibge.json").write_text(json.dumps({"municipios": []}), encoding="utf-8")
    chamadas = []

    def executar(*args, **opcoes):
        chamadas.append(opcoes)
        return {"etapas": {"total_s": 1}, "reprovados": dict(reprovados)}
    monkeypatch.setattr(sih, "executar", executar)
    comando = ["sih", "--coleta", str(tmp_path), "--trabalho", str(tmp_path / "t"), "--saida", str(tmp_path / "s")]
    reprovados = {"2024": "o ataque conjunto com a versão no ar não passou: 18 contagem(ns)"}
    assert cli.main(comando) == 1
    assert "::error title=SIH 2024 sem partição::o ataque conjunto com a versão no ar não passou" in capsys.readouterr().out
    reprovados = {}
    assert cli.main(comando) == 0 and chamadas[-1] == {"anterior": None, "no_ar_consultada": False}
    # Com a consulta feita e nenhuma versão no ar, é a primeira publicação: sem anterior, e isso fica registrado.
    (tmp_path / "no-ar").mkdir()
    (tmp_path / "no-ar" / "consulta.json").write_text('{"existe": false, "anos": []}', encoding="utf-8")
    assert cli.main(comando + ["--no-ar", str(tmp_path / "no-ar")]) == 0
    assert chamadas[-1] == {"anterior": None, "no_ar_consultada": True}


# O detalhe que sai dos dois anos mais novos (decidido em 11/11/2026): o que foi publicado continua publicado.

DETALHE = "sih_res_ano_capitulo"


@pytest.fixture(scope="module")
def ciclo_detalhe(cat, tmp_path_factory):
    """Três versões, de 2025 a 2027, com o detalhe por capítulo da CID. Em 2612, 2025 e 2026 têm o detalhe, e
    2025 está aberto. Em 2702, 2027 entra e 2025 sai dos dois mais novos ainda preliminar. Em 2705, 2025 fecha.
    Cada versão lê a anterior do arquivo publicado com o site, conferido por sih_superficie.ler."""
    # Só os da superfície: mês x sexo, que a página não mostra, só tornaria o ciclo mais lento.
    com_detalhe = cat | {"cruzamentos": [c for c in cat["cruzamentos"] if c["id"] in NA_TELA]
                         + [c for c in catalogo.carregar()["cruzamentos"] if c["id"] == DETALHE]}
    raiz = tmp_path_factory.mktemp("detalhe")
    aihs = pd.concat([aihs_sinteticas(600, semente, ano) for semente, ano in ((7, 2025), (8, 2026), (9, 2027))])
    con = duckdb.connect()
    con.register("todas", aihs)
    municipios7 = {m: m + "0" for m in set(aihs["mun_res"]) | set(aihs["mun_hosp"])}
    versoes, anterior, ataques = {}, None, []
    original = sih_versoes.montar

    def montar(*args, **opcoes):
        p = original(*args, **opcoes)
        ataques.append((ultima, args[4], args[6], p))
        return p
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sih_versoes, "montar", montar)
        for ultima in (202612, 202702, 202705):
            con.execute(f"CREATE OR REPLACE TABLE aih AS SELECT * FROM todas WHERE dt_saida // 100 <= {ultima}")
            jan = sih_janela.Janela(ultima, ultima, 12, 5, 2025)
            r = sih.processar_anos(con, "aih", jan, jan.anos(), com_detalhe, raiz / str(ultima), municipios7,
                                   f"{ultima // 100}-{ultima % 100:02d}-28T00:00:00Z", "2027-05-20", anterior=anterior,
                                   no_ar_consultada=anterior is not None, avisar=lambda texto: None)
            assert r["reprovados"] == {}, (ultima, r["reprovados"])
            anterior = sih_superficie.ler(raiz / str(ultima) / sih_superficie.ARQUIVO, com_detalhe)
            versoes[ultima] = {"r": r, "sup": anterior, "pasta": raiz / str(ultima)}
    return {"cat": com_detalhe, "versoes": versoes, "ataques": ataques}


def test_ano_que_sai_dos_dois_mais_novos_ainda_preliminar_mantem_o_detalhe(ciclo_detalhe):
    cat, v = ciclo_detalhe["cat"], ciclo_detalhe["versoes"]
    primeira, segunda, terceira = (v[u]["sup"] for u in (202612, 202702, 202705))
    assert sorted(primeira.anos) == [2025, 2026] and sorted(segunda.anos) == sorted(terceira.anos) == [2025, 2026, 2027]
    # Na primeira, 2025 e 2026 são os dois mais novos: os dois com o detalhe, nenhum mantido.
    assert all(DETALHE in primeira.anos[a]["superficie"] and primeira.anos[a]["detalhe_mantido"] == [] for a in (2025, 2026))
    # Pelo padrão, 2025 ficaria sem o detalhe na segunda; ele já estava no ar, então continua.
    assert DETALHE not in sih_superficie.cruzamentos_do_ano(cat, 2025, [2025, 2026, 2027])
    s = segunda.anos[2025]
    assert s["detalhe_mantido"] == [DETALHE] and DETALHE in s["superficie"] and s["preliminares"]
    assert all(segunda.anos[a]["detalhe_mantido"] == [] and DETALHE in segunda.anos[a]["superficie"] for a in (2026, 2027))
    # Ainda preliminar, o detalhe sai arredondado em múltiplo de 5; a partição registra o mesmo que o arquivo.
    cap = segunda.tabela(2025, DETALHE)
    visiveis = cap[~cap["oculto"] & (cap["internacoes"] >= 5)]
    assert len(visiveis) and visiveis["arredondado"].all() and (visiveis["internacoes"] % 5 == 0).all()
    assert sih.ler_situacao(v[202702]["pasta"] / "particoes", 2025)["detalhe_mantido"] == [DETALHE]
    # Na terceira, 2025 fechou: o detalhe continua, exato, e o que estava oculto continua oculto.
    s = terceira.anos[2025]
    assert s["detalhe_mantido"] == [DETALHE] and DETALHE in s["superficie"] and s["preliminares"] == []
    junto = cap.merge(terceira.tabela(2025, DETALHE), on=["mun_res", "capitulo"], suffixes=("_antes", "_depois"))
    assert len(junto) == len(cap) and junto.loc[junto["oculto_antes"], "oculto_depois"].all()
    assert not junto["arredondado_depois"].any()


def test_detalhe_mantido_entra_no_ataque_conjunto(ciclo_detalhe):
    v = ciclo_detalhe["versoes"]
    no = "mun_res+capitulo"
    for ultima in (202702, 202705):
        problemas = [p for u, ano, medida, p in ciclo_detalhe["ataques"] if (u, ano, medida) == (ultima, 2025, "internacoes")]
        assert len(problemas) == 1, ultima
        # A versão no ar e a candidata publicam o detalhe de 2025, e o ataque o vê nas duas.
        assert all(no in versao.publicados for versao in problemas[0].versoes), ultima
        conjunto = sih.ler_situacao(v[ultima]["pasta"] / "particoes", 2025)["deducao"]["conjunto"]
        assert conjunto["rodou"] and conjunto["passou"] and conjunto["motores"] == MOTORES


def test_pagina_oferece_no_seletor_o_ano_que_saiu_do_padrao(ciclo_detalhe):
    from test_site import coleta

    from pipeline import site_sih
    cat, segunda = ciclo_detalhe["cat"], ciclo_detalhe["versoes"][202702]
    m = {"codigo": "3500000", "nome": "Teste", "uf": "SP", "populacao_censo": 100000}
    paginas = {}
    for origem in (segunda["pasta"] / sih_superficie.ARQUIVO, segunda["pasta"] / "particoes"):
        paginas[origem.name] = site_sih.secao(m, site_sih.carregar(origem, cat), coleta())
    # Das partições ou do arquivo, a mesma página: a situação de cada ano leva o detalhe mantido.
    assert paginas[sih_superficie.ARQUIVO] == paginas["particoes"]
    html = paginas["particoes"]
    assert re.findall(r'name="sih-ano" value="(\d{4})"', html) == ["2027", "2026", "2025"]
    assert re.search(r'value="2027" checked', html) and not re.search(r'value="2025" checked', html)
    painel = html[html.index('data-ano="2025"'):]
    assert "internacoes-por-capitulo-2025" in painel
