"""Ciclo completo de publicação do SIH, simulado no build local, com as 27 UFs. Nada é publicado.

Registro da medição de 10/11/2026 (ciclo_publicacao_f1b.json), feita com o pipeline do commit 6f90077. Depois
dela, a versão no ar deixou de ser uma Release de partições e passou a ser a superfície publicada com o site
(sih_superficie, decidido em 10/11/2026), e este script não roda com o pipeline atual: release.versao_no_ar e
sih_particoes.empacotar não existem mais. O ciclo com a superfície é o de medir_motor_lp.py.

Cada versão é uma execução do pipeline (sih.processar_anos) sobre o Parquet mínimo de uma coleta local, só
com as competências que já teriam saído até a última competência da versão. Cenários:

- primeira: primeira publicação, com a última competência 2604. Nenhuma versão no ar.
- release: cada ano da primeira é empacotado (sih_particoes.empacotar), servido como Release por uma fonte
  falsa, baixado e conferido (release.consultar). A versão seguinte lê a versão no ar dessa pasta.
- seguinte: última competência 2605, com a versão no ar. Dezembro de 2024 fecha: as tabelas anuais de 2024
  passam de arredondadas a exatas. Herança do padrão e ataque conjunto em cada ano.
- sem_heranca: a mesma versão com `versoes.herdar_padrao_fechado: false`. Sem a herança, a medição de
  08/11/2026 achou contagens reveladas no fechamento de 2024; aqui é o ataque conjunto do pipeline que
  tem de achá-las e reprovar o ano.
- sem_reforco: primeira publicação com `supressao.reforco_max_rodadas: 0`, nos anos pedidos. O ano em que o
  teste de dedução revela alguma contagem sem o reforço tem de ficar sem partição.
- adulterada: um byte trocado num arquivo da versão no ar. A leitura tem de parar.

Em cada cenário, o script confere a pasta de partições: existe a pasta do ano se, e só se, o ano passou em
tudo, e cada pasta existente bate com a situação dela, arquivo por arquivo. Daqui só saem contagens por
cenário, ano e tabela: nenhum valor por município.

Uso: python simular_ciclo_sih.py <pasta_min> <ibge.json da coleta> <pasta_de_trabalho> <saida.json> [cenário ...]
"""
import json
import shutil
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import catalogo, rede, release, sih, sih_janela, sih_particoes  # noqa: E402

MIN, COLETA, TRABALHO, SAIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
SO = set(sys.argv[5:])
CAT = catalogo.carregar()
SIH = CAT["bases"]["sih"]
INICIO = int(SIH["coleta"]["primeiro_ano"])
MUNICIPIOS7 = {m["codigo"][:6]: m["codigo"] for m in json.loads(COLETA.read_text(encoding="utf-8"))["municipios"]}
PRIMEIRA, SEGUINTE = 202604, 202605


def com_regra(grupo: str, **troca) -> dict:
    """O catálogo com uma regra do SIH trocada, só para o cenário."""
    return CAT | {"bases": CAT["bases"] | {"sih": SIH | {grupo: SIH[grupo] | troca}}}


def executar(nome: str, ultima: int, cat: dict = CAT, anterior: Path | None = None, anos: list[int] | None = None) -> dict:
    inicio = time.perf_counter()
    jan = sih_janela.Janela(ultima, ultima, int(SIH["tempo"]["janela_republicada_meses"]),
                            int(SIH["tempo"]["defasagem_maxima_meses"]), INICIO)
    arquivos = [p.as_posix() for p in sorted(MIN.glob("RD*.parquet")) if INICIO * 100 < sih_janela.de_nome(p.stem[4:8]) <= ultima]
    con = duckdb.connect()
    con.execute("SET threads = 8")
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({arquivos!r}) WHERE competencia <= {ultima}")
    trabalho = TRABALHO / nome
    shutil.rmtree(trabalho, ignore_errors=True)
    r = sih.processar_anos(con, "aih", jan, anos or jan.anos(), cat, trabalho, MUNICIPIOS7, f"simulado-{ultima}",
                           f"ate-{ultima}", anterior=anterior, no_ar_consultada=anterior is not None,
                           avisar=lambda texto: print(f"[{nome}] {texto}", flush=True))
    return resumir(nome, ultima, jan, r, trabalho / "particoes", time.perf_counter() - inicio)


