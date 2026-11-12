"""O número do algoritmo de supressão acompanha o código que decide as células publicadas do SIH. Sem rede.

A versão no ar registra o número (supressao.ALGORITMO_DE_SUPRESSAO), e uma versão calculada com outro número não
tem nenhum ano fechado reaproveitado (sih_reaproveitamento). Um número esquecido deixaria anos fechados calculados
com o código antigo no ar. Por isso este teste guarda, para cada número, a impressão do código: a árvore sintática
dos módulos abaixo, sem docstrings nem comentários. Se o código mudar e o teste falhar:
- se alguma célula publicada, ou o veredito de algum teste de dedução, pode mudar, suba o número e registre a
  impressão nova para ele;
- se não pode (refatoração sem efeito no resultado), troque só a impressão do número atual.
"""
import ast
import hashlib
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
# Módulos inteiros: conversão dos arquivos, janela, tabelas, supressão, reforço, testes de dedução e ataque conjunto.
MODULOS = ("sih_coleta", "sih_janela", "sih_tabelas", "supressao", "deducao", "sih_deducao", "deducao_lp", "sih_versoes")
# Do sih.py, só o que decide as células e o veredito de cada ano; o resto é orquestração e medição.
DO_SIH = ("COLUNA_DA_METRICA", "NAO_SAEM", "tabelas_publicaveis", "resumo_supressao", "reprovados", "dependentes",
          "catalogo_sem", "fixas_da_anterior", "suprimir_publicaveis", "_suprimir_com_situacao_fixa", "d_de",
          "construir_ano", "ler_anterior", "anterior_do_ano")
IMPRESSOES = {1: "15cd4608422d020dec15adc4f8eb5d96bffdcc1bbd0a7017e482c91a54596614"}


def _sem_docstrings(arvore: ast.AST) -> ast.AST:
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if (isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and corpo
                and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)):
            no.body = corpo[1:] or [ast.Pass()]
    return arvore


def _nomes(no: ast.stmt) -> set[str]:
    if isinstance(no, (ast.FunctionDef, ast.ClassDef)):
        return {no.name}
    if isinstance(no, ast.Assign):
        return {t.id for t in no.targets if isinstance(t, ast.Name)}
    return set()


def impressao() -> str:
    partes = [ast.dump(_sem_docstrings(ast.parse((PIPELINE / f"{m}.py").read_text(encoding="utf-8")))) for m in MODULOS]
    sih = _sem_docstrings(ast.parse((PIPELINE / "sih.py").read_text(encoding="utf-8")))
    trechos = {nome: no for no in sih.body for nome in _nomes(no) if nome in DO_SIH}
    assert set(trechos) == set(DO_SIH), f"sem estes nomes em sih.py: {sorted(set(DO_SIH) - set(trechos))}"
    partes += [ast.dump(trechos[nome]) for nome in DO_SIH]
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()


def _numero() -> int:
    """supressao.ALGORITMO_DE_SUPRESSAO, lido do código-fonte, sem importar o numpy."""
    for no in ast.parse((PIPELINE / "supressao.py").read_text(encoding="utf-8")).body:
        if isinstance(no, ast.Assign) and "ALGORITMO_DE_SUPRESSAO" in _nomes(no):
            return ast.literal_eval(no.value)
    raise AssertionError("supressao.py sem ALGORITMO_DE_SUPRESSAO")


def test_algoritmo_de_supressao_acompanha_o_codigo():
    numero, atual = _numero(), impressao()
    assert numero in IMPRESSOES, f"Registre em IMPRESSOES a impressão do algoritmo {numero}: {atual}"
    assert IMPRESSOES[numero] == atual, (
        f"O código que decide as células publicadas do SIH mudou, e o algoritmo continua no número {numero}. Se "
        "alguma célula publicada ou o veredito de algum teste pode mudar, suba supressao.ALGORITMO_DE_SUPRESSAO e "
        f"registre esta impressão para o número novo; se não, troque a do número atual: {atual}")


def test_docstring_e_comentario_nao_mudam_a_impressao(tmp_path, monkeypatch):
    original = impressao()
    copia = tmp_path / "pipeline"
    copia.mkdir()
    for arquivo in PIPELINE.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        if arquivo.stem == "supressao":
            texto = texto.replace('"""Supressão por família', '"""Outra frase. Supressão por família', 1)
            texto = texto.replace("\ndef pequena(", "\n# comentário novo\ndef pequena(", 1)
        (copia / arquivo.name).write_text(texto, encoding="utf-8")
    monkeypatch.setitem(globals(), "PIPELINE", copia)
    assert impressao() == original
    texto = (copia / "supressao.py").read_text(encoding="utf-8")
    (copia / "supressao.py").write_text(texto.replace("valores < k", "valores <= k", 1), encoding="utf-8")
    assert impressao() != original
