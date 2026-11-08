"""Coleta do SIH sem rede: listagem do FTP, download com .part e o contrato de cada linha do .dbf."""
import ftplib

import pytest

pytest.importorskip("pandas")

from pipeline import catalogo, sih_coleta  # noqa: E402
from pipeline.contrato import ErroDeContrato  # noqa: E402
from tests.test_dbf_reader import build_dbf  # noqa: E402

COLUNAS = catalogo.carregar()["bases"]["sih"]["coleta"]["colunas"]
CAMPOS = (("ANO_CMPT", "C", 4, 0), ("MES_CMPT", "C", 2, 0), ("ESPEC", "C", 2, 0), ("N_AIH", "C", 13, 0),
          ("IDENT", "C", 1, 0), ("CEP", "C", 8, 0), ("MUNIC_RES", "C", 6, 0), ("NASC", "C", 8, 0), ("SEXO", "C", 1, 0),
          ("VAL_TOT", "N", 14, 2), ("DT_INTER", "C", 8, 0), ("DT_SAIDA", "C", 8, 0), ("DIAG_PRINC", "C", 4, 0),
          ("MUNIC_MOV", "C", 6, 0), ("COD_IDADE", "C", 1, 0), ("IDADE", "N", 2, 0), ("DIAS_PERM", "N", 5, 0),
          ("MORTE", "N", 1, 0), ("CAR_INT", "C", 2, 0), ("CPF_AUT", "C", 11, 0), ("CNES", "C", 7, 0), ("RACA_COR", "C", 2, 0))
MUNICIPIOS = {"354850", "355030", "330455"}


def aih(**mudar):
    """Uma AIH inventada, no layout do RD de SP, competência 2603. N_AIH, CEP, nascimento e CPF são sintéticos."""
    base = {"ANO_CMPT": "2026", "MES_CMPT": "03", "ESPEC": "03", "N_AIH": "3526100000001", "IDENT": "1",
            "CEP": "11000000", "MUNIC_RES": "354850", "NASC": "19800101", "SEXO": "3", "VAL_TOT": "1234.56",
            "DT_INTER": "20260210", "DT_SAIDA": "20260215", "DIAG_PRINC": "J189", "MUNIC_MOV": "354850",
            "COD_IDADE": "4", "IDADE": "46", "DIAS_PERM": "5", "MORTE": "0", "CAR_INT": "02",
            "CPF_AUT": "00000000000", "CNES": "2025507", "RACA_COR": "03"}
    base |= mudar
    return tuple(base[nome] for nome, *_ in CAMPOS)


def converter(linhas, nome="RDSP2603.dbc"):
    return sih_coleta.converter(build_dbf(linhas, fields=CAMPOS), nome, MUNICIPIOS, COLUNAS, 5,
                                descomprimir=lambda dados: dados)


def test_converte_so_as_colunas_do_catalogo_e_o_n_aih_nao_sai():
    tabela, resumo = converter([aih(), aih(N_AIH="3526100000002", IDENT="5", DIAS_PERM="30")])
    assert "n_aih" not in [c.lower() for c in tabela.column_names]
    assert not {"cep", "nasc", "cpf_aut"} & {c.lower() for c in tabela.column_names}
    assert tabela.column("dt_saida").to_pylist() == [20260215, 20260215]
    assert tabela.column("competencia").to_pylist() == [202603, 202603]
    assert (resumo["aihs"], resumo["internacoes"], resumo["dias"]) == (2, 1, 35)


def test_alta_de_meses_antes_entra_como_veio_e_o_eixo_e_decidido_depois():
    tabela, _ = converter([aih(DT_INTER="20251001", DT_SAIDA="20251020")])
    assert tabela.column("dt_saida").to_pylist() == [20251020]


@pytest.mark.parametrize("mudar, regra", [
    ({"MES_CMPT": "04"}, "competência diferente"),
    ({"IDENT": "3"}, "IDENT fora"),
    ({"MUNIC_MOV": "330455"}, "MUNIC_MOV de outra UF"),
    ({"MUNIC_RES": "999999"}, "MUNIC_RES fora da lista"),
    ({"DT_SAIDA": "20260231"}, "DT_SAIDA inválida"),
    ({"DT_INTER": "20260220"}, "DT_INTER depois de DT_SAIDA"),
    ({"DT_SAIDA": "20260415", "DT_INTER": "20260401"}, "alta depois da competência"),
    ({"DT_SAIDA": "20250915", "DT_INTER": "20250901"}, "mais de 5 meses antes"),
    ({"DIAG_PRINC": "189"}, "DIAG_PRINC fora"),
    ({"RACA_COR": "07"}, "RACA_COR fora"),
    ({"CAR_INT": "09"}, "CAR_INT fora"),
    ({"MORTE": "2"}, "MORTE fora"),
    ({"CNES": "12345"}, "CNES fora"),
])
def test_contrato_recusa_o_arquivo_e_diz_a_regra(mudar, regra):
    with pytest.raises(ErroDeContrato, match=regra):
        converter([aih(), aih(N_AIH="3526100000002", **mudar)])


