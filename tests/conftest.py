"""Dados sintéticos no formato das APIs do IBGE. Nenhum teste usa rede: o socket é bloqueado."""
import json
import socket

import pytest

from pipeline import rede

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


def codigos(n=5571):
    """n códigos de 7 dígitos, distribuídos pelas 27 UFs, com prefixo de 6 dígitos único."""
    ufs = list(UFS)
    return [f"{ufs[i % 27]}{(i // 27) * 10:05d}" for i in range(n)]


def localidades(lista=None, micro_nula=()):
    itens = []
    for codigo in lista or codigos():
        uf = {"id": int(codigo[:2]), "sigla": UFS[int(codigo[:2])], "nome": f"Estado {UFS[int(codigo[:2])]}",
              "regiao": {"id": 1, "sigla": "N", "nome": "Norte"}}
        imediata = {"id": 1, "nome": "Imediata", "regiao-intermediaria": {"id": 1, "nome": "Intermediária", "UF": uf}}
        micro = None if codigo in micro_nula else {"id": 1, "nome": "Micro", "mesorregiao": {"id": 1, "nome": "Meso", "UF": uf}}
        itens.append({"id": int(codigo), "nome": f"Município {codigo}", "microrregiao": micro, "regiao-imediata": imediata})
    return itens


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


def periodos(periodo, modificacao):
    return [{"id": "2021", "literals": ["2021"], "modificacao": "24/06/2024"},
            {"id": periodo, "literals": [periodo], "modificacao": modificacao}]


def resposta(valor, status=200, cabecalhos=None):
    corpo = valor if isinstance(valor, bytes) else json.dumps(valor, ensure_ascii=False).encode()
    return rede.Resposta(status, cabecalhos or {}, corpo, 0.01)


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
