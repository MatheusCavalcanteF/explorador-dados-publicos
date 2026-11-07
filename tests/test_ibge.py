import json
from datetime import datetime, timezone

import pytest

from pipeline import ibge
from conftest import FonteFalsa, codigos, localidades, periodos, resposta, sidra

AGORA = datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)


def fonte(estimativa=None, censo=None, censo_fora=False, lista=None):
    lista = lista or codigos()
    estimativa = {c: 1000 + i for i, c in enumerate(lista)} if estimativa is None else estimativa
    censo = {c: 900 + i for i, c in enumerate(lista[1:])} if censo is None else censo
    urls = {
        ibge.URL_LOCALIDADES: resposta(localidades(lista, micro_nula={lista[0]})),
        ibge.URL_SIDRA.format(**ibge.ESTIMATIVA): resposta(sidra(estimativa, 9324, "2026")),
        ibge.URL_PERIODOS.format(tabela=6579): resposta(periodos("2026", "28/08/2026")),
    }
    if not censo_fora:
        urls[ibge.URL_SIDRA.format(**ibge.CENSO)] = resposta(sidra(censo, 93, "2022"))
        urls[ibge.URL_PERIODOS.format(tabela=4714)] = resposta(periodos("2022", "07/05/2026"))
    return FonteFalsa(urls)


def corpo(valor):
    return json.dumps(valor, ensure_ascii=False).encode()


def test_localidades_aceita_microrregiao_nula_e_ordena():
    lista = codigos()
    municipios = ibge.ler_localidades(corpo(localidades(list(reversed(lista)), micro_nula={lista[5]})))
    assert len(municipios) == 5571
    assert [m["codigo"] for m in municipios] == sorted(lista)
    assert {m["uf"] for m in municipios} == {"RO", "AC", "AM", "RR", "PA", "AP", "TO", "MA", "PI", "CE", "RN", "PB",
                                              "PE", "AL", "SE", "BA", "MG", "ES", "RJ", "SP", "PR", "SC", "RS", "MS",
                                              "MT", "GO", "DF"}


@pytest.mark.parametrize("estrago", ["repetido", "prefixo", "uf_errada", "sem_uf", "poucos"])
def test_localidades_recusa_dado_errado(estrago):
    itens = localidades()
    if estrago == "repetido":
        itens.append(dict(itens[0]))
    elif estrago == "prefixo":
        # Mesmo prefixo de 6 dígitos: a conversão para SIH e CAGED ficaria ambígua.
        itens.append({**itens[0], "id": itens[0]["id"] + 1})
    elif estrago == "uf_errada":
        itens[0] = {**itens[0], "id": int("99" + str(itens[0]["id"])[2:])}
    elif estrago == "sem_uf":
        itens[0] = {k: v for k, v in itens[0].items() if k != "regiao-imediata"}
    elif estrago == "poucos":
        itens = itens[:5000]
    with pytest.raises(ibge.ErroDeContrato):
        ibge.ler_localidades(corpo(itens))


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


def test_modificacao_vira_data_iso():
    assert ibge.ler_modificacao(corpo(periodos("2026", "28/08/2026")), "2026", "t") == "2026-08-28"
    with pytest.raises(ibge.ErroDeContrato):
        ibge.ler_modificacao(corpo(periodos("2025", "28/08/2026")), "2026", "t")


def test_primeira_coleta_grava_arquivo_para_a_release(tmp_path):
    resultado = ibge.coletar(tmp_path, pedir=fonte(), agora=AGORA)
    assert resultado["coletado_em"] == "2026-11-07T23:30:00Z"
    censo = resultado["fontes"]["censo"]
    assert censo["origem"] == "fonte" and censo["ausentes"] == [sorted(codigos())[0]]
    assert resultado["municipios"][0]["populacao_censo"] is None
    assert resultado["fontes"]["estimativa"]["modificacao_na_origem"] == "2026-08-28"
    novo = json.loads((tmp_path / "censo-2022.json").read_text(encoding="utf-8"))
    assert len(novo["valores"]) == 5570 and novo["sha256"] == censo["sha256"]
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