def test_chave_repetida_no_arquivo_e_recusada():
    with pytest.raises(ErroDeContrato, match="chave"):
        converter([aih(), aih()])


def test_sexo_e_idade_fora_do_dicionario_viram_ignorado_e_ficam_contados():
    _, resumo = converter([aih(SEXO="4"), aih(N_AIH="3526100000002", COD_IDADE="0")])
    assert (resumo["sexo_ignorado"], resumo["idade_ignorada"]) == (1, 1)


def test_arquivo_vazio_ou_sem_coluna_e_recusado():
    with pytest.raises(ErroDeContrato, match="sem nenhuma AIH"):
        converter([])
    poucos = tuple(c for c in CAMPOS if c[0] != "RACA_COR")
    with pytest.raises(ErroDeContrato, match="sem as colunas"):
        sih_coleta.converter(build_dbf([aih()[:-1]], fields=poucos), "RDSP2603.dbc", MUNICIPIOS, COLUNAS, 5,
                             descomprimir=lambda d: d)


def test_listagem_do_ftp_no_formato_do_iis():
    linhas = ["10-16-26  05:30PM             20522295 RDSP2608.dbc",
              "09-06-26  09:31PM             19971764 RDSP2508.dbc",
              "06-04-18  11:54AM            178091353 RDSP2017.zip"]
    arquivos = sih_coleta.ler_listagem(linhas)
    assert set(arquivos) == {"RDSP2608.dbc", "RDSP2508.dbc"}
    assert arquivos["RDSP2608.dbc"] == {"uf": "SP", "competencia": 202608, "bytes": 20522295,
                                        "modificado_no_ftp": "2026-10-16T17:30"}


class FtpFalso:
    def __init__(self, conteudo, falhas=0):
        self.conteudo, self.falhas = conteudo, falhas

    def __call__(self):
        return self

    def retrbinary(self, comando, escrever):
        if self.falhas:
            self.falhas -= 1
            escrever(self.conteudo[: len(self.conteudo) // 2])
            raise ftplib.error_temp("426 conexão caiu")
        escrever(self.conteudo)

    def close(self):
        pass


def test_download_so_troca_o_part_com_o_tamanho_da_listagem(tmp_path):
    ftp = FtpFalso(b"x" * 100, falhas=1)
    alvo = sih_coleta.baixar("RDSP2608.dbc", 100, tmp_path, conectar_ftp=ftp, dormir=lambda s: None)
    assert alvo.read_bytes() == b"x" * 100 and not (tmp_path / "RDSP2608.part").exists()


def test_download_com_tamanho_errado_falha_sem_deixar_arquivo(tmp_path):
    with pytest.raises(ErroDeContrato, match="falhou após 2 tentativas"):
        sih_coleta.baixar("RDSP2608.dbc", 101, tmp_path, conectar_ftp=FtpFalso(b"x" * 100), tentativas=2,
                          dormir=lambda s: None)
    assert not list(tmp_path.iterdir())


def test_arquivo_ja_baixado_da_mesma_versao_nao_e_baixado_de_novo(tmp_path):
    sih_coleta.baixar("RDSP2608.dbc", 10, tmp_path, conectar_ftp=FtpFalso(b"y" * 10), modificado="2026-10-16T17:30")

    def proibido():
        raise AssertionError("baixou de novo")
    alvo = sih_coleta.baixar("RDSP2608.dbc", 10, tmp_path, conectar_ftp=proibido, modificado="2026-10-16T17:30")
    assert alvo.read_bytes() == b"y" * 10
    assert sih_coleta.versao_local(alvo) == {"bytes": 10, "modificado_no_ftp": "2026-10-16T17:30"}


def test_republicacao_de_mesmo_tamanho_e_baixada_de_novo(tmp_path):
    sih_coleta.baixar("RDSP2608.dbc", 10, tmp_path, conectar_ftp=FtpFalso(b"y" * 10), modificado="2026-10-16T17:30")
    # Mesmo tamanho, conteúdo e data diferentes: a listagem nova manda baixar.
    alvo = sih_coleta.baixar("RDSP2608.dbc", 10, tmp_path, conectar_ftp=FtpFalso(b"z" * 10), modificado="2026-11-16T09:00")
    assert alvo.read_bytes() == b"z" * 10
    assert sih_coleta.versao_local(alvo)["modificado_no_ftp"] == "2026-11-16T09:00"


@pytest.mark.parametrize("modificado", ["2026-10-16T17:30", None])
def test_arquivo_sem_registro_de_versao_ou_sem_data_e_baixado_de_novo(tmp_path, modificado):
    (tmp_path / "RDSP2608.dbc").write_bytes(b"y" * 10)   # de origem desconhecida: nada prova a versão
    alvo = sih_coleta.baixar("RDSP2608.dbc", 10, tmp_path, conectar_ftp=FtpFalso(b"z" * 10), modificado=modificado)
    assert alvo.read_bytes() == b"z" * 10
