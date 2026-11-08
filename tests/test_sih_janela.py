import pytest

from pipeline import catalogo, sih_janela as j

TEMPO = catalogo.carregar()["bases"]["sih"]["tempo"]


def por_uf(ultima=202608, faltando_na_ultima=("AC", "RR"), inicio=202101):
    competencias = set(j.intervalo(inicio, ultima))
    return {uf: competencias - ({ultima} if uf in faltando_na_ultima else set()) for uf in j.UFS}


def test_regra_do_plano_em_novembro_de_2026():
    jan = j.janela(por_uf(), TEMPO, 2021)
    # 2608 é a mais recente; AC e RR ainda não a têm, então a última completa é 2607.
    assert (jan.ultima_no_ftp, jan.ultima_completa) == (202608, 202607)
    # Fecha o mês M quando M + 5 <= 2608 - 12 = 2508: fechados até 2503, como diz o plano.
    assert jan.ultima_congelada == 202508 and jan.ultimo_mes_fechado == 202503
    assert jan.anos() == [2021, 2022, 2023, 2024, 2025, 2026]
    assert jan.anos_abertos() == [2025, 2026]
    assert jan.meses_preliminares(2025) == j.intervalo(202504, 202512)
    assert jan.meses_preliminares(2024) == []


def test_ano_aberto_precisa_das_competencias_ate_cinco_meses_depois_de_dezembro():
    jan = j.janela(por_uf(), TEMPO, 2021)
    assert jan.competencias_do_ano(2025) == j.intervalo(202501, 202605)
    # 2026 só vai até a última completa: 2608 espera AC e RR.
    assert jan.competencias_do_ano(2026) == j.intervalo(202601, 202607)
    # O plano contou 20 (2501 a 2608); com 2608 esperando AC e RR, são 19.
    assert len(set(jan.competencias_do_ano(2025)) | set(jan.competencias_do_ano(2026))) == 19


def test_competencia_antiga_ausente_para_o_pipeline():
    competencias = por_uf()
    competencias["SP"] = competencias["SP"] - {202403}
    with pytest.raises(ValueError, match="competências ausentes"):
        j.janela(competencias, TEMPO, 2021)


def test_uf_sem_nenhum_arquivo_para_o_pipeline():
    competencias = por_uf()
    del competencias["TO"]
    with pytest.raises(ValueError, match="TO"):
        j.janela(competencias, TEMPO, 2021)


@pytest.mark.parametrize("aamm, esperado", [("2608", 202608), ("0801", 200801), ("2512", 202512)])
def test_competencia_do_nome_do_arquivo(aamm, esperado):
    assert j.de_nome(aamm) == esperado


def test_conta_de_meses_atravessa_o_ano():
    assert j.somar(202601, -1) == 202512 and j.somar(202508, 5) == 202601
    with pytest.raises(ValueError):
        j.para_meses(202613)
