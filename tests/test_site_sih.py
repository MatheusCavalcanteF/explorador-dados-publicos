"""Página do município com o SIH, no build local (--sih-local), sobre partições sintéticas."""
import hashlib
import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pipeline import catalogo, site
from test_site import coleta, ler

RAIZ = Path(__file__).resolve().parent.parent


def _gravar(pasta, cid, uf, ano, linhas):
    caminho = pasta / cid / f"uf={uf}" / f"ano={ano}.parquet"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    colunas = {c: [l[c] for l in linhas] for c in linhas[0]}
    pq.write_table(pa.table(colunas), caminho)


def _celula(internacoes, oculto=False, prelim=True, arred=None, **extra):
    arred = (not oculto and prelim and internacoes >= 5) if arred is None else arred
    return {"internacoes": None if oculto else internacoes, "oculto": oculto, "preliminar": prelim, "arredondado": arred} | extra


def particoes(pasta: Path) -> Path:
    """2025 (abril a dezembro preliminares) e 2026 até julho. Em 2026, faixa etária x sexo não passou no critério."""
    pasta.mkdir(parents=True, exist_ok=True)
    for ano, ultimo in ((2025, 202607), (2026, 202607)):
        prelim = [str(m) for m in range(ano * 100 + 1, min(ano * 100 + 12, ultimo) + 1) if m > 202503]
        fora = {} if ano == 2025 else {"sih_res_ano_faixa12_sexo": {"motivo": "6,3% das internações ficariam ocultas (limite: 5%)"}}
        publicados = ["sih_res_ano", "sih_hosp_ano", "sih_res_mes", "sih_res_ano_capitulo", "sih_res_ano_faixa12_sexo"]
        situacao = {"ano": ano, "coletado_em": "2026-11-08T12:00:00Z", "versao_dos_arquivos": "2026-10-16T17:30",
                    "ultimo_mes": ultimo, "ultimo_mes_fechado": 202503, "preliminares": prelim, "arredondar_multiplo": 5,
                    "publicados": [p for p in publicados if p not in fora], "nao_publicados": fora,
                    "deducao": {"rodou": True, "passou": True, "pequenas_reveladas": 0, "obitos_passou": True}}
        (pasta / f"situacao_{ano}.json").write_text(json.dumps(situacao), encoding="utf-8")
        anual = dict(dias=9000, valor=1.5e6, obitos=55, obitos_oculto=False, obitos_arredondado=True)
        _gravar(pasta, "sih_res_ano", "35", ano, [{"mun_res": "3548500"} | _celula(1235, **anual)])
        _gravar(pasta, "sih_res_ano", "42", ano, [{"mun_res": "4206504"} | _celula(0, oculto=True, dias=None, valor=None,
                                                                                   obitos=None, obitos_oculto=True,
                                                                                   obitos_arredondado=False)])
        _gravar(pasta, "sih_hosp_ano", "35", ano, [{"mun_hosp": "3548500"} | _celula(2410, **anual)])
        meses = [{"mun_res": "3548500", "mes": str(m)} | _celula(100 + m % 100, oculto=(m % 100 == 2), prelim=str(m) in prelim,
                                                                   dias=1, valor=1.0)
                 for m in range(ano * 100 + 1, min(ano * 100 + 12, ultimo) + 1)]
        _gravar(pasta, "sih_res_mes", "35", ano, meses)
        _gravar(pasta, "sih_res_ano_capitulo", "35", ano, [{"mun_res": "3548500", "capitulo": "10"} | _celula(300),
                                                           {"mun_res": "3548500", "capitulo": "15"} | _celula(0, oculto=True)])
        if ano == 2025:
            _gravar(pasta, "sih_res_ano_faixa12_sexo", "35", ano,
                    [{"mun_res": "3548500", "faixa12": "20-29", "sexo": s} | _celula(v, oculto=o)
                     for s, v, o in (("M", 40, False), ("F", 0, True), ("I", 0, True))])
    return pasta


