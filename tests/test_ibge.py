import json
from datetime import datetime, timezone

import pytest

from pipeline import ibge
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


def test_municipio_da_sidra_fora_da_dtb_para(tmp_path):
    estimativa = {c: 1000 + i for i, c in enumerate(codigos())} | {"5300109": 10}
    with pytest.raises(ibge.ErroDeContrato, match="fora da lista da DTB"):
        ibge.coletar(tmp_path, pedir=fonte(estimativa=estimativa))
