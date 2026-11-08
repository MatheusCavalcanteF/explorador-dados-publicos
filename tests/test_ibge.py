import json
from datetime import datetime, timezone

import pytest

from pipeline import ibge, rede
from pipeline.contrato import sha256_valores
from conftest import FonteFalsa, codigos, fonte_dtb, resposta, sidra

AGORA = datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)


def fonte(estimativa=None, censo=None, censo_fora=False, lista=None, periodo="2026"):
    lista = lista or codigos()
    estimativa = {c: 1000 + i for i, c in enumerate(lista)} if estimativa is None else estimativa
    censo = {c: 900 + i for i, c in enumerate(lista[1:])} if censo is None else censo
    urls = fonte_dtb(lista)
    urls[ibge.URL_SIDRA.format(**ibge.ESTIMATIVA)] = resposta(sidra(estimativa, 9324, periodo))
    if not censo_fora:
        urls[ibge.URL_SIDRA.format(**ibge.CENSO)] = resposta(sidra(censo, 93, "2022"))
    return FonteFalsa(urls)


def corpo(valor):
    return json.dumps(valor, ensure_ascii=False).encode()


def test_sidra_acha_colunas_pelo_cabecalho_em_qualquer_ordem():
    linhas = sidra({"3548500": 429528}, 9324, "2026", ordem=("periodo", "municipio", "variavel"))
    assert ibge.ler_sidra(corpo(linhas), 9324, "teste") == ("2026", {"3548500": 429528})


@pytest.mark.parametrize("valor", ["-", "...", "X", "0", "12.5", ""])
def test_sidra_recusa_sinal_de_ausencia_ou_sigilo_como_numero(valor):
    with pytest.raises(ibge.ErroDeContrato):
        ibge.ler_sidra(corpo(sidra({"3548500": valor}, 9324, "2026")), 9324, "teste")


def test_sidra_recusa_variavel_errada_e_dois_periodos():
    with pytest.raises(ibge.ErroDeContrato, match="variável"):
        ibge.ler_sidra(corpo(sidra({"3548500": 10}, 93, "2026")), 9324, "teste")
    linhas = sidra({"3548500": 10}, 9324, "2026") + sidra({"3550308": 20}, 9324, "2025")[1:]
    with pytest.raises(ibge.ErroDeContrato, match="um só período"):
        ibge.ler_sidra(corpo(linhas), 9324, "teste")


def test_sidra_recusa_resposta_que_nao_e_json():
    with pytest.raises(ibge.ErroDeContrato, match="não é JSON"):
        ibge.ler_sidra(b"<html>manutencao</html>", 9324, "teste")


def test_cobertura_lista_poucos_ausentes_e_recusa_muitos_ou_desconhecidos():
    lista = set(codigos(100))
    assert ibge.conferir_cobertura(lista, {c: 1 for c in sorted(lista)[3:]}, "t") == sorted(lista)[:3]
    with pytest.raises(ibge.ErroDeContrato, match="sem valor"):
        ibge.conferir_cobertura(lista, {c: 1 for c in sorted(lista)[11:]}, "t")
    with pytest.raises(ibge.ErroDeContrato, match="fora da lista"):
        ibge.conferir_cobertura(lista, {"9999999": 1}, "t")


def test_sidra_recusa_periodo_que_nao_e_ano():
    with pytest.raises(ibge.ErroDeContrato, match="não é um ano"):
        ibge.ler_sidra(corpo(sidra({"3548500": 10}, 9324, "2026-T1")), 9324, "teste")


def test_hash_dos_valores_ignora_a_ordem_e_muda_com_um_valor():
    assert sha256_valores({"1": 10, "2": 20}) == sha256_valores({"2": 20, "1": 10})
    assert sha256_valores({"1": 10, "2": 20}) != sha256_valores({"1": 10, "2": 21})


def test_comparacao_com_a_coleta_anterior():
    anterior = {"estimativa": {"periodo": "2026", "sha256_valores": "abc"}}
    assert ibge.comparar(None, "estimativa", "2026", "abc") == "sem_coleta_anterior"
    assert ibge.comparar({"estimativa": {"periodo": "2026"}}, "estimativa", "2026", "abc") == "sem_coleta_anterior"
    assert ibge.comparar(anterior, "estimativa", "2026", "abc") == "igual"
    assert ibge.comparar(anterior, "estimativa", "2026", "def") == "valores_mudaram"
    assert ibge.comparar(anterior, "estimativa", "2027", "def") == "periodo_novo"


