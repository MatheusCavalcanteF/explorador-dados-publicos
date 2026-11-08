"""Quanto um mês da alta ainda muda depois de 6, 9 e 12 meses, por UF. Só medição: nenhuma regra muda aqui.

Duas leituras, porque o dado de cada uma é outro:
1. Depois do fechamento (M + 5 <= última competência - 12). Fechado, o mês só muda se o DATASUS regravar uma
   competência que já saiu da janela. A listagem do FTP dá a data de modificação de cada arquivo, nas 27 UFs:
   conta, por UF, os meses fechados há 6, 9 e 12 meses ou mais em que alguma competência com altas deles foi
   regravada depois do fechamento. Em SP, o projeto de origem guarda a última cópia na janela de 2501 a 2508,
   e o conteúdo é comparado byte a byte com o de hoje.
2. Depois do próprio mês (idade = última competência - M). O processamento tardio para no 5º mês, pelo
   contrato (alta até 5 meses antes da competência): conta, por UF do hospital, quanto do total final de cada
   mês de 2025 já estava nas competências até M + idade. Depois disso, só a correção numa republicação muda o
   mês, e só SP tem duas versões guardadas: setembro x outubro de 2026, nos meses com 6, 9 e 12 meses de idade.

Nada por município sai daqui: só totais por UF e contagens de células que mudaram. Nenhuma contagem de 1 a 4
sai, nem como diferença: percentuais com uma casa, e o que resta abaixo de 100% fica nulo quando são de 1 a
4 AIHs; variação de 1 a 4 entre versões fica nula.

Uso: python medir_mudanca_tardia.py <pasta_min> <pasta_min_sp_setembro> <pasta_dbc_atual> <pasta_dbc_origem> <saida.json>
"""
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pipeline import dtb, sih_coleta, sih_janela  # noqa: E402

PASTA, SETEMBRO, DBC_ATUAL, DBC_ORIGEM, SAIDA = (Path(a) for a in sys.argv[1:6])
IDADES = (6, 9, 12)
JANELA, DEFASAGEM = 12, 5


def meses_entre(a: datetime, b: datetime) -> float:
    return (b - a).days / 30.4375


def depois_do_fechamento(listagem: dict) -> dict:
    """Leitura 1, pela data de modificação na listagem do FTP.

    A competência C é regravada pela última vez na versão C + 11, e a C + 1 na versão seguinte. O mês M
    fecha na versão M + 17, cuja data é a da última regravação da competência M + 6. Uma competência com
    altas de M (M a M + 5) modificada mais de um dia depois dessa data foi regravada depois do fechamento.
    O dia de tolerância é porque um lote leva minutos: arquivos da mesma versão saem com minutos de diferença.
    Fora da janela do site (antes de 2021), conta as competências modificadas mais de 15 meses depois do
    mês delas, que é bem depois da última versão em que estavam na janela.
    """
    from datetime import timedelta
    data = {(a["uf"], a["competencia"]): datetime.fromisoformat(a["modificado_no_ftp"]) for a in listagem.values()}
    ultima = max(c for _, c in data)
    agora = max(data.values())
    um_dia = timedelta(days=1)
    por_uf, antigas = {}, []
    for uf in sih_janela.UFS:
        meses = {}
        for idade in IDADES:
            fechados, mudaram = [], []
            for m in sih_janela.intervalo(202101, sih_janela.somar(ultima, -JANELA - DEFASAGEM)):
                fechou_em = data.get((uf, sih_janela.somar(m, DEFASAGEM + 1)))
                if fechou_em is None or meses_entre(fechou_em, agora) < idade:
                    continue
                fechados.append(m)
                if any(data[(uf, c)] > fechou_em + um_dia for c in sih_janela.intervalo(m, sih_janela.somar(m, DEFASAGEM))):
                    mudaram.append(m)
            meses[str(idade)] = {"meses_fechados_ha_pelo_menos": len(fechados), "com_competencia_regravada": len(mudaram)}
        por_uf[uf] = meses
        for (u, c), quando in data.items():
            ano, mes = divmod(c, 100)
            if u == uf and c < 202101 and meses_entre(datetime(ano, mes, 1), quando) > 15:
                antigas.append(f"{u}{c % 10000:04d}:{quando:%Y-%m-%d}")
    # O resultado costuma ser o mesmo nas 27 UFs: grava uma vez, com as UFs, e à parte as que diferem.
    grupos = {}
    for uf, meses in por_uf.items():
        grupos.setdefault(json.dumps(meses, sort_keys=True), []).append(uf)
    por_uf = [{"ufs": ufs, "meses": json.loads(chave)} for chave, ufs in grupos.items()]
    return {"ultima_no_ftp": ultima, "listagem_mais_recente": agora.isoformat(), "por_uf": por_uf,
            "meses_de_2021_em_diante_que_mudaram_depois_de_fechar": sum(g["meses"][str(i)]["com_competencia_regravada"] * len(g["ufs"])
                                                                        for g in por_uf for i in IDADES),
            "antes_de_2021_regravadas_mais_de_15_meses_depois": len(antigas),
            "antes_de_2021_datas": sorted({a.split(":")[1] for a in antigas})}


