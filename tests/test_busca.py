"""A busca por município é JavaScript: os testes dela rodam no Node, sem navegador e sem rede."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

TESTE = Path(__file__).with_name("busca.test.cjs")


def test_busca_por_nome_e_por_uf():
    node = shutil.which("node")
    if node is None:
        # Nos runners do GitHub o Node já vem instalado: lá, faltar é erro, para o teste não ser pulado sem aviso.
        if os.environ.get("CI") or os.environ.get("EXIGIR_SIH") == "1":
            pytest.fail("Node não encontrado: os testes de web/busca.js não rodaram")
        pytest.skip("Node não instalado nesta máquina")
    r = subprocess.run([node, str(TESTE)], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 0, r.stderr
