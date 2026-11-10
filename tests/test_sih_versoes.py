"""Ataque conjunto com a versão no ar e o ciclo de publicação do SIH, com AIHs inventadas."""
import copy
import json

import numpy as np
import pytest

pd = pytest.importorskip("pandas")
duckdb = pytest.importorskip("duckdb")

from conftest import FonteFalsa, resposta  # noqa: E402
from test_release import LISTA, release_do_sih  # noqa: E402
from test_sih_tabelas import aihs_sinteticas  # noqa: E402

from pipeline import __main__ as cli  # noqa: E402
from pipeline import catalogo, deducao, release, sih, sih_janela, sih_particoes, sih_versoes  # noqa: E402

INF = deducao.INF
CRUZAMENTOS = ("sih_res_ano", "sih_res_mes", "sih_res_mes_sexo")


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


def test_duas_versoes_juntas_revelam_o_que_nenhuma_revela_sozinha():
    # No ar: as duas células ocultas e o total 12. Candidata: uma célula vira 9, e o total deixa de aparecer.
    no_ar, candidata = versao("no ar", [None, None], 12), versao("candidata", [None, 9], None)
    sozinhas = sih_versoes.atacar(problema(no_ar, candidata, iguais=False))
    assert sozinhas.total == 0 and sozinhas.reveladas == [{}, {}]
    # O período já fechou, então as células valem o mesmo nas duas: 12 - 9 = 3, em qualquer das versões.
    juntas = sih_versoes.atacar(problema(no_ar, candidata))
    assert juntas.reveladas == [{"celulas": 1}, {"celulas": 1}] and juntas.total == 2 and juntas.motor == "intervalos"


def test_diferenca_exata_de_1_a_4_entre_as_versoes_conta():
    # Período aberto, valores exatos nas duas: quem guardou as versões vê que a célula subiu 2.
    r = sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [9, 20], 29), iguais=False))
    assert r.reveladas == [{}, {}] and r.diferencas == {"0-1": {"celulas": 1, "total": 1}} and r.total == 2
    # Subir 13 não é contagem pequena.
    assert sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [20, 20], 40), iguais=False)).total == 0


def test_versoes_que_nao_fecham_entre_si_param_com_erro():
    # Período fechado com valores diferentes nas duas versões: uma delas não é verdadeira.
    with pytest.raises(sih_versoes.ErroDeVersoes, match="não fecham entre si"):
        sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [9, 20], 29)))
    with pytest.raises(sih_versoes.ErroDeVersoes, match="Motor do ataque conjunto desconhecido: 'outro'"):
        sih_versoes.atacar(problema(versao("no ar", [7, 20], 27), versao("candidata", [7, 20], 27)), motor="outro")


# O ciclo: primeira publicação, Release, versão seguinte com a versão no ar, e versões reprovadas.

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
    """Primeira publicação (2704: dezembro de 2025 ainda preliminar), a Release dela e a versão seguinte
    (2705: o ano fecha), que recebe a versão no ar pela consulta às Releases."""
    raiz = tmp_path_factory.mktemp("ciclo")
    aihs = aihs_sinteticas(1500)
    con = duckdb.connect()
    con.execute("CREATE TABLE aih AS SELECT * FROM aihs")
    ciclo = {"con": con, "raiz": raiz, "municipios7": {m: m + "0" for m in set(aihs["mun_res"]) | set(aihs["mun_hosp"])}}
    ciclo["primeira"] = processar(cat, ciclo, raiz / "primeira", 202704)
    pacote = sih_particoes.empacotar(raiz / "primeira" / "particoes", 2025)
    lancada = release_do_sih(2025, pacote)
    endereco = lancada["assets"][0]["browser_download_url"]
    lancada["assets"][0].pop("_corpo")
    release.consultar(raiz / "release", FonteFalsa({LISTA: resposta([lancada]), endereco: resposta(pacote)}))
    ciclo["no_ar"] = release.versao_no_ar(raiz / "release")
    # A segunda guarda o que construir_ano devolveu, para os testes de reprovação não refazerem o ano.
    original, guardado = sih.construir_ano, {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sih, "construir_ano", lambda *a, **k: guardado.setdefault("ano", original(*a, **k)))
        ciclo["segunda"] = processar(cat, ciclo, raiz / "segunda", 202705, ciclo["no_ar"], no_ar_consultada=True)
    ciclo["construido"] = guardado["ano"]
    return ciclo


def situacao(ciclo, nome):
    return sih_particoes.ler_publicada(ciclo["raiz"] / nome / "particoes", 2025)