def test_primeira_coleta_grava_arquivo_para_a_release(tmp_path):
    resultado = ibge.coletar(tmp_path, pedir=fonte(), agora=AGORA)
    assert resultado["coletado_em"] == "2026-11-07T23:30:00Z"
    censo = resultado["fontes"]["censo"]
    assert censo["origem"] == "fonte" and censo["ausentes"] == [sorted(codigos())[0]]
    assert resultado["municipios"][0]["populacao_censo"] is None
    assert resultado["fontes"]["dtb"]["data_base"] == "2025-12-31"
    assert resultado["municipios"][0]["uf_nome"] == "Rondônia"
    assert all(f["em_relacao_a_coleta_anterior"] == "sem_coleta_anterior" for f in resultado["fontes"].values())
    novo = json.loads((tmp_path / "censo-2022.json").read_text(encoding="utf-8"))
    assert len(novo["valores"]) == 5570 and novo["sha256"] == censo["sha256"]
    assert novo["sha256_valores"] == sha256_valores(novo["valores"]) == censo["sha256_valores"]
    assert "valores" not in json.loads((tmp_path / "ibge.json").read_text(encoding="utf-8"))["fontes"]["censo"]


def test_censo_vem_da_release_e_e_conferido_com_a_fonte(tmp_path):
    ibge.coletar(tmp_path / "primeira", pedir=fonte(), agora=AGORA)
    release = tmp_path / "primeira" / "censo-2022.json"
    resultado = ibge.coletar(tmp_path / "segunda", release, pedir=fonte(), agora=AGORA)
    censo = resultado["fontes"]["censo"]
    assert censo["origem"] == "release" and censo["conferido_com_a_fonte_em"] == "2026-11-07T23:30:00Z"
    assert not (tmp_path / "segunda" / "censo-2022.json").exists()


def test_particao_fechada_que_muda_na_origem_para_o_pipeline(tmp_path):
    ibge.coletar(tmp_path / "primeira", pedir=fonte(), agora=AGORA)
    lista = codigos()
    alterado = {c: 900 + i for i, c in enumerate(lista[1:])}
    alterado[lista[7]] += 1
    with pytest.raises(ibge.ErroDeContrato, match="partição fechada mudou"):
        ibge.coletar(tmp_path / "segunda", tmp_path / "primeira" / "censo-2022.json", pedir=fonte(censo=alterado))


def test_censo_fora_do_ar_usa_a_release_sem_dizer_que_conferiu(tmp_path):
    ibge.coletar(tmp_path / "primeira", pedir=fonte(), agora=AGORA)
    resultado = ibge.coletar(tmp_path / "segunda", tmp_path / "primeira" / "censo-2022.json", pedir=fonte(censo_fora=True))
    assert resultado["fontes"]["censo"]["conferido_com_a_fonte_em"] is None
    segundo = next(m for m in resultado["municipios"] if m["codigo"] == codigos()[1])
    assert segundo["populacao_censo"] == 900


def test_censo_fora_do_ar_sem_release_falha(tmp_path):
    with pytest.raises(Exception, match="fora do ar"):
        ibge.coletar(tmp_path, pedir=fonte(censo_fora=True))


def test_http_de_erro_na_estimativa_para_o_pipeline(tmp_path):
    falsa = fonte()
    falsa.respostas[ibge.URL_SIDRA.format(**ibge.ESTIMATIVA)] = resposta(b"erro", status=404)
    with pytest.raises(ibge.ErroDeContrato, match="HTTP 404"):
        ibge.coletar(tmp_path, pedir=falsa)


def test_coleta_nao_usa_a_api_de_servicos_do_ibge(tmp_path):
    falsa = fonte()
    ibge.coletar(tmp_path, pedir=falsa, agora=AGORA)
    assert falsa.pedidos and not [url for url, _ in falsa.pedidos if "servicodados" in url]


def test_mudanca_detectada_pelo_hash_em_relacao_a_coleta_anterior(tmp_path):
    primeira = ibge.coletar(tmp_path / "a", pedir=fonte(), agora=AGORA)
    anterior = json.loads(json.dumps(primeira["fontes"]))
    igual = ibge.coletar(tmp_path / "b", tmp_path / "a" / "censo-2022.json", anterior, pedir=fonte(), agora=AGORA)
    assert {k: f["em_relacao_a_coleta_anterior"] for k, f in igual["fontes"].items()} == {
        "dtb": "igual", "estimativa": "igual", "censo": "igual"}
    revisada = {c: 1000 + i for i, c in enumerate(codigos())}
    revisada[codigos()[3]] += 7
    mudou = ibge.coletar(tmp_path / "c", tmp_path / "a" / "censo-2022.json", anterior, pedir=fonte(estimativa=revisada))
    assert mudou["fontes"]["estimativa"]["em_relacao_a_coleta_anterior"] == "valores_mudaram"
    nova = ibge.coletar(tmp_path / "d", tmp_path / "a" / "censo-2022.json", anterior, pedir=fonte(periodo="2027"))
    assert nova["fontes"]["estimativa"]["em_relacao_a_coleta_anterior"] == "periodo_novo"


