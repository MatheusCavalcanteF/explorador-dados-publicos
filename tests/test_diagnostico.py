import hashlib
import io
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
    # Conexão que nem abre não depende de pacote nem de ClientHello: não há repetição.
    assert "repeticoes" not in item


@pytest.fixture
def tls_falha(monkeypatch):
    """Conexão abre, TLS falha com o erro dado, salvo quando o grupo da lista resolve."""
    monkeypatch.setattr(diagnostico, "resolver", enderecos((V4, "10.0.0.1"), (V4, "10.0.0.2")))
    monkeypatch.setattr(diagnostico, "_mss_suportado", lambda: True)
    abertos, grupos = [], []

    def abrir(familia, sockaddr, mss=None):
        abertos.append(SocketFalso(familia, sockaddr, mss))
        return abertos[-1]

    def usar(erro, resolve_com=None):
        def tls(sock, host, grupo=None):
            grupos.append(grupo)
            if grupo is None or grupo != resolve_com:
                raise erro
            return sock, {"versao": "TLSv1.3"}

        def pedir(sock, host, caminho, alvo):
            return io.BytesIO(b"ok"), {"status": 200}
        monkeypatch.setattr(diagnostico, "_abrir", abrir)
        monkeypatch.setattr(diagnostico, "_tls", tls)
        monkeypatch.setattr(diagnostico, "_pedir", pedir)
        return diagnostico.sondar_https({"url": "https://fonte.gov.br/api"})
    usar.abertos, usar.grupos = abertos, grupos
    return usar


def test_tls_parado_repete_no_mesmo_endereco_com_clienthello_pequeno_e_mss_menor(tls_falha):
    item = tls_falha(TimeoutError("The handshake operation timed out"))
    assert item["falhou_em"] == "tls"
    assert {n: r["falhou_em"] for n, r in item["repeticoes"].items()} == {"so_x25519": "tls", "mss_1200": "tls"}
    assert [(s.sockaddr[0], s.mss) for s in tls_falha.abertos] == [
        ("10.0.0.1", None), ("10.0.0.2", None), ("10.0.0.1", None), ("10.0.0.1", diagnostico.MSS_REDUZIDO)]
    assert tls_falha.grupos == [None, "X25519", None]
    assert all(s.fechado for s in tls_falha.abertos)


def test_tls_com_reset_repete_so_com_clienthello_pequeno(tls_falha):
    item = tls_falha(ConnectionResetError(104, "Connection reset by peer"), resolve_com="X25519")
    assert item["falhou_em"] == "tls" and list(item["repeticoes"]) == ["so_x25519"]
    assert "falhou_em" not in item["repeticoes"]["so_x25519"]
    assert item["repeticoes"]["so_x25519"]["passos"]["corpo"]["bytes"] == 2
    linha = diagnostico._texto_resultado({**item, "ok": False})
    assert linha.endswith("de novo com só X25519: ok")


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
