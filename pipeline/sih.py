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


def _um_arquivo(nome: str, esperado: int, trabalho: str, municipios6: frozenset, colunas: list, defasagem: int,
                manter_dbc: bool, origem_local: str | None) -> dict:
    """Baixa (ou lê da pasta local) e converte um arquivo. Roda num processo à parte."""
    import pyarrow.parquet as pq
    inicio = time.perf_counter()
    pasta = Path(trabalho)
    if origem_local:
        dbc = Path(origem_local) / nome
        if dbc.stat().st_size != esperado:
            raise ErroDeContrato(f"{nome}: a cópia local tem {dbc.stat().st_size} bytes, a listagem diz {esperado}")
    else:
        dbc = sih_coleta.baixar(nome, esperado, pasta / "dbc")
    baixado = time.perf_counter()
    tabela, resumo = sih_coleta.converter(dbc.read_bytes(), nome, set(municipios6), colunas, defasagem)
    destino = pasta / "min" / (nome[:-4] + ".parquet")
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".part")
    pq.write_table(tabela, parcial, compression="zstd")
    parcial.replace(destino)
    if not manter_dbc and not origem_local:
        dbc.unlink()
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
        futuros = {pool.submit(_um_arquivo, n, listagem[n]["bytes"], str(trabalho), frozenset(municipios6), colunas,
                               defasagem, manter_dbc, str(origem_local) if origem_local else None): n for n in arquivos}
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


