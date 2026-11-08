"""Confere o Parquet mínimo do pipeline com o TabNet, em dois municípios por região, nos eixos do TabNet.

O TabNet não tem o eixo do site (mês da alta). O que dá para conferir é se o pipeline parte das mesmas
AIHs, pelos dois eixos que ele oferece:
- competência: o formulário de cada UF, com uma competência por consulta (Arquivos = ni{uf}{aamm}.dbf);
- data de internação: "Ano/mês atendimento", com as 12 competências de 2025 selecionadas.

Visão de hospital: formulário ni{uf}, coluna MUNIC_MOV. Visão de residência: nr{uf}, coluna MUNIC_RES,
com os arquivos das 27 UFs, porque o TabNet de residência conta quem foi internado em outro estado.

Valores de 1 a 4 não são gravados, nem os pares cuja diferença seja de 1 a 4 (ver mascarar_diferencas).

Uso: python conferir_tabnet_f1b.py <pasta_min_do_pipeline> <saida.json>
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

BASE = "http://tabnet.datasus.gov.br/cgi"
UA = {"User-Agent": "Mozilla/5.0"}
# Dois por região: a capital e um município do interior com mais de 100 internações por mês.
AMOSTRA = {
    "Norte": [("am", "130260", "Manaus"), ("ac", "120020", "Cruzeiro do Sul")],
    "Nordeste": [("ba", "292740", "Salvador"), ("pi", "220800", "Picos")],
    "Sudeste": [("mg", "310620", "Belo Horizonte"), ("sp", "355030", "São Paulo")],
    "Sul": [("rs", "431490", "Porto Alegre"), ("sc", "420420", "Chapecó")],
    "Centro-Oeste": [("go", "520870", "Goiânia"), ("mt", "510760", "Rondonópolis")],
}
COMPETENCIAS = ["2503", "2601"]
MEDIDAS = {
    "Internações": "count(*) FILTER (WHERE ident = 1)",
    "Valor_total": "round(sum(valor), 2)",
    "Óbitos": "sum(morte)",
    "Dias_permanência": "sum(dias)",
}
MESES = {"Janeiro": "01", "Fevereiro": "02", "Março": "03", "Abril": "04", "Maio": "05", "Junho": "06", "Julho": "07",
         "Agosto": "08", "Setembro": "09", "Outubro": "10", "Novembro": "11", "Dezembro": "12"}


def pedir(url, corpo=None, tempo=180):
    cab = {**UA}
    if corpo is not None:
        cab |= {"Content-Type": "application/x-www-form-urlencoded", "Referer": url.replace("tabcgi.exe", "deftohtm.exe")}
    for tentativa in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, data=corpo, headers=cab), timeout=tempo).read().decode("latin-1")
        except OSError:
            if tentativa == 2:
                raise
            time.sleep(5 * (tentativa + 1))


def formulario(defn):
    return pedir(f"{BASE}/deftohtm.exe?sih/cnv/{defn}.def")


def opcao_municipio(texto, codigo):
    bloco = texto[re.search(r'name=["\']?SMunic.pio', texto, re.I).start():]
    bloco = bloco[: bloco.lower().find("</select>")]
    return re.search(r'value=["\']?(\d+)["\']?[^>]*>\s*' + codigo, bloco, re.I).group(1)


def consultar(defn, texto, municipio, linha, incremento, arquivos):
    nomes = re.findall(r'<select[^>]*name=["\']?([^"\' >]+)', texto, re.I)
    pares = [("Linha", linha), ("Coluna", "--Não-Ativa--"), ("Incremento", incremento)]
    pares += [("Arquivos", a) for a in arquivos]
    for n in nomes:
        if n in ("Linha", "Coluna", "Incremento", "Arquivos") or n.startswith("listahidden"):
            continue
        pares.append((n, opcao_municipio(texto, municipio) if n == "SMunicípio" else "TODAS_AS_CATEGORIAS__"))
    pares += [("zeradas", "exibirlz"), ("formato", "prn"), ("mostre", "Mostra")]
    corpo = urllib.parse.urlencode(pares, encoding="latin-1").encode()
    return pedir(f"{BASE}/tabcgi.exe?sih/cnv/{defn}.def", corpo)


def total(resposta):
    txt = html.unescape(re.sub(r"<[^>]+>", "\n", resposta))
    m = re.search(r'"Total";\s*([\d.,]+|-)', txt) or re.search(r"TOTAL\s*;?\s*([\d.,]+|-)", txt, re.I)
    if not m:
        return None
    s = m.group(1)
    return 0.0 if s == "-" else float(s.replace(".", "").replace(",", "."))


def por_mes(resposta):
    txt = html.unescape(re.sub(r"<[^>]+>", "\n", resposta))
    saida = {}
    for m in re.finditer(r'"[. ]*(' + "|".join(MESES) + r')/(\d{4})";\s*([\d.]+|-)', txt):
        saida[m.group(2) + MESES[m.group(1)]] = 0 if m.group(3) == "-" else int(m.group(3).replace(".", ""))
    return saida


def guardado(valor):
    """Valor de 1 a 4 não sai daqui."""
    return "<5" if valor is not None and 1 <= valor < 5 else valor


def mascarar_diferencas(resultado):
    """Diferença de 1 a 4 entre pipeline e TabNet é um grupo pequeno de AIHs que uma fonte tem e a outra não.

    Os dois valores juntos revelariam o tamanho exato dele por subtração. Quando as internações de um
    município, visão e competência diferem de 1 a 4, nenhuma medida desse grupo guarda valor nem diferença
    exata: valor, dias e óbitos descrevem as mesmas AIHs. O mesmo vale para óbitos sozinhos e para o total
    por data de internação.
    """
    pequena = lambda d: d is not None and not isinstance(d, str) and 1 <= abs(d) < 5
    grupos = {}
    for r in resultado["por_competencia"]:
        if r["medida"] in ("Internações", "Óbitos") and pequena(r["diferenca"]):
            grupos.setdefault((r["municipio"], r["visao"], r["competencia"]), set()).add(r["medida"])
    for r in resultado["por_competencia"]:
        medidas = grupos.get((r["municipio"], r["visao"], r["competencia"]))
        if medidas and ("Internações" in medidas or r["medida"] == "Óbitos"):
            r["pipeline"] = r["tabnet"] = None
            r["diferenca"] = "1 a 4" if r["medida"] in medidas else "omitida: descreve as mesmas AIHs"
    for r in resultado["por_data_de_internacao"]:
        if "total_tabnet" in r and pequena(r["total_pipeline"] - r["total_tabnet"]):
            r["diferenca_total"] = "1 a 4"
            r["total_pipeline"] = r["total_tabnet"] = None
        if pequena(r.get("maior_diferenca")):
            r["maior_diferenca"] = "1 a 4"


def resumir(resultado):
    """Contagens do resumo, calculadas antes da máscara: depois dela, valor ausente não quer dizer sem resposta."""
    pc = resultado["por_competencia"]
    return {"comparacoes_por_competencia": len(pc), "iguais": sum(r["igual"] for r in pc),
            "sem_resposta": sum(r["tabnet"] is None for r in pc),
            "por_data_de_internacao": len(resultado["por_data_de_internacao"]),
            "meses_iguais": sum(r.get("meses_iguais", 0) for r in resultado["por_data_de_internacao"]),
            "meses": sum(r.get("meses", 0) for r in resultado["por_data_de_internacao"])}


def main():
    pasta, saida = Path(sys.argv[1]), Path(sys.argv[2])
    con = duckdb.connect()
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet('{pasta.as_posix()}/RD*.parquet')")
    resultado = {"consultado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "competencias": COMPETENCIAS,
                 "por_competencia": [], "por_data_de_internacao": []}
    for regiao, municipios in AMOSTRA.items():
        for uf, mun, nome in municipios:
            for visao, prefixo, coluna in (("hospital", "ni", "mun_hosp"), ("residencia", "nr", "mun_res")):
                defn = f"{prefixo}{uf}"
                texto = formulario(defn)
                for comp in COMPETENCIAS:
                    for medida, expr in MEDIDAS.items():
                        calc = con.execute(f"SELECT {expr} FROM aih WHERE {coluna} = '{mun}' AND competencia = 20{comp}").fetchone()[0]
                        calc = float(calc or 0)
                        try:
                            oficial = total(consultar(defn, texto, mun, "Município", medida, [f"{defn}{comp}.dbf"]))
                        except Exception as erro:  # o TabNet cai às vezes; fica registrado como sem resposta
                            oficial = None
                            print("sem resposta", defn, mun, comp, medida, type(erro).__name__, flush=True)
                        igual = oficial is not None and abs(calc - oficial) < 0.011
                        resultado["por_competencia"].append({
                            "regiao": regiao, "municipio": mun, "nome": nome, "visao": visao, "competencia": "20" + comp,
                            "medida": medida, "igual": igual, "pipeline": guardado(calc), "tabnet": guardado(oficial),
                            "diferenca": None if oficial is None else round(calc - oficial, 2)})
                        # Só o progresso: os valores saem depois da máscara, no arquivo.
                        print(defn, mun, comp, medida, "igual" if igual else "diferente", flush=True)
                        time.sleep(0.5)
                arquivos = [f"{defn}25{m:02d}.dbf" for m in range(1, 13)]
                linha_tempo = next((v for v, rot in re.findall(r'<option[^>]*value=["\']?([^"\'>]+)["\']?[^>]*>\s*([^<]*)', texto, re.I)
                                    if re.search(r"Ano/m.s atendimento", html.unescape(rot), re.I)), None)
                if linha_tempo is None:
                    resultado["por_data_de_internacao"].append({"municipio": mun, "visao": visao, "erro": "eixo ausente"})
                    continue
                oficial = por_mes(consultar(defn, texto, mun, linha_tempo, "Internações", arquivos))
                calc = dict(con.execute(f"SELECT CAST(dt_inter // 100 AS VARCHAR), count(*) FILTER (WHERE ident = 1) FROM aih "
                                        f"WHERE {coluna} = '{mun}' AND competencia BETWEEN 202501 AND 202512 GROUP BY 1").fetchall())
                # O TabNet lista todos os meses desde 2008, quase todos vazios: só contam os que têm valor em um dos dois.
                meses = sorted({m for m, v in oficial.items() if v} | {m for m, v in calc.items() if v})
                iguais = sum(oficial.get(m, 0) == calc.get(m, 0) for m in meses)
                # Sem valores por mês: o total menos os meses listados revelaria os pequenos.
                resultado["por_data_de_internacao"].append({
                    "regiao": regiao, "municipio": mun, "nome": nome, "visao": visao, "meses": len(meses), "meses_iguais": iguais,
                    "maior_diferenca": max((abs(oficial.get(m, 0) - calc.get(m, 0)) for m in meses), default=0),
                    "total_tabnet": sum(oficial.values()), "total_pipeline": sum(calc.values())})
                print(defn, mun, "por data de internação:", iguais, "de", len(meses), "meses iguais", flush=True)
                time.sleep(0.5)
    resultado["resumo"] = resumir(resultado)
    mascarar_diferencas(resultado)
    saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(resultado["resumo"]))


if __name__ == "__main__":
    main()
