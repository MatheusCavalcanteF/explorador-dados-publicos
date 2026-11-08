"""Pedidos HTTP com tempo limite, novas tentativas e identificação do projeto. Os testes injetam um substituto."""
from __future__ import annotations

import gzip
import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import projeto

AGENTE = f"{projeto.NOME_CURTO} (+{projeto.REPOSITORIO})"


class ErroDeRede(RuntimeError):
    """A fonte não respondeu depois de todas as tentativas."""


@dataclass
class Resposta:
    status: int
    cabecalhos: dict
    corpo: bytes
    segundos: float

    def cabecalho(self, nome: str) -> str | None:
        alvo = nome.lower()
        return next((v for k, v in self.cabecalhos.items() if k.lower() == alvo), None)


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def pedir(url: str, metodo: str = "GET", cabecalhos: dict | None = None, tentativas: int = 3,
          espera: float = 5.0, tempo: float = 60, descomprimir: bool = True, dormir=time.sleep) -> Resposta:
    """Repete em falha de rede e em 5xx; 4xx volta como resposta, para quem chamou decidir."""
    ultimo = None
    for tentativa in range(tentativas):
        pedido = urllib.request.Request(url, method=metodo, headers={"User-Agent": AGENTE, **(cabecalhos or {})})
        inicio = time.monotonic()
        try:
            with urllib.request.urlopen(pedido, timeout=tempo) as r:
                corpo = r.read()
                resposta = Resposta(r.status, dict(r.headers.items()), corpo, time.monotonic() - inicio)
        except urllib.error.HTTPError as e:
            resposta = Resposta(e.code, dict(e.headers.items()), e.read(), time.monotonic() - inicio)
            if e.code < 500:
                return resposta
            ultimo = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            ultimo = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        else:
            # A API de serviços do IBGE responde em gzip mesmo sem pedir.
            if descomprimir and (resposta.cabecalho("Content-Encoding") == "gzip" or corpo[:2] == b"\x1f\x8b"):
                resposta.corpo = gzip.decompress(corpo)
            return resposta
        if tentativa + 1 < tentativas:
            dormir(espera * (tentativa + 1))
    raise ErroDeRede(f"{url} não respondeu após {tentativas} tentativas ({ultimo})")
