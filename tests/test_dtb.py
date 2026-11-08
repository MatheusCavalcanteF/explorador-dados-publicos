import io
import zipfile

import pytest

from pipeline import dtb
from pipeline.contrato import ErroDeContrato
from conftest import (CABECALHO_DTB, FonteFalsa, codigos, dtb_zip, fonte_dtb, indice, linhas_dtb, ods,
                      resposta)

AGORA = "2026-11-08T12:00:00Z"


def ler(linhas, membro="RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods"):
    return dtb.ler(dtb_zip(linhas, membro), "DTB teste")


def test_le_codigo_nome_uf_e_data_base():
    planilha, data_base, municipios = ler(linhas_dtb())
    assert planilha == "RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods" and data_base == "2025-12-31"
    assert len(municipios) == 5571 and [m["codigo"] for m in municipios] == sorted(codigos())
    sp = next(m for m in municipios if m["codigo"].startswith("35"))
    assert sp == {"codigo": sp["codigo"], "nome": f"Município {sp['codigo']}", "uf": "SP", "uf_nome": "São Paulo"}
    assert {m["uf"] for m in municipios} == set(dtb.UFS[c][0] for c in dtb.UFS)


def test_colunas_achadas_pelo_cabecalho_e_planilha_em_subpasta():
    # Em 2023 a planilha veio dentro de uma pasta e sem o ano no nome.
    invertido = list(reversed(CABECALHO_DTB))
    _, _, municipios = ler(linhas_dtb(cabecalho=invertido), "DTB_2023/RELATORIO_DTB_BRASIL_MUNICIPIO.ods")
    assert municipios[0]["nome"] == f"Município {sorted(codigos())[0]}"


