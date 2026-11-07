"""Confere se duas rodadas produziram as mesmas máscaras. Uso: python -I comparar_rodadas.py <r1.json> <r2.json>"""
import json
import sys

a = json.load(open(sys.argv[1], encoding="utf-8"))["tabelas"]
d = json.load(open(sys.argv[2], encoding="utf-8"))
b = d["tabelas"]
iguais = sum(x["hash_oculto"] == y["hash_oculto"] for x, y in zip(a, b))
print("idempotencia: mascaras iguais em", iguais, "de", len(a), "| convergiu em todas:", all(x["convergiu"] for x in b), "| linhas dedutiveis:", sum(x["linhas_dedutiveis_depois"] for x in b), "| visiveis 1a4:", sum(x["visiveis_internacoes_1a4"] for x in b))
print(ascii(json.dumps(d["ataque_entre_tabelas"], ensure_ascii=False)))
