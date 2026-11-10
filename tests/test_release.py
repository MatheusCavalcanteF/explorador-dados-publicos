"""Consulta às Releases: "não existe" segue, "não consegui consultar" para. Tudo com respostas falsas, sem rede."""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from conftest import FonteFalsa, resposta

from pipeline import __main__ as cli
from pipeline import projeto, release, sih_particoes

RAIZ = Path(__file__).resolve().parent.parent
LISTA = f"{release.API}/releases?per_page=100&page=1"
CENSO = b'{"periodo": "2022", "valores": {"3548500": 418608}}'


def arquivo(tag, nome, corpo, **troca):
    return {"name": nome, "size": len(corpo), "digest": "sha256:" + hashlib.sha256(corpo).hexdigest(),
            "browser_download_url": f"{projeto.REPOSITORIO}/releases/download/{tag}/{nome}"} | troca


def fonte(releases, corpos=None, lista=None):
    """Respostas da API e dos downloads. `corpos` troca o que um endereço de download devolve."""
    respostas = {}
    for r in releases:
        for a in r["assets"]:
            respostas[a["browser_download_url"]] = resposta(a.pop("_corpo"))
    respostas[LISTA] = resposta(releases) if lista is None else lista
    return FonteFalsa(respostas | (corpos or {}))


def release_do_censo(**troca):
    return {"tag_name": "ibge-censo-2022", "draft": False,
            "assets": [arquivo("ibge-censo-2022", "censo-2022.json", CENSO, _corpo=CENSO, **troca)]}


def ano_publicado(particoes, ano=2025, **deducao):
    """A partição de um ano, com um arquivo qualquer no lugar do Parquet: aqui só importam nomes e hashes."""
    def gravar(pasta):
        corpo = f"dados de {ano}".encode()
        (pasta / "sih_res_ano").mkdir()
        (pasta / "sih_res_ano" / "uf=35.parquet").write_bytes(corpo)
        return {"sih_res_ano/uf=35.parquet": {"bytes": len(corpo), "gzip": 1, "sha256": hashlib.sha256(corpo).hexdigest()}}
    situacao = {"ano": ano, "publicados": ["sih_res_ano"], "nao_publicados": {},
                "deducao": {"rodou": True, "passou": True, "obitos_passou": True} | deducao}
    sih_particoes.gravar_ano(particoes, ano, gravar, situacao)
    return particoes


def release_do_sih(ano, pacote):
    return {"tag_name": f"sih-{ano}", "draft": False, "assets": [arquivo(f"sih-{ano}", "particoes.zip", pacote, _corpo=pacote)]}


def reempacotar(pacote, troca):
    """O mesmo .zip com arquivos trocados ou acrescentados, como viria de uma Release adulterada."""
    saida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(pacote)) as z, zipfile.ZipFile(saida, "w") as novo:
        for nome in z.namelist():
            if nome not in troca:
                novo.writestr(nome, z.read(nome))
        for nome, corpo in troca.items():
            novo.writestr(nome, corpo)
    return saida.getvalue()


def test_sem_release_segue_como_primeira_publicacao(tmp_path):
    (tmp_path / "censo-2022.json").write_bytes(b"sobra de outra execucao")
    pedidos = fonte([{"tag_name": "v0.1", "draft": False, "assets": []}])
    consulta = release.consultar(tmp_path, pedidos, token="segredo")
    assert consulta["censo"] is False and consulta["sih"] == {"anos": []} and consulta["releases"] == ["v0.1"]
    assert not (tmp_path / "censo-2022.json").exists()           # a coleta do Censo vai à fonte
    assert release.versao_no_ar(tmp_path) is None                # consultou e não há: primeira publicação do SIH
    assert pedidos.pedidos[0][1]["cabecalhos"]["Authorization"] == "Bearer segredo"