def test_primeira_publicacao_grava_cruzamentos_e_margens_como_a_tela_mostra(ciclo):
    assert ciclo["primeira"]["reprovados"] == {}
    s = situacao(ciclo, "primeira")
    assert s["deducao"]["conjunto"] == {"obrigatorio": False, "rodou": False, "motivo": "nenhuma versão anterior informada"}
    assert s["versao_no_ar"] == {"consultada": False, "tinha_o_ano": False}
    assert set(s["publicados"]) == set(CRUZAMENTOS) and s["preliminares"] == ["202512"]
    # As margens publicadas vão para a partição: é delas que o ataque conjunto da versão seguinte parte.
    pasta = ciclo["raiz"] / "primeira" / "particoes" / "ano=2025"
    margens = sorted(n for n in s["arquivos"] if n.startswith("margens/"))
    assert margens == ["margens/internacoes/brasil.parquet", "margens/internacoes/mes.parquet",
                       "margens/internacoes/uf_hosp-mes.parquet", "margens/internacoes/uf_hosp.parquet",
                       "margens/internacoes/uf_res-mes.parquet", "margens/internacoes/uf_res.parquet",
                       "margens/obitos/brasil.parquet", "margens/obitos/uf_hosp.parquet", "margens/obitos/uf_res.parquet"]
    por_mes = pd.read_parquet(pasta / "margens/internacoes/mes.parquet")
    assert list(por_mes.columns) == ["mes", "valor", "oculto", "arredondado"] and len(por_mes) == 12
    # Dezembro, preliminar, em múltiplo de 5; os meses fechados, exatos. O ano, aberto, arredondado.
    assert (por_mes["arredondado"] == (por_mes["mes"] == "202512")).all()
    exato = ciclo["construido"][0][("mes",)].set_index("mes")["internacoes"]
    assert (por_mes.set_index("mes")["valor"].drop("202512") == exato.drop("202512")).all()
    assert por_mes.set_index("mes").loc["202512", "valor"] == (exato["202512"] + 2) // 5 * 5
    brasil = pd.read_parquet(pasta / "margens/internacoes/brasil.parquet")
    assert bool(brasil["arredondado"][0]) and brasil["valor"][0] % 5 == 0


def test_versao_seguinte_herda_passa_pelo_ataque_conjunto_e_so_entao_e_gravada(ciclo):
    assert ciclo["segunda"]["reprovados"] == {}
    s = situacao(ciclo, "segunda")
    conjunto = s["deducao"]["conjunto"]
    assert conjunto["obrigatorio"] and conjunto["rodou"] and conjunto["passou"] and conjunto["motor"] == "intervalos"
    assert conjunto["versao_no_ar_coletada_em"] == "2027-06-01T00:00:00Z"
    for medida in ("internacoes", "obitos"):
        assert conjunto[medida]["total"] == 0 and "por_no" not in conjunto[medida]
    assert s["versao_no_ar"] == {"consultada": True, "tinha_o_ano": True} and s["preliminares"] == []
    medicao = ciclo["segunda"]["anos"]["2025"]
    assert medicao["particao_gravada"] and medicao["herdou_da_anterior"] == sorted(CRUZAMENTOS)
    # O ano fechou: o que estava oculto na versão no ar continua oculto, e nada mais sai arredondado.
    for cid in CRUZAMENTOS:
        antes = pd.concat(pd.read_parquet(p) for p in sorted((ciclo["no_ar"] / "ano=2025" / cid).glob("*.parquet")))
        depois = pd.concat(pd.read_parquet(p) for p in sorted((ciclo["raiz"] / "segunda/particoes/ano=2025" / cid).glob("*.parquet")))
        chaves = [c for c in antes.columns if c in ("mun_res", "mes", "sexo")]
        junto = antes.merge(depois, on=chaves, suffixes=("_antes", "_depois"))
        assert len(junto) == len(antes) == len(depois)
        assert junto.loc[junto["oculto_antes"], "oculto_depois"].all() and not junto["arredondado_depois"].any(), cid


def refazer(cat, ciclo, monkeypatch, trabalho="segunda", medicao=None, **opcoes):
    """A segunda versão outra vez, na mesma pasta de trabalho, sem recalcular o ano."""
    nos, sup, m = ciclo["construido"]
    monkeypatch.setattr(sih, "construir_ano", lambda *a, **k: (nos, sup, copy.deepcopy(m) | (medicao or {})))
    return processar(cat, ciclo, ciclo["raiz"] / trabalho, 202705, ciclo["no_ar"], no_ar_consultada=True, **opcoes)


@pytest.fixture
def com_particao_aprovada(ciclo):
    """Devolve a partição aprovada da segunda versão ao lugar depois de cada teste que a apaga."""
    pasta = ciclo["raiz"] / "segunda" / "particoes"
    pacote = sih_particoes.empacotar(pasta, 2025)
    yield pasta
    sih_particoes.desempacotar(pacote, pasta, 2025)


