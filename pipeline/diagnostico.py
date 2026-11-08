"""Diagnóstico de alcance: cada fonte do plano, passo a passo e com tempo curto.

Separa DNS, conexão, TLS (ou boas-vindas do FTP) e resposta, para dizer em que passo a fonte
deixa de responder. Roda igual no runner e numa máquina local, para comparar os dois.
Uma fonte que falha não interrompe as outras. O arquivo do SIH fica só na memória:
sai daqui apenas tamanho e hash.
"""
from __future__ import annotations

import ftplib
import hashlib
import http.client
import os
import platform
import posixpath
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from . import alcance, ibge, rede

TEMPO_DNS = 10
TEMPO_CONEXAO = 10
TEMPO_RESPOSTA = 20
TEMPO_CORPO = 60
ENDERECOS_POR_FAMILIA = 2
# Se o TLS ou a resposta param depois de a conexão abrir, repetir com segmento menor separa
# pacote grande perdido no caminho (MTU) de bloqueio na origem.
MSS_REDUZIDO = 1200

ALVOS = [
    {"nome": "ibge_localidades", "url": ibge.URL_LOCALIDADES},
    {"nome": "ibge_agregados", "url": ibge.URL_PERIODOS.format(tabela=ibge.ESTIMATIVA["tabela"])},
    {"nome": "ibge_sidra", "url": "https://apisidra.ibge.gov.br/values/t/6579/n6/3548500/v/9324/p/last%201"},
    {"nome": "ibge_ftp", "url": "ftp://ftp.ibge.gov.br/Estimativas_de_Populacao/"},
    {"nome": "ibge_ftp_https", "url": "https://ftp.ibge.gov.br/Estimativas_de_Populacao/"},
    # Divisão Territorial Brasileira: a lista oficial de municípios fora da API de localidades.
    {"nome": "ibge_geoftp_https", "url": "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/"
                                         "divisao_territorial/2025/DTB_2025.zip", "cabecalhos": {"Range": "bytes=0-1023"}},
    {"nome": "datasus_ftp", "url": f"ftp://ftp.datasus.gov.br{alcance.SIH_PASTA}/{alcance.SIH_ARQUIVO}"},
    {"nome": "inep", "url": alcance.INEP_URL, "cabecalhos": {"Range": "bytes=0-1023"}},
    {"nome": "pdet_ftp", "url": f"ftp://ftp.mtps.gov.br{alcance.CAGED_PASTA}/"},
    {"nome": "siconfi", "url": alcance.SICONFI_URL},
    # Controle: se nem o GitHub responde, o problema é do ambiente, não da fonte.
    {"nome": "controle_github", "url": "https://api.github.com/zen"},
]

_FAMILIA = {socket.AF_INET: "IPv4", socket.AF_INET6: "IPv6"}


class _Falha(Exception):
    """Falha com detalhes que valem registro, como o status de uma resposta de erro."""

    def __init__(self, mensagem, **detalhe):
        super().__init__(mensagem)
        self.detalhe = detalhe


class _Interrompido(Exception):
    """Um passo falhou; os seguintes dependem dele e não rodam."""

    def __init__(self, passo):
        super().__init__(passo)
        self.passo = passo


def _ms(inicio: float) -> int:
    return round((time.monotonic() - inicio) * 1000)


def _erro(e: BaseException) -> str:
    return f"{type(e).__name__}: {e}"[:300]


def _passo(passos: dict, nome: str, funcao):
    """Roda um passo, guarda tempo e detalhes e devolve o valor. Se falhar, interrompe a fonte."""
    inicio = time.monotonic()
    try:
        valor, detalhe = funcao()
    except Exception as e:
        passos[nome] = {"ok": False, "ms": _ms(inicio), "erro": _erro(e), **getattr(e, "detalhe", {})}
        raise _Interrompido(nome) from e
    passos[nome] = {"ok": True, "ms": _ms(inicio), **detalhe}
    return valor


