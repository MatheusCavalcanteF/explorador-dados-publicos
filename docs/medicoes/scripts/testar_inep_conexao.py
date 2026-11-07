"""Queda de conexão no INEP é da fonte ou desta máquina? Repete pedidos pequenos e compara com outro host do governo."""
import json
import sys
import time
import urllib.error
import urllib.request

ALVOS = {
    "inep_download": "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_2024.zip",
    "inep_ideb": "https://download.inep.gov.br/ideb/resultados/divulgacao_anos_iniciais_municipios_2023.xlsx",
    "ibge_api": "https://servicodados.ibge.gov.br/api/v1/localidades/estados",
    "tesouro_api": "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/anexos-relatorios",
}
res = {}
for nome, url in ALVOS.items():
    ok = falhas = 0
    erros = []
    tempos = []
    for i in range(10):
        t = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=0-1023", "User-Agent": "medicao-etapa0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                r.read()
            ok += 1
        except Exception as e:
            falhas += 1
            erros.append(repr(e)[:90])
        tempos.append(round(time.perf_counter() - t, 2))
        time.sleep(2)
    res[nome] = {"ok": ok, "falhas": falhas, "erros": sorted(set(erros))[:2], "tempo_max_s": max(tempos), "tempo_mediano_s": sorted(tempos)[5]}
    print(nome, json.dumps(res[nome]), flush=True)
json.dump(res, open(sys.argv[1], "w"), indent=1)
