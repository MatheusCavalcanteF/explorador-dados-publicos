"""SIH de ponta a ponta: coleta, tabelas por ano da alta, supressão, teste de dedução e partições.

Nada desta etapa vai para o site nem para as Releases: o catálogo diz `publicacao: {site: false,
releases: false}` até o OK do dono do projeto. As partições ficam na pasta de trabalho do runner, e o
que sai dele é só a medição: tempos, disco, tamanhos e contagens agregadas por cruzamento.

O Parquet mínimo, com uma linha por AIH, fica em `trabalho/min` e nunca é artefato.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import sih_coleta, sih_janela
from .contrato import ErroDeContrato


def _tamanho(pasta: Path) -> int:
    return sum(p.stat().st_size for p in pasta.rglob("*") if p.is_file()) if pasta.exists() else 0


def _memoria_mb() -> dict:
    """Pico de memória do processo e dos filhos, onde o sistema informa (Linux e macOS)."""
    try:
        import resource
    except ImportError:
        return {}
    proprio = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    filhos = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return {"processo_mb": round(proprio / 1024), "maior_filho_mb": round(filhos / 1024)}


def _um_arquivo(nome: str, esperado: int, modificado: str, trabalho: str, municipios6: frozenset, colunas: list,
                defasagem: int, manter_dbc: bool, origem_local: str | None) -> dict:
    """Baixa (ou lê da pasta local) e converte um arquivo. Roda num processo à parte."""
    import pyarrow.parquet as pq
    inicio = time.perf_counter()
    pasta = Path(trabalho)
    if origem_local:
        # Cópia local, só para medir: precisa ter a versão da listagem atual gravada ao lado.
        dbc = Path(origem_local) / nome
        versao = {"bytes": esperado, "modificado_no_ftp": modificado}
        if dbc.stat().st_size != esperado or sih_coleta.versao_local(dbc) != versao:
            raise ErroDeContrato(f"{nome}: a cópia local não é a versão da listagem atual ({versao})")
    else:
        dbc = sih_coleta.baixar(nome, esperado, pasta / "dbc", modificado=modificado)
    baixado = time.perf_counter()
    tabela, resumo = sih_coleta.converter(dbc.read_bytes(), nome, set(municipios6), colunas, defasagem)
    destino = pasta / "min" / (nome[:-4] + ".parquet")
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".part")
    pq.write_table(tabela, parcial, compression="zstd")
    parcial.replace(destino)
    if not manter_dbc and not origem_local:
        dbc.unlink()
        dbc.with_name(dbc.name + ".versao").unlink(missing_ok=True)
    return resumo | {"arquivo": nome, "bytes_dbc": esperado, "s_download": round(baixado - inicio, 2),
                     "s_conversao": round(time.perf_counter() - baixado, 2), "bytes_min": destino.stat().st_size}


def coletar(listagem: dict[str, dict], arquivos: list[str], trabalho: Path, municipios6: set[str], catalogo: dict,
            processos: int = 4, manter_dbc: bool = False, origem_local: Path | None = None, avisar=print) -> dict:
    """Baixa e converte os arquivos pedidos em paralelo. Um arquivo com contrato violado para tudo."""
    base = catalogo["bases"]["sih"]
    colunas, defasagem = base["coleta"]["colunas"], int(base["tempo"]["defasagem_maxima_meses"])
    inicio = time.perf_counter()
    resumos, maior_disco = [], 0
    with ProcessPoolExecutor(processos) as pool:
        futuros = {pool.submit(_um_arquivo, n, listagem[n]["bytes"], listagem[n]["modificado_no_ftp"], str(trabalho),
                               frozenset(municipios6), colunas, defasagem, manter_dbc,
                               str(origem_local) if origem_local else None): n for n in arquivos}
        for i, futuro in enumerate(as_completed(futuros), 1):
            resumos.append(futuro.result() | {"modificado_no_ftp": listagem[futuros[futuro]]["modificado_no_ftp"]})
            if i % 50 == 0 or i == len(arquivos):
                maior_disco = max(maior_disco, _tamanho(trabalho))
                avisar(f"SIH: {i} de {len(arquivos)} arquivos em {time.perf_counter() - inicio:.0f} s")
    resumos.sort(key=lambda r: (r["uf"], r["competencia"]))
    return {"arquivos": resumos, "segundos": round(time.perf_counter() - inicio, 1),
            "bytes_dbc": sum(r["bytes_dbc"] for r in resumos), "bytes_min": sum(r["bytes_min"] for r in resumos),
            "maior_disco_bytes": maior_disco, "processos": processos}


def arquivos_necessarios(jan: sih_janela.Janela, anos: list[int], ufs: list[str]) -> list[str]:
    competencias = sorted({c for a in anos for c in jan.competencias_do_ano(a)})
    return [sih_coleta.nome_do_arquivo(uf, c) for uf in ufs for c in competencias]


COLUNA_DA_METRICA = {"internacoes": "internacoes", "dias_permanencia": "dias", "valor_total": "valor", "obitos": "obitos"}
NAO_SAEM = ("aihs", "internacoes", "dias", "valor", "obitos", "oculto", "estado", "estado_obitos", "publicado")


def gravar_particao(suprimidas: dict, ano: int, destino: Path, municipios7: dict[str, str],
                    motivo_por_celula: bool = False, metricas: dict[str, list[str]] | None = None,
                    preliminares: set[str] | frozenset = frozenset(), multiplo: int = 0, k: int = 5,
                    contagens: tuple = ("internacoes", "obitos")) -> dict:
    """Um Parquet sem compressão por cruzamento e UF, como o site vai servir, e o tamanho com gzip.

    O município sai com o código de 7 dígitos do IBGE. As AIHs não saem; os valores ocultos saem nulos,
    com o motivo ao lado quando o catálogo manda publicá-lo, ou só a marca de oculta. Óbitos têm máscara
    própria. Cada cruzamento leva só as métricas que o catálogo declara para ele (`metricas`, por id).

    O trimestre sem os três meses na base não sai. Nas linhas cujo período inclui um mês de
    `preliminares` (AAAAMM), `preliminar` é verdadeiro, e cada contagem visível de k para cima sai
    arredondada para múltiplo de `multiplo`, com `arredondado` (internações) e `obitos_arredondado`.
    """
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    from . import sih_deducao, supressao
    tamanhos = {}
    for cid, df in suprimidas.items():
        geo = "mun_res" if "mun_res" in df else "mun_hosp"
        df = df.loc[df["publicado"]] if "publicado" in df else df
        df = df.copy()
        df[geo] = df[geo].map(municipios7)
        oculto = df["oculto"].to_numpy()
        aberto = sih_deducao.periodo_aberto(df, tuple(df.columns), ano, set(preliminares))
        colunas = {c: pa.array(df[c], pa.string()) for c in df.columns if c not in NAO_SAEM}
        declaradas = {COLUNA_DA_METRICA[m] for m in (metricas or {}).get(cid, ["internacoes", "dias_permanencia", "valor_total", "obitos"])}
        intern = df["internacoes"].to_numpy(np.int64)
        arredondado = (~oculto & aberto & (intern >= k)) if multiplo and "internacoes" in contagens else np.zeros(len(df), bool)
        df["internacoes"] = np.where(arredondado, sih_deducao.arredondar(intern, multiplo or 1), intern)
        for medida in ("internacoes", "dias", "valor"):
            if medida in declaradas:
                tipo = pa.float64() if medida == "valor" else pa.int64()
                colunas[medida] = pa.array(df[medida].where(~oculto, None), tipo)
        if motivo_por_celula:
            colunas["motivo"] = pa.array([supressao.MOTIVOS[int(e)] for e in df["estado"]], pa.string())
        else:
            colunas["oculto"] = pa.array(oculto, pa.bool_())
        colunas["preliminar"] = pa.array(aberto, pa.bool_())
        colunas["arredondado"] = pa.array(arredondado, pa.bool_())
        if "estado_obitos" in df and "obitos" in declaradas:
            oculto_ob = df["estado_obitos"].to_numpy() != 0
            obitos = df["obitos"].to_numpy(np.int64)
            ob_arred = (~oculto_ob & aberto & (obitos >= k)) if multiplo and "obitos" in contagens else np.zeros(len(df), bool)
            df["obitos"] = np.where(ob_arred, sih_deducao.arredondar(obitos, multiplo or 1), obitos)
            colunas["obitos"] = pa.array(df["obitos"].where(~oculto_ob, None), pa.int64())
            if motivo_por_celula:
                colunas["motivo_obitos"] = pa.array([supressao.MOTIVOS[int(e)] for e in df["estado_obitos"]], pa.string())
            else:
                colunas["obitos_oculto"] = pa.array(oculto_ob, pa.bool_())
            colunas["obitos_arredondado"] = pa.array(ob_arred, pa.bool_())
        tabela = pa.table(colunas)
        uf_col = df[geo].str[:2]
        for uf in sorted(uf_col.unique()):
            parte = tabela.filter(pa.array((uf_col == uf).to_numpy()))
            caminho = destino / cid / f"uf={uf}" / f"ano={ano}.parquet"
            caminho.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(parte, caminho, compression="NONE")
            bruto = caminho.read_bytes()
            tamanhos[f"{cid}/uf={uf}/ano={ano}"] = {"bytes": len(bruto), "gzip": len(gzip.compress(bruto, 6))}
    return tamanhos


def resumo_supressao(suprimidas: dict) -> dict:
    """Por cruzamento: linhas, células ocultas e internações ocultas, em contagens e percentuais.

    Conta só as linhas que vão para o arquivo: o trimestre incompleto fica de fora.
    """
    saida = {}
    for cid, df in suprimidas.items():
        if "publicado" in df:
            df = df.loc[df["publicado"]]
        intern = df["internacoes"].to_numpy()
        oculto = df["oculto"].to_numpy()
        total = int(intern.sum())
        saida[cid] = {"linhas": len(df), "celulas_ocultas": int(oculto.sum()),
                      "pct_celulas_ocultas": round(100 * oculto.mean(), 2) if len(df) else 0.0,
                      "pct_internacoes_ocultas": round(100 * intern[oculto].sum() / total, 3) if total else 0.0,
                      "por_motivo": {m: int((df["estado"] == e).sum()) for e, m in
                                     ((1, "contagem_pequena"), (2, "complementar"), (4, "familia"))}}
    return saida


def disco_livre() -> int:
    return shutil.disk_usage(Path.cwd()).free


def ambiente() -> dict:
    return {"cpus": os.cpu_count(), "disco_livre_bytes": disco_livre(), **_memoria_mb()}


def mascarar(valor: int, k: int):
    """Contagem de 1 a k-1 não sai do runner, nem em totais de qualidade."""
    return f"<{k}" if 1 <= valor < k else valor


def _pct(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + "%"


def reprovados(resumo: dict, criterio: dict) -> dict[str, dict]:
    """Cruzamentos que passam do critério de publicação, com o motivo em texto e os percentuais."""
    saida = {}
    for cid, r in resumo.items():
        partes = []
        if r["pct_internacoes_ocultas"] > criterio["internacoes_ocultas_pct_max"]:
            partes.append(f"{_pct(r['pct_internacoes_ocultas'])} das internações ficariam ocultas "
                          f"(limite: {criterio['internacoes_ocultas_pct_max']}%)")
        if r["pct_celulas_ocultas"] > criterio["celulas_ocultas_pct_max"]:
            partes.append(f"{_pct(r['pct_celulas_ocultas'])} das células ficariam ocultas "
                          f"(limite: {criterio['celulas_ocultas_pct_max']}%)")
        if partes:
            saida[cid] = {"motivo": " e ".join(partes), "pct_internacoes_ocultas": r["pct_internacoes_ocultas"],
                          "pct_celulas_ocultas": r["pct_celulas_ocultas"]}
    return saida


def dependentes(catalogo: dict, cid: str) -> list[str]:
    """Cruzamentos que dependem de `cid` pela família (mãe) ou pelo trimestre, em qualquer grau."""
    saida, fila = [], [cid]
    while fila:
        atual = fila.pop()
        for c in catalogo["cruzamentos"]:
            if atual in (c.get("mae"), c.get("herda_trimestre_de")) and c["id"] not in saida:
                saida.append(c["id"])
                fila.append(c["id"])
    return saida


def catalogo_sem(catalogo: dict, fora) -> dict:
    """Cópia rasa do catálogo sem os cruzamentos de `fora`."""
    return catalogo | {"cruzamentos": [c for c in catalogo["cruzamentos"] if c["id"] not in set(fora)]}


def fixas_da_anterior(nos: dict, catalogo: dict, anterior: dict, ano: int, fechado_ate: int) -> dict:
    """O padrão herdado da versão publicada antes, nas células de período já fechado (até `fechado_ate`).

    `anterior` traz, por cruzamento, as chaves e as colunas `oculto` e `arredondado` como foram publicadas.
    Período fechado não muda mais de valor, então quem guardou a versão anterior já sabe o que ela mostrou:
    a célula que estava oculta continua oculta, e a que estava visível e exata fica travada, sem poder
    virar complementar, porque escondê-la agora não tira o valor de ninguém. A que estava arredondada pode
    ser ocultada, e o teste entre versões confere o que sobra do intervalo dela.
    """
    from . import sih_deducao, sih_tabelas as tab
    saida = {}
    for c in catalogo["cruzamentos"]:
        if c["id"] not in anterior:
            continue
        n = tab.colunas_de(c, catalogo)
        chaves = list(n)
        antes = anterior[c["id"]][chaves + ["oculto", "arredondado"]]
        junto = nos[n][chaves].merge(antes, on=chaves, how="left", validate="one_to_one")
        congelada = sih_deducao.periodo_fechado(nos[n], n, ano, fechado_ate)
        estava = junto["oculto"].notna().to_numpy()
        oculta = junto["oculto"].astype("boolean").fillna(False).to_numpy(bool)
        arredondada = junto["arredondado"].astype("boolean").fillna(False).to_numpy(bool)
        saida[c["id"]] = (congelada & estava & oculta, congelada & estava & ~oculta & ~arredondada)
    return saida


def suprimir_publicaveis(nos: dict, catalogo: dict, k: int, ultimo_mes: int | None = None, arredondamento=None,
                         max_rodadas: int | None = None, fixas: dict | None = None) -> dict:
    """Supressão com reforço até o teste de dedução dar zero, e o critério de publicação do ano.

    O cruzamento que passa do critério sai do ano, com o motivo, e o que depende dele sai junto. A
    supressão e o teste são refeitos sem eles, porque cada tabela a menos muda o que se pode deduzir.
    `fixas` é o padrão herdado da versão publicada antes (fixas_da_anterior). Devolve o resultado de
    suprimir_ate_passar mais o catálogo do ano, os não publicados e o resumo da primeira volta, com todos
    os cruzamentos.
    """
    from . import sih_deducao
    regras = catalogo["bases"]["sih"]["supressao"]
    criterio = regras.get("criterio_publicacao")
    fora: dict[str, dict] = {}
    cat, primeira = catalogo, None
    for _ in range(len(catalogo["cruzamentos"]) + 1):
        r = sih_deducao.suprimir_ate_passar(nos, cat, k, bool(regras["motivo_por_celula"]), max_rodadas,
                                            arredondamento=arredondamento, ultimo_mes=ultimo_mes, fixas=fixas)
        resumo = resumo_supressao(r["suprimidas"])
        primeira = primeira or resumo
        novos = reprovados(resumo, criterio) if criterio else {}
        if not novos:
            break
        for cid, motivo in novos.items():
            fora[cid] = motivo
            for d in dependentes(catalogo, cid):
                fora.setdefault(d, {"motivo": f"depende de {d_de(catalogo, d)}, que não passou no critério"})
        cat = catalogo_sem(catalogo, fora)
    return r | {"catalogo": cat, "nao_publicados": fora, "resumo": resumo, "resumo_com_todos": primeira}


def d_de(catalogo: dict, cid: str) -> str:
    c = next(x for x in catalogo["cruzamentos"] if x["id"] == cid)
    return c.get("mae") or c.get("herda_trimestre_de")


def construir_ano(con, tabela: str, ano: int, catalogo: dict, k: int, deduzir: bool = True,
                  ultimo_mes: int | None = None, preliminares: set[str] | frozenset = frozenset(),
                  anterior: dict | None = None, fechado_ate: int | None = None) -> tuple[dict, dict, dict]:
    """Nós do fechamento, cruzamentos suprimidos (só os publicáveis) e medição de um ano.

    `ultimo_mes` (AAAAMM) é o último mês da alta na base: trimestre sem os três meses fica fora do
    arquivo. `preliminares` são os meses que ainda podem mudar: o teste os vê arredondados, como a tela.
    `anterior` traz o que a versão publicada antes mostrou deste ano (ler_anterior): nas células de período
    fechado até `fechado_ate`, a nova herda o padrão dela (fixas_da_anterior).
    """
    from . import sih_deducao, sih_tabelas as tab, supressao
    t = {"inicio": time.perf_counter()}
    pub_int = sih_deducao.nos_publicados(catalogo, "internacoes")
    pub_ob = sih_deducao.nos_publicados(catalogo, "obitos")
    base = tab.calcular_base(con, tabela, ano, list(dict.fromkeys(pub_int + pub_ob)), catalogo)
    t["base"] = time.perf_counter()
    nos = tab.montar(base, list(dict.fromkeys(pub_int + pub_ob)))
    t["fechamento"] = time.perf_counter()
    regras = catalogo["bases"]["sih"]["supressao"]
    multiplo = int((catalogo["bases"]["sih"].get("preliminares") or {}).get("arredondar_multiplo", 0))
    arred = (multiplo, set(preliminares), ano) if multiplo and preliminares else None
    cat_ano, nao_publicados = catalogo, {}
    if deduzir:
        # Supressão, teste de dedução e reforço até passar, e o critério de publicação. O teste vê o que a
        # tela mostraria: só "oculta", sem o motivo, e os preliminares arredondados.
        fixas = fixas_da_anterior(nos, catalogo, anterior, ano, fechado_ate) if anterior and fechado_ate else None
        r = suprimir_publicaveis(nos, catalogo, k, ultimo_mes, arred, int(regras["reforco_max_rodadas"]), fixas)
        sup, cat_ano, nao_publicados = r["suprimidas"], r["catalogo"], r["nao_publicados"]
    else:
        sup = supressao.suprimir(nos, catalogo, k, ultimo_mes=ultimo_mes)
    for c in cat_ano["cruzamentos"]:
        if "obitos" in c["metricas"]:
            n = tab.colunas_de(c, catalogo)
            sup[c["id"]]["estado_obitos"] = supressao.suprimir_obitos(nos[n], n, k)
    t["supressao"] = time.perf_counter()
    medicao = {"ano": ano, "aihs": int(nos[()]["aihs"].sum()), "internacoes": int(nos[()]["internacoes"].sum()),
               "nos_no_fechamento": len(tab.fechamento(pub_int)), "supressao": resumo_supressao(sup),
               "publicados": [c["id"] for c in cat_ano["cruzamentos"]], "nao_publicados": nao_publicados,
               "preliminares": sorted(preliminares), "ultimo_mes": ultimo_mes,
               "herdou_da_anterior": sorted(anterior) if anterior and fechado_ate else []}
    if deduzir:
        medicao["supressao_com_todos"] = r["resumo_com_todos"]
        medicao["deducao_internacoes"] = r["auditoria"] | {"rodadas": r["historico"], "passou": r["passou"],
                                                            "motivo_por_celula": bool(regras["motivo_por_celula"])}
        est_ob = sih_deducao.estados_publicados(nos, sup, cat_ano, k, "obitos")
        if not regras["motivo_por_celula"]:
            est_ob = sih_deducao.sem_motivo(est_ob)
        pub_ob_ano = sih_deducao.nos_publicados(cat_ano, "obitos")
        medicao["deducao_obitos"] = sih_deducao.auditar(sih_deducao.sistema(nos, est_ob, pub_ob_ano, k, medida="obitos",
                                                                            arredondamento=arred))
        medicao["deducao_obitos"]["passou"] = medicao["deducao_obitos"]["pequenas_reveladas"] == 0
        t["deducao_obitos"] = time.perf_counter()
    etapas = list(t)
    medicao["segundos"] = {e: round(t[e] - t[etapas[i - 1]], 1) for i, e in enumerate(etapas) if i}
    return nos, sup, medicao


def ler_anterior(pasta: Path, ano: int, catalogo: dict) -> dict:
    """O que a versão publicada antes mostrou de um ano: por cruzamento, as chaves (município com 6 dígitos,
    como no pipeline) e as colunas oculto e arredondado. Partição sem `arredondado` conta como exata."""
    import pandas as pd

    from . import sih_tabelas as tab
    saida = {}
    for c in catalogo["cruzamentos"]:
        arquivos = sorted((Path(pasta) / c["id"]).glob(f"uf=*/ano={ano}.parquet"))
        if not arquivos:
            continue
        df = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
        geo = "mun_res" if "mun_res" in df else "mun_hosp"
        df[geo] = df[geo].str[:6]
        if "arredondado" not in df:
            df["arredondado"] = False
        saida[c["id"]] = df[list(tab.colunas_de(c, catalogo)) + ["oculto", "arredondado"]]
    return saida


def executar(coleta_ibge: dict, catalogo: dict, trabalho: Path, saida: Path, ufs: list[str] | None = None,
             anos: list[int] | None = None, processos: int = 4, origem_local: Path | None = None,
             manter_dbc: bool = False, deduzir: bool = True, listagem: dict | None = None, avisar=print,
             anterior: Path | None = None) -> dict:
    """A execução inteira. Devolve a medição, que é o único arquivo gravado fora da pasta de trabalho.

    `anterior` é a pasta de partições da versão publicada antes: nos períodos já fechados, a nova herda o
    padrão de células ocultas dela, para que quem guardou as duas não cruze um padrão com o outro.
    """
    import duckdb

    from datetime import datetime, timezone

    base = catalogo["bases"]["sih"]
    k = int(base["supressao"]["k"])
    inicio = time.perf_counter()
    coletado_em = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    medicao = {"ambiente_inicio": ambiente(), "etapas": {}, "coletado_em": coletado_em}
    listagem = listagem or sih_coleta.listar()
    jan = sih_janela.janela(sih_coleta.competencias_por_uf(listagem), base["tempo"], int(base["coleta"]["primeiro_ano"]))
    ufs = ufs or list(sih_janela.UFS)
    anos = anos or jan.anos()
    medicao["janela"] = {"ultima_no_ftp": jan.ultima_no_ftp, "ultima_completa": jan.ultima_completa,
                         "ultima_congelada": jan.ultima_congelada, "ultimo_mes_fechado": jan.ultimo_mes_fechado,
                         "anos": anos, "anos_abertos": [a for a in anos if a in jan.anos_abertos()],
                         "aguardando": sorted(n for n, a in listagem.items() if a["competencia"] > jan.ultima_completa)}
    medicao["etapas"]["listagem_s"] = round(time.perf_counter() - inicio, 1)
    arquivos = arquivos_necessarios(jan, anos, ufs)
    municipios7 = {m["codigo"][:6]: m["codigo"] for m in coleta_ibge["municipios"]}
    avisar(f"SIH: {len(arquivos)} arquivos de {len(ufs)} UF(s), competências para os anos {anos}; "
           f"última completa {jan.ultima_completa}, fechado até {jan.ultimo_mes_fechado}")
    coleta = coletar(listagem, arquivos, trabalho, set(municipios7), catalogo, processos, manter_dbc, origem_local, avisar)
    medicao["coleta"] = {c: v for c, v in coleta.items() if c != "arquivos"}
    medicao["coleta"]["arquivos"] = len(coleta["arquivos"])
    medicao["coleta"]["sexo_ignorado"] = mascarar(sum(r["sexo_ignorado"] for r in coleta["arquivos"]), k)
    medicao["coleta"]["idade_ignorada"] = mascarar(sum(r["idade_ignorada"] for r in coleta["arquivos"]), k)
    medicao["coleta"]["lentos"] = sorted(coleta["arquivos"], key=lambda r: -(r["s_download"] + r["s_conversao"]))[:5]
    medicao["coleta"]["lentos"] = [{c: r[c] for c in ("arquivo", "bytes_dbc", "aihs", "s_download", "s_conversao")}
                                   for r in medicao["coleta"]["lentos"]]
    medicao["totais_uf_competencia"] = {f"{r['uf']}/{r['competencia']}": {"aihs": mascarar(r["aihs"], k),
                                        "internacoes": mascarar(r["internacoes"], k), "bytes_dbc": r["bytes_dbc"],
                                        "modificado_no_ftp": r["modificado_no_ftp"]} for r in coleta["arquivos"]}
    con = duckdb.connect()
    con.execute(f"SET threads = {max(1, processos)}")
    caminhos = [str(trabalho / "min" / (a[:-4] + ".parquet")).replace("\\", "/") for a in arquivos]
    con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({caminhos!r})")
    medicao["anos"] = {}
    medicao["particoes"] = {}
    prelim_regra = base.get("preliminares") or {}
    versao_arquivos = max(r["modificado_no_ftp"] for r in coleta["arquivos"])
    for ano in anos:
        preliminares = {str(mes) for mes in jan.meses_preliminares(ano)}
        antes = ler_anterior(anterior, ano, catalogo) if anterior else None
        _, sup, m = construir_ano(con, "aih", ano, catalogo, k, deduzir, jan.ultimo_mes, preliminares,
                                  antes, jan.ultimo_mes_fechado)
        t = time.perf_counter()
        tamanhos = gravar_particao(sup, ano, trabalho / "particoes", municipios7,
                                   bool(base["supressao"]["motivo_por_celula"]),
                                   {c["id"]: c["metricas"] for c in catalogo["cruzamentos"]},
                                   preliminares, int(prelim_regra.get("arredondar_multiplo", 0)), k,
                                   tuple(prelim_regra.get("contagens", ())))
        m["segundos"]["gravar"] = round(time.perf_counter() - t, 1)
        ded = m.get("deducao_internacoes", {})
        # O que o site precisa saber do ano: o que foi publicado, o que não foi e por quê, e o teste.
        situacao = {"ano": ano, "coletado_em": coletado_em, "versao_dos_arquivos": versao_arquivos,
                    "ultimo_mes": jan.ultimo_mes, "ultimo_mes_fechado": jan.ultimo_mes_fechado,
                    "preliminares": sorted(preliminares), "arredondar_multiplo": prelim_regra.get("arredondar_multiplo"),
                    "publicados": m["publicados"], "nao_publicados": m["nao_publicados"],
                    "deducao": {"rodou": deduzir, "passou": ded.get("passou", False),
                                "pequenas_reveladas": ded.get("pequenas_reveladas"),
                                "obitos_passou": m.get("deducao_obitos", {}).get("passou", False)}}
        (trabalho / "particoes" / f"situacao_{ano}.json").write_text(json.dumps(situacao, ensure_ascii=False, indent=1),
                                                                    encoding="utf-8")
        medicao["anos"][str(ano)] = m
        medicao["particoes"][str(ano)] = {"arquivos": len(tamanhos), "bytes": sum(v["bytes"] for v in tamanhos.values()),
                                          "gzip": sum(v["gzip"] for v in tamanhos.values()),
                                          "maior": max(tamanhos.items(), key=lambda kv: kv[1]["bytes"]) if tamanhos else None}
        ded = m.get("deducao_internacoes", {})
        avisar(f"SIH {ano}: {m['internacoes']} internações; dedução: {ded.get('pequenas_reveladas', '-')} contagens "
               f"pequenas reveladas; {m['segundos']}")
    medicao["disco"] = {"trabalho_bytes": _tamanho(trabalho), "min_bytes": _tamanho(trabalho / "min"),
                        "dbc_bytes": _tamanho(trabalho / "dbc"), "particoes_bytes": _tamanho(trabalho / "particoes")}
    medicao["ambiente_fim"] = ambiente()
    medicao["etapas"]["total_s"] = round(time.perf_counter() - inicio, 1)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "medicao.json").write_text(json.dumps(medicao, ensure_ascii=False, indent=1), encoding="utf-8")
    return medicao
