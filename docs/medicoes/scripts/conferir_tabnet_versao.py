"""O TabNet já mostra a versão de outubro? Compara Santo André por competência, e lê a nota técnica sobre o eixo de atendimento.

Uso: python -I conferir_tabnet_versao.py <saida>
"""
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.append(sys.argv[2] if len(sys.argv) > 2 else "")
from pypdf import PdfReader

SAIDA = Path(sys.argv[1])
BASE = "http://tabnet.datasus.gov.br/cgi"
UA = {"User-Agent": "Mozilla/5.0"}
ESPERADO = {"2605": {"setembro": 3616, "outubro": 1269}, "2606": {"setembro": 4021, "outubro": 1401}, "2607": {"setembro": 3719, "outubro": 1333}}

t = urllib.request.urlopen(urllib.request.Request(f"{BASE}/deftohtm.exe?sih/cnv/nisp.def", headers=UA), timeout=90).read().decode("latin-1")
nomes = re.findall(r'<select[^>]*name=["\']?([^"\' >]+)', t, re.I)
b = t[re.search(r'name=["\']?SMunic.pio', t, re.I).start():]
b = b[: b.lower().find("</select>")]
op = re.search(r'value=["\']?(\d+)["\']?[^>]*>\s*354780', b, re.I).group(1)
res = {"santo_andre_por_competencia": {}}
for comp, esperado in ESPERADO.items():
    pares = [("Linha", "Município"), ("Coluna", "--Não-Ativa--"), ("Incremento", "Internações"), ("Arquivos", f"nisp{comp}.dbf")]
    for n in nomes:
        if n in ("Linha", "Coluna", "Incremento", "Arquivos") or n.startswith("listahidden"):
            continue
        pares.append((n, op if n == "SMunicípio" else "TODAS_AS_CATEGORIAS__"))
    pares += [("zeradas", "exibirlz"), ("formato", "table"), ("mostre", "Mostra")]
    r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/tabcgi.exe?sih/cnv/nisp.def", data=urllib.parse.urlencode(pares, encoding="latin-1").encode(), headers={**UA, "Content-Type": "application/x-www-form-urlencoded"}), timeout=120).read().decode("latin-1")
    limpo = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", r)))
    m = re.search(r"TOTAL ([\d.]+)", limpo)
    valor = int(m.group(1).replace(".", "")) if m else None
    res["santo_andre_por_competencia"][comp] = {"tabnet": valor, **esperado, "coincide_com": "outubro" if valor == esperado["outubro"] else ("setembro" if valor == esperado["setembro"] else "nenhuma")}
    print(comp, res["santo_andre_por_competencia"][comp], flush=True)

try:
    pdf = urllib.request.urlopen(urllib.request.Request(f"{BASE}/sih/Morb_geral_loc_int_2008.pdf", headers=UA), timeout=90).read()
    leitor = PdfReader(io.BytesIO(pdf))
    texto = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in leitor.pages))
    trechos = [texto[max(0, m.start() - 220) : m.end() + 320] for m in re.finditer(r"(?i)ano/m[eê]s (de )?atendimento|m[eê]s de atendimento|data de (sa[ií]da|interna)", texto)][:4]
    res["nota_tecnica"] = {"paginas": len(leitor.pages), "trechos": trechos}
    for x in trechos:
        print("NOTA:", ascii(x)[:640], flush=True)
    if not trechos:
        print("NOTA: nenhum trecho sobre atendimento; termos proximos:", ascii([texto[max(0, m.start() - 100) : m.end() + 160] for m in re.finditer(r"(?i)atendimento", texto)][:3])[:900], flush=True)
        res["nota_tecnica"]["trechos_atendimento"] = [texto[max(0, m.start() - 100) : m.end() + 160] for m in re.finditer(r"(?i)atendimento", texto)][:3]
except Exception as exc:
    res["nota_tecnica"] = {"erro": repr(exc)[:200]}
    print("nota tecnica:", repr(exc)[:200], flush=True)
(SAIDA / "conferencia_tabnet_versao.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