@pytest.fixture
def com_sih(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    saida = tmp_path / "site"
    site.construir(coleta(), catalogo.carregar(), saida, execucao="local", sih_local=particoes(tmp_path / "particoes"))
    return saida


def test_sem_a_opcao_local_nao_ha_sih_no_site(tmp_path):
    saida = tmp_path / "site"
    site.construir(coleta(), catalogo.carregar(), saida, execucao="1")
    assert not (saida / "sih.js").exists()
    html = ler(saida, "municipio/3548500/index.html")
    assert "Internações no SUS" not in html and "sih.js" not in html
    assert "sih" not in json.loads(ler(saida, "versao.json"))


def test_celula_oculta_aparece_sempre_igual_e_sem_intervalo(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    # Na tabela: sem valor e com a mesma situação; no gráfico: o mesmo anel na linha de base.
    assert 'data-v="" data-s="oculto" class="oculto">oculto</td>' in html
    assert html.count('class="oculta"') >= 3
    assert "contagem_pequena" not in html and "complementar" not in html
    for pagina in com_sih.rglob("*.html"):
        texto = pagina.read_text(encoding="utf-8")
        assert not re.search(r"&lt;\s*5|<\s*5\b|menos de 5", texto), pagina
    # A regra continua explicada no painel "Fonte e método".
    assert "Contagens de 1 a 4 não são publicadas" in html and "Toda célula oculta aparece do mesmo jeito" in html


def test_preliminar_arredondado_marcado_e_taxa_com_o_valor_arredondado(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    assert 'data-v="1235" data-s="preliminar, arredondado">1.235</td>' in html
    assert "barra barra--prelim" in html and ">preliminar</text>" in html
    # Taxa de 2026: 1.235 (arredondado) / 429.528 (estimativa 2026) x 1.000; só nos anos com população do mesmo ano.
    taxa = f"{1000 * 1235 / 429528:.1f}"
    assert f'data-v="{taxa}" data-s="preliminar, arredondado"' in html
    assert "<th scope=\"row\" data-v=\"2025\">2025</th>" in html and "2026 (jan. a jul.)" in html
    # Mês fechado sai exato, sem marca; o CSV lê a situação de cada valor.
    assert 'data-v="101" data-s="">101</td>' in html


def test_cruzamento_reprovado_no_ano_diz_por_que(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    motivo = "não publicado em 2026, porque 6,3% das internações ficariam ocultas (limite: 5%)."
    assert motivo in html
    assert "<li>2026, moradores por faixa etária e sexo: 6,3% das internações ficariam ocultas (limite: 5%).</li>" in html
    assert "Por faixa etária e sexo</h5>" in html   # 2025 publicado


def test_municipio_com_tudo_oculto_abre_no_ano(com_sih):
    html = ler(com_sih, "municipio/4206504/index.html")
    assert 'data-v="" data-s="oculto" class="oculto">oculto</td>' in html
    assert "<summary>Ver por mês</summary>" in html or "Por mês da alta" in html


def test_opcao_local_para_no_ci_e_nao_toca_no_catalogo(tmp_path, monkeypatch):
    antes = hashlib.sha256((RAIZ / "catalogo" / "catalogo.yaml").read_bytes()).hexdigest()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(site.ErroBuildLocal):
        site.construir(coleta(), catalogo.carregar(), tmp_path / "site", sih_local=particoes(tmp_path / "p"))
    assert not (tmp_path / "site").exists()
    assert hashlib.sha256((RAIZ / "catalogo" / "catalogo.yaml").read_bytes()).hexdigest() == antes


def test_sih_continua_fora_da_publicacao():
    cat = catalogo.carregar()
    assert cat["bases"]["sih"]["publicacao"] == {"site": False, "releases": False}
    for workflow in (RAIZ / ".github" / "workflows").glob("*.yml"):
        texto = workflow.read_text(encoding="utf-8")
        assert "--sih-local" not in texto, workflow.name
    publicar = (RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
    assert "pipeline sih" not in publicar and "particoes" not in publicar