def resolver(host: str, porta: int, tempo: float = TEMPO_DNS, consultar=socket.getaddrinfo):
    """getaddrinfo não aceita tempo limite, então a consulta roda numa thread que pode ser abandonada."""
    saida = {}

    def consulta():
        try:
            saida["enderecos"] = consultar(host, porta, type=socket.SOCK_STREAM)
        except Exception as e:
            saida["erro"] = e
    linha = threading.Thread(target=consulta, daemon=True)
    linha.start()
    linha.join(tempo)
    if linha.is_alive():
        raise TimeoutError(f"DNS sem resposta em {tempo} s")
    if "erro" in saida:
        raise saida["erro"]
    vistos, enderecos = set(), []
    for familia, _, _, _, sockaddr in saida["enderecos"]:
        if sockaddr[0] not in vistos:
            vistos.add(sockaddr[0])
            enderecos.append((familia, sockaddr))
    if not enderecos:
        raise _Falha("DNS sem endereços")
    return enderecos, {"enderecos": [{"endereco": s[0], "familia": _FAMILIA.get(f, str(f))} for f, s in enderecos]}


def _mss_suportado() -> bool:
    """O Linux aceita TCP_MAXSEG antes de conectar; o Windows recusa."""
    if not hasattr(socket, "TCP_MAXSEG"):
        return False
    with socket.socket() as sock:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, MSS_REDUZIDO)
        except OSError:
            return False
    return True


def _abrir(familia, sockaddr, mss=None) -> socket.socket:
    sock = socket.socket(familia, socket.SOCK_STREAM)
    try:
        if mss:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, mss)
        sock.settimeout(TEMPO_CONEXAO)
        sock.connect(sockaddr)
    except BaseException:
        sock.close()
        raise
    return sock


def _conectar(enderecos, mss=None):
    """Tenta até dois endereços por família e fica com o primeiro que abrir, na ordem do DNS."""
    tentativas, escolhido, por_familia = [], None, {}
    for familia, sockaddr in enderecos:
        if por_familia.get(familia, 0) >= ENDERECOS_POR_FAMILIA:
            continue
        por_familia[familia] = por_familia.get(familia, 0) + 1
        tentativa = {"endereco": sockaddr[0], "familia": _FAMILIA.get(familia, str(familia))}
        inicio = time.monotonic()
        try:
            sock = _abrir(familia, sockaddr, mss)
        except OSError as e:
            tentativas.append({**tentativa, "ok": False, "ms": _ms(inicio), "erro": _erro(e)})
            continue
        tentativas.append({**tentativa, "ok": True, "ms": _ms(inicio)})
        if escolhido is None:
            escolhido = (sock, familia, sockaddr)
        else:
            sock.close()
    if escolhido is None:
        primeira = tentativas[0]["erro"] if tentativas else "sem endereço"
        raise _Falha(f"nenhum de {len(tentativas)} endereços abriu ({primeira})", tentativas=tentativas)
    return escolhido, {"endereco": escolhido[2][0], "tentativas": tentativas}


def _tls(sock: socket.socket, host: str):
    sock.settimeout(TEMPO_CONEXAO)
    try:
        seguro = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    except BaseException:
        sock.close()
        raise
    return seguro, {"versao": seguro.version()}


def _pedir(sock, host: str, caminho: str, alvo: dict):
    conexao = http.client.HTTPSConnection(host, timeout=TEMPO_RESPOSTA)
    conexao.sock = sock
    sock.settimeout(TEMPO_RESPOSTA)
    conexao.request(alvo.get("metodo", "GET"), caminho,
                    headers={"User-Agent": rede.AGENTE, "Accept-Encoding": "gzip", **alvo.get("cabecalhos", {})})
    resposta = conexao.getresponse()
    detalhe = {"status": resposta.status, "content_encoding": resposta.getheader("Content-Encoding"),
               "content_type": resposta.getheader("Content-Type")}
    if resposta.status >= 400:
        raise _Falha(f"HTTP {resposta.status}", **detalhe)
    return resposta, detalhe


def _contar(prazo: float):
    """Recebe blocos e guarda só tamanho e hash, com prazo para o total."""
    limite, resumo, estado = time.monotonic() + prazo, hashlib.sha256(), {"bytes": 0}

    def receber(bloco: bytes):
        estado["bytes"] += len(bloco)
        resumo.update(bloco)
        if time.monotonic() > limite:
            raise TimeoutError(f"incompleto após {prazo} s, com {estado['bytes']} bytes")
    return receber, lambda: {"bytes": estado["bytes"], "sha256": resumo.hexdigest()}


def _corpo(resposta):
    receber, total = _contar(TEMPO_CORPO)
    while bloco := resposta.read(65536):
        receber(bloco)
    return None, total()


