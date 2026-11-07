import gzip
import io
import urllib.error

import pytest

from pipeline import rede


class Aberta(io.BytesIO):
    def __init__(self, corpo, status=200, cabecalhos=None):
        super().__init__(corpo)
        self.status = status
        self.headers = cabecalhos or {}


def roteiro(monkeypatch, passos):
    chamadas = []

    def urlopen(pedido, timeout):
        chamadas.append(pedido.full_url)
        passo = passos.pop(0)
        if isinstance(passo, Exception):
            raise passo
        return passo
    monkeypatch.setattr(rede.urllib.request, "urlopen", urlopen)
    return chamadas


def test_tenta_de_novo_em_falha_de_rede(monkeypatch):
    chamadas = roteiro(monkeypatch, [urllib.error.URLError("reset"), Aberta(b"ok")])
    assert rede.pedir("https://x", dormir=lambda s: None).corpo == b"ok"
    assert len(chamadas) == 2


def test_4xx_volta_sem_repetir(monkeypatch):
    erro = urllib.error.HTTPError("https://x", 404, "Not Found", {}, io.BytesIO(b"nada"))
    chamadas = roteiro(monkeypatch, [erro])
    assert rede.pedir("https://x", dormir=lambda s: None).status == 404
    assert len(chamadas) == 1


def test_5xx_esgota_as_tentativas(monkeypatch):
    erros = [urllib.error.HTTPError("https://x", 503, "Busy", {}, io.BytesIO(b"")) for _ in range(3)]
    roteiro(monkeypatch, erros)
    with pytest.raises(rede.ErroDeRede, match="HTTP 503"):
        rede.pedir("https://x", dormir=lambda s: None)


def test_descomprime_gzip_so_quando_pedido(monkeypatch):
    comprimido = gzip.compress(b'{"a": 1}')
    roteiro(monkeypatch, [Aberta(comprimido, cabecalhos={"Content-Encoding": "gzip"}),
                          Aberta(comprimido, cabecalhos={"Content-Encoding": "gzip"})])
    assert rede.pedir("https://x").corpo == b'{"a": 1}'
    assert rede.pedir("https://x", descomprimir=False).corpo == comprimido
