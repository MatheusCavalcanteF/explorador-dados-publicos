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


def links_quebrados(documentos: list[Path], raiz: Path) -> tuple[list[str], int]:
    """Os links internos que não levam a lugar nenhum, como "documento: alvo", e quantos foram conferidos."""
    quebrados, conferidos = [], 0
    for documento in documentos:
        for alvo in LINK.findall("\n".join(sem_codigo(documento.read_text(encoding="utf-8")))):
            if re.match(r"[a-z]+:", alvo):
                continue
            caminho, _, ancora = alvo.partition("#")
            destino = (documento.parent / caminho).resolve() if caminho else documento
            conferidos += 1
            if not destino.exists() or (ancora and (destino.suffix != ".md" or ancora not in ancoras(destino))):
                quebrados.append(f"{documento.relative_to(raiz).as_posix()}: {alvo}")
    return quebrados, conferidos


def test_links_internos_da_documentacao_nao_quebram():
    quebrados, conferidos = links_quebrados(DOCUMENTOS, RAIZ)
    assert not quebrados, quebrados
    assert conferidos > 50


def test_link_quebrado_de_proposito_e_apontado(tmp_path):
    (tmp_path / "docs" / "plano").mkdir(parents=True)
    (tmp_path / "docs" / "dados.json").write_text("{}", encoding="utf-8")
    parte = tmp_path / "docs" / "plano" / "parte.md"
    parte.write_text("[Índice](../plano.md)\n\n## Seção única\n\n### O que as medições mudaram\n\nTexto.\n", encoding="utf-8")
    certos = ["[parte](plano/parte.md)", "[seção](plano/parte.md#seção-única)", "[acento](plano/parte.md#o-que-as-medições-mudaram)",
              "[aqui mesmo](#índice)", "[arquivo](dados.json)", "[pasta](plano/)", "[fora](https://example.org/nada.md#nada)"]
    quebrados = ["[arquivo que não existe](plano/sumiu.md)", "[seção que não existe](plano/parte.md#seção-que-saiu)",
                 "[âncora com maiúscula](plano/parte.md#Seção-única)", "[aqui mesmo, sem a seção](#não-tem)",
                 "[seção em arquivo que não é texto](dados.json#chave)", "[subiu uma pasta a menos](parte.md)"]
    indice = tmp_path / "docs" / "plano.md"
    cerca = "```\n[dentro de bloco de código](plano/nao-conta.md)\n```\n"
    indice.write_text("# Índice\n\n" + "\n".join(certos) + "\n\n" + cerca, encoding="utf-8")
    documentos = [indice, parte]
    # Conferidos: os do índice, menos o de fora do repositório, mais o link da parte de volta para o índice.
    internos = len(certos) - 1 + 1
    assert links_quebrados(documentos, tmp_path) == ([], internos)
    # Cada link quebrado, sozinho, é apontado com o documento e o alvo; os certos continuam sem aparecer.
    for link in quebrados:
        indice.write_text("# Índice\n\n" + "\n".join(certos) + "\n" + link + "\n\n" + cerca, encoding="utf-8")
        achados, conferidos = links_quebrados(documentos, tmp_path)
        assert achados == [f"docs/plano.md: {LINK.search(link).group(1)}"] and conferidos == internos + 1, link


def test_plano_tem_indice_com_todas_as_partes_e_todas_as_secoes():
    indice = (RAIZ / "docs" / "plano.md").read_text(encoding="utf-8")
    partes = sorted((RAIZ / "docs" / "plano").glob("*.md"))
    assert len(partes) >= 10
    for parte in partes:
        assert parte.read_text(encoding="utf-8").startswith("[Índice do plano](../plano.md)\n"), parte.name
        for ancora in ancoras(parte):
            assert f"(plano/{parte.name}#{ancora})" in indice, f"{parte.name}#{ancora} fora do índice"