def gravar_particao(suprimidas: dict, ano: int, destino: Path, municipios7: dict[str, str],
                    motivo_por_celula: bool = False, metricas: dict[str, list[str]] | None = None) -> dict:
    """Um Parquet sem compressão por cruzamento e UF, como o site vai servir, e o tamanho com gzip.

    O município sai com o código de 7 dígitos do IBGE. As AIHs não saem; os valores ocultos saem nulos,
    com o motivo ao lado quando o catálogo manda publicá-lo, ou só a marca de oculta. Óbitos têm máscara
    própria. Cada cruzamento leva só as métricas que o catálogo declara para ele (`metricas`, por id).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from . import supressao
    tamanhos = {}
    for cid, df in suprimidas.items():
        geo = "mun_res" if "mun_res" in df else "mun_hosp"
        df = df.copy()
        df[geo] = df[geo].map(municipios7)
        oculto = df["oculto"].to_numpy()
        colunas = {c: pa.array(df[c], pa.string()) for c in df.columns
                   if c not in ("aihs", "internacoes", "dias", "valor", "obitos", "oculto", "estado", "estado_obitos")}
        declaradas = {COLUNA_DA_METRICA[m] for m in (metricas or {}).get(cid, ["internacoes", "dias_permanencia", "valor_total", "obitos"])}
        for medida in ("internacoes", "dias", "valor"):
            if medida in declaradas:
                tipo = pa.float64() if medida == "valor" else pa.int64()
                colunas[medida] = pa.array(df[medida].where(~oculto, None), tipo)
        if motivo_por_celula:
            colunas["motivo"] = pa.array([supressao.MOTIVOS[int(e)] for e in df["estado"]], pa.string())
        else:
            colunas["oculto"] = pa.array(oculto, pa.bool_())
        if "estado_obitos" in df and "obitos" in declaradas:
            oculto_ob = df["estado_obitos"].to_numpy() != 0
            colunas["obitos"] = pa.array(df["obitos"].where(~oculto_ob, None), pa.int64())
            if motivo_por_celula:
                colunas["motivo_obitos"] = pa.array([supressao.MOTIVOS[int(e)] for e in df["estado_obitos"]], pa.string())
            else:
                colunas["obitos_oculto"] = pa.array(oculto_ob, pa.bool_())
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
    """Por cruzamento: linhas, células ocultas e internações ocultas, em contagens e percentuais."""
    saida = {}
    for cid, df in suprimidas.items():
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


def construir_ano(con, tabela: str, ano: int, catalogo: dict, k: int, deduzir: bool = True) -> tuple[dict, dict, dict]:
    """Nós do fechamento, cruzamentos suprimidos e medição de um ano."""
    from . import sih_deducao, sih_tabelas as tab, supressao
    t = {"inicio": time.perf_counter()}
    pub_int = sih_deducao.nos_publicados(catalogo, "internacoes")
    pub_ob = sih_deducao.nos_publicados(catalogo, "obitos")
    base = tab.calcular_base(con, tabela, ano, list(dict.fromkeys(pub_int + pub_ob)), catalogo)
    t["base"] = time.perf_counter()
    nos = tab.montar(base, list(dict.fromkeys(pub_int + pub_ob)))
    t["fechamento"] = time.perf_counter()
    regras = catalogo["bases"]["sih"]["supressao"]
    if deduzir:
        # Supressão, teste de dedução e reforço até passar. O teste vê o que a tela mostraria: com o
        # motivo de cada célula, se o catálogo mandar publicá-lo, ou só "oculta".
        r = sih_deducao.suprimir_ate_passar(nos, catalogo, k, bool(regras["motivo_por_celula"]),
                                            int(regras["reforco_max_rodadas"]))
        sup = r["suprimidas"]
    else:
        sup = supressao.suprimir(nos, catalogo, k)
    for c in catalogo["cruzamentos"]:
        if "obitos" in c["metricas"]:
            n = tab.colunas_de(c, catalogo)
            sup[c["id"]]["estado_obitos"] = supressao.suprimir_obitos(nos[n], n, k)
    t["supressao"] = time.perf_counter()
    medicao = {"ano": ano, "aihs": int(nos[()]["aihs"].sum()), "internacoes": int(nos[()]["internacoes"].sum()),
               "nos_no_fechamento": len(tab.fechamento(pub_int)), "supressao": resumo_supressao(sup)}
    if deduzir:
        medicao["deducao_internacoes"] = r["auditoria"] | {"rodadas": r["historico"], "passou": r["passou"],
                                                            "motivo_por_celula": bool(regras["motivo_por_celula"])}
        est_ob = sih_deducao.estados_publicados(nos, sup, catalogo, k, "obitos")
        if not regras["motivo_por_celula"]:
            est_ob = sih_deducao.sem_motivo(est_ob)
        medicao["deducao_obitos"] = sih_deducao.auditar(sih_deducao.sistema(nos, est_ob, pub_ob, k, medida="obitos"))
        medicao["deducao_obitos"]["passou"] = medicao["deducao_obitos"]["pequenas_reveladas"] == 0
        t["deducao_obitos"] = time.perf_counter()
    etapas = list(t)
    medicao["segundos"] = {e: round(t[e] - t[etapas[i - 1]], 1) for i, e in enumerate(etapas) if i}
    return nos, sup, medicao


def executar(coleta_ibge: dict, catalogo: dict, trabalho: Path, saida: Path, ufs: list[str] | None = None,
             anos: list[int] | None = None, processos: int = 4, origem_local: Path | None = None,
             manter_dbc: bool = False, deduzir: bool = True, listagem: dict | None = None, avisar=print) -> dict:
    """A execução inteira. Devolve a medição, que é o único arquivo gravado fora da pasta de trabalho."""
    import duckdb

    base = catalogo["bases"]["sih"]
    k = int(base["supressao"]["k"])
    inicio = time.perf_counter()
    medicao = {"ambiente_inicio": ambiente(), "etapas": {}}
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
    for ano in anos:
        _, sup, m = construir_ano(con, "aih", ano, catalogo, k, deduzir)
        t = time.perf_counter()
        tamanhos = gravar_particao(sup, ano, trabalho / "particoes", municipios7,
                                   bool(base["supressao"]["motivo_por_celula"]),
                                   {c["id"]: c["metricas"] for c in catalogo["cruzamentos"]})
        m["segundos"]["gravar"] = round(time.perf_counter() - t, 1)
        m["preliminares"] = jan.meses_preliminares(ano)
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
