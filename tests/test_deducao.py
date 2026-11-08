import numpy as np
import pytest

from pipeline import deducao as d

V, P, C, L = d.VISIVEL, d.PEQUENA, d.COMPLEMENTAR, d.LIVRE


def linha(valores, estados, margem_visivel=True, k=5):
    """Uma linha marginal: células finas e a margem, que é a soma delas."""
    s = d.Sistema(k)
    valores = np.array(valores)
    s.no("celulas", np.array(estados), valores, publicado=True)
    s.no("margem", np.array([V if margem_visivel else L]), np.array([valores.sum()]), publicado=margem_visivel)
    s.aresta("celulas", "margem", np.zeros(len(valores), dtype=int))
    s.propagar()
    s.conferir_solidez()
    return s


def test_uma_so_oculta_com_margem_visivel_e_revelada():
    s = linha([3, 10, 20], [P, V, V])
    assert s.reveladas()["celulas"]["pequenas_reveladas"] == 1


def test_motivo_publico_estreita_a_pequena_quando_as_ocultas_somam_6():
    # O exemplo do plano: uma oculta de cada tipo, soma 6. A complementar não pode ser de 1 a 4, então
    # é 5 ou 6. Como a regra também oculta pelas AIHs, a pequena pode ter 0 internação: fica 0 ou 1.
    s = linha([1, 5, 30], [P, C, V])
    no = s.nos["celulas"]
    assert list(no.lo[:2]) == [0, 5] and list(no.hi[:2]) == [1, 6]
    r = s.reveladas()["celulas"]
    assert r["pequenas_reveladas"] == 0 and r["pequenas_estreitadas"] == 1


def test_motivo_publico_fecha_as_duas_quando_as_ocultas_somam_5():
    s = linha([0, 5, 30], [P, C, V])
    assert list(s.nos["celulas"].lo[:2]) == [0, 5] and list(s.nos["celulas"].hi[:2]) == [0, 5]
    assert s.reveladas()["celulas"]["exatas"] == 2 and s.total_pequenas_reveladas() == 0


def test_duas_pequenas_com_soma_5_nao_se_revelam():
    s = linha([2, 3, 30], [P, P, V])
    assert s.reveladas()["celulas"]["pequenas_reveladas"] == 0
    assert list(s.nos["celulas"].lo[:2]) == [1, 1] and list(s.nos["celulas"].hi[:2]) == [4, 4]


def test_sem_margem_publicada_nada_se_revela():
    s = linha([3, 10, 20], [P, V, V], margem_visivel=False)
    assert s.total_pequenas_reveladas() == 0


def test_cadeia_entre_tabelas_revela_o_que_uma_tabela_sozinha_nao_revela():
    # Mês x sexo: em cada mês, as duas células ocultas protegem uma à outra. Mas o total anual por sexo,
    # de outra tabela, fecha a coluna dos homens, e a cadeia revela tudo.
    s = d.Sistema(5)
    valores = np.array([3, 2, 10, 12])         # (jan, M), (jan, F), (fev, M), (fev, F)
    s.no("mes_sexo", np.array([P, P, V, V]), valores, publicado=True)
    s.no("mes", np.array([V, V]), np.array([5, 22]), publicado=True)
    s.no("ano_sexo", np.array([V, V]), np.array([13, 14]), publicado=True)
    s.aresta("mes_sexo", "mes", np.array([0, 0, 1, 1]))
    s.aresta("mes_sexo", "ano_sexo", np.array([0, 1, 0, 1]))
    s.propagar()
    s.conferir_solidez()
    assert s.reveladas()["mes_sexo"]["pequenas_reveladas"] == 2


def test_soma_que_ninguem_publica_tambem_conta():
    # Mês x faixa é publicado; trimestre x faixa não, mas é a soma dos três meses. Com o total do
    # trimestre publicado e a outra faixa toda visível, o trimestre da faixa A fecha em 3: a contagem
    # pequena vazou por uma soma que nenhuma tabela mostra, e o mês oculto vaza junto.
    s = d.Sistema(5)
    #                    (m1,A) (m2,A) (m3,A) (m1,B) (m2,B) (m3,B)
    s.no("mes_faixa", np.array([P, V, V, V, V, V]), np.array([3, 0, 0, 10, 5, 5]), publicado=True)
    s.no("tri_faixa", np.array([L, L]), np.array([3, 20]), publicado=False)
    s.no("tri", np.array([V]), np.array([23]), publicado=True)
    s.aresta("mes_faixa", "tri_faixa", np.array([0, 0, 0, 1, 1, 1]))
    s.aresta("tri_faixa", "tri", np.array([0, 0]))
    s.propagar()
    s.conferir_solidez()
    r = s.reveladas()
    assert r["tri_faixa"]["pequenas_reveladas"] == 1 and r["mes_faixa"]["pequenas_reveladas"] == 1