@pytest.mark.parametrize("lista", [
    resposta({"message": "API rate limit exceeded"}, status=403),
    resposta({"message": "Not Found"}, status=404),      # o repositório não respondeu como repositório: não é "sem Release"
    resposta(b"<html>erro</html>"),
    resposta({"message": "ok"}),                         # 200, mas não é a lista
    resposta([{"nome": "sem tag"}]),
    None,                                                # sem resposta depois das tentativas
])
def test_falha_ao_consultar_para_e_nao_parece_ausencia(tmp_path, lista):
    (tmp_path / "consulta.json").write_text('{"sih": {"anos": []}}', encoding="utf-8")   # de uma execução anterior
    pedidos = FonteFalsa({LISTA: lista} if lista is not None else {})
    with pytest.raises(release.ErroDeRelease, match="Não consegui consultar as Releases"):
        release.consultar(tmp_path, pedidos)
    # Sem a consulta gravada, a etapa do SIH também para, em vez de concluir que não há versão no ar.
    assert not (tmp_path / "consulta.json").exists()
    with pytest.raises(release.ErroDeRelease, match="não foram consultadas"):
        release.versao_no_ar(tmp_path)


def test_censo_da_release_e_baixado_e_conferido(tmp_path):
    pedidos = fonte([release_do_censo()])
    assert release.consultar(tmp_path, pedidos)["censo"] is True
    assert (tmp_path / "censo-2022.json").read_bytes() == CENSO
    # O download vai sem o token: o endereço redireciona para outro domínio.
    assert "cabecalhos" not in pedidos.pedidos[1][1] and pedidos.pedidos[1][1]["descomprimir"] is False


@pytest.mark.parametrize("releases, corpos, motivo", [
    ([{"tag_name": "ibge-censo-2022", "draft": False, "assets": []}], {}, "existe, mas não tem o arquivo censo-2022.json"),
    ([release_do_censo(size=3)], {}, "bytes, e a Release registra 3"),
    ([release_do_censo(digest="sha256:" + "0" * 64)], {}, "SHA-256 diferente"),
    ([release_do_censo()], {f"{projeto.REPOSITORIO}/releases/download/ibge-censo-2022/censo-2022.json":
                            resposta(b"", status=404)}, "Não consegui baixar censo-2022.json"),
    ([release_do_censo()], {f"{projeto.REPOSITORIO}/releases/download/ibge-censo-2022/censo-2022.json": None},
     "Não consegui baixar censo-2022.json"),
])
def test_release_que_existe_mas_nao_confere_para(tmp_path, releases, corpos, motivo):
    with pytest.raises(release.ErroDeRelease, match=motivo):
        release.consultar(tmp_path, fonte(releases, corpos))
    assert not (tmp_path / "consulta.json").exists()


def test_rascunho_nao_conta_e_a_lista_e_lida_ate_o_fim(tmp_path):
    cheia = [{"tag_name": f"v{i}", "draft": False, "assets": []} for i in range(100)]
    segunda = [release_do_censo(), {"tag_name": "sih-2025", "draft": True, "assets": []}]
    pedidos = fonte(segunda)
    pedidos.respostas |= {LISTA: resposta(cheia), LISTA[:-1] + "2": resposta(segunda)}
    consulta = release.consultar(tmp_path, pedidos)
    assert consulta["censo"] is True and consulta["sih"]["anos"] == [] and len(consulta["releases"]) == 101


def test_versao_no_ar_do_sih_e_baixada_e_conferida_com_a_situacao(tmp_path):
    origem = ano_publicado(ano_publicado(tmp_path / "origem", 2024), 2025)
    pacotes = {ano: sih_particoes.empacotar(origem, ano) for ano in (2024, 2025)}
    assert sih_particoes.empacotar(origem, 2025) == pacotes[2025]                   # os mesmos bytes a cada vez
    destino = tmp_path / "release"
    (destino / "sih" / "ano=2023").mkdir(parents=True)                             # sobra de outra execução
    consulta = release.consultar(destino, fonte([release_do_sih(a, p) for a, p in pacotes.items()]))
    assert consulta["sih"]["anos"] == [2024, 2025]
    no_ar = release.versao_no_ar(destino)
    assert no_ar == destino / "sih" and sih_particoes.anos_na_pasta(no_ar) == [2024, 2025]
    for ano in (2024, 2025):
        assert sih_particoes.ler_publicada(no_ar, ano) == sih_particoes.ler_publicada(origem, ano)
        assert (no_ar / f"ano={ano}" / "sih_res_ano" / "uf=35.parquet").read_bytes() == f"dados de {ano}".encode()


