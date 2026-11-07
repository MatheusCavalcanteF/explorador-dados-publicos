"""Sonda o FTP do SIH/SUS: lista RD, última competência, tamanhos por UF e datas de republicação."""
import ftplib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

saida = Path(sys.argv[1])
ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=120)
print(ftp.getwelcome())
print(ftp.login())
ftp.cwd("/dissemin/publicos/SIHSUS/")
print("raiz SIHSUS:", ftp.nlst())
ftp.cwd("/dissemin/publicos/SIHSUS/200801_/")
print("200801_:", ftp.nlst())
ftp.cwd("/dissemin/publicos/SIHSUS/200801_/Dados")
linhas: list[str] = []
ftp.retrlines("LIST", linhas.append)
print("linhas no LIST:", len(linhas))
print("amostra:", linhas[:3])

padrao = re.compile(r"(\d\d-\d\d-\d\d)\s+(\d\d:\d\d[AP]M)\s+(\d+)\s+(\S+)")
arquivos = []
for l in linhas:
    m = padrao.match(l)
    if not m:
        continue
    data, hora, tam, nome = m.groups()
    arquivos.append({"nome": nome, "tam": int(tam), "mod": datetime.strptime(data + " " + hora, "%m-%d-%y %I:%M%p").isoformat()})
print("arquivos reconhecidos:", len(arquivos))

prefixos = defaultdict(int)
for a in arquivos:
    prefixos[a["nome"][:2]] += 1
print("prefixos:", dict(prefixos))

rd = [a for a in arquivos if re.fullmatch(r"RD[A-Z]{2}\d{4}\.dbc", a["nome"], re.I)]
por_comp = defaultdict(lambda: {"ufs": 0, "tam": 0})
for a in rd:
    c = a["nome"][4:8]
    por_comp[c]["ufs"] += 1
    por_comp[c]["tam"] += a["tam"]
comps = sorted(por_comp, key=lambda c: (("19" if c[:2] > "50" else "20") + c))
print("primeira/ultima comp:", comps[0], comps[-1], "total de competências:", len(comps))
for c in comps[-30:]:
    print(c, por_comp[c]["ufs"], "UFs", round(por_comp[c]["tam"] / 1e6, 1), "MB")

# datas de modificação recentes por competência, em SP
sp = sorted((a for a in rd if a["nome"].upper().startswith("RDSP")), key=lambda a: a["nome"])
for a in sp[-30:]:
    print(a["nome"], a["tam"], a["mod"])

(saida / "sih_ftp_lista.json").write_text(json.dumps(arquivos), encoding="utf-8")
ftp.quit()
