"""Teste de alcance: as fontes das próximas etapas respondem a partir do runner?

Só confere que respondem e que o formato é o esperado. O arquivo do SIH tem uma linha
por internação, então fica só na memória: sai daqui apenas tamanho, data e hash.
"""
from __future__ import annotations

import ftplib
import json
import re
import time
from datetime import datetime, timezone

from . import rede

SIH_PASTA = "/dissemin/publicos/SIHSUS/200801_/Dados"
# Roraima, jan/2025: pequeno, e já fora da janela de 12 competências republicadas, então o hash deve ficar estável.
SIH_ARQUIVO = "RDRR2501.dbc"
CAGED_PASTA = "/pdet/microdados/NOVO CAGED"
INEP_URL = "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2024.zip"
SICONFI_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_entregas?id_ente=3548500&an_referencia=2024"


def _ftp(host, abrir, tentativas, dormir):
    ultimo = None
    for tentativa in range(tentativas):
        try:
            ftp = abrir(host, timeout=120, encoding="latin-1")
            ftp.login()
            return ftp
        except (OSError, EOFError, ftplib.Error) as e:
            ultimo = e
            if tentativa + 1 < tentativas:
                dormir(10 * (tentativa + 1))
    raise rede.ErroDeRede(f"{host}: {type(ultimo).__name__}: {ultimo}")


def datasus(abrir=ftplib.FTP, tentativas=3, dormir=time.sleep) -> dict:
    ftp = _ftp("ftp.datasus.gov.br", abrir, tentativas, dormir)
    try:
        ftp.cwd(SIH_PASTA)
        rd = sorted(n for n in ftp.nlst() if re.fullmatch(r"RD[A-Z]{2}\d{4}\.dbc", n, re.I))
        tamanho = ftp.size(SIH_ARQUIVO)
        mdtm = ftp.voidcmd(f"MDTM {SIH_ARQUIVO}").split()[-1]
        partes = []
        ftp.retrbinary(f"RETR {SIH_ARQUIVO}", partes.append)
    finally:
        ftp.close()
    dados = b"".join(partes)
    if len(dados) != tamanho or dados[:1] != b"\x03":
        raise ValueError(f"{SIH_ARQUIVO}: {len(dados)} bytes de {tamanho}, ou cabeçalho que não é de DBF")
    competencias = sorted({n[4:8] for n in rd}, key=lambda c: ("19" if c[:2] > "50" else "20") + c)
    return {"arquivo": SIH_ARQUIVO, "bytes": len(dados), "sha256": rede.sha256(dados),
            "modificado_na_origem": f"{mdtm[:4]}-{mdtm[4:6]}-{mdtm[6:8]}T{mdtm[8:10]}:{mdtm[10:12]}:{mdtm[12:14]}Z",
            "arquivos_rd_na_pasta": len(rd), "ultima_competencia": competencias[-1] if competencias else None}


def caged(abrir=ftplib.FTP, tentativas=3, dormir=time.sleep) -> dict:
    ftp = _ftp("ftp.mtps.gov.br", abrir, tentativas, dormir)
    try:
        ftp.cwd(CAGED_PASTA)
        anos = sorted(n for n in ftp.nlst() if re.fullmatch(r"20\d\d", n))
        if not anos:
            raise ValueError("Listagem do CAGED sem pastas de ano")
        ftp.cwd(anos[-1])
        meses = sorted(n for n in ftp.nlst() if re.fullmatch(r"20\d{4}", n))
    finally:
        ftp.close()
    return {"pasta": CAGED_PASTA, "anos": len(anos), "ultimo_ano": anos[-1], "ultima_competencia": meses[-1] if meses else None}


def inep(pedir=rede.pedir) -> dict:
    cabeca = pedir(INEP_URL, metodo="HEAD")
    inicio = pedir(INEP_URL, cabecalhos={"Range": "bytes=0-1023"}, descomprimir=False)
    if cabeca.status != 200 or inicio.status != 206 or inicio.corpo[:4] != b"PK\x03\x04":
        raise ValueError(f"INEP: HEAD {cabeca.status}, Range {inicio.status}, início {inicio.corpo[:4]!r}")
    return {"url": INEP_URL, "bytes": int(cabeca.cabecalho("Content-Length") or 0),
            "last_modified": cabeca.cabecalho("Last-Modified"), "range": inicio.cabecalho("Content-Range")}


def siconfi(pedir=rede.pedir) -> dict:
    resposta = pedir(SICONFI_URL)
    itens = json.loads(resposta.corpo).get("items") if resposta.status == 200 else None
    if not itens:
        raise ValueError(f"Siconfi: HTTP {resposta.status}, sem itens no extrato")
    return {"url": SICONFI_URL, "itens": len(itens), "segundos": round(resposta.segundos, 2)}


# O INEP fica fora até a F1c: recusou o runner em 3 execuções do diagnóstico, e a hipótese de bloqueio
# por excesso de pedidos (ver Riscos no plano) desaconselha bater nele toda semana. O diagnóstico
# manual (`python -m pipeline diagnostico`) continua testando o INEP; esta função volta na F1c.
ALVOS = {"datasus_ftp": datasus, "caged_ftp": caged, "siconfi": siconfi}


def executar(alvos=ALVOS, agora=None) -> dict:
    """Cada fonte é testada sozinha: uma queda não esconde o resultado das outras."""
    resultado = {"conferido_em": (agora or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"), "fontes": {}}
    for nome, testar in alvos.items():
        inicio = time.monotonic()
        try:
            item = {"ok": True, **testar()}
        except Exception as e:
            item = {"ok": False, "erro": f"{type(e).__name__}: {str(e)[:300]}"}
        item["segundos_total"] = round(time.monotonic() - inicio, 2)
        resultado["fontes"][nome] = item
    return resultado
