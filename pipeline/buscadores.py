"""Buscadores: JSON-LD do schema.org (Dataset), sitemap e arquivo de verificação do Google Search Console.

O JSON-LD descreve o que a página mostra: cada número vira uma parte, com a fonte oficial, a licença
da base, o período de referência e o link do valor na origem. Cada bloco é validado antes de ser
gravado, e um bloco inválido para a publicação.

O lastmod do sitemap e o dateModified do JSON-LD são a data em que a coleta viu pela primeira vez
os valores que a página mostra. A página é refeita toda semana, com a data da coleta no rodapé,
mas só muda de fato quando um valor muda.
"""
from __future__ import annotations

import json
import re
from xml.sax.saxutils import escape

from . import projeto

# Limites do protocolo de sitemap: 50.000 endereços e 50 MiB sem compressão por arquivo.
MAX_URLS = 50_000
MAX_BYTES = 52_428_800
DATA_HORA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
# Ano, data ou intervalo ISO 8601, como o schema.org pede em temporalCoverage.
PERIODO = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?(/\d{4}(-\d{2}(-\d{2})?)?)?")
URL = re.compile(r"https?://[^\s\"'<>]+")
BRASIL = {"@type": "Country", "name": "Brasil"}


class ErroDeBuscadores(ValueError):
    """JSON-LD ou sitemap fora do que os buscadores aceitam."""


def desde(fonte: dict) -> str:
    """Desde quando a coleta vê os valores atuais desta fonte. Sem o registro, vale a própria coleta."""
    return fonte.get("valores_desde") or fonte["coletado_em"]


def _data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def licenca(base: dict) -> str | dict:
    """URL da licença quando a base declara uma; senão, um CreativeWork que diz que a origem não declara."""
    if base["licenca"].get("url"):
        return base["licenca"]["url"]
    return {"@type": "CreativeWork", "name": "Licença não declarada na origem"}


def _parte(nome: str, descricao: str, base: dict, periodo: str, fonte_oficial: str, download: str,
           formato: str, variavel: dict | None = None) -> dict:
    parte = {"@type": "Dataset", "name": nome, "description": descricao,
             "creator": {"@type": "Organization", "name": base["orgao"]},
             "citation": base["licenca"]["atribuicao"], "license": licenca(base),
             "isBasedOn": fonte_oficial, "temporalCoverage": periodo,
             "distribution": {"@type": "DataDownload", "contentUrl": download, "encodingFormat": formato}}
    if variavel:
        parte["variableMeasured"] = variavel
    return parte


def parte_metrica(chave: str, metrica: dict, base: dict, fonte: dict, m: dict | None = None) -> dict:
    """Um número da página; `chave` é o nome da métrica, que também é o campo do município.
    Sem município, a parte descreve a resposta da fonte para todos eles."""
    f, periodo, rotulo = metrica["fonte"], fonte["periodo"], metrica["rotulo"]
    onde = f"{m['nome']} ({m['uf']})" if m else "cada município do Brasil"
    nome = f"{rotulo} de {onde}" + ("" if periodo in rotulo else f", {periodo}")
    download = f["acesso"]["url"].format(municipio=m["codigo"], periodo=periodo) if m else fonte["url"]
    descricao = (f"{rotulo}, em {metrica['unidade']}, de {onde}, segundo o {f['orgao']}: {f['pesquisa']}. "
                 f"Período de referência: {periodo}.")
    variavel = {"@type": "PropertyValue", "name": rotulo, "unitText": metrica["unidade"]}
    if m and m.get(chave) is not None:
        variavel["value"] = m[chave]
    return _parte(nome, descricao, base, periodo, f["tabela"], download, "application/json", variavel)


def parte_dtb(base: dict, fonte: dict, m: dict | None = None, uf_nome: str | None = None) -> dict:
    edicao = f"{base['nome']} {fonte['periodo']}"
    quando = f"com data-base em {_data(fonte['data_base'])}"
    if m:
        nome = f"{m['nome']} ({m['uf']}) na {edicao}"
        descricao = f"Código IBGE {m['codigo']}, nome e UF de {m['nome']} na {edicao} do {base['orgao']}, {quando}."
    else:
        onde = f"de {uf_nome}" if uf_nome else "do Brasil"
        nome = f"Municípios {onde} na {edicao}"
        descricao = f"Código IBGE, nome e UF dos municípios {onde} na {edicao} do {base['orgao']}, {quando}."
    return _parte(nome, descricao, base, fonte["data_base"], base["coleta"]["origem"], fonte["url"], "application/zip")


def lugar_municipio(m: dict) -> dict:
    return {"@type": "Place", "name": f"{m['nome']}, {m['uf_nome']}, Brasil",
            "identifier": {"@type": "PropertyValue", "propertyID": "Código IBGE do município", "value": m["codigo"]},
            "containedInPlace": {"@type": "AdministrativeArea", "name": m["uf_nome"]}}


def lugar_uf(codigo_uf: str, uf_nome: str) -> dict:
    return {"@type": "AdministrativeArea", "name": f"{uf_nome}, Brasil",
            "identifier": {"@type": "PropertyValue", "propertyID": "Código IBGE da UF", "value": codigo_uf}}


def _um_ou_lista(valores: list):
    unicos = list({json.dumps(v, sort_keys=True, ensure_ascii=False): v for v in valores}.values())
    return unicos[0] if len(unicos) == 1 else unicos


