"""Superfície do SIH: o que o site mostra, o arquivo da versão no ar e a consulta a ele. Sem rede."""
import json
import shutil

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest

pytest.importorskip("pandas")

from conftest import site_falso  # noqa: E402
from test_site_sih import particoes  # noqa: E402

from pipeline import catalogo, projeto, rede, sih_superficie  # noqa: E402


@pytest.fixture(scope="module")
def cat():
    return catalogo.carregar()


@pytest.fixture(scope="module")
def _publicado(cat, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("publicado")
    sup = sih_superficie.extrair(particoes(pasta / "particoes"), cat)
    arquivo = pasta / "superficie.parquet"
    sih_superficie.gravar(sup, arquivo, cat)
    return arquivo


@pytest.fixture
def publicado(_publicado, tmp_path):
    """O arquivo da superfície de 2025 e 2026, como o pipeline grava: montado uma vez, e cada teste recebe uma cópia
    que pode alterar."""
    arquivo = tmp_path / "superficie.parquet"
    shutil.copyfile(_publicado, arquivo)
    return arquivo


def endereco(cat):
    return projeto.SITE + cat["bases"]["sih"]["superficie"]["arquivo"]


def regravar(arquivo, tabela=None, meta=None, hash_novo=True):
    """O mesmo arquivo com a tabela ou os metadados trocados; com `hash_novo`, o SHA-256 do conteúdo é refeito."""
    lido = pq.read_table(arquivo)
    antigo = json.loads(lido.schema.metadata[sih_superficie.METADADOS])
    lido = lido.replace_schema_metadata(None)
    tabela = tabela(lido) if tabela else lido
    meta = meta(antigo) if meta else antigo
    if hash_novo:
        meta["conteudo_sha256"] = sih_superficie._conteudo(tabela)
    pq.write_table(tabela.replace_schema_metadata({sih_superficie.METADADOS: json.dumps(meta)}), arquivo)


def test_detalhe_so_nos_anos_mais_recentes(cat):
    anos = [2021, 2022, 2023, 2024, 2025, 2026]
    assert set(sih_superficie.cruzamentos_do_ano(cat, 2026, anos)) == set(cat["bases"]["sih"]["superficie"]["cruzamentos"])
    assert sih_superficie.cruzamentos_do_ano(cat, 2024, anos) == {
        "sih_res_ano": ["internacoes", "obitos"], "sih_hosp_ano": ["internacoes"], "sih_res_mes": ["internacoes"]}


def test_detalhe_mantido_e_so_o_que_a_versao_no_ar_mostrava_fora_dos_mais_novos(cat):
    anos = [2023, 2024, 2025, 2026]
    no_ar = sih_superficie.Superficie(anos={
        2024: {"superficie": {"sih_res_ano": ["internacoes", "obitos"], "sih_res_ano_capitulo": ["internacoes"]}},
        2025: {"superficie": {"sih_res_ano_capitulo": ["internacoes"], "sih_res_ano_faixa12_sexo": ["internacoes"]}}})
    assert sih_superficie.detalhe_mantido(cat, 2024, anos, no_ar) == ["sih_res_ano_capitulo"]
    # 2025 ainda está entre os dois mais novos; 2023 a versão no ar não tinha; sem versão no ar, nada.
    assert sih_superficie.detalhe_mantido(cat, 2025, anos, no_ar) == []
    assert sih_superficie.detalhe_mantido(cat, 2023, anos, no_ar) == []
    assert sih_superficie.detalhe_mantido(cat, 2024, anos, None) == []
    assert set(sih_superficie.cruzamentos_do_ano(cat, 2024, anos, ["sih_res_ano_capitulo"])) == {
        "sih_res_ano", "sih_hosp_ano", "sih_res_mes", "sih_res_ano_capitulo"}

def test_arquivo_guarda_a_superficie_e_a_situacao_sem_a_lista_de_arquivos(cat, publicado):
    sup = sih_superficie.ler(publicado, cat)
    assert sorted(sup.anos) == [2025, 2026]
    # Em 2026, faixa etária x sexo não passou no critério: não está na superfície daquele ano.
    assert set(sup.anos[2026]["superficie"]) == {"sih_res_ano", "sih_hosp_ano", "sih_res_mes", "sih_res_ano_capitulo"}
    assert "arquivos" not in sup.anos[2025] and sup.anos[2026]["nao_publicados"]["sih_res_ano_faixa12_sexo"]
    mes = sup.tabela(2025, "sih_res_mes")
    assert list(mes.columns) == ["mun_res", "mes", "internacoes", "oculto", "arredondado", "preliminar"]
    assert mes["internacoes"].isna().equals(mes["oculto"])
    # Gravar de novo a mesma superfície dá os mesmos bytes.
    antes = publicado.read_bytes()
    sih_superficie.gravar(sup, publicado, cat)
    assert publicado.read_bytes() == antes


@pytest.mark.parametrize("tabela, meta, hash_novo, motivo", [
    # Valor trocado sem refazer o SHA-256 do conteúdo.
    (lambda t: t.set_column(t.schema.get_field_index("internacoes"), "internacoes",
                            pc.add(t["internacoes"], pa.scalar(5, pa.int64()))), None, False, "não confere com o SHA-256"),
    # Ano que não poderia ter ido ao ar.
    (None, lambda m: m | {"anos": m["anos"] | {"2025": m["anos"]["2025"] | {"deducao": {"rodou": True, "passou": False}}}},
     True, "2025 consta como publicado, mas o teste de dedução revelou"),
    # Linhas de um cruzamento que a situação não diz mostrar.
    (None, lambda m: m | {"anos": m["anos"] | {"2025": m["anos"]["2025"] | {"superficie": {"sih_res_ano": ["internacoes", "obitos"]}}}},
     True, "linhas de cruzamentos que a situação não diz mostrar"),
    # Valor nulo numa célula que não está oculta.
    (lambda t: t.set_column(t.schema.get_field_index("oculto"), "oculto", pc.fill_null(pc.and_(t["oculto"], pa.scalar(False)), False)),
     None, True, "valor nulo e marca de oculta não coincidem"),
    # Arredondado fora do múltiplo de 5.
    (lambda t: t.set_column(t.schema.get_field_index("internacoes"), "internacoes",
                            pc.if_else(pc.fill_null(t["arredondado"], False), pc.add(t["internacoes"], pa.scalar(1, pa.int64())),
                                       t["internacoes"])), None, True, "fora do múltiplo de 5"),
    # A mesma célula duas vezes.
    (lambda t: pa.concat_tables([t, t.slice(0, 1)]), None, True, "chave repetida"),
    # Outro formato.
    (None, lambda m: m | {"formato": 2}, True, "sem os metadados da superfície no formato 1"),
    # Registro das regras do cálculo fora do formato: hash curto, número que não é inteiro, chave faltando ou a mais.
    *[(None, lambda m, c=c: m | {"calculo": c}, True, "registro das regras do cálculo não está no formato")
      for c in ({"regras_sha256": "ab", "algoritmo_de_supressao": 1}, {"regras_sha256": "A" * 64, "algoritmo_de_supressao": 1},
                {"regras_sha256": "a" * 64, "algoritmo_de_supressao": True}, {"regras_sha256": "a" * 64},
                {"regras_sha256": "a" * 64, "algoritmo_de_supressao": 1, "outro": 1}, "a" * 64)],
])
def test_arquivo_que_nao_confere_para(cat, publicado, tabela, meta, hash_novo, motivo):
    regravar(publicado, tabela, meta, hash_novo)
    with pytest.raises(sih_superficie.ErroDeSuperficie, match=motivo):
        sih_superficie.ler(publicado, cat)


def test_registro_do_calculo_vai_e_volta(cat, publicado):
    sup = sih_superficie.ler(publicado, cat)
    # Sem o registro (uma pasta de partições não o tem), a leitura segue, e nada pode ser reaproveitado dela.
    assert sup.calculo is None
    sup.calculo = {"regras_sha256": "0123456789abcdef" * 4, "algoritmo_de_supressao": 3}
    sih_superficie.gravar(sup, publicado, cat)
    assert sih_superficie.ler(publicado, cat).calculo == sup.calculo


def test_bytes_que_nao_sao_parquet_param(cat, publicado):
    publicado.write_bytes(b"isto nao e um parquet")
    with pytest.raises(sih_superficie.ErroDeSuperficie, match="não é um Parquet legível"):
        sih_superficie.ler(publicado, cat)


def test_versao_no_ar_baixada_do_site_e_conferida(cat, publicado, tmp_path):
    pedir = site_falso(endereco(cat), publicado)
    consulta = sih_superficie.consultar(tmp_path / "no-ar", cat, pedir)
    assert consulta["existe"] and consulta["anos"] == [2025, 2026] and consulta["bytes"] == publicado.stat().st_size
    # O pedido leva uma marca de consulta, para não receber uma cópia velha do cache do host.
    assert pedir.pedidos[0][0].startswith(endereco(cat) + "?consulta=")
    sup = sih_superficie.versao_no_ar(tmp_path / "no-ar", cat)
    assert sorted(sup.anos) == [2025, 2026] and sup.tabelas.keys() == sih_superficie.ler(publicado, cat).tabelas.keys()


def test_sem_versao_no_ar_e_a_primeira_publicacao(cat, tmp_path):
    (tmp_path / "no-ar").mkdir()
    (tmp_path / "no-ar" / sih_superficie.ARQUIVO).write_bytes(b"sobra de outra execucao")
    consulta = sih_superficie.consultar(tmp_path / "no-ar", cat, site_falso(endereco(cat)))
    assert consulta["existe"] is False and consulta["anos"] == []
    assert not (tmp_path / "no-ar" / sih_superficie.ARQUIVO).exists()
    assert sih_superficie.versao_no_ar(tmp_path / "no-ar", cat) is None


@pytest.mark.parametrize("pedir, motivo", [
    # 404 no arquivo e o site também fora: não dá para dizer que a versão não existe.
    (lambda e, a: site_falso(e, None, raiz=503), "HTTP 404, e o site respondeu HTTP 503"),
    (lambda e, a: site_falso(e, None, raiz=None), "fora do ar no teste"),
    (lambda e, a: lambda url, **k: rede.Resposta(500, {}, b"", 0.1), "HTTP 500"),
    (lambda e, a: lambda url, **k: (_ for _ in ()).throw(rede.ErroDeRede("sem conexão")), "sem conexão"),
])
def test_falha_ao_consultar_para_e_nao_parece_ausencia(cat, publicado, tmp_path, pedir, motivo):
    destino = tmp_path / "no-ar"
    destino.mkdir()
    (destino / sih_superficie.CONSULTA).write_text('{"existe": false, "anos": []}', encoding="utf-8")   # de uma execução anterior
    with pytest.raises(sih_superficie.ErroDeSuperficie, match=f"Não consegui consultar a versão no ar do SIH.*{motivo}"):
        sih_superficie.consultar(destino, cat, pedir(endereco(cat), publicado))
    # Sem a consulta gravada, a etapa do SIH também para, em vez de concluir que não há versão no ar.
    assert not (destino / sih_superficie.CONSULTA).exists()
    with pytest.raises(sih_superficie.ErroDeSuperficie, match="não foi consultada"):
        sih_superficie.versao_no_ar(destino, cat)


def test_arquivo_adulterado_no_site_para_a_consulta(cat, publicado, tmp_path):
    regravar(publicado, meta=lambda m: m | {"anos": m["anos"] | {"2026": m["anos"]["2026"] | {"ano": 2027}}})
    with pytest.raises(sih_superficie.ErroDeSuperficie, match="a situação de 2026 não é a desse ano"):
        sih_superficie.consultar(tmp_path / "no-ar", cat, site_falso(endereco(cat), publicado))
    assert not (tmp_path / "no-ar" / sih_superficie.ARQUIVO).exists() and not (tmp_path / "no-ar" / sih_superficie.CONSULTA).exists()


def test_superficie_de_versao_reprovada_nao_e_gravada(cat, tmp_path):
    pasta = particoes(tmp_path / "particoes")
    caminho = pasta / "ano=2026" / "situacao.json"
    situacao = json.loads(caminho.read_text(encoding="utf-8"))
    caminho.write_text(json.dumps(situacao | {"deducao": situacao["deducao"] | {"obitos_passou": False}}), encoding="utf-8")
    sup = sih_superficie.extrair(pasta, cat)
    assert sorted(sup.anos) == [2025] and sorted(sup.reprovados) == [2026]
    with pytest.raises(sih_superficie.ErroDeSuperficie, match="não vão para a superfície"):
        sih_superficie.gravar(sup, tmp_path / "superficie.parquet", cat)
    assert not (tmp_path / "superficie.parquet").exists()
