"""Dados sintéticos no formato das fontes do IBGE (DTB e SIDRA). Nenhum teste usa rede: o socket é bloqueado."""
import functools
import importlib.util
import io
import json
import os
import socket
import zipfile
from xml.sax.saxutils import escape

import pytest

from pipeline import rede

# Os testes do SIH precisam de requirements-sih.txt. O Publicar instala só requirements.txt e não roda
# o SIH, então neles esses módulos ficam de fora. O CI define EXIGIR_SIH=1: lá, faltar dependência é erro,
# para que nenhum teste do SIH seja pulado sem aviso.
_SIH = ("numpy", "pandas", "duckdb", "dbfread", "hypothesis", "scipy")
_FALTAM = [m for m in _SIH if importlib.util.find_spec(m) is None]
if _FALTAM and os.environ.get("EXIGIR_SIH") == "1":
    raise RuntimeError(f"EXIGIR_SIH=1, mas faltam {_FALTAM}: instale requirements-sih.txt")
collect_ignore = (["test_dbf_reader.py", "test_deducao.py", "test_medicoes.py", "test_sih_coleta.py", "test_sih_superficie.py",
                   "test_sih_tabelas.py", "test_sih_trava.py", "test_sih_versoes.py", "test_site_sih.py"]
                  if _FALTAM else [])

# Códigos reais das 27 UFs; os municípios são inventados.
UFS = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
       24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
       41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    def recusar(*args, **kwargs):
        raise AssertionError("Teste tentou usar a rede")
    monkeypatch.setattr(socket.socket, "connect", recusar)
    monkeypatch.setattr(socket, "create_connection", recusar)


@functools.lru_cache(maxsize=4)
def _codigos(n):
    ufs = list(UFS)
    return tuple(f"{ufs[i % 27]}{(i // 27) * 10:05d}" for i in range(n))


def codigos(n=5571):
    """n códigos de 7 dígitos, distribuídos pelas 27 UFs, com prefixo de 6 dígitos único. Cada chamada ganha uma lista nova."""
    return list(_codigos(n))


NOMES_UF = {"RO": "Rondônia", "AC": "Acre", "AM": "Amazonas", "RR": "Roraima", "PA": "Pará", "AP": "Amapá",
            "TO": "Tocantins", "MA": "Maranhão", "PI": "Piauí", "CE": "Ceará", "RN": "Rio Grande do Norte",
            "PB": "Paraíba", "PE": "Pernambuco", "AL": "Alagoas", "SE": "Sergipe", "BA": "Bahia",
            "MG": "Minas Gerais", "ES": "Espírito Santo", "RJ": "Rio de Janeiro", "SP": "São Paulo",
            "PR": "Paraná", "SC": "Santa Catarina", "RS": "Rio Grande do Sul", "MS": "Mato Grosso do Sul",
            "MT": "Mato Grosso", "GO": "Goiás", "DF": "Distrito Federal"}
CABECALHO_DTB = ["UF", "Nome_UF", "Região Geográfica Intermediária", "Nome Região Geográfica Intermediária",
                 "Região Geográfica Imediata", "Nome Região Geográfica Imediata", "Município",
                 "Código Município Completo", "Nome_Município"]


def linhas_dtb(lista=None, data_base="31/12/2025", cabecalho=CABECALHO_DTB):
    """Linhas no formato da planilha de municípios da DTB: título, data-base, cabeçalho e um município por linha."""
    linhas = [["TÍTULO : BET - BANCO DE ESTRUTURAS TERRITORIAIS"], ["RELATÓRIO DE DIVISÃO TERRITORIAL BRASILEIRA"],
              ["UF: 99 - BRASIL"]]
    if data_base:
        linhas.append([f"DATA BASE: {data_base}"])
    linhas.append(list(cabecalho))
    for codigo in lista or codigos():
        uf = codigo[:2]
        valores = {"UF": uf, "Nome_UF": NOMES_UF[UFS[int(uf)]], "Região Geográfica Intermediária": uf + "01",
                   "Nome Região Geográfica Intermediária": "Intermediária", "Região Geográfica Imediata": uf + "0001",
                   "Nome Região Geográfica Imediata": "Imediata", "Município": codigo[2:],
                   "Código Município Completo": codigo, "Nome_Município": f"Município {codigo}"}
        linhas.append([valores.get(c, "") for c in cabecalho])
    return linhas


def _celula_ods(texto):
    if texto == "":
        return "<table:table-cell/>"
    # Dois espaços seguidos viram <text:s/> no ODS, como o LibreOffice grava.
    corpo = escape(texto).replace("  ", ' <text:s/>')
    return f'<table:table-cell office:value-type="string"><text:p>{corpo}</text:p></table:table-cell>'


def ods(linhas):
    """Planilha .ods mínima: um zip com content.xml, células repetidas no fim de cada linha e linhas vazias no fim."""
    corpo = "".join("<table:table-row>" + "".join(_celula_ods(c) for c in linha)
                    + '<table:table-cell table:number-columns-repeated="16365"/></table:table-row>' for linha in linhas)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
           'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>'
           f'<table:table table:name="DTB_Municípios">{corpo}'
           '<table:table-row table:number-rows-repeated="1042997"><table:table-cell table:number-columns-repeated="16384"/>'
           '</table:table-row></table:table></office:spreadsheet></office:body></office:document-content>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", xml)
    return buffer.getvalue()


