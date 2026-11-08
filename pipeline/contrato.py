"""Erro de contrato e hash dos valores, comuns a todas as coletas."""
from __future__ import annotations

import hashlib
import json


class ErroDeContrato(ValueError):
    """O dado chegou, mas não é o que o contrato aceita. Nada é publicado."""


def sha256_valores(valores: dict) -> str:
    """Hash dos valores, não da resposta: muda só quando um número, nome ou código muda.

    A forma canônica é o JSON com chaves ordenadas e sem espaços, então a ordem das linhas
    e a formatação da resposta não alteram o hash.
    """
    texto = json.dumps(valores, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
