"""Números do plano que são contas sobre outros resultados. Cada item diz de onde vem e como foi calculado.

Uso: python -I derivar_numeros.py <pasta_resultados> <saida.json>
"""
import json
import statistics
import sys
from pathlib import Path

PASTA, SAIDA = Path(sys.argv[1]), Path(sys.argv[2])
ler = lambda nome: json.loads((PASTA / f"{nome}.json").read_text(encoding="utf-8"))

sih, regras, caged, educacao, tabnet = ler("sih_agregados"), ler("sih_regras"), ler("caged_agregados"), ler("educacao"), ler("conferencia_tabnet_alta")
coleta, formatos, fontes = ler("rd_brasil_coleta"), ler("particoes"), ler("fontes")
tabelas = {t["tabela"]: t for t in sih["tabelas"]}
res = {}

fluxo = "fluxo_res_hosp_ano"
sem_fluxo = [n for n in sih["publicar"] if n != fluxo]
res["sih_regra_antiga"] = {"origem": "sih_agregados.json", "periodo": "Altas de 2025, Brasil", "calculo": "Soma de regra_antiga_visiveis_internacoes_1a4 nas tabelas publicáveis, sem o fluxo, que fica à parte",
                           "tabelas": len(sem_fluxo), "celulas_visiveis_com_1a4_internacoes": sum(tabelas[n]["regra_antiga_visiveis_internacoes_1a4"] for n in sem_fluxo), "no_fluxo_por_ano": tabelas[fluxo]["regra_antiga_visiveis_internacoes_1a4"]}

fatos = sih["fatos"]
res["sih_altas_antes_de_2025"] = {"origem": "sih_agregados.json, fatos.amplitude_mes", "calculo": "Linhas das competências de 2025 com alta antes de 2025 / total de linhas", "linhas": fatos["amplitude_mes"][3], "total": fatos["linhas_total"], "pct": round(100 * fatos["amplitude_mes"][3] / fatos["linhas_total"], 1)}
res["sih_municipios_sem_internacao_por_hospital"] = {"origem": "sih_agregados.json", "calculo": "mun_res - mun_hosp", "valor": fatos["mun_res"] - fatos["mun_hosp"]}
zero = regras["qualidade"]["valor_zero_ou_nulo"][0]
leitos_87 = dict(map(tuple, regras["qualidade"]["aih_valor_zero_por_espec"]))["87"]
res["sih_valor_zero"] = {"origem": "sih_regras.json", "calculo": "AIHs com valor zero na especialidade 87 / todas com valor zero", "aihs": zero, "especialidade_87": leitos_87, "pct": round(100 * leitos_87 / zero, 1)}
res["sih_coleta_fora_sp"] = {"origem": "rd_brasil_coleta.json", "calculo": "Soma dos arquivos das 26 UFs fora SP, competências de 2025", "arquivos": len(coleta["arquivos"]), "mb": round(sum(a["dbc_bytes"] for a in coleta["arquivos"]) / 1e6), "segundos_de_relogio": coleta["segundos_de_relogio"]}

comps = tabnet["comparacoes"]
fora_capital = [c for c in comps if c["municipio"] != "355030"]
fecham = [c for c in comps if c["total_tabnet"] == c["total_saida"]]
res["tabnet_atendimento"] = {"origem": "conferencia_tabnet_alta.json", "periodo": "Competências de 2025, 5 municípios, 2 visões", "comparacoes": len(comps), "meses": sum(c["meses"] for c in comps), "iguais_data_de_internacao": sum(c["iguais_data_de_internacao"] for c in comps), "iguais_data_de_saida": sum(c["iguais_data_de_saida"] for c in comps),
                             "meses_fora_da_capital": sum(c["meses"] for c in fora_capital), "iguais_data_de_internacao_fora_da_capital": sum(c["iguais_data_de_internacao"] for c in fora_capital), "comparacoes_com_total_igual": len(fecham),
                             "maior_diferenca_de_total_pct": round(max(100 * abs(c["total_tabnet"] - c["total_saida"]) / c["total_tabnet"] for c in comps), 2)}

f = caged["fatos"]
com, so = f["saldo_2025_com_ajustes"], f["saldo_2025_so_mov"]
fora = dict(map(tuple, f["defasagem_for_meses"]))
res["caged"] = {"origem": "caged_agregados.json", "periodo": "2025", "erro_do_saldo_so_com_mov_pct": round(100 * (com - so) / com, 1), "for_no_mes_seguinte_pct": round(100 * fora[1] / sum(fora.values()), 1), "defasagem_maxima_for_meses": max(fora),
                "mov_comprimido_mb_medio": round(statistics.mean(a["comprimido_mb"] for a in f["arquivos_mov"]), 1), "mov_aberto_mb_medio": round(statistics.mean(a["aberto_mb"] for a in f["arquivos_mov"]), 1),
                "parquet_mb_tabelas_com_ate_recorte": round(sum(t["parquet_mb"] for t in caged["tabelas"] if t["tabela"] in ("mun_mes", "mun_ano_secao", "mun_mes_sexo", "mun_ano_subclasse", "mun_mes_faixa", "mun_mes_cbo1", "mun_mes_secao", "mun_mes_instrucao")), 2)}
res["educacao_parquet_mb"] = {"origem": "educacao.json", "calculo": "censo.parquet_mb + geral.parquet_mb", "valor": round(educacao["censo"]["parquet_mb"] + educacao["geral"]["parquet_mb"], 2)}

zstd, sem = formatos["formatos_sp"]["zstd"]["transferencia_gzip_kb"], formatos["formatos_sp"]["sem"]["transferencia_gzip_kb"]
bundles = ler("leitor_x_motor")["bundles"]
res["primeira_carga_kb"] = {"origem": "particoes.json e leitor_x_motor.json", "calculo": "Código com gzip + arquivo da maior tabela testada com gzip", "sem_compressao_e_leitor_leve": round(bundles["hyp_leve.js"]["gzip_bytes"] / 1e3 + sem, 1), "zstd_e_leitor_com_descompressor": round(bundles["hyp.js"]["gzip_bytes"] / 1e3 + zstd, 1)}

porte = fontes["ibge"]["municipios_por_porte_estimativa_2026"]
res["municipios_ate_20_mil"] = {"origem": "fontes.json", "calculo": "(até 5 mil + 5 a 20 mil) / todos, na estimativa de 2026", "municipios": porte["ate_5mil"] + porte["5_a_20mil"], "total": sum(porte.values()), "pct": round(100 * (porte["ate_5mil"] + porte["5_a_20mil"]) / sum(porte.values()), 1)}

SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
