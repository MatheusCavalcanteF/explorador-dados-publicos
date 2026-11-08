"""Scripts de medição que gravam resultado versionado: o que sai deles não pode revelar grupo pequeno."""
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

RAIZ = Path(__file__).resolve().parent.parent


def carregar(nome):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "docs" / "medicoes" / "scripts" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def linha(municipio, medida, pipeline, tabnet, competencia="202503"):
    return {"regiao": "Sudeste", "municipio": municipio, "nome": "x", "visao": "hospital", "competencia": competencia,
            "medida": medida, "igual": abs(pipeline - tabnet) < 0.011, "pipeline": pipeline, "tabnet": tabnet,
            "diferenca": round(pipeline - tabnet, 2)}


def test_conferencia_do_tabnet_nao_guarda_nem_imprime_diferenca_de_1_a_4():
    conferir = carregar("conferir_tabnet_f1b")
    resultado = {
        "por_competencia": [
            linha("355030", "Internações", 61044.0, 61041.0), linha("355030", "Valor_total", 1000.5, 900.25),
            linha("355030", "Dias_permanência", 300.0, 290.0), linha("355030", "Óbitos", 20.0, 20.0),
            linha("310620", "Internações", 23311.0, 23311.0), linha("310620", "Óbitos", 900.0, 898.0),
            linha("292740", "Internações", 9000.0, 8990.0)],
        "por_data_de_internacao": [
            {"municipio": "355030", "visao": "hospital", "meses": 21, "meses_iguais": 7, "maior_diferenca": 7,
             "total_tabnet": 749495, "total_pipeline": 749526},
            {"municipio": "130260", "visao": "hospital", "meses": 18, "meses_iguais": 15, "maior_diferenca": 1,
             "total_tabnet": 162198, "total_pipeline": 162201}]}
    resumo = conferir.resumir(resultado)
    conferir.mascarar_diferencas(resultado)
    texto = json.dumps(resultado)
    # Nenhum dos valores que, subtraídos, dariam 3 ou 2 sobra no que é gravado.
    for valor in ("61044", "61041", "1000.5", "900.25", "300.0", "290.0", "898.0", "162198", "162201"):
        assert valor not in texto, valor
    sp = [r for r in resultado["por_competencia"] if r["municipio"] == "355030"]
    assert all(r["pipeline"] is None and r["tabnet"] is None and isinstance(r["diferenca"], str) for r in sp)
    # Óbitos com diferença de 1 a 4 somem sozinhos; internações iguais continuam com valor.
    bh = {r["medida"]: r for r in resultado["por_competencia"] if r["municipio"] == "310620"}
    assert bh["Internações"]["pipeline"] == 23311.0 and bh["Óbitos"]["pipeline"] is None
    # Diferença de 5 ou mais não é grupo pequeno e fica como está.
    salvador = next(r for r in resultado["por_competencia"] if r["municipio"] == "292740")
    assert (salvador["pipeline"], salvador["diferenca"]) == (9000.0, 10.0)
    manaus = next(r for r in resultado["por_data_de_internacao"] if r["municipio"] == "130260")
    assert manaus["total_pipeline"] is None and manaus["maior_diferenca"] == "1 a 4"
    assert resultado["por_data_de_internacao"][0]["total_pipeline"] == 749526
    # O resumo foi contado antes da máscara: valor retirado não vira "sem resposta".
    assert resumo["sem_resposta"] == 0 and conferir.resumir(resultado)["sem_resposta"] > 0


def test_conferencia_do_tabnet_so_imprime_progresso_sem_valores():
    fonte = (RAIZ / "docs" / "medicoes" / "scripts" / "conferir_tabnet_f1b.py").read_text(encoding="utf-8")
    impressoes = [l.strip() for l in fonte.splitlines() if "print(" in l]
    assert not any("linha" in l or "calc" in l or "oficial" in l or "total" in l.replace("total(", "") for l in impressoes), impressoes
    # A máscara vem antes de gravar e de imprimir o resumo.
    corpo = fonte[fonte.index("def main():"):]
    assert corpo.index("mascarar_diferencas(resultado)") < corpo.index("saida.write_text")


def test_contagem_pequena_com_diferenca_grande_nao_volta_pela_subtracao():
    conferir = carregar("conferir_tabnet_f1b")
    g = conferir.guardado
    # Como a coleta grava: a contagem de 1 a 4 já sai como "<5", mas a diferença foi calculada com o valor real.
    def coletada(municipio, medida, pipeline, tabnet):
        return {"municipio": municipio, "visao": "residencia", "competencia": "202601", "medida": medida,
                "igual": pipeline == tabnet, "pipeline": g(pipeline), "tabnet": g(tabnet), "diferenca": pipeline - tabnet}
    resultado = {
        "por_competencia": [
            coletada("120020", "Internações", 3.0, 10.0), coletada("120020", "Valor_total", 900.0, 3000.0),
            coletada("120020", "Óbitos", 0.0, 0.0),
            coletada("220800", "Internações", 800.0, 800.0), coletada("220800", "Óbitos", 2.0, 12.0),
            coletada("220800", "Dias_permanência", 4000.0, 4000.0)],
        "por_data_de_internacao": [{"municipio": "220800", "visao": "residencia", "meses": 12, "meses_iguais": 11,
                                    "maior_diferenca": 9, "total_tabnet": 12, "total_pipeline": 3}]}
    conferir.mascarar_diferencas(resultado)
    acre = [r for r in resultado["por_competencia"] if r["municipio"] == "120020"]
    # Internações com "<5": o grupo inteiro sai, sem os valores nem as diferenças (-7 e -2.100 devolveriam 3).
    assert all(r["pipeline"] is None and r["tabnet"] is None and isinstance(r["diferenca"], str) for r in acre)
    picos = {r["medida"]: r for r in resultado["por_competencia"] if r["municipio"] == "220800"}
    # Óbitos com "<5" e diferença de 10: só a linha de óbitos sai; as internações do grupo continuam.
    assert picos["Óbitos"]["diferenca"] == "omitida: contagem de 1 a 4" and picos["Óbitos"]["tabnet"] is None
    assert picos["Internações"]["pipeline"] == 800.0 and picos["Dias_permanência"]["diferenca"] == 0.0
    total = resultado["por_data_de_internacao"][0]
    assert total["total_pipeline"] is None and total["total_tabnet"] is None
    assert total["diferenca_total"] == "omitida: contagem de 1 a 4"
    # Nenhuma linha guarda "<5" ao lado de uma diferença exata.
    assert not any(isinstance(r["diferenca"], (int, float)) and "<5" in (r["pipeline"], r["tabnet"])
                   for r in resultado["por_competencia"])


def test_mascara_aplicada_duas_vezes_da_o_mesmo_resultado():
    import copy

    conferir = carregar("conferir_tabnet_f1b")
    resultado = {"por_competencia": [linha("355030", "Internações", 61044.0, 61041.0), linha("355030", "Óbitos", 20.0, 20.0)],
                 "por_data_de_internacao": [{"municipio": "130260", "visao": "hospital", "meses": 18, "meses_iguais": 15,
                                             "maior_diferenca": 1, "total_tabnet": 162198, "total_pipeline": 162201},
                                            {"municipio": "120020", "visao": "hospital", "erro": "eixo ausente"}]}
    conferir.mascarar_diferencas(resultado)
    uma_vez = copy.deepcopy(resultado)
    conferir.mascarar_diferencas(resultado)
    assert resultado == uma_vez