def test_espacos_e_celulas_repetidas_do_ods():
    linhas = linhas_dtb()
    linhas[5][-1] = "Nome  com dois espaços"
    _, _, municipios = ler(linhas)
    assert "Nome  com dois espaços" in {m["nome"] for m in municipios}
    # Célula vazia repetida no meio da linha mantém a posição das seguintes.
    xml_linha = ('<table:table-row><table:table-cell office:value-type="string"><text:p>a</text:p></table:table-cell>'
                 '<table:table-cell table:number-columns-repeated="2"/>'
                 '<table:table-cell office:value-type="string"><text:p>d</text:p></table:table-cell></table:table-row>')
    with zipfile.ZipFile(io.BytesIO(ods([["x"]]))) as z:
        content = z.read("content.xml").decode()
    content = content.replace("<table:table-row>", xml_linha + "<table:table-row>", 1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("content.xml", content)
    assert dtb.linhas_ods(buffer.getvalue(), "t")[0] == ["a", "", "", "d"]


@pytest.mark.parametrize("estrago, mensagem", [
    ("sem_data_base", "DATA BASE"),
    ("sem_coluna", "nenhuma linha com as colunas"),
    ("uf_desconhecida", "UF '99' desconhecida"),
    ("nome_uf_diferente", "vem como"),
    ("codigo_de_outra_uf", "inválido para a UF"),
    ("sem_nome", "sem nome"),
    ("repetido", "repetido"),
    ("prefixo", "prefixo de 6 dígitos"),
    ("poucos", "fora do esperado"),
    ("rodape", "desconhecida"),
])
def test_recusa_estrutura_ou_dado_errado(estrago, mensagem):
    linhas = linhas_dtb(data_base=None if estrago == "sem_data_base" else "31/12/2025",
                        cabecalho=[c for c in CABECALHO_DTB if c != "Nome_UF"] if estrago == "sem_coluna" else CABECALHO_DTB)
    primeira = linhas[5] if estrago != "sem_data_base" else linhas[4]
    i = {c: CABECALHO_DTB.index(c) for c in CABECALHO_DTB}
    if estrago == "uf_desconhecida":
        primeira[i["UF"]] = "99"
    elif estrago == "nome_uf_diferente":
        primeira[i["Nome_UF"]] = "Rondonia"
    elif estrago == "codigo_de_outra_uf":
        primeira[i["Código Município Completo"]] = "35" + primeira[i["Código Município Completo"]][2:]
    elif estrago == "sem_nome":
        primeira[i["Nome_Município"]] = ""
    elif estrago == "repetido":
        linhas.append(list(primeira))
    elif estrago == "prefixo":
        # Mesmo prefixo de 6 dígitos: a conversão para SIH e CAGED ficaria ambígua.
        outra = list(primeira)
        outra[i["Código Município Completo"]] = primeira[i["Código Município Completo"]][:6] + "9"
        linhas.append(outra)
    elif estrago == "poucos":
        linhas = linhas[:5000]
    elif estrago == "rodape":
        linhas.append(["Fonte: IBGE, Diretoria de Geociências"])
    with pytest.raises(ErroDeContrato, match=mensagem):
        ler(linhas)


@pytest.mark.parametrize("data_base", ["31/02/2025", "00/12/2025", "31/13/2025", "29/02/2025"])
def test_recusa_data_base_que_nao_existe_no_calendario(data_base):
    with pytest.raises(ErroDeContrato, match="não existe no calendário"):
        ler(linhas_dtb(data_base=data_base))


def test_aceita_29_de_fevereiro_em_ano_bissexto():
    assert ler(linhas_dtb(data_base="29/02/2024"))[1] == "2024-02-29"


def test_recusa_zip_sem_planilha_ou_com_duas_e_planilha_que_nao_e_ods():
    with pytest.raises(ErroDeContrato, match="achei 0"):
        dtb.ler(dtb_zip(linhas_dtb(), "RELATORIO_DTB_BRASIL_2025_DISTRITOS.ods", extras=()), "t")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("RELATORIO_DTB_BRASIL_MUNICIPIO.ods", ods(linhas_dtb()))
        z.writestr("antigo/RELATORIO_DTB_BRASIL_MUNICIPIO.ods", ods(linhas_dtb()))
    with pytest.raises(ErroDeContrato, match="achei 2"):
        dtb.ler(buffer.getvalue(), "t")
    # Em 2022, o arquivo .ods da DTB era um .xls com outra extensão.
    with pytest.raises(ErroDeContrato, match="não é uma planilha .ods"):
        dtb.ler(dtb_zip(b"\xd0\xcf\x11\xe0" + b"\x00" * 100), "t")
    with pytest.raises(ErroDeContrato, match="não é um .zip"):
        dtb.ler(b"<html>manutencao</html>", "t")


def test_acha_a_pasta_de_ano_mais_recente():
    falsa = FonteFalsa(fonte_dtb())
    assert dtb.achar(falsa) == ("2025", f"{dtb.RAIZ}2025/DTB_2025.zip", [])


def test_pasta_nova_ainda_vazia_usa_a_anterior_e_registra():
    falsa = FonteFalsa(fonte_dtb(pastas={"2025": ["DTB_2025.zip"], "2026": []}))
    assert dtb.achar(falsa) == ("2025", f"{dtb.RAIZ}2025/DTB_2025.zip", ["2026"])


def test_pasta_com_outro_arquivo_para_em_vez_de_voltar_um_ano():
    falsa = FonteFalsa(fonte_dtb(pastas={"2025": ["DTB_2025.zip"], "2026": ["DTB_2026_v2.zip"]}))
    with pytest.raises(ErroDeContrato, match="em vez de DTB_2026.zip"):
        dtb.achar(falsa)


def test_sem_pastas_de_ano_ou_sem_arquivo_nas_recentes_falha():
    with pytest.raises(ErroDeContrato, match="não tem pastas de ano"):
        dtb.achar(FonteFalsa({dtb.RAIZ: resposta(indice(["leia-me.txt"]))}))
    vazias = FonteFalsa(fonte_dtb(pastas={"2023": ["DTB_2023.zip"], "2024": [], "2025": [], "2026": []}))
    with pytest.raises(ErroDeContrato, match=r"nas pastas \['2026', '2025', '2024'\]"):
        dtb.achar(vazias)
    with pytest.raises(ErroDeContrato, match="HTTP 404"):
        dtb.achar(FonteFalsa({dtb.RAIZ: resposta(b"", status=404)}))


def test_coleta_registra_arquivo_data_base_e_hash_dos_valores():
    fonte, municipios = dtb.coletar(FonteFalsa(fonte_dtb()), AGORA)
    assert fonte["periodo"] == "2025" and fonte["data_base"] == "2025-12-31" and fonte["municipios"] == 5571
    assert fonte["last_modified"] == "Thu, 26 Mar 2026 21:07:36 GMT" and len(fonte["sha256"]) == 64
    assert fonte["url"].endswith("2025/DTB_2025.zip") and fonte["pastas_sem_dtb"] == []
    # O hash é dos valores, não do arquivo: outro zip com a mesma lista dá o mesmo hash.
    outro = fonte_dtb(corpo=dtb_zip(linhas_dtb(), extras=()))
    fonte2, _ = dtb.coletar(FonteFalsa(outro), AGORA)
    assert fonte2["sha256"] != fonte["sha256"] and fonte2["sha256_valores"] == fonte["sha256_valores"]
    renomeado = linhas_dtb()
    renomeado[5][-1] += " (novo nome)"
    fonte3, _ = dtb.coletar(FonteFalsa(fonte_dtb(corpo=dtb_zip(renomeado))), AGORA)
    assert fonte3["sha256_valores"] != fonte["sha256_valores"]


def test_download_incompleto_para():
    respostas = fonte_dtb()
    url = f"{dtb.RAIZ}2025/DTB_2025.zip"
    respostas[url] = resposta(respostas[url].corpo[:1000], cabecalhos={"Content-Length": "1635600"})
    with pytest.raises(ErroDeContrato, match="1000 bytes recebidos de 1635600"):
        dtb.coletar(FonteFalsa(respostas), AGORA)