def _https(enderecos, host, caminho, alvo, passos, mss=None):
    sock = None
    try:
        sock, _, _ = _passo(passos, "conexao", lambda: _conectar(enderecos, mss))
        sock = _passo(passos, "tls", lambda: _tls(sock, host))
        resposta = _passo(passos, "resposta", lambda: _pedir(sock, host, caminho, alvo))
        _passo(passos, "corpo", lambda: _corpo(resposta))
    finally:
        if sock is not None:
            sock.close()


def sondar_https(alvo: dict) -> dict:
    partes = urlsplit(alvo["url"])
    host, porta = partes.hostname, partes.port or 443
    caminho = partes.path + (f"?{partes.query}" if partes.query else "")
    item = {"url": alvo["url"], "host": host, "passos": {}}
    try:
        enderecos = _passo(item["passos"], "dns", lambda: resolver(host, porta))
        _https(enderecos, host, caminho, alvo, item["passos"])
    except _Interrompido as e:
        item["falhou_em"] = e.passo
        if e.passo in ("tls", "resposta", "corpo") and isinstance(e.__cause__, TimeoutError) and _mss_suportado():
            usado = item["passos"]["conexao"]["endereco"]
            reduzido = item["com_mss_reduzido"] = {"mss": MSS_REDUZIDO, "passos": {}}
            try:
                _https([(f, s) for f, s in enderecos if s[0] == usado], host, caminho, alvo,
                       reduzido["passos"], MSS_REDUZIDO)
            except _Interrompido as e2:
                reduzido["falhou_em"] = e2.passo
    return item


def _baixar_ftp(ftp: ftplib.FTP, arquivo: str):
    tamanho = ftp.size(arquivo)
    receber, total = _contar(TEMPO_CORPO)
    ftp.retrbinary(f"RETR {arquivo}", receber)
    if total()["bytes"] != tamanho:
        raise _Falha(f"{total()['bytes']} bytes de {tamanho}", **total())
    return None, total()


def sondar_ftp(alvo: dict) -> dict:
    """Pasta terminada em / só é listada; caminho de arquivo também é baixado."""
    partes = urlsplit(alvo["url"])
    host = partes.hostname
    pasta, arquivo = posixpath.split(partes.path)
    item = {"url": alvo["url"], "host": host, "passos": {}}
    passos = item["passos"]
    ftp = ftplib.FTP(timeout=TEMPO_RESPOSTA, encoding="latin-1")
    try:
        enderecos = _passo(passos, "dns", lambda: resolver(host, 21))
        sock, _, sockaddr = _passo(passos, "conexao", lambda: _conectar(enderecos))
        sock.close()
        _passo(passos, "boas_vindas", lambda: (None, {"texto": ftp.connect(sockaddr[0], 21)[:120]}))
        _passo(passos, "login", lambda: (None, {"texto": ftp.login()[:120]}))
        _passo(passos, "pasta", lambda: (None, {"texto": ftp.cwd(pasta)[:120]}))
        _passo(passos, "listagem", lambda: (None, {"itens": len(ftp.nlst())}))
        if arquivo:
            _passo(passos, "download", lambda: _baixar_ftp(ftp, arquivo))
    except _Interrompido as e:
        item["falhou_em"] = e.passo
    finally:
        ftp.close()
    return item


SONDAS = {"https": sondar_https, "ftp": sondar_ftp}


