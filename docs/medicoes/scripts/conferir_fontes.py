"""Registra o que as fontes informam sobre si mesmas: listagens dos FTPs, datas do INEP e da SIDRA, listas de municípios e respostas do Siconfi.

Cada bloco guarda o erro em vez de parar a coleta, porque as fontes caem. Só lê: nenhum dado por pessoa é pedido.

Uso: python -I conferir_fontes.py <pasta_ibge> <siconfi_amostra.json> <saida.json>
"""
import collections
import ftplib
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

IBGE, AMOSTRA, SAIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
UA = {"User-Agent": "medicao-etapa0"}
LINHA = re.compile(r"(\d\d-\d\d-\d\d)\s+(\d\d:\d\d[AP]M)\s+(<DIR>|\d+)\s+(.+)$")
PORTES = [("ate_5mil", 0, 5000), ("5_a_20mil", 5000, 20000), ("20_a_100mil", 20000, 100000), ("100_a_500mil", 100000, 500000), ("mais_500mil", 500000, 10**9)]


def listar(ftp, caminho):
    linhas = []
    ftp.cwd(caminho)
    ftp.retrlines("LIST", linhas.append)
    itens = []
    for l in linhas:
        m = LINHA.match(l)
        if m:
            itens.append({"nome": m[4].strip(), "data": datetime.strptime(m[1], "%m-%d-%y").date().isoformat(), "bytes": None if m[3] == "<DIR>" else int(m[3])})
    return itens


