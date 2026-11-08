"""projeto.yaml é a única configuração com o endereço do site e do repositório."""
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from pipeline import projeto, rede

RAIZ = Path(__file__).resolve().parent.parent


def test_configuracao_do_repositorio_e_coerente():
    c = projeto.carregar()
    assert c["site"] == projeto.SITE and c["site"].startswith("https://") and c["site"].endswith("/")
    assert projeto.CAMINHO_DO_SITE == urlsplit(projeto.SITE).path == f"/{projeto.NOME_CURTO}/"
    assert rede.AGENTE == f"{projeto.NOME_CURTO} (+{projeto.REPOSITORIO})"


@pytest.mark.parametrize("texto, motivo", [
    ("repositorio: github.com/dono/nome\nsite: https://dono.github.io/nome/\n", "repositorio"),
    ("repositorio: https://github.com/dono/nome\nsite: http://dono.github.io/nome/\n", "site"),
    ("repositorio: https://github.com/dono/nome\nsite: https://dono.github.io/nome\n", "site"),
    ("repositorio: https://github.com/dono/nome\nsite: https://dono.github.io/nome/\ngoogle_search_console: ../x\n",
     "google_search_console"),
])
def test_configuracao_errada_para_com_erro_claro(tmp_path, texto, motivo):
    arquivo = tmp_path / "projeto.yaml"
    arquivo.write_text(texto, encoding="utf-8")
    with pytest.raises(projeto.ErroDeConfiguracao, match=motivo):
        projeto.carregar(arquivo)


def test_codigo_do_search_console_aceita_com_ou_sem_html(tmp_path):
    arquivo = tmp_path / "projeto.yaml"
    arquivo.write_text("repositorio: https://github.com/dono/nome\nsite: https://dono.github.io/nome/\n"
                       "google_search_console: google0123456789abcdef.html\n", encoding="utf-8")
    assert projeto.carregar(arquivo)["google_search_console"] == "google0123456789abcdef"


def test_nenhum_endereco_do_projeto_fora_da_configuracao():
    arquivos = [*RAIZ.glob("pipeline/*.py"), *RAIZ.glob("web/*.js"), *RAIZ.glob("web/*.css"),
                *RAIZ.glob("ferramentas/leitor/*.mjs"), *RAIZ.glob(".github/workflows/*.yml")]
    padrao = re.compile(r"github\.io|github\.com/MatheusCavalcanteF|explorador-(de-)?dados-publicos", re.IGNORECASE)
    achados = [f"{a.relative_to(RAIZ)}:{n}" for a in arquivos
               for n, linha in enumerate(a.read_text(encoding="utf-8").splitlines(), 1) if padrao.search(linha)]
    assert achados == []


def test_readme_aponta_para_o_endereco_configurado():
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert f"**Site:** {projeto.SITE}" in texto
    for workflow in ("ci", "publicar"):
        assert f"({projeto.REPOSITORIO}/actions/workflows/{workflow}.yml/badge.svg)" in texto
    repositorios = set(re.findall(r"github\.com/MatheusCavalcanteF/([\w.-]+)", texto))
    assert repositorios == {projeto.NOME_CURTO}
    assert "matheuscavalcantef.github.io/explorador-dados-publicos" not in texto