def dataset(nome: str, descricao: str, endereco: str, alterado_em: str, lugar: dict, partes: list[dict],
            palavras: list[str], distribuicao: list[dict] | None = None) -> dict:
    """O Dataset da página, com uma parte por fonte. Licença e órgão da raiz saem das partes."""
    url = projeto.SITE + endereco
    dado = {"@context": "https://schema.org", "@type": "Dataset", "name": nome, "description": descricao,
            "url": url, "inLanguage": "pt-BR", "isAccessibleForFree": True, "dateModified": alterado_em,
            "keywords": palavras, "spatialCoverage": lugar,
            "creator": _um_ou_lista([p["creator"] for p in partes]),
            "license": _um_ou_lista([p["license"] for p in partes]),
            "isBasedOn": list(dict.fromkeys(p["isBasedOn"] for p in partes)),
            "includedInDataCatalog": {"@type": "DataCatalog", "name": projeto.NOME, "url": projeto.SITE},
            "hasPart": partes}
    if distribuicao:
        dado["distribution"] = distribuicao
    validar(dado, url)
    return dado


def _lista(valor) -> list:
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _url(valor) -> bool:
    return isinstance(valor, str) and URL.fullmatch(valor) is not None


def _validar_dataset(d: dict, onde: str, erros: list[str]) -> None:
    if d.get("@type") != "Dataset":
        erros.append(f"{onde}: @type deve ser Dataset")
    nome, descricao = d.get("name"), d.get("description")
    if not isinstance(nome, str) or not nome.strip():
        erros.append(f"{onde}: sem name")
    # O Google pede descrição de 50 a 5.000 caracteres.
    if not isinstance(descricao, str) or not 50 <= len(descricao) <= 5000:
        erros.append(f"{onde}: description precisa ter de 50 a 5.000 caracteres")
    licencas = _lista(d.get("license"))
    if not licencas or not all(_url(lic) or (isinstance(lic, dict) and lic.get("@type") == "CreativeWork"
                                             and lic.get("name")) for lic in licencas):
        erros.append(f"{onde}: license deve ser URL ou CreativeWork com name")
    criadores = _lista(d.get("creator"))
    if not criadores or not all(isinstance(c, dict) and c.get("@type") == "Organization" and c.get("name")
                                for c in criadores):
        erros.append(f"{onde}: creator deve ser Organization com name")
    fontes = _lista(d.get("isBasedOn"))
    if not fontes or not all(_url(f) for f in fontes):
        erros.append(f"{onde}: isBasedOn deve trazer a URL da fonte oficial")
    for dist in _lista(d.get("distribution")):
        if dist.get("@type") != "DataDownload" or not _url(dist.get("contentUrl")) or not dist.get("encodingFormat"):
            erros.append(f"{onde}: distribution deve ser DataDownload com contentUrl e encodingFormat")


def validar(dado: dict, url: str) -> None:
    """Confere o que o pipeline promete em cada página; falha com a lista de problemas."""
    erros: list[str] = []
    if dado.get("@context") != "https://schema.org":
        erros.append("raiz: @context deve ser https://schema.org")
    _validar_dataset(dado, "raiz", erros)
    if dado.get("url") != url or not url.startswith(projeto.SITE):
        erros.append(f"raiz: url deve ser o endereço canônico {url}")
    if not DATA_HORA.fullmatch(str(dado.get("dateModified"))):
        erros.append("raiz: dateModified deve ser data e hora em UTC")
    if not (dado.get("spatialCoverage") or {}).get("name"):
        erros.append("raiz: spatialCoverage sem name")
    if (dado.get("includedInDataCatalog") or {}).get("url") != projeto.SITE:
        erros.append("raiz: includedInDataCatalog deve apontar para o site")
    partes = _lista(dado.get("hasPart"))
    if not partes:
        erros.append("raiz: hasPart vazio; cada fonte da página é uma parte")
    for i, parte in enumerate(partes):
        onde = f"hasPart[{i}]"
        _validar_dataset(parte, onde, erros)
        if not PERIODO.fullmatch(str(parte.get("temporalCoverage"))):
            erros.append(f"{onde}: temporalCoverage deve ser ano, data ou intervalo ISO 8601")
        if not parte.get("distribution"):
            erros.append(f"{onde}: sem distribution com o endereço do dado na origem")
    if erros:
        raise ErroDeBuscadores(f"JSON-LD de {url}: " + "; ".join(erros))


def script(dado: dict) -> str:
    texto = json.dumps(dado, ensure_ascii=False, separators=(",", ":"))
    # Um nome com "</script>" fecharia o bloco. O JSON aceita os três caracteres escritos como \u.
    texto = texto.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/ld+json">{texto}</script>'


def sitemap(entradas: list[tuple[str, str]]) -> str:
    """entradas: (endereço relativo ao site, data da última mudança dos valores)."""
    if len(entradas) > MAX_URLS:
        raise ErroDeBuscadores(f"Sitemap com {len(entradas)} endereços, acima do limite de {MAX_URLS}")
    linhas = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    vistos = set()
    for endereco, alterado_em in entradas:
        if endereco in vistos:
            raise ErroDeBuscadores(f"Sitemap: endereço repetido {endereco!r}")
        if not DATA_HORA.fullmatch(alterado_em):
            raise ErroDeBuscadores(f"Sitemap: lastmod {alterado_em!r} de {endereco!r} não é data e hora em UTC")
        vistos.add(endereco)
        linhas.append(f"<url><loc>{escape(projeto.SITE + endereco)}</loc><lastmod>{alterado_em}</lastmod></url>")
    texto = "\n".join(linhas + ["</urlset>"]) + "\n"
    if len(texto.encode("utf-8")) > MAX_BYTES:
        raise ErroDeBuscadores(f"Sitemap com {len(texto.encode('utf-8'))} bytes, acima do limite de {MAX_BYTES}")
    return texto


def verificacao_google(codigo: str) -> tuple[str, str]:
    """Nome e conteúdo do arquivo que o Search Console procura na raiz do site."""
    return f"{codigo}.html", f"google-site-verification: {codigo}.html"