def resumir(nome: str, ultima: int, jan, r: dict, particoes: Path, segundos: float) -> dict:
    """Por ano: os testes, se a partição foi gravada, e a conferência da pasta com o que o pipeline disse."""
    na_pasta = sih_particoes.anos_na_pasta(particoes) if particoes.exists() else []
    sobras = sorted(p.name for p in particoes.iterdir() if not p.name.startswith("ano=")) if particoes.exists() else []
    anos = {}
    for ano, m in r["anos"].items():
        ded, conjunto = m.get("deducao_internacoes", {}), m["ataque_conjunto"]
        gravada = int(ano) in na_pasta
        confere = None
        if gravada:
            situacao = sih_particoes.ler_publicada(particoes, int(ano))      # cada arquivo, por tamanho e SHA-256
            confere = sih_particoes.nao_publicavel(situacao) is None
        anos[ano] = {
            "internacoes": m["internacoes"], "meses_preliminares": len(m["preliminares"]),
            "publicados": len(m["publicados"]), "nao_publicados": sorted(m["nao_publicados"]),
            "herdou_da_anterior": len(m["herdou_da_anterior"]), "situacao_fixa": m["situacao_fixa"],
            "rodadas_de_reforco": len(ded.get("rodadas", [])) - 1,
            "teste_sozinha": {"internacoes": ded.get("pequenas_reveladas"), "passou": ded.get("passou"),
                              "obitos_passou": m.get("deducao_obitos", {}).get("passou")},
            "ataque_conjunto": {c: v for c, v in conjunto.items() if c not in ("internacoes", "obitos")}
            | {c: {x: y for x, y in conjunto[c].items() if x not in ("detalhe",)} for c in ("internacoes", "obitos") if c in conjunto},
            "reprovado": r["reprovados"].get(ano), "particao_gravada": gravada, "particao_confere": confere,
            "arquivos": r["particoes"][ano]["arquivos"], "bytes": r["particoes"][ano]["bytes"],
            "segundos": m["segundos"]}
        # A afirmação do cenário: reprovado não tem pasta, aprovado tem, e o pipeline disse o mesmo.
        assert gravada == (ano not in r["reprovados"]) == m["particao_gravada"], (nome, ano)
        assert not gravada or confere, (nome, ano)
    assert not sobras, (nome, sobras)
    return {"cenario": nome, "ultima_competencia": ultima, "fechado_ate": jan.ultimo_mes_fechado,
            "anos_reprovados": r["reprovados"], "anos_com_particao": na_pasta, "publicavel": not r["reprovados"],
            "segundos": round(segundos), "anos": anos}


def pela_release(origem: Path, destino: Path) -> dict:
    """Empacota cada ano, serve como Release por uma fonte falsa e baixa pela consulta do pipeline."""
    releases, corpos = [], {}
    for ano in sih_particoes.anos_na_pasta(origem):
        pacote = sih_particoes.empacotar(origem, ano)
        url = f"https://release.invalid/sih-{ano}/{release.SIH_PACOTE}"
        corpos[url] = pacote
        releases.append({"tag_name": f"sih-{ano}", "draft": False,
                         "assets": [{"name": release.SIH_PACOTE, "size": len(pacote), "browser_download_url": url,
                                     "digest": "sha256:" + rede.sha256(pacote)}]})

    def pedir(url, **opcoes):
        if url.startswith(release.API):
            return rede.Resposta(200, {}, json.dumps(releases).encode(), 0.0)
        return rede.Resposta(200, {}, corpos[url], 0.0)
    shutil.rmtree(destino, ignore_errors=True)
    consulta = release.consultar(destino, pedir)
    no_ar = release.versao_no_ar(destino)
    arquivos = sum(len(sih_particoes.ler_publicada(no_ar, ano)["arquivos"]) for ano in consulta["sih"]["anos"])
    return {"anos": consulta["sih"]["anos"], "pacotes_bytes": sum(len(c) for c in corpos.values()),
            "arquivos_conferidos_por_sha256": arquivos}


def adulterada(no_ar: Path) -> dict:
    """Um byte a mais num arquivo da versão no ar: a leitura para antes de qualquer conta."""
    copia = TRABALHO / "adulterada"
    shutil.rmtree(copia, ignore_errors=True)
    shutil.copytree(no_ar, copia)
    ano = sih_particoes.anos_na_pasta(copia)[-1]
    alvo = sorted((copia / f"ano={ano}" / "sih_res_mes").glob("uf=*.parquet"))[0]
    alvo.write_bytes(alvo.read_bytes() + b"x")
    try:
        sih.anterior_do_ano(copia, ano, CAT, fechado=False)
    except sih.ErroDeParticao as erro:
        return {"ano": ano, "parou": True, "erro": type(erro).__name__, "motivo": "arquivo diferente do que situacao.json registra"}
    return {"ano": ano, "parou": False}


resultado = json.loads(SAIDA.read_text(encoding="utf-8")) if SO and SAIDA.exists() else {"cenarios": {}}
resultado |= {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ufs": 27, "k": int(SIH["supressao"]["k"]),
              "arredondar_multiplo": SIH["preliminares"]["arredondar_multiplo"]}


def guardar(nome: str, valor: dict) -> None:
    resultado["cenarios"][nome] = valor
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")


def pedido(nome: str) -> bool:
    return not SO or nome in SO


NO_AR = TRABALHO / "release"
if pedido("primeira"):
    guardar("primeira", executar("primeira", PRIMEIRA))
if pedido("release"):
    guardar("release", pela_release(TRABALHO / "primeira" / "particoes", NO_AR))
if pedido("seguinte"):
    guardar("seguinte", executar("seguinte", SEGUINTE, anterior=release.versao_no_ar(NO_AR)))
if pedido("sem_heranca"):
    guardar("sem_heranca", executar("sem_heranca", SEGUINTE, com_regra("versoes", herdar_padrao_fechado=False),
                                    anterior=release.versao_no_ar(NO_AR)))
if pedido("sem_reforco"):
    guardar("sem_reforco", executar("sem_reforco", PRIMEIRA, com_regra("supressao", reforco_max_rodadas=0), anos=[2021, 2025]))
if pedido("adulterada"):
    guardar("adulterada", adulterada(release.versao_no_ar(NO_AR)))
print("fim", flush=True)
