import hashlib
import json
import socket
import time
from urllib.parse import urlsplit

import pytest

from pipeline import diagnostico

V4, V6 = socket.AF_INET, socket.AF_INET6


class SocketFalso:
    def __init__(self, familia, sockaddr, mss=None):
        self.familia, self.sockaddr, self.mss = familia, sockaddr, mss
        self.fechado = False

    def settimeout(self, tempo):
        pass

    def close(self):
        self.fechado = True


def enderecos(*lista):
    return lambda host, porta: ([(f, (ip, porta)) for f, ip in lista],
                                {"enderecos": [{"endereco": ip, "familia": "IPv6" if f == V6 else "IPv4"} for f, ip in lista]})


def test_dns_sem_resposta_tem_tempo_limite():
    def lento(*args, **kwargs):
        time.sleep(2)
    inicio = time.monotonic()
    with pytest.raises(TimeoutError):
        diagnostico.resolver("x", 443, tempo=0.05, consultar=lento)
    assert time.monotonic() - inicio < 1


def test_dns_tira_enderecos_repetidos():
    respostas = [(V4, 1, 6, "", ("10.0.0.1", 443)), (V4, 1, 6, "", ("10.0.0.1", 443)), (V6, 1, 6, "", ("::1", 443, 0, 0))]
    lista, detalhe = diagnostico.resolver("x", 443, consultar=lambda *a, **k: respostas)
    assert [s[0] for _, s in lista] == ["10.0.0.1", "::1"]
    assert [e["familia"] for e in detalhe["enderecos"]] == ["IPv4", "IPv6"]


def test_conexao_recusada_para_a_fonte_e_testa_no_maximo_dois_por_familia(monkeypatch):
    monkeypatch.setattr(diagnostico, "resolver", enderecos((V4, "10.0.0.1"), (V4, "10.0.0.2"), (V4, "10.0.0.3"), (V6, "::1")))

    def recusar(familia, sockaddr, mss=None):
        raise TimeoutError("timed out")
    monkeypatch.setattr(diagnostico, "_abrir", recusar)
    item = diagnostico.sondar_https({"url": "https://fonte.gov.br/api"})
    assert item["falhou_em"] == "conexao" and "tls" not in item["passos"]
    assert [t["endereco"] for t in item["passos"]["conexao"]["tentativas"]] == ["10.0.0.1", "10.0.0.2", "::1"]
    # Conexão que nem abre não é problema de tamanho de pacote: não repete com MSS menor.
    assert "com_mss_reduzido" not in item


def test_tls_parado_repete_com_mss_menor_no_mesmo_endereco(monkeypatch):
    monkeypatch.setattr(diagnostico, "resolver", enderecos((V4, "10.0.0.1"), (V4, "10.0.0.2")))
    abertos = []

    def abrir(familia, sockaddr, mss=None):
        abertos.append(SocketFalso(familia, sockaddr, mss))
        return abertos[-1]

    def tls_parado(sock, host):
        raise TimeoutError("The handshake operation timed out")
    monkeypatch.setattr(diagnostico, "_abrir", abrir)
    monkeypatch.setattr(diagnostico, "_tls", tls_parado)
    monkeypatch.setattr(diagnostico, "_mss_suportado", lambda: True)
    item = diagnostico.sondar_https({"url": "https://fonte.gov.br/api"})
    assert item["falhou_em"] == "tls"
    assert item["com_mss_reduzido"]["falhou_em"] == "tls"
    assert [(s.sockaddr[0], s.mss) for s in abertos] == [("10.0.0.1", None), ("10.0.0.2", None),
                                                       ("10.0.0.1", diagnostico.MSS_REDUZIDO)]
    assert all(s.fechado for s in abertos)


class FtpFalso:
    def __init__(self, conteudo, tamanho=None):
        self.conteudo = conteudo
        self.tamanho = len(conteudo) if tamanho is None else tamanho

    def __call__(self, timeout, encoding):
        return self

    def connect(self, host, porta):
        return "220 bem-vindo"

    def login(self):
        return "230 ok"

    def cwd(self, pasta):
        self.pasta = pasta
        return "250 ok"

    def nlst(self):
        return ["RDRR2501.dbc", "RDSP2608.dbc"]

    def size(self, nome):
        return self.tamanho

    def retrbinary(self, comando, receber):
        receber(self.conteudo[:3])
        receber(self.conteudo[3:])

    def close(self):
        pass