def test_release_com_valores_que_nao_batem_com_o_proprio_hash_para(tmp_path):
    ibge.coletar(tmp_path / "primeira", pedir=fonte(), agora=AGORA)
    release = tmp_path / "primeira" / "censo-2022.json"
    guardado = json.loads(release.read_text(encoding="utf-8"))
    guardado["valores"][codigos()[2]] += 1
    release.write_text(json.dumps(guardado), encoding="utf-8")
    with pytest.raises(ibge.ErroDeContrato, match="não conferem com o hash"):
        ibge.coletar(tmp_path / "segunda", release, pedir=fonte(censo_fora=True))


def test_municipio_da_sidra_fora_da_dtb_para_com_erro_claro(tmp_path):
    estimativa = {c: 1000 + i for i, c in enumerate(codigos())} | {"5300109": 10}
    with pytest.raises(ibge.ErroDeContrato) as erro:
        ibge.coletar(tmp_path, pedir=fonte(estimativa=estimativa))
    texto = str(erro.value)
    assert "Estimativa de população: 1 município(s) na SIDRA fora da lista da DTB 2025: ['5300109']" in texto
    assert "Nada foi publicado, e o site anterior continua no ar" in texto
    assert not (tmp_path / "ibge.json").exists()


# Histórico dos valores e revisões da estimativa no mesmo período.

DEPOIS = datetime(2026, 11, 15, 0, 47, tzinfo=timezone.utc)
ORIGINAL = {c: 1000 + i for i, c in enumerate(codigos())}


def revisada():
    valores = dict(ORIGINAL)
    valores[codigos()[3]] = 1100   # de 1003: +9,67%
    valores[codigos()[5]] = 1006   # de 1005: +0,10%
    return valores


def test_valores_desde_atravessa_coletas_iguais(tmp_path):
    primeira = ibge.coletar(tmp_path / "a", pedir=fonte(), agora=AGORA)
    est = primeira["fontes"]["estimativa"]
    assert est["valores_desde"] == est["periodo_desde"] == "2026-11-07T23:30:00Z" and est["revisoes"] == []
    segunda = ibge.coletar(tmp_path / "b", tmp_path / "a" / "censo-2022.json", primeira["fontes"], pedir=fonte(), agora=DEPOIS)
    assert {k: f["valores_desde"] for k, f in segunda["fontes"].items()} == {
        "dtb": "2026-11-07T23:30:00Z", "estimativa": "2026-11-07T23:30:00Z", "censo": "2026-11-07T23:30:00Z"}


def test_manifesto_sem_historico_usa_a_data_da_coleta_anterior(tmp_path):
    # O manifesto de 08/11/2026 não tem valores_desde: a primeira coleta registrada vale como início.
    primeira = ibge.coletar(tmp_path / "a", pedir=fonte(), agora=AGORA)
    antigo = json.loads(json.dumps(primeira["fontes"]))
    for f in antigo.values():
        f.pop("valores_desde")
    antigo["estimativa"].pop("periodo_desde")
    antigo["estimativa"].pop("revisoes")
    segunda = ibge.coletar(tmp_path / "b", tmp_path / "a" / "censo-2022.json", antigo, pedir=fonte(), agora=DEPOIS)
    assert segunda["fontes"]["estimativa"]["periodo_desde"] == "2026-11-07T23:30:00Z"
    assert segunda["fontes"]["dtb"]["valores_desde"] == "2026-11-07T23:30:00Z"


