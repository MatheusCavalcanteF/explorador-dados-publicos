"""Baixa CAGEDMOV/FOR/EXC de 2025 com 3 conexões (cada arquivo em sua própria subpasta)."""
import ftplib, sys, time, json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
dest = Path(sys.argv[1])
def baixar(args):
    tipo, comp = args
    nome = f"CAGED{tipo}{comp}.7z"; alvo = dest/comp/nome; alvo.parent.mkdir(parents=True, exist_ok=True)
    for t in range(4):
        try:
            with ftplib.FTP("ftp.mtps.gov.br", timeout=120, encoding="latin-1") as f:
                f.login(); f.cwd(f"/pdet/microdados/NOVO CAGED/{comp[:4]}/{comp}"); f.voidcmd("TYPE I")
                tam = f.size(nome)
                if not (alvo.exists() and alvo.stat().st_size == tam):
                    with alvo.open("wb") as fh: f.retrbinary(f"RETR {nome}", fh.write)
                resp = f.sendcmd(f"MDTM {nome}")
            return {"nome": nome, "bytes": alvo.stat().st_size, "mod": resp.split()[-1]}
        except ftplib.all_errors as e:
            err = str(e); time.sleep(5*2**t)
    return {"nome": nome, "erro": err}
ini=time.perf_counter()
itens=[(t,f"2025{m:02d}") for m in range(1,13) for t in ("MOV","FOR","EXC")]
with ThreadPoolExecutor(3) as p: res=list(p.map(baixar, itens))
Path(sys.argv[2]).write_text(json.dumps(res,indent=0))
print("fim",round(time.perf_counter()-ini),"s erros",[r for r in res if "erro" in r],"MB",round(sum(r.get("bytes",0) for r in res)/1e6))
for r in res:
    if "MOV" in r["nome"]: print(r)
