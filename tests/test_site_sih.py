"""Página do município com o SIH, no build local (--sih-local), sobre partições sintéticas."""
import copy
import hashlib
import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_site import coleta, ler

from pipeline import catalogo, sih, site, site_sih

RAIZ = Path(__file__).resolve().parent.parent


def _gravar(pasta, cid, uf, linhas):
    caminho = pasta / cid / f"uf={uf}.parquet"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({c: [linha[c] for linha in linhas] for c in linhas[0]}), caminho)
    bruto = caminho.read_bytes()
    return {f"{cid}/uf={uf}.parquet": {"bytes": len(bruto), "sha256": hashlib.sha256(bruto).hexdigest()}}


def _celula(internacoes, oculto=False, prelim=True, arred=None, **extra):
    arred = (not oculto and prelim and internacoes >= 5) if arred is None else arred
    return {"internacoes": None if oculto else internacoes, "oculto": oculto, "preliminar": prelim, "arredondado": arred} | extra


def particoes(pasta: Path, fora_2025: dict | None = None) -> Path:
    """2025 (abril a dezembro preliminares) e 2026 até julho, gravados como o pipeline grava, pela troca do
    conjunto do ano. Em 2026, faixa etária x sexo não passou no critério. Herval d'Oeste (SC) não tem hospital."""
    for ano, ultimo in ((2025, 202607), (2026, 202607)):
        prelim = [str(m) for m in range(ano * 100 + 1, min(ano * 100 + 12, ultimo) + 1) if m > 202503]
        fora = dict(fora_2025 or {}) if ano == 2025 else {"sih_res_ano_faixa12_sexo": {"motivo": "6,3% das internações ficariam ocultas (limite: 5%)"}}
        publicados = ["sih_res_ano", "sih_hosp_ano", "sih_res_mes", "sih_res_ano_capitulo", "sih_res_ano_faixa12_sexo"]
        situacao = {"ano": ano, "coletado_em": "2026-11-08T12:00:00Z", "versao_dos_arquivos": "2026-10-16T17:30",
                    "ultimo_mes": ultimo, "ultimo_mes_fechado": 202503, "preliminares": prelim, "arredondar_multiplo": 5,
                    "publicados": [p for p in publicados if p not in fora], "nao_publicados": fora,
                    "deducao": {"rodou": True, "passou": True, "pequenas_reveladas": 0, "obitos_passou": True}}

        def gravar(p, ano=ano, prelim=prelim, fora=fora):
            arquivos = {}
            gravar_se = lambda cid, uf, linhas: {} if cid in fora else _gravar(p, cid, uf, linhas)
            anual = dict(dias=9000, valor=1.5e6, obitos=55, obitos_oculto=False, obitos_arredondado=True)
            arquivos |= gravar_se("sih_res_ano", "35", [{"mun_res": "3548500"} | _celula(1235, **anual)])
            arquivos |= gravar_se("sih_res_ano", "42", [{"mun_res": "4206504"} | _celula(
                0, oculto=True, dias=None, valor=None, obitos=None, obitos_oculto=True, obitos_arredondado=False)])
            arquivos |= gravar_se("sih_hosp_ano", "35", [{"mun_hosp": "3548500"} | _celula(2410, **anual)])
            meses = [{"mun_res": "3548500", "mes": str(m)} | _celula(100 + m % 100, oculto=(m % 100 == 2), prelim=str(m) in prelim,
                                                                       dias=1, valor=1.0)
                     for m in range(ano * 100 + 1, min(ano * 100 + 12, ultimo) + 1)]
            arquivos |= gravar_se("sih_res_mes", "35", meses)
            arquivos |= _gravar(p, "sih_res_ano_capitulo", "35", [{"mun_res": "3548500", "capitulo": "10"} | _celula(300),
                                                                  {"mun_res": "3548500", "capitulo": "15"} | _celula(0, oculto=True)])
            if ano == 2025:
                arquivos |= _gravar(p, "sih_res_ano_faixa12_sexo", "35",
                                    [{"mun_res": "3548500", "faixa12": "20-29", "sexo": s} | _celula(v, oculto=o)
                                     for s, v, o in (("M", 40, False), ("F", 0, True), ("I", 0, True))])
            return arquivos
        sih.gravar_ano(pasta, ano, gravar, situacao)
    return pasta


