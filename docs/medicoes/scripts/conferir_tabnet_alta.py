"""O TabNet consulta por mês da alta? Lista os eixos do formulário e compara uma amostra pequena.

Uso: python -I conferir_tabnet_alta.py <pasta_rd_sp> <pasta_outras_uf> <saida>
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

PASTA_SP, PASTA_UF, SAIDA = sys.argv[1], sys.argv[2], Path(sys.argv[3])
BASE = "http://tabnet.datasus.gov.br/cgi"
UA = {"User-Agent": "Mozilla/5.0"}
COMPETENCIAS = [f"25{m:02d}" for m in range(1, 13)]
MUNICIPIOS = ["354850", "350635", "352210", "350010", "355030"]


def formulario(defn):
    return urllib.request.urlopen(urllib.request.Request(f"{BASE}/deftohtm.exe?sih/cnv/{defn}.def", headers=UA), timeout=90).read().decode("latin-1")


def opcoes(texto, nome):
    i = re.search(r'name=["\']?' + nome + r'["\']?', texto, re.I)
    bloco = texto[i.start():]
    bloco = bloco[: bloco.lower().find("</select>")]
    return re.findall(r'value=["\']?([^"\'>]+)["\']?[^>]*>\s*([^<\r\n]*)', bloco, re.I)


def consultar(defn, texto, municipio, linha, incremento):
    nomes = re.findall(r'<select[^>]*name=["\']?([^"\' >]+)', texto, re.I)
    bloco = texto[re.search(r'name=["\']?SMunic.pio', texto, re.I).start():]
    bloco = bloco[: bloco.lower().find("</select>")]
    op = re.search(r'value=["\']?(\d+)["\']?[^>]*>\s*' + municipio, bloco, re.I).group(1)
    pares = [("Linha", linha), ("Coluna", "--Não-Ativa--"), ("Incremento", incremento)]
    pares += [("Arquivos", f"{defn}{c}.dbf") for c in COMPETENCIAS]
    for n in nomes:
        if n in ("Linha", "Coluna", "Incremento", "Arquivos") or n.startswith("listahidden"):
            continue
        pares.append((n, op if n == "SMunicípio" else "TODAS_AS_CATEGORIAS__"))
    pares += [("zeradas", "exibirlz"), ("formato", "prn"), ("mostre", "Mostra")]
    corpo = urllib.parse.urlencode(pares, encoding="latin-1").encode()
    req = urllib.request.Request(f"{BASE}/tabcgi.exe?sih/cnv/{defn}.def", data=corpo, headers={**UA, "Content-Type": "application/x-www-form-urlencoded", "Referer": f"{BASE}/deftohtm.exe?sih/cnv/{defn}.def"})
    return urllib.request.urlopen(req, timeout=180).read().decode("latin-1")


texto = formulario("nisp")
linhas = opcoes(texto, "Linha")
colunas = opcoes(texto, "Coluna")
print("Linha:", ascii([html.unescape(b).strip() for _, b in linhas]), flush=True)
print("Coluna:", ascii([html.unescape(b).strip() for _, b in colunas]), flush=True)
candidatas = [(a, html.unescape(b).strip()) for a, b in linhas if re.search(r"atendimento|saida|sa.da|alta|interna..o", html.unescape(b + " " + a), re.I) and re.search(r"ano|m.s", html.unescape(b), re.I)]
print("eixos de tempo candidatos:", ascii(candidatas), flush=True)
notas = re.findall(r'href=["\']?([^"\' >]+\.(?:pdf|htm))', texto, re.I)
print("documentos citados:", ascii(sorted(set(notas))[:12]), flush=True)

res = {"eixos_de_tempo_no_formulario": candidatas, "competencias_selecionadas": COMPETENCIAS, "comparacoes": []}
if not candidatas:
    res["conclusao"] = "o formulário não oferece eixo por data"
else:
    eixo = next((a for a, b in candidatas if re.search(r"ano/m.s", b, re.I)), candidatas[0][0])
    res["eixo_usado"] = eixo
    bruto = consultar("nisp", texto, MUNICIPIOS[0], eixo, "Internações")
    amostra = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", bruto)))
    print("amostra da resposta:", ascii(amostra[:900]), flush=True)

    con = duckdb.connect()
    col = "ANO_CMPT,MES_CMPT,IDENT,MUNIC_MOV,MUNIC_RES,DT_SAIDA,DT_INTER"
    con.execute(f"CREATE VIEW sp AS SELECT {col} FROM read_parquet('{PASTA_SP}/RDSP25*.parquet')")
    con.execute(f"CREATE VIEW br AS SELECT {col} FROM read_parquet('{PASTA_SP}/RDSP25*.parquet') UNION ALL BY NAME SELECT {col} FROM read_parquet('{PASTA_UF}/RD*.parquet')")
    MESES = {"Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04", "Maio": "05", "Junho": "06", "Julho": "07", "Agosto": "08", "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12",
             "Jan": "01", "Fev": "02", "Mar": "03", "Abr": "04", "Mai": "05", "Jun": "06", "Jul": "07", "Ago": "08", "Set": "09", "Out": "10", "Nov": "11", "Dez": "12"}

    def linhas_tabnet(resposta):
        txt = html.unescape(re.sub(r"<[^>]+>", "\n", resposta))
        saida = {}
        for m in re.finditer(r'"[. ]*(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)/(\d{4})";\s*([\d.]+|-)', txt):
            valor = 0 if m.group(3) == "-" else int(m.group(3).replace(".", ""))
            if valor:
                saida[m.group(2) + MESES[m.group(1)]] = valor
        return saida

    for visao, defn, coluna, base in (("hospital", "nisp", "MUNIC_MOV", "sp"), ("residencia", "nrsp", "MUNIC_RES", "br")):
        form = formulario(defn) if defn != "nisp" else texto
        eixo_v = next((a for a, b in opcoes(form, "Linha") if a == eixo), None)
        if eixo_v is None:
            res["comparacoes"].append({"visao": visao, "erro": "eixo ausente"})
            continue
        for mun in MUNICIPIOS:
            oficial = linhas_tabnet(consultar(defn, form, mun, eixo_v, "Internações"))
            saida = dict(con.execute(f"SELECT substr(DT_SAIDA,1,6), count(*) FILTER (IDENT='1') FROM {base} WHERE {coluna}='{mun}' GROUP BY 1").fetchall())
            entrada = dict(con.execute(f"SELECT substr(DT_INTER,1,6), count(*) FILTER (IDENT='1') FROM {base} WHERE {coluna}='{mun}' GROUP BY 1").fetchall())
            meses = sorted(set(oficial) | {k for k, v in saida.items() if v})
            igual_saida = sum(oficial.get(m, 0) == saida.get(m, 0) for m in meses)
            igual_entrada = sum(oficial.get(m, 0) == entrada.get(m, 0) for m in meses)
            maior = max((abs(oficial.get(m, 0) - saida.get(m, 0)) for m in meses), default=None)
            # Nada por mês no resultado guardado: o total menos os meses listados revelaria os omitidos, ainda que pequenos
            l = {"visao": visao, "municipio": mun, "meses": len(meses), "meses_lidos_do_tabnet": len(oficial), "iguais_data_de_saida": igual_saida, "iguais_data_de_internacao": igual_entrada, "maior_diferenca_saida": maior, "total_tabnet": sum(oficial.values()), "total_saida": sum(saida.values())}
            res["comparacoes"].append(l)
            print(json.dumps(l), flush=True)
            time.sleep(0.7)

(SAIDA / "conferencia_tabnet_alta.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print("fim")
