"""Compara números calculados dos RD de SP com o TabNet, em municípios e competências de amostra.

Uso: python -I conferir_tabnet.py <pasta_rd_sp> <saida>
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb

PASTA, SAIDA = sys.argv[1], Path(sys.argv[2])
BASE = "http://tabnet.datasus.gov.br/cgi"
UA = {"User-Agent": "Mozilla/5.0"}


def formulario(defn):
    req = urllib.request.Request(f"{BASE}/deftohtm.exe?sih/cnv/{defn}.def", headers=UA)
    return urllib.request.urlopen(req, timeout=90).read().decode("latin-1")


def selects(texto):
    return re.findall(r'<select[^>]*name=["\']?([^"\' >]+)', texto, re.I)


def opcao_municipio(texto, codigo):
    bloco = texto[re.search(r'name=["\']?SMunic.pio', texto, re.I).start():]
    bloco = bloco[: bloco.lower().find("</select>")]
    m = re.search(r'value=["\']?(\d+)["\']?[^>]*>\s*' + codigo, bloco, re.I)
    return m.group(1)


def consultar(defn, texto, municipio, competencia, incremento, linha="Município"):
    nomes = selects(texto)
    pares = [("Linha", linha), ("Coluna", "--Não-Ativa--"), ("Incremento", incremento), ("Arquivos", f"{defn}{competencia}.dbf")]
    for n in nomes:
        if n in ("Linha", "Coluna", "Incremento", "Arquivos") or n.startswith("listahidden"):
            continue
        pares.append((n, opcao_municipio(texto, municipio) if n == "SMunicípio" else "TODAS_AS_CATEGORIAS__"))
    pares += [("zeradas", "exibirlz"), ("formato", "table"), ("mostre", "Mostra")]
    corpo = urllib.parse.urlencode(pares, encoding="latin-1").encode()
    req = urllib.request.Request(f"{BASE}/tabcgi.exe?sih/cnv/{defn}.def", data=corpo, headers={**UA, "Content-Type": "application/x-www-form-urlencoded", "Referer": f"{BASE}/deftohtm.exe?sih/cnv/{defn}.def"})
    resp = urllib.request.urlopen(req, timeout=120).read().decode("latin-1")
    fonte = re.findall(r"Fonte:[^<]*", resp)
    texto_limpo = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", resp)))
    achado = re.search(r"TOTAL (-|[\d.]+(?:,\d+)?)", texto_limpo)
    if achado:
        return achado.group(1), fonte[:1]
    return None, fonte[:1] or [texto_limpo[:200]]


def numero(s):
    if s is None:
        return None
    s = s.strip().replace(".", "").replace(",", ".")
    return float(s) if s not in ("-", "") else 0.0


con = duckdb.connect()
q = f"read_parquet('{PASTA}/RDSP25*.parquet')"
AMOSTRA_MUN = ["354850", "350635", "352210", "355030", "350010"]  # Santos, Bertioga, Itanhaém, São Paulo, Adamantina
AMOSTRA_COMP = ["2501", "2504", "2508"]
INCREMENTOS = {"Internações": "count(*) FILTER (IDENT='1')", "AIH_aprovadas": "count(*)", "Valor_total": "round(sum(VAL_TOT),2)", "Óbitos": "sum(MORTE)", "Dias_permanência": "sum(DIAS_PERM) FILTER (IDENT='1')"}
resultado = []
for defn, coluna in (("nisp", "MUNIC_MOV"), ("nrsp", "MUNIC_RES")):
    texto = formulario(defn)
    print(defn, "título:", ascii(re.findall(r"<title>(.*?)</title>", texto, re.I | re.S)[:1]), flush=True)
    for mun in AMOSTRA_MUN:
        for comp in AMOSTRA_COMP:
            for inc, expr in INCREMENTOS.items():
                calc = con.execute(f"SELECT {expr} FROM {q} WHERE {coluna}='{mun}' AND ANO_CMPT||MES_CMPT='20{comp}'").fetchone()[0]
                try:
                    bruto, fonte = consultar(defn, texto, mun, comp, inc)
                except Exception as exc:
                    bruto, fonte = None, [repr(exc)[:120]]
                oficial = numero(bruto)
                igual = oficial is not None and calc is not None and abs(float(calc) - oficial) < 0.011
                resultado.append({"visao": defn, "mun": mun, "comp": comp, "medida": inc, "calculado": float(calc) if calc is not None else None, "tabnet": oficial, "igual": igual})
                print(defn, mun, comp, ascii(inc), calc, oficial, "OK" if igual else "DIF", flush=True)
                time.sleep(0.5)
    print("fonte:", ascii(fonte), flush=True)
(SAIDA / "conferencia_tabnet.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=0), encoding="utf-8")
print("total", len(resultado), "iguais", sum(r["igual"] for r in resultado), "sem resposta", sum(r["tabnet"] is None for r in resultado))
por = {}
for r in resultado:
    por.setdefault(r["medida"], [0, 0])
    por[r["medida"]][0] += r["igual"]
    por[r["medida"]][1] += 1
print(ascii(por))
