"""Links internos da documentação: cada arquivo e cada seção apontados existem."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS = [RAIZ / "README.md", *sorted((RAIZ / "docs").rglob("*.md"))]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def sem_codigo(texto: str) -> list[str]:
    linhas, cerca = [], False
    for linha in texto.split("\n"):
        if linha.startswith("```"):
            cerca = not cerca
        elif not cerca:
            linhas.append(linha)
    return linhas


def ancoras(arquivo: Path) -> set[str]:
    """As âncoras que o GitHub dá aos títulos: minúsculas, sem pontuação, espaços como hífens."""
    saida = set()
    for linha in sem_codigo(arquivo.read_text(encoding="utf-8")):
        titulo = re.match(r"#{1,6} (.+)", linha)
        if titulo:
            ancora = re.sub(r"[^\w\- ]", "", titulo.group(1).strip().lower()).replace(" ", "-")
            assert ancora not in saida, f"{arquivo.name}: dois títulos com a âncora {ancora}"
            saida.add(ancora)
    return saida


def test_links_internos_da_documentacao_nao_quebram():
    quebrados, conferidos = [], 0
    for documento in DOCUMENTOS:
        for alvo in LINK.findall("\n".join(sem_codigo(documento.read_text(encoding="utf-8")))):
            if re.match(r"[a-z]+:", alvo):
                continue
            caminho, _, ancora = alvo.partition("#")
            destino = (documento.parent / caminho).resolve() if caminho else documento
            conferidos += 1
            if not destino.exists() or (ancora and (destino.suffix != ".md" or ancora not in ancoras(destino))):
                quebrados.append(f"{documento.relative_to(RAIZ).as_posix()}: {alvo}")
    assert not quebrados, quebrados
    assert conferidos > 50


def test_plano_tem_indice_com_todas_as_partes_e_todas_as_secoes():
    indice = (RAIZ / "docs" / "plano.md").read_text(encoding="utf-8")
    partes = sorted((RAIZ / "docs" / "plano").glob("*.md"))
    assert len(partes) >= 10
    for parte in partes:
        assert parte.read_text(encoding="utf-8").startswith("[Índice do plano](../plano.md)\n"), parte.name
        for ancora in ancoras(parte):
            assert f"(plano/{parte.name}#{ancora})" in indice, f"{parte.name}#{ancora} fora do índice"