def test_revisao_no_mesmo_periodo_guarda_antes_e_depois_sem_bloquear(tmp_path):
    release = tmp_path / "a" / "censo-2022.json"
    primeira = ibge.coletar(tmp_path / "a", pedir=fonte(), agora=AGORA)
    segunda = ibge.coletar(tmp_path / "b", release, primeira["fontes"], pedir=fonte(estimativa=revisada()),
                           agora=DEPOIS, publicados=lambda: dict(ORIGINAL))
    est = segunda["fontes"]["estimativa"]
    assert est["em_relacao_a_coleta_anterior"] == "valores_mudaram"
    assert est["valores_desde"] == "2026-11-15T00:47:00Z" and est["periodo_desde"] == "2026-11-07T23:30:00Z"
    (evento,) = est["revisoes"]
    assert evento["detectada_em"] == "2026-11-15T00:47:00Z" and evento["sem_detalhe_porque"] is None
    assert evento["municipios"] == [
        {"codigo": codigos()[3], "antes": 1003, "depois": 1100, "variacao_pct": 9.67},
        {"codigo": codigos()[5], "antes": 1005, "depois": 1006, "variacao_pct": 0.1}]
    assert evento["sha256_valores_antes"] == primeira["fontes"]["estimativa"]["sha256_valores"]
    assert next(m for m in segunda["municipios"] if m["codigo"] == codigos()[3])["populacao_estimada"] == 1100

    # Na coleta seguinte, igual, a revisão continua valendo; com um período novo, some.
    terceira = ibge.coletar(tmp_path / "c", release, segunda["fontes"], pedir=fonte(estimativa=revisada()), agora=DEPOIS)
    assert terceira["fontes"]["estimativa"]["revisoes"] == [evento]
    assert terceira["fontes"]["estimativa"]["valores_desde"] == "2026-11-15T00:47:00Z"
    nova = ibge.coletar(tmp_path / "d", release, terceira["fontes"], pedir=fonte(periodo="2027"), agora=DEPOIS)
    assert nova["fontes"]["estimativa"]["revisoes"] == [] and nova["fontes"]["estimativa"]["periodo_desde"] == "2026-11-15T00:47:00Z"


@pytest.mark.parametrize("publicados, motivo", [
    (None, "sem leitura do site anterior"),
    (lambda: (_ for _ in ()).throw(rede.ErroDeRede("fora do ar")), "o site anterior não respondeu (ErroDeRede: fora do ar)"),
    (lambda: {**ORIGINAL, codigos()[0]: 1}, "não tem o hash da coleta anterior"),
])
def test_revisao_sem_o_site_anterior_fica_registrada_sem_detalhe(tmp_path, publicados, motivo):
    primeira = ibge.coletar(tmp_path / "a", pedir=fonte(), agora=AGORA)
    segunda = ibge.coletar(tmp_path / "b", tmp_path / "a" / "censo-2022.json", primeira["fontes"],
                           pedir=fonte(estimativa=revisada()), agora=DEPOIS, publicados=publicados)
    (evento,) = segunda["fontes"]["estimativa"]["revisoes"]
    assert evento["municipios"] is None and motivo in evento["sem_detalhe_porque"]


def test_revisao_registra_municipio_que_saiu_ou_entrou_na_estimativa():
    antes = {"sha256_valores": sha256_valores({"1": 100, "2": 200})}
    evento = ibge.revisar(antes, {"2": 200, "3": 300}, "2026-11-15T00:47:00Z", lambda: {"1": 100, "2": 200})
    assert evento["municipios"] == [{"codigo": "1", "antes": 100, "depois": None, "variacao_pct": None},
                                    {"codigo": "3", "antes": None, "depois": 300, "variacao_pct": None}]


def test_site_anterior_so_e_lido_quando_a_estimativa_muda(tmp_path):
    lidos = []
    primeira = ibge.coletar(tmp_path / "a", pedir=fonte(), agora=AGORA, publicados=lambda: lidos.append(1))
    ibge.coletar(tmp_path / "b", tmp_path / "a" / "censo-2022.json", primeira["fontes"], pedir=fonte(), agora=DEPOIS,
                 publicados=lambda: lidos.append(1))
    assert lidos == []


def test_aviso_no_workflow_so_acima_do_limite():
    evento = {"municipios": [
        {"codigo": "1", "antes": 100, "depois": 106, "variacao_pct": 6.0},
        {"codigo": "2", "antes": 100, "depois": 105, "variacao_pct": 5.0},
        {"codigo": "3", "antes": 100, "depois": 94, "variacao_pct": -6.0},
        {"codigo": "4", "antes": None, "depois": 50, "variacao_pct": None},
        # 5,001%: arredondada para o manifesto, fica 5,0; o aviso usa a variação exata.
        {"codigo": "5", "antes": 100000, "depois": 105001, "variacao_pct": 5.0}]}
    linhas = ibge.avisos_de_revisao(evento, 5, {"1": "Um", "3": "Três", "4": "Quatro", "5": "Cinco"})
    assert linhas == ["Um (1): 100 para 106 (+6.000%), acima do limite de 5%",
                      "Três (3): 100 para 94 (-6.000%), acima do limite de 5%",
                      "Quatro (4): None para 50, município que entrou ou saiu da estimativa",
                      "Cinco (5): 100000 para 105001 (+5.001%), acima do limite de 5%"]
    (sem_detalhe,) = ibge.avisos_de_revisao({"municipios": None, "sem_detalhe_porque": "x"}, 5, {})
    assert "sem o detalhe por município: x" in sem_detalhe
