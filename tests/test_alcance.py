import hashlib

import pytest

from pipeline import alcance
from conftest import FonteFalsa, resposta

DBF = b"\x03\x7e\x02\x06" + b"\x00" * 60


class FtpFalso:
    def __init__(self, arquivos, conteudo=DBF, tamanho=None, falhar_conexoes=0):
        self.arquivos, self.conteudo = arquivos, conteudo
        self.tamanho = len(conteudo) if tamanho is None else tamanho
        self.falhar = falhar_conexoes
        self.pasta = []

    def __call__(self, host, timeout, encoding):
        if self.falhar:
            self.falhar -= 1
            raise ConnectionResetError("reset no teste")
        return self

    def login(self):
        pass

    def cwd(self, pasta):
        self.pasta.append(pasta)

    def nlst(self):
        return self.arquivos[self.pasta[-1]]

    def size(self, nome):
        return self.tamanho

    def voidcmd(self, comando):
        return "213 20260208171741"

    def retrbinary(self, comando, receber):
        receber(self.conteudo)

    def close(self):
        pass


SIH = {alcance.SIH_PASTA: ["RDSP2608.dbc", "RDRR2501.dbc", "RDAC9912.dbc", "leia.txt"]}


def test_datasus_confere_tamanho_cabecalho_e_hash_sem_gravar():
    resultado = alcance.datasus(FtpFalso(SIH))
    assert resultado["sha256"] == hashlib.sha256(DBF).hexdigest()
    assert resultado["modificado_na_origem"] == "2026-02-08T17:17:41Z"
    assert resultado["arquivos_rd_na_pasta"] == 3 and resultado["ultima_competencia"] == "2608"


@pytest.mark.parametrize("ftp", [FtpFalso(SIH, tamanho=999), FtpFalso(SIH, conteudo=b"<html>erro</html>")])
def test_datasus_recusa_arquivo_truncado_ou_que_nao_e_dbf(ftp):
    with pytest.raises(ValueError):
        alcance.datasus(ftp)


def test_ftp_tenta_de_novo_e_depois_desiste():
    assert alcance.datasus(FtpFalso(SIH, falhar_conexoes=2), dormir=lambda s: None)["bytes"] == len(DBF)
    with pytest.raises(Exception, match="ftp.datasus.gov.br"):
        alcance.datasus(FtpFalso(SIH, falhar_conexoes=3), dormir=lambda s: None)


def test_caged_acha_a_ultima_competencia():
    ftp = FtpFalso({alcance.CAGED_PASTA: ["2025", "2026", "Leia-me.txt"], "2026": ["202608", "202609"]})
    assert alcance.caged(ftp) == {"pasta": alcance.CAGED_PASTA, "anos": 2, "ultimo_ano": "2026",
                                  "ultima_competencia": "202609"}


def test_inep_exige_range_e_zip():
    def pedido(url, kwargs):
        if kwargs.get("metodo") == "HEAD":
            return resposta(b"", cabecalhos={"Content-Length": "33829396", "Last-Modified": "Wed, 08 Jul 2026"})
        return resposta(b"PK\x03\x04" + b"\x00" * 1020, status=206, cabecalhos={"Content-Range": "bytes 0-1023/33829396"})
    assert alcance.inep(FonteFalsa({alcance.INEP_URL: pedido}))["bytes"] == 33829396
    with pytest.raises(ValueError):
        alcance.inep(FonteFalsa({alcance.INEP_URL: resposta(b"<html>", status=200)}))


def test_uma_fonte_fora_nao_esconde_as_outras():
    def quebra():
        raise TimeoutError("sem resposta")
    resultado = alcance.executar({"boa": lambda: {"x": 1}, "ruim": quebra})
    assert resultado["fontes"]["boa"]["ok"] is True and resultado["fontes"]["boa"]["x"] == 1
    assert resultado["fontes"]["ruim"] == {"ok": False, "erro": "TimeoutError: sem resposta",
                                           "segundos_total": resultado["fontes"]["ruim"]["segundos_total"]}