def test_ano_que_reprova_no_teste_de_deducao_nao_grava_particao(cat, ciclo, monkeypatch, com_particao_aprovada):
    assert (com_particao_aprovada / "ano=2025" / "situacao.json").exists()
    _, _, m = ciclo["construido"]
    reprovado = {"deducao_internacoes": m["deducao_internacoes"] | {"passou": False, "pequenas_reveladas": 3}}
    r = refazer(cat, ciclo, monkeypatch, medicao=reprovado)
    assert r["reprovados"] == {"2025": "o teste de dedução revelou 3 contagem(ns) de internações"}
    assert r["particoes"]["2025"]["arquivos"] == 0 and not r["anos"]["2025"]["particao_gravada"]
    # Nem a partição nova, nem a que a execução anterior tinha deixado ali, nem sobra da troca.
    assert list(com_particao_aprovada.iterdir()) == []
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
    r = refazer(cat, ciclo, monkeypatch, motor="de teste")
    motivo = "o ataque conjunto com a versão no ar não passou: 1 contagem(ns) de 1 a 4 revelada(s) com as duas versões juntas"
    assert r["reprovados"] == {"2025": motivo} and list(com_particao_aprovada.iterdir()) == []
    conjunto = r["anos"]["2025"]["ataque_conjunto"]
    assert conjunto["rodou"] and not conjunto["passou"] and conjunto["internacoes"]["por_no"]["candidata"] == {"mun_res+mes": 1}
    # O motor recebeu o problema inteiro, sem depender de como ele é resolvido.
    p = recebidos[0]
    assert [v.rotulo for v in p.versoes] == ["no ar", "candidata"] and p.versoes[0].valor is None
    assert {"mun_res+mes", "uf_res+mes", "brasil"} <= set(p.versoes[0].lo) == set(p.versoes[1].lo)
    assert all(v.lo[n].shape == v.hi[n].shape == v.escondida[n].shape for v in p.versoes for n in v.lo)
    assert {(f, g) for f, g, _ in p.arestas} >= {("mun_res+mes", "uf_res+mes"), ("uf_res", "brasil")}
    # O ano fechou na candidata: todas as células valem o mesmo nas duas versões.
    assert all(mascara.all() for _, _, _, mascara in p.iguais) and len(p.iguais) == len(p.versoes[0].lo)
    # A versão no ar entra como foi publicada: dezembro arredondado é um intervalo de 5 valores.
    no_ar = p.versoes[0]
    largura = (no_ar.hi["mes"] - no_ar.lo["mes"])[~no_ar.escondida["mes"]]
    assert sorted(set(largura.tolist())) == [0, 4] and (largura == 4).sum() == 1


def test_versao_no_ar_adulterada_ou_incoerente_nao_deixa_publicar(cat, ciclo, monkeypatch, com_particao_aprovada):
    # Um valor de período fechado diferente do que a candidata tem: as versões não fecham entre si.
    def ler_trocado(pasta, ano, catalogo):
        lido = original(pasta, ano, catalogo)
        df = lido["margens"]["internacoes", ("mes",)]
        df.loc[df["mes"] == "202503", "valor"] += 7
        return lido
    original = sih_versoes.ler_no_ar
    monkeypatch.setattr(sih_versoes, "ler_no_ar", ler_trocado)
    r = refazer(cat, ciclo, monkeypatch)
    assert "não rodou: As versões não fecham entre si (internacoes)" in r["reprovados"]["2025"]
    assert list(com_particao_aprovada.iterdir()) == []
    monkeypatch.setattr(sih_versoes, "ler_no_ar", original)
    # Arquivo da versão no ar diferente do que a situação dela registra: o pipeline para na leitura.
    copia = ciclo["raiz"] / "adulterada"
    sih_particoes.desempacotar(sih_particoes.empacotar(ciclo["no_ar"], 2025), copia, 2025)
    arquivo = copia / "ano=2025" / "margens" / "internacoes" / "mes.parquet"
    arquivo.write_bytes(arquivo.read_bytes() + b"x")
    with pytest.raises(sih.ErroDeParticao, match="diferente do que situacao.json"):
        sih.processar_anos(ciclo["con"], "aih", sih_janela.Janela(202705, 202705, 12, 5, 2025), [2025], cat,
                           ciclo["raiz"] / "segunda", ciclo["municipios7"], "x", "x", anterior=copia, avisar=lambda t: None)


def test_sem_teste_de_deducao_nada_e_gravado(cat, ciclo, monkeypatch, com_particao_aprovada):
    r = refazer(cat, ciclo, monkeypatch, deduzir=False)
    # Não é reprovação, é medição: mas sem teste não há partição publicável.
    assert r["reprovados"] == {} and r["particoes"]["2025"]["nao_gravada"] == "o teste de dedução não rodou"
    assert list(com_particao_aprovada.iterdir()) == []


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
    (tmp_path / "release").mkdir()
    (tmp_path / "release" / "consulta.json").write_text('{"sih": {"anos": []}}', encoding="utf-8")
    assert cli.main(comando + ["--no-ar", str(tmp_path / "release")]) == 0
    assert chamadas[-1] == {"anterior": None, "no_ar_consultada": True}