def _situacao(pacote, **troca):
    with zipfile.ZipFile(io.BytesIO(pacote)) as z:
        return json.dumps(json.loads(z.read("situacao.json")) | troca).encode()


@pytest.mark.parametrize("adulterar, motivo", [
    (lambda p: reempacotar(p, {"sih_res_ano/uf=35.parquet": b"outros dados"}), "diferente do que situacao.json"),
    (lambda p: reempacotar(p, {"sih_res_ano/uf=33.parquet": b"a mais"}), "não são os que a situação lista"),
    (lambda p: reempacotar(p, {"../fora.txt": b"x"}), "não são os que a situação lista"),
    (lambda p: reempacotar(p, {"situacao.json": _situacao(p, ano=2024)}), "de outro ano"),
    (lambda p: reempacotar(p, {"situacao.json": _situacao(p, deducao={"rodou": True, "passou": False, "obitos_passou": True})}),
     "consta como versão publicada, mas o teste de dedução revelou"),
    (lambda p: reempacotar(p, {"situacao.json": _situacao(p, arquivos={"../../fora.parquet": {"bytes": 1, "sha256": "0"}}),
                               "../../fora.parquet": b"x", "sih_res_ano/uf=35.parquet": b""}), "não são os que a situação lista"),
    (lambda p: b"isto nao e um zip", "não é um .zip"),
])
def test_versao_no_ar_que_nao_confere_para_e_nao_deixa_pasta(tmp_path, adulterar, motivo):
    pacote = adulterar(sih_particoes.empacotar(ano_publicado(tmp_path / "origem"), 2025))
    destino = tmp_path / "release"
    with pytest.raises(release.ErroDeRelease, match=f"A versão no ar do SIH de 2025 não confere.*{motivo}"):
        release.consultar(destino, fonte([release_do_sih(2025, pacote)]))
    assert not (destino / "consulta.json").exists() and not (destino / "sih" / "ano=2025").exists()
    assert not (tmp_path / "fora.txt").exists() and not (tmp_path / "fora.parquet").exists()


