"""Compara o saldo de 2025 calculado dos microdados com a divulgação do Ministério do Trabalho e Emprego.

Lê o comunicado e a apresentação do ministério e procura os números oficiais no texto. Do lado dos microdados,
soma MOV + FOR - EXC das competências de 2025, usando os arquivos gerados por medir_caged.py.

Uso: python -I conferir_caged_oficial.py <pasta_trabalho_caged> <saida.json>
"""
import html
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import duckdb
from pypdf import PdfReader

TRAB, SAIDA = Path(sys.argv[1]), Path(sys.argv[2])
BASE = "https://www.gov.br/trabalho-e-emprego/pt-br"
FONTES = {
    "comunicado": f"{BASE}/noticias-e-conteudo/2026/janeiro/novo-caged-brasil-encerra-2025-com-saldo-positivo-de-1-27-milhao-de-empregos-formais",
    "apresentacao": f"{BASE}/acesso-a-informacao/acoes-e-programas/programas-projetos-acoes-obras-e-atividades/estatisticas-trabalho/novo-caged/2025/dezembro/apresentacao-dezembro-de-2025-1.pdf",
    "sumario_executivo": f"{BASE}/acesso-a-informacao/acoes-e-programas/programas-projetos-acoes-obras-e-atividades/estatisticas-trabalho/novo-caged/2025/dezembro/sumario-executivo_-acumulado-e-dezembro-2025.pdf",
}
# A apresentação traz admissões e desligamentos que fecham com o saldo. O sumário executivo traz outros, que não fecham.
PROCURADOS = {"saldo": "1.279.498", "admissoes": "26.599.777", "desligamentos": "25.320.279", "saldo_dezembro": "618.164",
              "admissoes_sumario": "26.599.698", "desligamentos_sumario": "25.320.179"}


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read()


res = {"fontes": {}}
for nome, url in FONTES.items():
    try:
        dados = baixar(url)
        if url.endswith(".pdf"):
            texto = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(dados)).pages)
        else:
            texto = html.unescape(re.sub(r"<[^>]+>", " ", dados.decode("utf-8", errors="replace")))
        texto = re.sub(r"\s+", " ", texto)
        achados = {k: v in texto for k, v in PROCURADOS.items()}
        i = texto.find(PROCURADOS["saldo"])
        res["fontes"][nome] = {"url": url, "bytes": len(dados), "encontrados": achados, "trecho": texto[max(0, i - 130) : i + 150] if i >= 0 else None, "saldo_1278498_no_texto": "1.278.498" in texto}
    except Exception as exc:
        res["fontes"][nome] = {"url": url, "erro": repr(exc)[:160]}
    print(nome, ascii(json.dumps(res["fontes"][nome], ensure_ascii=False))[:520], flush=True)

con = duckdb.connect()
vistas = {}
for tipo in ("MOV", "FOR", "EXC"):
    arquivos = sorted(p.as_posix() for p in TRAB.glob(f"{tipo}_2025*.parquet"))
    con.execute(f"CREATE VIEW v_{tipo.lower()} AS SELECT * FROM read_parquet({arquivos!r}, union_by_name=true)")
nomes = [r[0] for r in con.execute("DESCRIBE SELECT * FROM v_mov").fetchall()]
comp = next(n for n in nomes if "compet" in n and "mov" in n)
saldo = next(n for n in nomes if "saldo" in n)


def contagem(tipo, valor):
    return con.execute(f"SELECT count(*) FROM v_{tipo} WHERE {comp} LIKE '2025%' AND {saldo}::INT={valor}").fetchone()[0]


adm = contagem("mov", 1) + contagem("for", 1) - contagem("exc", 1)
des = contagem("mov", -1) + contagem("for", -1) - contagem("exc", -1)
res["calculado"] = {"admissoes": adm, "desligamentos": des, "saldo": adm - des, "regra": "MOV + FOR - EXC, competências de 2025, arquivos publicados até 202512"}
res["oficial"] = {"admissoes": 26599777, "desligamentos": 25320279, "saldo": 1279498, "fonte": "apresentacao"}
res["iguais"] = {k: res["calculado"][k] == res["oficial"][k] for k in ("admissoes", "desligamentos", "saldo")}
res["sumario_executivo"] = {"admissoes": 26599698, "desligamentos": 25320179, "diferenca_entre_eles": 26599698 - 25320179, "nota": "não fecha com o saldo de 1.279.498 que o próprio documento informa"}
print(json.dumps({k: res[k] for k in ("calculado", "iguais", "sumario_executivo")}, ensure_ascii=False))
SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