def conteudo_sp() -> list[dict]:
    """A última cópia na janela, guardada no projeto de origem, contra a de hoje."""
    saida = []
    for antigo in sorted(DBC_ORIGEM.glob("RDSP25*.dbc")):
        atual = DBC_ATUAL / antigo.name
        comp = sih_janela.de_nome(antigo.stem[4:8])
        if not atual.exists() or comp > sih_janela.somar(202608, -JANELA):
            continue
        h = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (antigo, atual)]
        versao = json.loads((DBC_ATUAL / (antigo.name + ".versao")).read_text(encoding="utf-8"))
        saida.append({"arquivo": antigo.name, "modificado_no_ftp": versao["modificado_no_ftp"], "igual": h[0] == h[1]})
    return saida


def processamento_tardio(con) -> dict:
    """Leitura 2: parte do total final de cada mês de 2025 que já estava nas competências até M + idade."""
    linhas = con.execute("""
        SELECT substr(mun_hosp, 1, 2) AS uf, dt_saida // 100 AS mes,
               ((competencia // 100) * 12 + competencia % 100) - (((dt_saida // 100) // 100) * 12 + (dt_saida // 100) % 100) AS idade,
               count(*) FILTER (WHERE ident = 1) AS n
        FROM aih WHERE dt_saida // 10000 = 2025 GROUP BY 1, 2, 3""").fetchall()
    codigos = {c: s for c, (s, _) in dtb.UFS.items()}
    total, ate = {}, {}
    for uf, mes, idade, n in linhas:
        uf = codigos[uf]
        total[uf] = total.get(uf, 0) + n
        for a in range(0, 13):
            if idade <= a:
                ate[(uf, a)] = ate.get((uf, a), 0) + n
    acima = con.execute("SELECT count(*) FROM aih WHERE ((competencia // 100) * 12 + competencia % 100) "
                        "- (((dt_saida // 100) // 100) * 12 + (dt_saida // 100) % 100) > 5").fetchone()[0]
    def pct(uf, a, resto=False):
        falta = total[uf] - ate.get((uf, a), 0)
        if 1 <= falta <= 4:
            return None
        return round(100 * (falta if resto else total[uf] - falta) / total[uf], 1)
    # De 0 a 5 meses, por UF; depois de 6, 9 e 12, o maior resto entre as 27 UFs (zero pelo contrato).
    por_uf = {uf: [pct(uf, a) for a in range(6)] for uf in sorted(total)}
    depois = {str(a): max(pct(uf, a, True) or 0 for uf in total) for a in IDADES}
    return {"meses": "altas de 2025, competências até 2607", "aihs_com_alta_mais_de_5_meses_antes": int(acima),
            "pct_ate_a_idade_0_a_5_por_uf_do_hospital": por_uf, "maior_pct_que_ainda_chega_depois_de": depois}


def correcao_sp(con) -> dict:
    """SP setembro x outubro: o que mudou nos meses com 6, 9 e 12 meses de idade na versão de outubro (2608)."""
    con.execute(f"""CREATE VIEW antiga AS SELECT * FROM read_parquet({sorted(p.as_posix() for p in SETEMBRO.glob('RDSP*.parquet'))!r})""")
    atuais = [(PASTA / p.name).as_posix() for p in SETEMBRO.glob("RDSP*.parquet")]
    con.execute(f"CREATE VIEW nova AS SELECT * FROM read_parquet({sorted(atuais)!r})")
    saida = {}
    for idade in range(1, 17):
        mes = sih_janela.somar(202608, -idade)
        r = {}
        for visao, coluna in (("residencia", "mun_res"), ("hospital", "mun_hosp")):
            dif = con.execute(f"""
                WITH a AS (SELECT {coluna} AS m, count(*) FILTER (WHERE ident = 1) AS n FROM antiga WHERE dt_saida // 100 = {mes} GROUP BY 1),
                     b AS (SELECT {coluna} AS m, count(*) FILTER (WHERE ident = 1) AS n FROM nova WHERE dt_saida // 100 = {mes} GROUP BY 1)
                SELECT coalesce(b.n, 0) - coalesce(a.n, 0) AS d, coalesce(a.n, 0) AS antes FROM a FULL JOIN b USING (m)""").fetchnumpy()
            d = dif["d"]
            pequeno = lambda v: None if 1 <= abs(int(v)) <= 4 else int(v)
            r[visao] = {"municipios": int(d.size), "mudaram": int((d != 0).sum()), "de_1_a_4_em_modulo": int(((np.abs(d) >= 1) & (np.abs(d) <= 4)).sum()),
                        "internacoes_antes": pequeno(dif["antes"].sum()), "variacao_liquida": pequeno(d.sum()),
                        "soma_das_mudancas_em_modulo": pequeno(np.abs(d).sum())}
        saida[str(idade)] = {"mes": mes} | r
    # Ficam as idades pedidas (6, 9 e 12 meses); das outras, só se o mês mudou.
    mudaram = [int(i) for i, v in saida.items() if v["residencia"]["mudaram"] or v["hospital"]["mudaram"]]
    return {"idades_com_mudanca": mudaram} | {str(i): saida[str(i)] for i in IDADES}


inicio = time.perf_counter()
con = duckdb.connect()
con.execute("SET threads=8")
con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet('{PASTA.as_posix()}/RD*.parquet')")
resultado = {"medido_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "idades": list(IDADES),
             "depois_do_fechamento": depois_do_fechamento(sih_coleta.listar()), "conteudo_sp_congelado": conteudo_sp(),
             "processamento_tardio": processamento_tardio(con), "correcao_sp_setembro_outubro": correcao_sp(con)}
resultado["segundos"] = round(time.perf_counter() - inicio, 1)
SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in resultado.items() if k not in ("processamento_tardio",)}, ensure_ascii=False)[:3000])
