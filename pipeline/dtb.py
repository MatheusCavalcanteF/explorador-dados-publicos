"""Lista oficial de municípios pela Divisão Territorial Brasileira (DTB), no geoftp do IBGE.

A API de localidades do IBGE não aceitou conexão do runner (ver "Fontes que recusam o runner"
no plano), e o geoftp aceitou. A DTB sai uma vez por ano, numa pasta por ano, como um .zip com
planilhas em .ods e .xls. O pipeline acha a mais recente e lê a planilha de municípios em .ods,
que é XML dentro de um zip e dispensa dependência nova. Qualquer mudança de estrutura para o
pipeline com erro claro, em vez de virar lista errada.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

from . import rede
from .contrato import ErroDeContrato, sha256_valores

RAIZ = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/"
# Se as pastas mais recentes não tiverem arquivo nenhum, a publicação mudou de lugar ou de forma.
PASTAS_A_PROCURAR = 3
PLANILHA = re.compile(r"(?:^|/)RELATORIO_DTB_BRASIL[^/]*MUNICIPIO[^/]*\.ods", re.IGNORECASE)
COLUNAS = {"uf": "UF", "uf_nome": "Nome_UF", "codigo": "Código Município Completo", "nome": "Nome_Município"}
DATA_BASE = re.compile(r"DATA BASE:\s*(\d{2})/(\d{2})/(\d{4})")
# Contra arquivo corrompido ou malicioso: a planilha de 2025 tem 206 KB, e o XML dentro dela, 7,7 MB.
MAX_PLANILHA = 50_000_000
MAX_XML = 200_000_000
MAX_COLUNAS = 200

# A DTB traz o código e o nome da UF, não a sigla. As 27 UFs não mudam desde 1988; se o nome
# vier diferente, a tabela da DTB mudou e o pipeline para.
UFS = {
    "11": ("RO", "Rondônia"), "12": ("AC", "Acre"), "13": ("AM", "Amazonas"), "14": ("RR", "Roraima"),
    "15": ("PA", "Pará"), "16": ("AP", "Amapá"), "17": ("TO", "Tocantins"), "21": ("MA", "Maranhão"),
    "22": ("PI", "Piauí"), "23": ("CE", "Ceará"), "24": ("RN", "Rio Grande do Norte"), "25": ("PB", "Paraíba"),
    "26": ("PE", "Pernambuco"), "27": ("AL", "Alagoas"), "28": ("SE", "Sergipe"), "29": ("BA", "Bahia"),
    "31": ("MG", "Minas Gerais"), "32": ("ES", "Espírito Santo"), "33": ("RJ", "Rio de Janeiro"),
    "35": ("SP", "São Paulo"), "41": ("PR", "Paraná"), "42": ("SC", "Santa Catarina"),
    "43": ("RS", "Rio Grande do Sul"), "50": ("MS", "Mato Grosso do Sul"), "51": ("MT", "Mato Grosso"),
    "52": ("GO", "Goiás"), "53": ("DF", "Distrito Federal"),
}

_TABELA = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_TEXTO = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_CELULAS = (f"{{{_TABELA}}}table-cell", f"{{{_TABELA}}}covered-table-cell")


def _baixar(url: str, pedir) -> rede.Resposta:
    resposta = pedir(url)
    if resposta.status != 200:
        raise ErroDeContrato(f"DTB: HTTP {resposta.status} em {url}")
    return resposta


def _links(html: bytes) -> list[str]:
    """Links relativos de uma listagem de pasta do servidor (Apache "Index of")."""
    return re.findall(r'<a href="([^"?/:][^":]*)"', html.decode("latin-1"))


def achar(pedir) -> tuple[str, str, list[str]]:
    """Devolve (ano, url do .zip, pastas recentes que ainda não têm arquivo)."""
    anos = sorted({link[:4] for link in _links(_baixar(RAIZ, pedir).corpo) if re.fullmatch(r"\d{4}/", link)},
                  reverse=True)
    if not anos:
        raise ErroDeContrato(f"DTB: a listagem de {RAIZ} não tem pastas de ano. A estrutura do geoftp mudou.")
    vazias = []
    for ano in anos[:PASTAS_A_PROCURAR]:
        arquivos = [link for link in _links(_baixar(f"{RAIZ}{ano}/", pedir).corpo) if link.lower().endswith(".zip")]
        if f"DTB_{ano}.zip" in arquivos:
            return ano, f"{RAIZ}{ano}/DTB_{ano}.zip", vazias
        if arquivos:
            # Arquivo com outro nome: usar a DTB do ano anterior esconderia a mais recente.
            raise ErroDeContrato(f"DTB: a pasta {ano} tem {arquivos} em vez de DTB_{ano}.zip. A estrutura mudou.")
        vazias.append(ano)
    raise ErroDeContrato(f"DTB: nenhuma DTB_{{ano}}.zip nas pastas {vazias} de {RAIZ}")


def _texto(elemento) -> str:
    partes = [elemento.text or ""]
    for filho in elemento:
        if filho.tag == f"{{{_TEXTO}}}s":
            partes.append(" " * int(filho.get(f"{{{_TEXTO}}}c", "1")))
        elif filho.tag == f"{{{_TEXTO}}}tab":
            partes.append("\t")
        elif filho.tag == f"{{{_TEXTO}}}line-break":
            partes.append("\n")
        else:
            partes.append(_texto(filho))
        partes.append(filho.tail or "")
    return "".join(partes)


def linhas_ods(ods: bytes, onde: str) -> list[list[str]]:
    """Linhas não vazias da primeira folha, como texto. Células repetidas e mescladas mantêm a posição."""
    try:
        with zipfile.ZipFile(io.BytesIO(ods)) as z:
            info = z.getinfo("content.xml")
            if info.file_size > MAX_XML:
                raise ErroDeContrato(f"{onde}: content.xml com {info.file_size} bytes, acima do limite")
            raiz = ET.fromstring(z.read(info))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise ErroDeContrato(f"{onde}: não é uma planilha .ods legível ({type(e).__name__})") from None
    folha = raiz.find(f".//{{{_TABELA}}}table")
    if folha is None:
        raise ErroDeContrato(f"{onde}: planilha sem folha")
    linhas = []
    for linha in folha.iter(f"{{{_TABELA}}}table-row"):
        celulas = []
        for celula in linha:
            if celula.tag not in _CELULAS:
                continue
            texto = "\n".join(_texto(p) for p in celula.iter(f"{{{_TEXTO}}}p")).strip()
            repetir = int(celula.get(f"{{{_TABELA}}}number-columns-repeated", "1"))
            celulas.extend([texto] * min(repetir, MAX_COLUNAS - len(celulas)))
        while celulas and not celulas[-1]:
            celulas.pop()
        if celulas:
            # Linha com conteúdo repetida duplicaria municípios; o contrato pega a repetição.
            linhas.extend([celulas] * min(int(linha.get(f"{{{_TABELA}}}number-rows-repeated", "1")), 2))
    return linhas


def ler(zip_dtb: bytes, onde: str) -> tuple[str, str, list[dict]]:
    """Devolve (nome da planilha, data-base em ISO, municípios ordenados por código)."""
    try:
        externo = zipfile.ZipFile(io.BytesIO(zip_dtb))
    except zipfile.BadZipFile:
        raise ErroDeContrato(f"{onde}: o arquivo não é um .zip") from None
    with externo:
        candidatas = [i for i in externo.infolist() if PLANILHA.search(i.filename)]
        if len(candidatas) != 1:
            nomes = [i.filename for i in externo.infolist()]
            raise ErroDeContrato(f"{onde}: esperava uma planilha de municípios em .ods, achei "
                                 f"{len(candidatas)} entre {nomes[:12]}")
        info = candidatas[0]
        if info.file_size > MAX_PLANILHA:
            raise ErroDeContrato(f"{onde}: {info.filename} com {info.file_size} bytes, acima do limite")
        try:
            ods = externo.read(info)
        except (zipfile.BadZipFile, RuntimeError, ValueError) as e:
            raise ErroDeContrato(f"{onde}: {info.filename} não abre ({type(e).__name__}: {e})") from None
        linhas = linhas_ods(ods, f"{onde}, {info.filename}")

    inicio = next((i for i, l in enumerate(linhas) if set(COLUNAS.values()) <= set(l)), None)
    if inicio is None:
        raise ErroDeContrato(f"{onde}: nenhuma linha com as colunas {sorted(COLUNAS.values())}. A estrutura mudou.")
    datas = {m.groups() for linha in linhas[:inicio] for celula in linha if (m := DATA_BASE.fullmatch(celula))}
    if len(datas) != 1:
        raise ErroDeContrato(f"{onde}: esperava uma 'DATA BASE: dd/mm/aaaa' acima do cabeçalho, achei {len(datas)}")
    dia, mes, ano = datas.pop()
    posicao = {nome: linhas[inicio].index(rotulo) for nome, rotulo in COLUNAS.items()}

    municipios, prefixos = {}, set()
    for linha in linhas[inicio + 1:]:
        valor = {nome: (linha[i] if i < len(linha) else "") for nome, i in posicao.items()}
        codigo, uf = valor["codigo"], valor["uf"]
        if uf not in UFS:
            raise ErroDeContrato(f"{onde}: UF {uf!r} desconhecida na linha {linha[:9]}")
        sigla, uf_nome = UFS[uf]
        if valor["uf_nome"] != uf_nome:
            raise ErroDeContrato(f"{onde}: a UF {uf} vem como {valor['uf_nome']!r}, e não {uf_nome!r}")
        if not re.fullmatch(r"\d{7}", codigo) or not codigo.startswith(uf):
            raise ErroDeContrato(f"{onde}: código {codigo!r} inválido para a UF {sigla}")
        if not valor["nome"]:
            raise ErroDeContrato(f"{onde}: município {codigo} sem nome")
        if codigo in municipios or codigo[:6] in prefixos:
            # SIH e CAGED usam 6 dígitos; a conversão só é segura se o prefixo for único.
            raise ErroDeContrato(f"{onde}: código ou prefixo de 6 dígitos repetido em {codigo}")
        prefixos.add(codigo[:6])
        municipios[codigo] = {"codigo": codigo, "nome": valor["nome"], "uf": sigla, "uf_nome": uf_nome}
    ufs = {m["uf"] for m in municipios.values()}
    if len(ufs) != 27 or not 5_500 <= len(municipios) <= 5_700:
        raise ErroDeContrato(f"{onde}: {len(municipios)} municípios em {len(ufs)} UFs, fora do esperado")
    return info.filename, f"{ano}-{mes}-{dia}", [municipios[c] for c in sorted(municipios)]


def coletar(pedir, coletado_em: str) -> tuple[dict, list[dict]]:
    """Devolve (fonte para o manifesto, municípios)."""
    ano, url, vazias = achar(pedir)
    resposta = _baixar(url, pedir)
    # Com gzip no caminho, o Content-Length é o do comprimido; aí o próprio zip denuncia o corte.
    esperado = None if resposta.cabecalho("Content-Encoding") else resposta.cabecalho("Content-Length")
    if esperado is not None and esperado != str(len(resposta.corpo)):
        raise ErroDeContrato(f"DTB {ano}: {len(resposta.corpo)} bytes recebidos de {esperado}")
    planilha, data_base, municipios = ler(resposta.corpo, f"DTB {ano}")
    fonte = {
        "base": "ibge_dtb", "url": url, "periodo": ano, "data_base": data_base, "planilha": planilha,
        "coletado_em": coletado_em, "bytes": len(resposta.corpo), "sha256": rede.sha256(resposta.corpo),
        "last_modified": resposta.cabecalho("Last-Modified"), "pastas_sem_dtb": vazias,
        "municipios": len(municipios),
        "sha256_valores": sha256_valores({m["codigo"]: [m["nome"], m["uf"]] for m in municipios}),
    }
    return fonte, municipios