def test_caminho_para_fora_da_pasta_do_ano_e_recusado(tmp_path):
    # Mesmo listado na situação, um nome que sai da pasta do ano não é extraído.
    pacote = sih_particoes.empacotar(ano_publicado(tmp_path / "origem"), 2025)
    situacao = json.loads(_situacao(pacote))
    situacao["arquivos"]["../fora.parquet"] = {"bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()}
    pacote = reempacotar(pacote, {"situacao.json": json.dumps(situacao).encode(), "../fora.parquet": b"x"})
    with pytest.raises(sih_particoes.ErroDeParticao, match="caminho fora da pasta do ano"):
        sih_particoes.desempacotar(pacote, tmp_path / "destino", 2025)
    assert not (tmp_path / "destino" / "fora.parquet").exists() and not (tmp_path / "destino" / "ano=2025").exists()


@pytest.mark.parametrize("deducao, motivo", [
    ({"rodou": False}, "o teste de dedução não rodou"),
    ({"passou": False, "pequenas_reveladas": 3}, "revelou 3 contagem"),
    ({"obitos_passou": False}, "contagens de óbitos"),
    ({"conjunto": {"obrigatorio": True, "rodou": True, "passou": False, "motivo": "2 contagem(ns) reveladas"}}, "ataque conjunto com a versão no ar não passou: 2"),
    ({"conjunto": {"obrigatorio": True, "rodou": False, "motivo": "versão no ar ilegível"}}, "não rodou: versão no ar ilegível"),
])
def test_ano_reprovado_nao_vira_particao_nem_pacote(tmp_path, deducao, motivo):
    with pytest.raises(sih_particoes.ErroDeParticao, match=motivo):
        ano_publicado(tmp_path, **deducao)
    assert list(tmp_path.iterdir()) == []                        # nenhum arquivo, nem a pasta de troca
    # E a partição que já existia, se a situação dela for trocada à mão, não é lida como publicada nem empacotada.
    pasta = ano_publicado(tmp_path)
    caminho = pasta / "ano=2025" / "situacao.json"
    situacao = json.loads(caminho.read_text(encoding="utf-8"))
    caminho.write_text(json.dumps(situacao | {"deducao": situacao["deducao"] | deducao}), encoding="utf-8")
    for ler in (sih_particoes.ler_publicada, sih_particoes.empacotar):
        with pytest.raises(sih_particoes.ErroDeParticao, match=motivo):
            ler(pasta, 2025)


def test_primeira_publicacao_do_ano_e_publicavel_sem_ataque_conjunto(tmp_path):
    conjunto = {"obrigatorio": False, "rodou": False, "motivo": "primeira publicação do ano"}
    assert sih_particoes.nao_publicavel({"deducao": {"rodou": True, "passou": True, "obitos_passou": True, "conjunto": conjunto}}) is None
    ano_publicado(tmp_path, conjunto=conjunto)
    assert sih_particoes.ler_publicada(tmp_path, 2025)["deducao"]["conjunto"] == conjunto


def test_comandos_do_publicar(tmp_path, capsys):
    # Sem a consulta às Releases, o SIH com --no-ar para antes de qualquer coleta.
    with pytest.raises(release.ErroDeRelease, match="não foram consultadas"):
        cli.main(["sih", "--coleta", str(tmp_path), "--trabalho", str(tmp_path / "t"), "--saida", str(tmp_path / "s"),
                  "--no-ar", str(tmp_path / "release")])
    assert not (tmp_path / "t").exists()
    with pytest.raises(SystemExit):                              # uma pasta escolhida à mão ou a consulta, nunca as duas
        cli.main(["sih", "--coleta", "c", "--trabalho", "t", "--saida", "s", "--no-ar", "a", "--anterior", "b"])
    capsys.readouterr()
    assert cli.main(["publicacao", "--base", "sih"]) == 0
    assert capsys.readouterr().out.strip() == "publicar=false"   # o catálogo ainda não manda publicar o SIH


def test_publicar_consulta_as_releases_antes_da_coleta_e_so_roda_o_sih_se_o_catalogo_mandar():
    texto = (RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
    assert "gh release view" not in texto and "/dev/null" not in texto
    passos = yaml.safe_load(texto)["jobs"]["construir"]["steps"]
    comandos = [p.get("run", "") for p in passos]
    consulta = next(i for i, c in enumerate(comandos) if "pipeline releases --destino build/release" in c)
    coleta = next(i for i, c in enumerate(comandos) if "pipeline coletar" in c)
    decide = next(i for i, c in enumerate(comandos) if "pipeline publicacao --base sih" in c)
    sih = next(i for i, c in enumerate(comandos) if "pipeline sih " in c)
    site = next(i for i, c in enumerate(comandos) if "pipeline construir" in c)
    assert consulta < coleta < decide < sih < site
    # A consulta que falha para o job: sem `continue-on-error` e sem condição.
    assert "continue-on-error" not in passos[consulta] and "if" not in passos[consulta]
    assert "--censo-release build/release/censo-2022.json" in comandos[coleta]
    assert passos[decide]["id"] == "sih" and comandos[decide].rstrip().endswith('>> "$GITHUB_OUTPUT"')
    # O SIH recebe a versão no ar pela consulta, nunca por uma pasta fixa, e só com o catálogo mandando publicar.
    assert "--no-ar build/release" in comandos[sih] and "--anterior" not in comandos[sih]
    assert passos[sih]["if"] == "steps.sih.outputs.publicar == 'true'" and "continue-on-error" not in passos[sih]
