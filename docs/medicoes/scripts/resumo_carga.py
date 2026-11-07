"""Mediana por cenário e perfil. Uso: python -I resumo_carga.py <carga.json>"""
import json
import statistics
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
perfis = list(dict.fromkeys(x["perfil"] for x in d if "perfil" in x))
cenarios = list(dict.fromkeys(x["cenario"] for x in d if "perfil" in x))
print("linhas", len(d), "perfis", perfis)
for c in cenarios:
    print("\n" + ascii(c))
    for p in perfis:
        l = [x for x in d if x.get("perfil") == p and x["cenario"] == c]
        if not l:
            continue
        ms = [x["ms"] for x in l]
        by = [x["bytes"] for x in l]
        pc = [x["pico_mb"] for x in l if x.get("pico_mb")]
        print(f"  {ascii(p):<26} n={len(l)} ms med={statistics.median(ms):>8.0f} [{min(ms)}-{max(ms)}] bytes med={statistics.median(by):>9.0f} req={l[0]['req']} status={l[0].get('status', '-')} r206={l[0].get('r206', '-')} grupos={l[0].get('grupos', '-')} pico_mb={statistics.median(pc) if pc else '-'}")