def _ambiente() -> dict:
    return {"sistema": platform.platform(), "python": platform.python_version(), "openssl": ssl.OPENSSL_VERSION,
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true"}


def executar(alvos=ALVOS, sondas=SONDAS, agora=None) -> dict:
    """Cada fonte é testada sozinha; nem um defeito do próprio diagnóstico esconde as outras."""
    resultado = {"conferido_em": (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "ambiente": _ambiente(), "fontes": {}}
    for alvo in alvos:
        inicio = time.monotonic()
        try:
            item = sondas[urlsplit(alvo["url"]).scheme](alvo)
        except Exception as e:
            item = {"url": alvo["url"], "passos": {}, "falhou_em": "diagnostico", "erro": _erro(e)}
        item["ok"] = "falhou_em" not in item
        item["ms_total"] = _ms(inicio)
        resultado["fontes"][alvo["nome"]] = item
    return resultado


# Resumo em Markdown, para o resumo da execução no GitHub e para comparar com a máquina local.

def _s(ms: int) -> str:
    return f"{ms / 1000:.1f} s".replace(".", ",")


def _tamanho(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB".replace(".", ",")
    return f"{n / 1000:.1f} KB".replace(".", ",") if n >= 1000 else f"{n} B"


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def _texto_dns(p: dict) -> str:
    dns = p.get("dns")
    if dns is None:
        return "—"
    if not dns["ok"]:
        return f"falhou em {_s(dns['ms'])}"
    familias = [e["familia"] for e in dns["enderecos"]]
    return f"{_s(dns['ms'])} · " + ", ".join(f"{familias.count(f)} {f}" for f in dict.fromkeys(familias))


def _texto_conexao(p: dict) -> str:
    conexao = p.get("conexao")
    if conexao is None:
        return "—"
    return "; ".join(f"{t['familia']} {'ok' if t['ok'] else 'falhou'} em {_s(t['ms'])}"
                     for t in conexao.get("tentativas", [])) or conexao.get("erro", "—")


def _texto_meio(p: dict) -> str:
    if "tls" in p:
        tls = p["tls"]
        return f"{tls['versao']} em {_s(tls['ms'])}" if tls["ok"] else f"falhou em {_s(tls['ms'])}"
    partes = []
    for nome, rotulo in (("boas_vindas", "boas-vindas"), ("login", "login"), ("listagem", "listagem")):
        if nome in p:
            extra = f" ({p[nome]['itens']} itens)" if p[nome]["ok"] and "itens" in p[nome] else ""
            partes.append(f"{rotulo} {'' if p[nome]['ok'] else 'falhou '}em {_s(p[nome]['ms'])}{extra}")
    return " · ".join(partes) or "—"


def _texto_resposta(p: dict) -> str:
    if "resposta" in p:
        resposta, corpo = p["resposta"], p.get("corpo")
        texto = f"HTTP {resposta['status']}" if "status" in resposta else "sem resposta"
        texto += f" em {_s(resposta['ms'])}"
        if corpo is not None:
            texto += f" · {_tamanho(corpo['bytes'])} em {_s(corpo['ms'])}" if corpo["ok"] else " · corpo incompleto"
        return texto
    if "download" in p:
        d = p["download"]
        return f"{_tamanho(d['bytes'])} em {_s(d['ms'])}" if d["ok"] else f"download falhou em {_s(d['ms'])}"
    return "—"


def _texto_resultado(item: dict) -> str:
    if item["ok"]:
        texto = "ok"
    else:
        passo = item["falhou_em"]
        erro = item.get("erro") or item["passos"].get(passo, {}).get("erro", "")
        texto = f"**falhou em {passo}**: {erro}"
    reduzido = item.get("com_mss_reduzido")
    if reduzido:
        texto += f"; com MSS {reduzido['mss']}: " + (f"falhou em {reduzido['falhou_em']}"
                                                       if "falhou_em" in reduzido else "ok")
    return texto


def resumo(resultado: dict) -> str:
    ambiente = resultado["ambiente"]
    onde = "GitHub Actions" if ambiente["github_actions"] else "máquina local"
    linhas = [f"### Alcance das fontes ({onde})", "",
              f"{resultado['conferido_em']} · {ambiente['sistema']} · Python {ambiente['python']} · {ambiente['openssl']}",
              "", "| Fonte | DNS | Conexão | TLS ou FTP | Resposta | Total | Resultado |",
              "|---|---|---|---|---|---:|---|"]
    for nome, item in resultado["fontes"].items():
        p = item["passos"]
        celulas = [f"`{nome}`", _texto_dns(p), _texto_conexao(p), _texto_meio(p), _texto_resposta(p),
                   _s(item["ms_total"]), _texto_resultado(item)]
        linhas.append("| " + " | ".join(_celula(c) for c in celulas) + " |")
    linhas += ["", "Endereços usados:", ""]
    for nome, item in resultado["fontes"].items():
        conexao = item["passos"].get("conexao", {})
        enderecos = [e["endereco"] for e in item["passos"].get("dns", {}).get("enderecos", [])]
        linhas.append(f"- `{nome}` ({item.get('host', '?')}): DNS {', '.join(enderecos) or '—'}; "
                      f"conexão por {conexao.get('endereco', '—')}")
    return "\n".join(linhas) + "\n"