def pedir(url, metodo="GET", extra=None, ler=False):
    req = urllib.request.Request(url, method=metodo, headers={**UA, **(extra or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            corpo = r.read() if ler else b""
            # A API do IBGE responde em gzip mesmo sem pedir
            return {"status": r.status, "cabecalhos": dict(r.headers.items()), "corpo": gzip.decompress(corpo) if corpo[:2] == b"\x1f\x8b" else corpo}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "cabecalhos": dict(e.headers.items()), "corpo": b""}


def bloco(nome, funcao):
    try:
        res[nome] = funcao()
    except Exception as e:
        res[nome] = {"erro": repr(e)[:200]}
    print(nome, json.dumps(res[nome], ensure_ascii=False)[:600], flush=True)


def sih():
    ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=120, encoding="latin-1")
    ftp.login()
    raiz = "/dissemin/publicos/SIHSUS"
    itens_raiz = listar(ftp, raiz)
    duck = next((i for i in itens_raiz if i["nome"].endswith(".duck")), None)
    rd = [a for a in listar(ftp, f"{raiz}/200801_/Dados") if re.fullmatch(r"RD[A-Z]{2}\d{4}\.dbc", a["nome"], re.I)]
    ordem = lambda c: ("19" if c[:2] > "50" else "20") + c
    comps = sorted({a["nome"][4:8] for a in rd}, key=ordem)
    ufs = {a["nome"][2:4].upper() for a in rd}
    ultima = comps[-1]
    grupo = [a for a in rd if a["nome"][4:8] == ultima]
    pastas = {}
    for sub in ("CSV", "DBF", "XML"):
        itens = listar(ftp, f"{raiz}/{sub}")
        anos = [int(m[1]) for i in itens for m in [re.search(r"[A-Z]{2}(\d\d)\d\d\.", i["nome"], re.I)] if m]
        pastas[sub] = {"itens": len(itens), "data_mais_recente": max((i["data"] for i in itens), default=None), "ano_mais_recente_nos_nomes": 2000 + max(anos) if anos else None, "primeiros": [i["nome"] for i in itens[:4]]}
    aviso = next((i for i in listar(ftp, f"{raiz}/CSV") if "leia" in i["nome"].lower()), None)
    if aviso:
        pedacos = []
        ftp.retrbinary(f"RETR {raiz}/CSV/{aviso['nome']}", pedacos.append)
        pastas["CSV"]["aviso"] = {"arquivo": aviso["nome"], "data": aviso["data"], "diz_temporariamente": "temporariamente" in b"".join(pedacos).decode("latin-1").lower()}
    ftp.quit()
    return {"raiz": [i["nome"] for i in itens_raiz], "arquivo_duck": duck, "competencias": len(comps), "primeira": comps[0], "ultima": ultima, "ufs_no_rd": len(ufs), "ufs_na_ultima": len(grupo),
            "ufs_ausentes_na_ultima": sorted(ufs - {a["nome"][2:4].upper() for a in grupo}), "data_da_ultima": collections.Counter(a["data"] for a in grupo).most_common(1)[0][0], "pastas": pastas}


def caged():
    ftp = ftplib.FTP("ftp.mtps.gov.br", timeout=120, encoding="latin-1")
    ftp.login()
    raiz = "/pdet/microdados/NOVO CAGED/2026"
    meses = [i for i in listar(ftp, raiz) if i["bytes"] is None]
    ultima = max(meses, key=lambda i: i["nome"])
    arquivos = listar(ftp, f"{raiz}/{ultima['nome']}")
    ftp.quit()
    return {"ultima_competencia": ultima["nome"], "data": ultima["data"], "arquivos": arquivos}


def inep():
    alvos = {"censo_2025": "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2025.zip", "censo_2024": "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2024.zip",
             "ideb_iniciais_2023": "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_iniciais_municipios_2023.xlsx", "ideb_finais_2023": "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_finais_municipios_2023.xlsx",
             "ideb_medio_2023": "https://download.inep.gov.br/ideb/resultados/divulgacao_ensino_medio_municipios_2023.xlsx", "ideb_iniciais_2025": "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_iniciais_municipios_2025.xlsx"}
    saida = {}
    for nome, url in alvos.items():
        linha = {}
        for rotulo, metodo, extra in (("head", "HEAD", None), ("get_1kb", "GET", {"Range": "bytes=0-1023"})):
            try:
                r = pedir(url, metodo, extra)
                linha[rotulo] = {"status": r["status"], "last_modified": r["cabecalhos"].get("Last-Modified"), "content_length": r["cabecalhos"].get("Content-Length"), "content_range": r["cabecalhos"].get("Content-Range")}
            except Exception as e:
                linha[rotulo] = {"erro": type(e).__name__ + ": " + str(getattr(e, "reason", e))[:90]}
            time.sleep(2)
        saida[nome] = linha
    return saida


def ibge():
    base = "https://servicodados.ibge.gov.br/api"
    loc = pedir(f"{base}/v1/localidades/municipios", ler=True, extra={"Origin": "https://exemplo.github.io"})
    lista = json.loads(loc["corpo"])
    periodos = {}
    for tabela, nome in ((4714, "censo_2022"), (6579, "estimativa"), (5938, "pib")):
        r = pedir(f"{base}/v3/agregados/{tabela}/periodos", ler=True)
        periodos[nome] = {"tabela": tabela, "periodos": [{"id": p.get("id"), "modificacao": p.get("modificacao")} for p in json.loads(r["corpo"])]}
    pesquisas = pedir(f"{base}/v1/pesquisas", ler=True)
    ids_loc = {str(m["id"]) for m in lista}
    sidra = {}
    pop = {}
    for tabela, nome in ((4714, "censo_2022"), (6579, "estimativa_2026"), (5938, "pib")):
        linhas = json.load(open(IBGE / f"sidra_{tabela}.json", encoding="utf-8"))[1:]
        sidra[nome] = {str(r["D1C"]) for r in linhas}
        if tabela == 6579:
            pop = {str(r["D1C"]): int(r["V"]) for r in linhas}
    return {"localidades": {"municipios": len(lista), "cache_control": loc["cabecalhos"].get("Cache-Control"), "cors": loc["cabecalhos"].get("Access-Control-Allow-Origin"), "prefixos_de_6_digitos_unicos": len({i[:6] for i in ids_loc})},
            "periodos_sidra": periodos, "pesquisas_na_api": len(json.loads(pesquisas["corpo"])), "municipios_por_lista": {k: len(v) for k, v in sidra.items()},
            "fora_do_censo_2022": sorted(ids_loc - sidra["censo_2022"]), "fora_do_pib": sorted(ids_loc - sidra["pib"]), "fora_da_estimativa": sorted(ids_loc - sidra["estimativa_2026"]),
            "municipios_por_porte_estimativa_2026": {n: sum(1 for h in pop.values() if a <= h < b) for n, a, b in PORTES}}


def siconfi():
    base = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
    amostra = json.load(open(AMOSTRA, encoding="utf-8"))
    sem = [x for x in amostra if not x["rreo2025_6"]]
    com_simplificado = falhas = 0
    tipo = urllib.parse.quote("RREO Simplificado")
    for x in sem:
        try:
            r = pedir(f"{base}/rreo?an_exercicio=2025&nr_periodo=6&co_tipo_demonstrativo={tipo}&id_ente={x['id']}", ler=True)
            com_simplificado += 1 if json.loads(r["corpo"]).get("items") else 0
        except Exception:
            falhas += 1
        time.sleep(1.05)
    rajada = collections.Counter()
    for _ in range(15):
        try:
            rajada[str(pedir(f"{base}/extrato_entregas?id_ente=3548500&an_referencia=2024")["status"])] += 1
        except Exception as e:
            rajada[type(e).__name__] += 1
    anexo = urllib.parse.quote("DCA-Anexo I-E")
    r = pedir(f"{base}/dca?an_exercicio=2023&no_anexo={anexo}&id_ente=3548500", ler=True)
    contas = collections.Counter(i.get("cod_conta") for i in json.loads(r["corpo"]).get("items", []))
    bytes_dca = {a: round(sum(x[f"bytes{a}"] or 0 for x in amostra if x[f"bytes{a}"]) / sum(1 for x in amostra if x[f"bytes{a}"]) / 1e3) for a in ("2023", "2024", "2025")}
    return {"amostra": len(amostra), "sem_rreo_no_6o_bimestre_2025": len(sem), "com_rreo_simplificado": com_simplificado, "falhas_de_consulta": falhas, "rajada_de_15_sem_espera": dict(rajada),
            "dca_anexo_i_e_santos_2023_cod_conta": dict(contas), "kb_medios_de_dca_por_municipio": bytes_dca}


res = {"coletado_em": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
for nome, funcao in (("sih_ftp", sih), ("caged_ftp", caged), ("inep", inep), ("ibge", ibge), ("siconfi", siconfi)):
    bloco(nome, funcao)
SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
