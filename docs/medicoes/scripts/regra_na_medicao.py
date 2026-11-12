"""Muda regras do SIH numa cópia do catálogo, só para medir o pipeline depois de uma mudança de regra.

    python docs/medicoes/scripts/regra_na_medicao.py <catalogo.yaml> <destino.yaml> supressao.k=6 [outra.regra=valor ...]

Cada regra é `caminho=valor`, com o caminho a partir de `bases.sih` e o valor lido como YAML. O workflow
`SIH (medição)` grava o destino por cima do catálogo do checkout do runner, que some com ele: o catálogo versionado
não muda. A chave tem de existir, para um erro de digitação não virar regra nova; `publicacao` não pode ser mudada,
e o destino só é gravado se continuar com `publicacao: {site: false}` e passar na validação do catálogo.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from pipeline import catalogo  # noqa: E402


class ErroDeRegra(ValueError):
    pass


def aplicar(cat: dict, regras: list[str]) -> dict:
    """Aplica cada `caminho=valor` em `cat["bases"]["sih"]`, no próprio dicionário, e devolve o que mudou."""
    mudou = {}
    for regra in regras:
        caminho, sinal, texto = regra.partition("=")
        partes = [p.strip() for p in caminho.strip().split(".")]
        if not sinal or not all(partes) or not texto.strip():
            raise ErroDeRegra(f"Regra {regra!r}: o formato é caminho=valor, como supressao.k=6")
        if partes[0] == "publicacao":
            raise ErroDeRegra(f"Regra {regra!r}: a medição não muda o que o catálogo manda publicar")
        no = cat["bases"]["sih"]
        for parte in partes[:-1]:
            if not isinstance(no.get(parte), dict):
                raise ErroDeRegra(f"Regra {regra!r}: bases.sih não tem {parte!r} nesse caminho")
            no = no[parte]
        if partes[-1] not in no:
            raise ErroDeRegra(f"Regra {regra!r}: bases.sih não tem a chave {caminho.strip()!r}")
        valor = yaml.safe_load(texto)
        if valor == no[partes[-1]]:
            raise ErroDeRegra(f"Regra {regra!r}: o catálogo já tem esse valor, e nada mudaria")
        mudou[caminho.strip()] = {"de": no[partes[-1]], "para": valor}
        no[partes[-1]] = valor
    return mudou


def gravar(origem: Path, destino: Path, regras: list[str]) -> dict:
    cat = catalogo.carregar(origem)
    mudou = aplicar(cat, regras)
    if cat["bases"]["sih"].get("publicacao") != {"site": False}:
        raise ErroDeRegra("O catálogo da medição tem de continuar com publicacao: {site: false} no SIH")
    catalogo.validar(cat)
    destino.write_text(yaml.safe_dump(cat, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # O que foi gravado é o que o pipeline vai ler.
    if catalogo.carregar(destino) != cat:
        raise ErroDeRegra("O catálogo gravado não é o que foi montado")
    return mudou


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    try:
        for chave, v in gravar(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]).items():
            print(f"bases.sih.{chave}: de {v['de']!r} para {v['para']!r}")
    except (ErroDeRegra, catalogo.ErroDeCatalogo) as erro:
        sys.exit(f"{erro}")
