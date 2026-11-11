"""Consulta às Releases (só o Censo): "não existe" segue, "não consegui consultar" para. Respostas falsas, sem rede."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from conftest import FonteFalsa, resposta

from pipeline import __main__ as cli
from pipeline import projeto, release, sih_particoes, sih_superficie

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


def test_sem_release_segue_como_primeira_publicacao(tmp_path):
    (tmp_path / "censo-2022.json").write_bytes(b"sobra de outra execucao")
    pedidos = fonte([{"tag_name": "v0.1", "draft": False, "assets": []}])
    consulta = release.consultar(tmp_path, pedidos, token="segredo")
    assert consulta == {"consultado_em": consulta["consultado_em"], "releases": ["v0.1"], "censo": False}
    assert not (tmp_path / "censo-2022.json").exists()           # a coleta do Censo vai à fonte
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
    (tmp_path / "consulta.json").write_text('{"censo": false}', encoding="utf-8")   # de uma execução anterior
    pedidos = FonteFalsa({LISTA: lista} if lista is not None else {})
    with pytest.raises(release.ErroDeRelease, match="Não consegui consultar as Releases"):
        release.consultar(tmp_path, pedidos)
    # Sem a consulta gravada, a coleta seguinte não acha o resultado de uma execução anterior.
    assert not (tmp_path / "consulta.json").exists()


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
    assert consulta["censo"] is True and len(consulta["releases"]) == 101 and "sih-2025" not in consulta["releases"]


@pytest.mark.parametrize("deducao, motivo", [
    ({"rodou": False}, "o teste de dedução não rodou"),
    ({"passou": False, "pequenas_reveladas": 3}, "revelou 3 contagem"),
    ({"obitos_passou": False}, "contagens de óbitos"),
    ({"conjunto": {"obrigatorio": True, "rodou": True, "passou": False, "motivo": "2 contagem(ns) reveladas"}}, "ataque conjunto com a versão no ar não passou: 2"),
    ({"conjunto": {"obrigatorio": True, "rodou": False, "motivo": "versão no ar ilegível"}}, "não rodou: versão no ar ilegível"),
])
def test_ano_reprovado_nao_vira_particao(tmp_path, deducao, motivo):
    with pytest.raises(sih_particoes.ErroDeParticao, match=motivo):
        ano_publicado(tmp_path, **deducao)
    assert list(tmp_path.iterdir()) == []                        # nenhum arquivo, nem a pasta de troca
    # E a partição que já existia, se a situação dela for trocada à mão, não é lida como publicada.
    pasta = ano_publicado(tmp_path)
    caminho = pasta / "ano=2025" / "situacao.json"
    situacao = json.loads(caminho.read_text(encoding="utf-8"))
    caminho.write_text(json.dumps(situacao | {"deducao": situacao["deducao"] | deducao}), encoding="utf-8")
    with pytest.raises(sih_particoes.ErroDeParticao, match=motivo):
        sih_particoes.ler_publicada(pasta, 2025)


def test_primeira_publicacao_do_ano_e_publicavel_sem_ataque_conjunto(tmp_path):
    conjunto = {"obrigatorio": False, "rodou": False, "motivo": "primeira publicação do ano"}
    assert sih_particoes.nao_publicavel({"deducao": {"rodou": True, "passou": True, "obitos_passou": True, "conjunto": conjunto}}) is None
    ano_publicado(tmp_path, conjunto=conjunto)
    assert sih_particoes.ler_publicada(tmp_path, 2025)["deducao"]["conjunto"] == conjunto


def test_comandos_do_publicar(tmp_path, capsys):
    # Sem a consulta ao site, o SIH com --no-ar para antes de qualquer coleta.
    with pytest.raises(sih_superficie.ErroDeSuperficie, match="não foi consultada"):
        cli.main(["sih", "--coleta", str(tmp_path), "--trabalho", str(tmp_path / "t"), "--saida", str(tmp_path / "s"),
                  "--no-ar", str(tmp_path / "no-ar")])
    assert not (tmp_path / "t").exists()
    with pytest.raises(SystemExit):                              # uma pasta escolhida à mão ou a consulta, nunca as duas
        cli.main(["sih", "--coleta", "c", "--trabalho", "t", "--saida", "s", "--no-ar", "a", "--anterior", "b"])
    capsys.readouterr()
    assert cli.main(["publicacao", "--base", "sih"]) == 0
    assert capsys.readouterr().out.strip() == "publicar=false"   # o catálogo ainda não manda publicar o SIH


def test_publicar_consulta_o_censo_antes_da_coleta_e_so_roda_o_sih_se_o_catalogo_mandar():
    texto = (RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
    assert "gh release view" not in texto and "/dev/null" not in texto
    passos = yaml.safe_load(texto)["jobs"]["construir"]["steps"]
    comandos = [p.get("run", "") for p in passos]
    consulta = next(i for i, c in enumerate(comandos) if "pipeline releases --destino build/release" in c)
    coleta = next(i for i, c in enumerate(comandos) if "pipeline coletar" in c)
    decide = next(i for i, c in enumerate(comandos) if "pipeline publicacao --base sih" in c)
    no_ar = next(i for i, c in enumerate(comandos) if "pipeline no-ar --destino build/no-ar" in c)
    sih = next(i for i, c in enumerate(comandos) if "pipeline sih " in c)
    site = next(i for i, c in enumerate(comandos) if "pipeline construir" in c)
    assert consulta < coleta < decide < no_ar < sih < site
    # A consulta que falha para o job: sem `continue-on-error` e sem condição.
    assert "continue-on-error" not in passos[consulta] and "if" not in passos[consulta]
    assert "--censo-release build/release/censo-2022.json" in comandos[coleta]
    assert passos[decide]["id"] == "sih" and comandos[decide].rstrip().endswith('>> "$GITHUB_OUTPUT"')
    # O SIH recebe a versão no ar pela consulta ao site, nunca por uma pasta fixa, e só com o catálogo mandando
    # publicar. Nada do SIH vem de Release.
    assert "--no-ar build/no-ar" in comandos[sih] and "--anterior" not in comandos[sih]
    for passo in (no_ar, sih):
        assert passos[passo]["if"] == "steps.sih.outputs.publicar == 'true'" and "continue-on-error" not in passos[passo]
    assert "sih" not in comandos[consulta]