def _coleta_estimativa(periodo):
    c = copy.deepcopy(coleta())
    c["fontes"]["estimativa"]["periodo"] = periodo
    return c


@pytest.fixture
def com_sih(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    saida = tmp_path / "site"
    site.construir(_coleta_estimativa("2025"), catalogo.carregar(), saida, execucao="local",
                   sih_local=particoes(tmp_path / "particoes"))
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
    assert 'data-v="" data-s="oculto" class="oculto">oculto</td>' in html
    assert "contagem_pequena" not in html and "complementar" not in html
    for pagina in com_sih.rglob("*.html"):
        texto = pagina.read_text(encoding="utf-8")
        assert not re.search(r"&lt;\s*5|<\s*5\b|menos de 5", texto), pagina
    assert "Contagens de 1 a 4 não são publicadas" in html and "Toda célula oculta aparece do mesmo jeito" in html


def test_graficos_saem_das_tabelas_e_o_html_nao_leva_svg(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    secao = html[html.index('<section class="sih"'):html.index("</section>", html.index('<section class="sih"'))]
    assert "<svg" not in secao
    for id_, tipo in (("sih-mes", "colunas"), ("sih-cap-2025", "barras"), ("sih-idade-2025", "piramide")):
        assert f'<div id="{id_}" class="grafico-sih" data-tipo="{tipo}" data-tabela="{id_}-tab"' in secao
        assert f'<table id="{id_}-tab"' in secao
    # O gráfico mensal marca a faixa preliminar pelas linhas da tabela; a pirâmide acha as séries pelo cabeçalho.
    assert '<tr data-p=1><th scope="row" data-v="202504">abr/2025</th>' in secao
    assert 'data-serie="M">Masculino</th><th scope="col" data-serie="F">Feminino</th>' in secao


def test_preliminar_arredondado_marcado_e_taxa_so_em_ano_completo(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    assert 'data-v="1235" data-s="preliminar, arredondado">1.235</td>' in html
    # 2025 está completo e tem estimativa do mesmo ano: a taxa usa o valor arredondado.
    taxa = f"{1000 * 1235 / 429528:.1f}"
    assert f'data-v="{taxa}" data-s="preliminar, arredondado"' in html
    # 2026 só vai até julho: sem taxa, para não comparar meses com um ano inteiro.
    linha_2026 = re.search(r'<tr><th scope="row" data-v="2026">2026 \(até jul/2026\)</th>(.*?)</tr>', html).group(1)
    assert "<td>—</td>" in linha_2026
    assert 'data-v="101" data-s="">101</td>' in html


def test_um_formato_de_mes_so(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    assert "de jan/2025 a jul/2026" in html and "a partir de abr/2025" in html and "Meses fechados até mar/2025" in html
    meses = "janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
    assert not re.search(rf"\b({meses}) de 20\d\d", html)
    assert not re.search(r"\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.? de 20\d\d", html)


def test_municipio_sem_hospital_diz_isso_em_vez_de_zeros(com_sih):
    html = ler(com_sih, "municipio/4206504/index.html")
    assert "Nenhuma internação pelo SUS em hospital de Herval d&#x27;Oeste &amp; &lt;Teste&gt; de jan/2025 a jul/2026" in html
    assert "Internações nos hospitais do município" not in html
    assert "Internações nos hospitais do município" in ler(com_sih, "municipio/3548500/index.html")


def test_cruzamento_reprovado_no_ano_diz_por_que(com_sih):
    html = ler(com_sih, "municipio/3548500/index.html")
    assert "não publicado em 2026, porque 6,3% das internações ficariam ocultas (limite: 5%)." in html
    assert "<li>2026, moradores por faixa etária e sexo: 6,3% das internações ficariam ocultas (limite: 5%).</li>" in html


def test_cruzamento_retirado_do_ano_mostra_o_motivo_e_nunca_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    motivo = {"motivo": "o teste de dedução revelou contagens com ele no ano"}
    fora = {"sih_res_ano": motivo, "sih_hosp_ano": motivo, "sih_res_mes": motivo}
    saida = tmp_path / "site"
    site.construir(_coleta_estimativa("2025"), catalogo.carregar(), saida, sih_local=particoes(tmp_path / "p", fora))
    html = ler(saida, "municipio/3548500/index.html")
    linha = re.search(r'<tr><th scope="row" data-v="2025">2025</th>(.*?)</tr>', html).group(1)
    nao = '<td data-v="" data-s="não publicado" class="oculto">não publicado</td>'
    # Internações, taxa, óbitos e hospital: o motivo, em vez de zero ou de uma taxa.
    assert linha.count(nao) == 4 and 'data-v="0"' not in linha
    for nome in ("Moradores por ano", "Hospitais do município por ano", "Moradores por mês"):
        assert f"<strong>{nome}:</strong> não publicado em 2025, porque o teste de dedução revelou contagens com ele no ano." in html
    # A série mensal de 2025 também: nenhum mês como zero; 2026, publicado, segue normal.
    meses = re.findall(r'data-v="2025(\d\d)">[a-z]+/2025</th>(<td[^>]*>[^<]*</td>)', html)
    assert len(meses) == 12 and all(td == nao for _, td in meses)
    assert 'data-v="202601">jan/2026</th><td data-v="101"' in html
    # O município sem linha em 2026 continua com zero onde o cruzamento foi publicado, e sem a frase de "sem hospital",
    # porque em 2025 não dá para saber.
    herval = ler(saida, "municipio/4206504/index.html")
    assert "Nenhuma internação pelo SUS em hospital de" not in herval
    assert re.search(r'data-v="2026">2026 \(até jul/2026\)</th>.*?<td data-v="0" data-s="">0</td><td class="situacao">', herval)


def test_particao_ausente_para_o_build_e_linha_ausente_e_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("CI", raising=False)
    pasta = particoes(tmp_path / "particoes")
    # Linha ausente num arquivo que existe é zero: Herval não aparece em sih_hosp_ano, e a página diz isso.
    assert "4206504" not in pq.read_table(pasta / "ano=2025" / "sih_hosp_ano" / "uf=35.parquet").column("mun_hosp").to_pylist()
    (pasta / "ano=2025" / "sih_hosp_ano" / "uf=35.parquet").unlink()
    with pytest.raises(site_sih.ErroSIH, match=r"sih_hosp_ano.uf=35.parquet: listado em situacao.json de 2025, mas ausente"):
        site.construir(coleta(), catalogo.carregar(), tmp_path / "site", sih_local=pasta)


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
        assert "--sih-local" not in workflow.read_text(encoding="utf-8"), workflow.name
    # No Publicar, o SIH só roda se o catálogo mandar publicar, e com a versão no ar como anterior. O que
    # ele grava não vira artefato nem entra no site. Os detalhes estão em test_release.py.
    import yaml
    passos = yaml.safe_load((RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8"))["jobs"]
    for job in passos.values():
        for passo in job["steps"]:
            texto = json.dumps(passo, ensure_ascii=False)
            if "pipeline sih " in texto or "requirements-sih" in texto:
                assert passo.get("if") == "steps.sih.outputs.publicar == 'true'", passo.get("name")
            assert "particoes" not in texto and "build/sih" not in texto.replace("--trabalho build/sih --saida build/sih-medicao", "")