@pytest.fixture
def ftp_falso(monkeypatch):
    monkeypatch.setattr(diagnostico, "resolver", enderecos((V4, "10.0.0.9")))
    monkeypatch.setattr(diagnostico, "_abrir", SocketFalso)

    def usar(ftp):
        monkeypatch.setattr(diagnostico.ftplib, "FTP", ftp)
        return diagnostico.sondar_ftp({"url": "ftp://ftp.fonte.gov.br/dados/RDRR2501.dbc"})
    return usar


def test_ftp_baixa_na_memoria_e_guarda_so_tamanho_e_hash(ftp_falso):
    conteudo = b"\x03linha de internacao"
    item = ftp_falso(FtpFalso(conteudo))
    assert "falhou_em" not in item
    assert item["passos"]["listagem"]["itens"] == 2
    assert item["passos"]["download"]["bytes"] == len(conteudo)
    assert item["passos"]["download"]["sha256"] == hashlib.sha256(conteudo).hexdigest()
    assert "linha de internacao" not in json.dumps(item)


def test_ftp_recusa_download_truncado(ftp_falso):
    item = ftp_falso(FtpFalso(b"\x03abc", tamanho=999))
    assert item["falhou_em"] == "download" and "de 999" in item["passos"]["download"]["erro"]


def test_uma_fonte_fora_nao_interrompe_as_outras():
    def sonda(alvo):
        host = urlsplit(alvo["url"]).hostname
        if host == "quebrada":
            raise RuntimeError("defeito na sonda")
        passos = {"dns": {"ok": True, "ms": 3, "enderecos": [{"endereco": "10.0.0.1", "familia": "IPv4"}]}}
        if host == "fora":
            passos["conexao"] = {"ok": False, "ms": 10000, "erro": "_Falha: nenhum de 1 endereços abriu",
                                 "tentativas": [{"endereco": "10.0.0.1", "familia": "IPv4", "ok": False, "ms": 10000,
                                                 "erro": "TimeoutError: timed out"}]}
            return {"url": alvo["url"], "host": host, "passos": passos, "falhou_em": "conexao"}
        return {"url": alvo["url"], "host": host, "passos": passos}
    alvos = [{"nome": "fora", "url": "https://fora/"}, {"nome": "quebrada", "url": "ftp://quebrada/"},
             {"nome": "boa", "url": "https://boa/"}]
    resultado = diagnostico.executar(alvos, {"https": sonda, "ftp": sonda})
    fontes = resultado["fontes"]
    assert list(fontes) == ["fora", "quebrada", "boa"]
    assert fontes["boa"]["ok"] is True
    assert fontes["fora"]["ok"] is False and fontes["fora"]["falhou_em"] == "conexao"
    assert fontes["quebrada"]["falhou_em"] == "diagnostico" and "defeito na sonda" in fontes["quebrada"]["erro"]

    texto = diagnostico.resumo(resultado)
    linhas = {linha.split(" | ")[0]: linha for linha in texto.splitlines() if linha.startswith("| `")}
    assert set(linhas) == {"| `fora`", "| `quebrada`", "| `boa`"}
    assert "IPv4 falhou em 10,0 s" in linhas["| `fora`"] and "**falhou em conexao**" in linhas["| `fora`"]
    assert linhas["| `boa`"].endswith("| ok |")


def test_resumo_escapa_barra_vertical_do_erro():
    resultado = {"conferido_em": "2026-11-07T00:00:00Z", "fontes": {},
                 "ambiente": {"sistema": "Linux", "python": "3.14", "openssl": "OpenSSL 3", "github_actions": True}}
    resultado["fontes"]["x"] = {"url": "https://x/", "host": "x", "ok": False, "falhou_em": "diagnostico",
                                "erro": "a | b", "passos": {}, "ms_total": 5}
    linha = next(linha for linha in diagnostico.resumo(resultado).splitlines() if linha.startswith("| `x`"))
    assert "a \\| b" in linha and linha.count(" | ") == 6
