"""Investiga o que mais existe no FTP do SIH e compara as cópias locais com a versão atual."""
import ftplib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

saida = Path(sys.argv[1])
raw_local = Path(sys.argv[2])

ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=120)
ftp.login()


def listar(caminho, limite=25):
    print(f"\n--- {caminho}")
    linhas = []
    try:
        ftp.cwd(caminho)
        ftp.retrlines("LIST", linhas.append)
    except ftplib.all_errors as exc:
        print("erro:", exc)
        return []
    print("itens:", len(linhas))
    for l in linhas[:limite]:
        print(" ", l)
    if len(linhas) > limite:
        print("  ...")
        for l in linhas[-5:]:
            print(" ", l)
    return linhas


listar("/dissemin/publicos/SIHSUS/")
for sub in ("CSV", "DBF", "XML", "Arquivos_MTBR"):
    listar(f"/dissemin/publicos/SIHSUS/{sub}", 12)
listar("/dissemin/publicos/SIHSUS/200801_/Auxiliar")
listar("/dissemin/publicos/SIHSUS/200801_/Doc")

# Quais UFs faltam na última competência?
arquivos = json.loads((saida / "sih_ftp_lista.json").read_text(encoding="utf-8"))
rd = [a for a in arquivos if re.fullmatch(r"RD[A-Z]{2}\d{4}\.dbc", a["nome"], re.I)]
ufs = sorted({a["nome"][2:4].upper() for a in rd})
print("\nUFs no RD:", len(ufs), ufs)
presentes = {a["nome"][2:4].upper() for a in rd if a["nome"][4:8] == "2608"}
print("faltam em 2608:", sorted(set(ufs) - presentes))
buracos = {}
for ano in range(8, 27):
    for mes in range(1, 13):
        c = f"{ano:02d}{mes:02d}"
        if c > "2607":
            continue
        pres = {a["nome"][2:4].upper() for a in rd if a["nome"][4:8] == c}
        if pres != set(ufs):
            buracos[c] = sorted(set(ufs) - pres)
print("competências com UF faltando até 2607:", buracos)

# Republicação: datas distintas de modificação nos últimos anos, para todas as UFs
ultimas = sorted({a["mod"][:10] for a in rd if a["mod"] >= "2025-10"})
print("\ndatas de modificação de RD desde 10/2025:", ultimas)
for d in ultimas[-6:]:
    grupo = [a for a in rd if a["mod"][:10] == d]
    print(d, len(grupo), "arquivos", "comp min/max", min(a["nome"][4:8] for a in grupo), max(a["nome"][4:8] for a in grupo))

# Local x FTP: a cópia local guarda o mtime do FTP da época em que foi baixada
print("\nlocal x FTP atual (revisão de RDSP):")
atual = {a["nome"].upper(): a for a in rd}
print("arquivo tam_local tam_ftp dif% mod_local mod_ftp")
for p in sorted(raw_local.glob("RDSP*.dbc")):
    a = atual.get(p.name.upper())
    if not a:
        continue
    st = p.stat()
    mod = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    print(p.name, st.st_size, a["tam"], f"{100 * (a['tam'] - st.st_size) / st.st_size:+.2f}%", mod, a["mod"][:10])
ftp.quit()