def test_valor_arredondado_nao_entrega_a_diferenca():
    s = d.Sistema(5)
    # Visíveis arredondados para múltiplo de 5: 23 aparece como 25, 41 como 40.
    s.no("celulas", np.array([P, V, V]), np.array([3, 23, 41]), publicado=True,
         lo=np.array([0, 23, 38]), hi=np.array([4, 27, 42]))
    s.no("margem", np.array([V]), np.array([67]), publicado=True, lo=np.array([63]), hi=np.array([67]))
    s.aresta("celulas", "margem", np.array([0, 0, 0]))
    s.propagar()
    s.conferir_solidez()
    assert s.total_pequenas_reveladas() == 0


def test_dominio_errado_e_denunciado_em_vez_de_aceito():
    s = d.Sistema(5)
    with pytest.raises(ValueError, match="sem valor possível"):
        # Uma complementar com máximo 3 não existe: a lacuna exclui 1 a 4, e 0 está abaixo do mínimo 2.
        s.no("x", np.array([C]), np.array([0]), publicado=True, lo=np.array([2]), hi=np.array([3]))


@pytest.mark.parametrize("semente", range(40))
def test_solidez_em_tabelas_aleatorias_com_supressao_qualquer(semente):
    """O valor verdadeiro nunca sai do intervalo, com qualquer padrão de células ocultas e margens."""
    rng = np.random.default_rng(semente)
    linhas, colunas = rng.integers(2, 6, size=2)
    valores = rng.choice([0, 1, 2, 3, 4, 5, 6, 9, 15, 40], size=linhas * colunas)
    estados = np.where((valores >= 1) & (valores <= 4), P, np.where(rng.random(valores.size) < 0.3, C, V))
    s = d.Sistema(5)
    s.no("celula", estados, valores, publicado=True)
    i, j = np.divmod(np.arange(valores.size), colunas)
    soma_l = np.bincount(i, weights=valores).astype(int)
    soma_c = np.bincount(j, weights=valores).astype(int)
    vis = lambda x: np.where((x >= 1) & (x <= 4), P, V)
    s.no("linha", vis(soma_l), soma_l, publicado=True)
    s.no("coluna", vis(soma_c), soma_c, publicado=True)
    s.no("total", np.array([V]), np.array([valores.sum()]), publicado=True)
    s.aresta("celula", "linha", i)
    s.aresta("celula", "coluna", j)
    s.aresta("linha", "total", np.zeros(linhas, dtype=int))
    s.aresta("coluna", "total", np.zeros(colunas, dtype=int))
    s.propagar()
    s.conferir_solidez()


def _versao(valores, estados, k=5):
    s = d.Sistema(k)
    valores = np.array(valores)
    s.no("celulas", np.array(estados), valores, publicado=True)
    s.no("margem", np.array([V]), np.array([valores.sum()]), publicado=True)
    s.aresta("celulas", "margem", np.zeros(len(valores), dtype=int))
    s.propagar()
    return {n: (no.lo, no.hi) for n, no in s.nos.items()}, s.arestas


def test_diferenca_pequena_entre_duas_versoes_visiveis_aparece():
    a, arestas = _versao([10, 20, 30], [V, V, V])
    b, _ = _versao([13, 20, 30], [V, V, V])
    r = d.diferencas(a, b, arestas, 5)
    assert r["celulas"]["pequenas_diretas"] == 1 and r["margem"]["pequenas_diretas"] == 1


def test_diferenca_de_celula_oculta_sai_pela_cadeia_das_diferencas():
    # A célula do meio fica oculta nas duas versões, e não se revela em nenhuma delas sozinha (há
    # outra oculta na linha). Mas a margem e as outras duas visíveis mudam, e a diferença dela fecha.
    a, arestas = _versao([6, 9, 7, 40], [C, C, V, V])
    b, _ = _versao([6, 11, 7, 40], [C, C, V, V])
    r = d.diferencas(a, b, arestas, 5)
    assert r["celulas"]["pequenas_pela_cadeia"] == 0      # duas ocultas: a diferença se divide entre elas
    a, arestas = _versao([6, 9, 7, 40], [V, C, C, V])
    b, _ = _versao([6, 12, 7, 40], [V, C, C, V])
    assert d.diferencas(a, b, arestas, 5)["celulas"]["pequenas_pela_cadeia"] == 0


def test_diferenca_deduzida_quando_so_uma_celula_muda_de_valor_escondido():
    a, arestas = _versao([6, 20, 30], [C, C, V])
    b, _ = _versao([9, 20, 30], [C, C, V])
    # As duas ocultas têm intervalos largos, a diferença da margem (+3) não diz qual mudou.
    r = d.diferencas(a, b, arestas, 5)
    assert r["margem"]["pequenas_diretas"] == 1 and r["celulas"]["pequenas_pela_cadeia"] == 0