def dtb_zip(linhas=None, membro="RELATORIO_DTB_BRASIL_2025_MUNICIPIOS.ods", extras=("RELATORIO_DTB_BRASIL_2025_DISTRITOS.ods",)):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(membro, linhas if isinstance(linhas, bytes) else ods(linhas or linhas_dtb()))
        for nome in extras:
            z.writestr(nome, ods([["outra planilha"]]))
    return buffer.getvalue()


def indice(nomes):
    """Listagem de pasta como a do geoftp (Apache "Index of"), com os links de ordenação e o da pasta acima."""
    itens = "".join(f'<tr><td><a href="{n}">{n}</a></td><td>2026-03-26 18:38</td></tr>' for n in nomes)
    return ('<html><body><a href="https://www.ibge.gov.br/">IBGE</a><table><tr><th><a href="?C=N;O=D">Name</a></th></tr>'
            '<tr><td><a href="/organizacao_do_territorio/estrutura_territorial/">Parent Directory</a></td></tr>'
            f'{itens}</table></body></html>').encode("latin-1")


@functools.lru_cache(maxsize=8)
def _dtb_zip_de(lista):
    """O mesmo .zip para a mesma lista: gerar a planilha com 5.571 linhas é o que mais pesa nos testes."""
    return dtb_zip(linhas_dtb(list(lista) if lista else None))


@pytest.fixture(scope="session")
def dtb_lida():
    """A DTB padrão montada e lida de ponta a ponta (zip, planilha, contrato) uma vez por sessão de testes.
    Quem usa só lê: (nome da planilha, data-base, municípios)."""
    from pipeline import dtb
    return dtb.ler(_dtb_zip_de(None), "DTB teste")


def fonte_dtb(lista=None, pastas=None, corpo=None):
    """Respostas do geoftp: raiz com as pastas de ano e o .zip da mais recente."""
    from pipeline import dtb
    pastas = pastas or {"2024": ["DTB_2024.zip"], "2025": ["DTB_2025.zip"]}
    respostas = {dtb.RAIZ: resposta(indice(["1940/", *[f"{a}/" for a in pastas]]))}
    for ano, arquivos in pastas.items():
        respostas[f"{dtb.RAIZ}{ano}/"] = resposta(indice(arquivos))
        for arquivo in arquivos:
            respostas[f"{dtb.RAIZ}{ano}/{arquivo}"] = resposta(corpo or _dtb_zip_de(tuple(lista) if lista else None),
                                                               cabecalhos={"Last-Modified": "Thu, 26 Mar 2026 21:07:36 GMT"})
    return respostas


def sidra(valores, variavel, periodo, ordem=("municipio", "variavel", "periodo")):
    nomes = {"municipio": "Município", "variavel": "Variável", "periodo": "Ano"}
    cabecalho = {"NC": "Nível Territorial (Código)", "NN": "Nível Territorial", "MC": "Unidade de Medida (Código)",
                 "MN": "Unidade de Medida", "V": "Valor"}
    for i, nome in enumerate(ordem, 1):
        cabecalho[f"D{i}C"] = f"{nomes[nome]} (Código)"
        cabecalho[f"D{i}N"] = nomes[nome]
    linhas = [cabecalho]
    for codigo, valor in valores.items():
        dados = {"municipio": codigo, "variavel": str(variavel), "periodo": periodo}
        linha = {"NC": "6", "NN": "Município", "MC": "45", "MN": "Pessoas", "V": str(valor)}
        for i, nome in enumerate(ordem, 1):
            linha[f"D{i}C"] = dados[nome]
            linha[f"D{i}N"] = dados[nome]
        linhas.append(linha)
    return linhas


def resposta(valor, status=200, cabecalhos=None):
    corpo = valor if isinstance(valor, bytes) else json.dumps(valor, ensure_ascii=False).encode()
    return rede.Resposta(status, cabecalhos or {}, corpo, 0.01)


def site_falso(endereco_da_superficie, arquivo=None, raiz=200):
    """O site no ar: a superfície do SIH em `endereco_da_superficie` (404 sem `arquivo`) e a página inicial, com
    qualquer marca de consulta no fim do endereço. Outro endereço é falha de rede. Registra os pedidos."""
    from pipeline import projeto

    def pedir(url, **opcoes):
        pedir.pedidos.append((url, opcoes))
        base = url.split("?")[0]
        if base == endereco_da_superficie:
            return resposta(arquivo.read_bytes()) if arquivo is not None else resposta(b"Not Found", status=404)
        if base == projeto.SITE and raiz is not None:
            return resposta(b"<html></html>", status=raiz)
        raise rede.ErroDeRede(f"{url} fora do ar no teste")
    pedir.pedidos = []
    return pedir


class FonteFalsa:
    """Substitui rede.pedir: responde por URL e registra o que foi pedido."""

    def __init__(self, respostas):
        self.respostas = respostas
        self.pedidos = []

    def __call__(self, url, **kwargs):
        self.pedidos.append((url, kwargs))
        item = self.respostas.get(url)
        if item is None:
            raise rede.ErroDeRede(f"{url} fora do ar no teste")
        return item(url, kwargs) if callable(item) else item
