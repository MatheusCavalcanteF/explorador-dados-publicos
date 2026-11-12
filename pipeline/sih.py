"""SIH de ponta a ponta: coleta, tabelas por ano da alta, supressão, teste de dedução, partições e superfície.

Nada desta etapa vai para o site: o catálogo diz `publicacao: {site: false}` até o OK do dono do projeto, e
nada do SIH vai para Releases. As partições ficam na pasta de trabalho do runner. Quando todos os anos passam,
a etapa grava também `trabalho/superficie.parquet`, com exatamente o que o site mostraria (sih_superficie):
é o arquivo que um dia vai para o site como versão no ar. O que sai do runner hoje é só a medição: tempos,
disco, tamanhos e contagens agregadas por cruzamento.

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

from . import sih_coleta, sih_janela, sih_particoes
from .contrato import ErroDeContrato
from .sih_particoes import ErroDeParticao, gravar_ano, ler_situacao  # noqa: F401  (usados por quem importa sih)


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


def tabelas_publicaveis(suprimidas: dict, ano: int, municipios7: dict[str, str],
                        motivo_por_celula: bool = False, metricas: dict[str, list[str]] | None = None,
                        preliminares: set[str] | frozenset = frozenset(), multiplo: int = 0, k: int = 5,
                        contagens: tuple = ("internacoes", "obitos")) -> dict:
    """Cada cruzamento do ano como vai para a partição e para a tela: uma tabela Arrow por cruzamento.

    O município sai com o código de 7 dígitos do IBGE. As AIHs não saem; os valores ocultos saem nulos,
    com o motivo ao lado quando o catálogo manda publicá-lo, ou só a marca de oculta. Óbitos têm máscara
    própria. Cada cruzamento leva só as métricas que o catálogo declara para ele (`metricas`, por id).

    O trimestre sem os três meses na base não sai. Nas linhas cujo período inclui um mês de
    `preliminares` (AAAAMM), `preliminar` é verdadeiro, e cada contagem visível de k para cima sai
    arredondada para múltiplo de `multiplo`, com `arredondado` (internações) e `obitos_arredondado`.
    """
    import numpy as np
    import pyarrow as pa

    from . import sih_deducao, supressao
    tabelas = {}
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
        tabelas[cid] = pa.table(colunas)
    return tabelas


def gravar_particao(suprimidas: dict, ano: int, destino: Path, municipios7: dict[str, str],
                    motivo_por_celula: bool = False, metricas: dict[str, list[str]] | None = None,
                    preliminares: set[str] | frozenset = frozenset(), multiplo: int = 0, k: int = 5,
                    contagens: tuple = ("internacoes", "obitos"), tabelas: dict | None = None) -> dict:
    """Um Parquet sem compressão por cruzamento e UF, em `destino` (a pasta do ano), e o tamanho com gzip.

    As tabelas são as de tabelas_publicaveis (ou `tabelas`, já montadas com os mesmos argumentos). Devolve, por
    arquivo ("<cruzamento>/uf=<UF>.parquet"), bytes, bytes com gzip e SHA-256.
    """
    import hashlib

    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    if tabelas is None:
        tabelas = tabelas_publicaveis(suprimidas, ano, municipios7, motivo_por_celula, metricas, preliminares,
                                      multiplo, k, contagens)
    tamanhos = {}
    for cid, tabela in tabelas.items():
        geo = "mun_res" if "mun_res" in tabela.column_names else "mun_hosp"
        uf_col = pc.utf8_slice_codeunits(tabela[geo], 0, 2)
        for uf in sorted(set(uf_col.to_pylist())):
            parte = tabela.filter(pc.equal(uf_col, uf))
            caminho = destino / cid / f"uf={uf}.parquet"
            caminho.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(parte, caminho, compression="NONE")
            bruto = caminho.read_bytes()
            tamanhos[f"{cid}/uf={uf}.parquet"] = {"bytes": len(bruto), "gzip": len(gzip.compress(bruto, 6)),
                                                  "sha256": hashlib.sha256(bruto).hexdigest()}
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
                         max_rodadas: int | None = None, fixas: dict | None = None, fixo: dict | None = None) -> dict:
    """Supressão com reforço até o teste de dedução dar zero, e o critério de publicação do ano.

    O cruzamento que passa do critério sai do ano, com o motivo, e o que depende dele sai junto. A
    supressão e o teste são refeitos sem eles, porque cada tabela a menos muda o que se pode deduzir.
    `fixas` é o padrão herdado da versão publicada antes (fixas_da_anterior). Devolve o resultado de
    suprimir_ate_passar mais o catálogo do ano, os não publicados e o resumo da primeira volta, com todos
    os cruzamentos.

    `fixo` é a situação da primeira publicação de um ano ainda aberto (decidido em 08/11/2026): publica
    exatamente os cruzamentos dela, sem refazer o critério, e só o teste de dedução tira algum: o
    cruzamento com contagem revelada sai, com o que depende dele. Se o teste não passar e não der para
    dizer qual tirar, o resultado sai com `passou` falso, e o ano não é publicado.
    """
    from . import sih_deducao
    regras = catalogo["bases"]["sih"]["supressao"]
    if fixo is not None:
        return _suprimir_com_situacao_fixa(nos, catalogo, k, ultimo_mes, arredondamento, max_rodadas, fixas, fixo)
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


def _suprimir_com_situacao_fixa(nos, catalogo, k, ultimo_mes, arredondamento, max_rodadas, fixas, fixo) -> dict:
    from . import sih_deducao, sih_tabelas as tab
    regras = catalogo["bases"]["sih"]["supressao"]
    fora = {c["id"]: fixo["nao_publicados"].get(c["id"], {"motivo": "não foi publicado na primeira versão do ano"})
            for c in catalogo["cruzamentos"] if c["id"] not in fixo["publicados"]}
    for _ in range(len(catalogo["cruzamentos"]) + 1):
        cat = catalogo_sem(catalogo, fora)
        r = sih_deducao.suprimir_ate_passar(nos, cat, k, bool(regras["motivo_por_celula"]), max_rodadas,
                                            arredondamento=arredondamento, ultimo_mes=ultimo_mes, fixas=fixas)
        if r["passou"]:
            break
        nos_dos = {tab.nome(tab.colunas_de(c, cat)): c["id"] for c in cat["cruzamentos"]}
        revelados = sorted({nos_dos[n] for n, x in r["auditoria"].get("por_no", {}).items()
                            if n in nos_dos and x["pequenas_reveladas"]})
        if not revelados:
            break
        for cid in revelados:
            fora[cid] = {"motivo": "o teste de dedução revelou contagens com ele no ano"}
            for d in dependentes(catalogo, cid):
                fora.setdefault(d, {"motivo": f"depende de {d_de(catalogo, d)}, que saiu pelo teste de dedução"})
    resumo = resumo_supressao(r["suprimidas"])
    return r | {"catalogo": cat, "nao_publicados": fora, "resumo": resumo, "resumo_com_todos": resumo,
                "situacao_fixa": True}


def d_de(catalogo: dict, cid: str) -> str:
    c = next(x for x in catalogo["cruzamentos"] if x["id"] == cid)
    return c.get("mae") or c.get("herda_trimestre_de")


def construir_ano(con, tabela: str, ano: int, catalogo: dict, k: int, deduzir: bool = True,
                  ultimo_mes: int | None = None, preliminares: set[str] | frozenset = frozenset(),
                  anterior: dict | None = None, fechado_ate: int | None = None,
                  fixo: dict | None = None) -> tuple[dict, dict, dict]:
    """Nós do fechamento, cruzamentos suprimidos (só os publicáveis) e medição de um ano.

    `ultimo_mes` (AAAAMM) é o último mês da alta na base: trimestre sem os três meses fica fora do
    arquivo. `preliminares` são os meses que ainda podem mudar: o teste os vê arredondados, como a tela.
    `anterior` traz o que a versão publicada antes mostrou deste ano (ler_anterior): nas células de período
    fechado até `fechado_ate`, a nova herda o padrão dela (fixas_da_anterior). `fixo` é a situação da
    primeira publicação do ano, que vale enquanto ele está aberto (suprimir_publicaveis).
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
        r = suprimir_publicaveis(nos, catalogo, k, ultimo_mes, arred, int(regras["reforco_max_rodadas"]), fixas, fixo)
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
               "herdou_da_anterior": sorted(anterior) if anterior and fechado_ate else [],
               "situacao_fixa": fixo is not None}
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


def ler_anterior(anterior, ano: int, catalogo: dict) -> tuple[dict, dict]:
    """O que a versão publicada antes mostrou de um ano, e a situação dela.

    `anterior` é a superfície daquela versão (sih_superficie.Superficie), já conferida na leitura: só o que o
    site mostrou. Por cruzamento mostrado no ano, devolve as chaves (município com 6 dígitos, como no
    pipeline) e as colunas oculto e arredondado das internações."""
    from . import sih_tabelas as tab
    situacao = anterior.anos[ano]
    cruzamentos = {c["id"]: c for c in catalogo["cruzamentos"]}
    saida = {}
    for cid in situacao["superficie"]:
        df = anterior.tabela(ano, cid)
        geo = "mun_res" if "mun_res" in df else "mun_hosp"
        df[geo] = df[geo].astype(str).str[:6]
        saida[cid] = df[list(tab.colunas_de(cruzamentos[cid], catalogo)) + ["oculto", "arredondado"]]
    return saida, situacao


def anterior_do_ano(anterior, ano: int, catalogo: dict, fechado: bool) -> tuple[dict | None, dict | None]:
    """O padrão e a situação da versão publicada antes (a superfície dela), para um ano. Ano que ela não
    tinha, e é mais novo que todos os dela, é a primeira publicação dele: nada a herdar. Ano que falta no
    meio é erro."""
    anos = sorted(anterior.anos)
    if ano not in anos:
        if anos and ano > anos[-1]:
            return None, None
        raise ErroDeParticao(f"A versão anterior não tem o ano {ano}, que não é o mais novo")
    padrao, situacao = ler_anterior(anterior, ano, catalogo)
    versoes = catalogo["bases"]["sih"].get("versoes") or {}
    fixo = situacao if versoes.get("situacao_fixa_no_ano_aberto") and not fechado else None
    return (padrao if versoes.get("herdar_padrao_fechado", True) else None), fixo


MEDIDAS_DO_CONJUNTO = ("internacoes", "obitos")


def resumo_do_conjunto(conjunto: dict) -> dict:
    """O ataque conjunto para a situação do ano: sem o detalhe por tabela, que fica na medição."""
    saida = {}
    for c, v in conjunto.items():
        if c in MEDIDAS_DO_CONJUNTO:
            v = v | {"motores": {nome: {a: b for a, b in r.items() if a != "por_no"} for nome, r in v["motores"].items()}}
        saida[c] = v
    return saida


def processar_anos(con, tabela: str, jan: sih_janela.Janela, anos: list[int], catalogo: dict, trabalho: Path,
                   municipios7: dict[str, str], coletado_em: str, versao_arquivos: str, deduzir: bool = True,
                   anterior=None, no_ar_consultada: bool = False, motores: list[str] | None = None,
                   avisar=print, reaproveitados=()) -> dict:
    """Cada ano: tabelas, supressão, teste de dedução, ataque conjunto com a versão anterior e a partição.

    `anterior` é a superfície da versão publicada antes (sih_superficie.Superficie), ou None. Só o ano que passa
    em tudo vira partição em `trabalho/particoes` (sih_particoes.nao_publicavel). O que reprova, ou que não foi
    testado, não é gravado, e a partição que uma execução anterior tenha deixado para ele na pasta de trabalho
    é apagada: ali só fica o que esta execução aprovou. Quando todos os anos passam, grava a superfície da versão
    em `trabalho/superficie.parquet`, com o registro das regras do cálculo; senão, apaga a que houver ali. Devolve
    a medição de cada ano, o resumo das partições, a superfície e os reprovados com o motivo; um reprovado basta
    para nada ser publicado.

    Os anos de `reaproveitados` (sih_reaproveitamento.planejar) não são calculados: a superfície deles é copiada
    de `anterior` como está, e eles ficam sem partição, porque a versão no ar só tem a superfície.
    """
    from . import sih_reaproveitamento, sih_superficie, sih_versoes
    base = catalogo["bases"]["sih"]
    k = int(base["supressao"]["k"])
    prelim_regra = base.get("preliminares") or {}
    multiplo = int(prelim_regra.get("arredondar_multiplo", 0))
    contagens = tuple(prelim_regra.get("contagens", ()))
    obrigatorio = bool((base.get("versoes") or {}).get("ataque_conjunto_obrigatorio", True))
    anos_anteriores = sorted(anterior.anos) if anterior else []
    saida = {"anos": {}, "particoes": {}, "reprovados": {}}
    superficie = sih_superficie.Superficie(calculo=sih_reaproveitamento.calculo(catalogo))
    for ano in anos:
        if ano in reaproveitados:
            sih_particoes.remover_ano(trabalho / "particoes", ano)
            superficie.anos[ano] = anterior.anos[ano]
            superficie.tabelas.update({(ano, cid): anterior.tabelas[ano, cid] for cid in anterior.anos[ano]["superficie"]})
            saida["anos"][str(ano)] = {"ano": ano, "reaproveitado_da_versao_no_ar": True, "particao_gravada": False}
            saida["particoes"][str(ano)] = {"arquivos": 0, "bytes": 0, "gzip": 0, "maior": None,
                                            "nao_gravada": "reaproveitado da versão no ar, que só tem a superfície"}
            avisar(f"SIH {ano}: fechado, copiado da versão no ar de {anterior.anos[ano].get('coletado_em')}, sem recalcular")
            continue
        preliminares = {str(mes) for mes in jan.meses_preliminares(ano)}
        antes, fixo = anterior_do_ano(anterior, ano, catalogo, jan.ano_fechado(ano)) if anterior else (None, None)
        nos, sup, m = construir_ano(con, tabela, ano, catalogo, k, deduzir, jan.ultimo_mes, preliminares,
                                    antes, jan.ultimo_mes_fechado, fixo)
        t = time.perf_counter()
        ded = m.get("deducao_internacoes", {})
        passou = bool(deduzir and ded.get("passou") and m.get("deducao_obitos", {}).get("passou"))
        # O que o site precisa saber do ano: o que foi publicado, o que não foi e por quê, e os testes.
        situacao = {"ano": ano, "coletado_em": coletado_em, "versao_dos_arquivos": versao_arquivos,
                    "ultimo_mes": jan.ultimo_mes, "ultimo_mes_fechado": jan.ultimo_mes_fechado,
                    "preliminares": sorted(preliminares), "arredondar_multiplo": prelim_regra.get("arredondar_multiplo"),
                    "publicados": m["publicados"], "nao_publicados": m["nao_publicados"],
                    "situacao_fixa": m["situacao_fixa"],
                    # O detalhe que a versão no ar mostrava do ano continua publicado depois que ele sai dos
                    # mais novos (decidido em 11/11/2026), e por isso entra no ataque conjunto.
                    "detalhe_mantido": sih_superficie.detalhe_mantido(catalogo, ano, anos, anterior),
                    "versao_no_ar": {"consultada": bool(no_ar_consultada), "tinha_o_ano": ano in anos_anteriores},
                    "deducao": {"rodou": deduzir, "passou": bool(ded.get("passou", False)),
                                "pequenas_reveladas": ded.get("pequenas_reveladas"),
                                "obitos_passou": bool(m.get("deducao_obitos", {}).get("passou", False))}}
        # A candidata como a tela a mostraria: as mesmas tabelas que vão para a partição, recortadas na superfície.
        tabelas = candidata = None
        if passou:
            tabelas = tabelas_publicaveis(sup, ano, municipios7, bool(base["supressao"]["motivo_por_celula"]),
                                          {c["id"]: c["metricas"] for c in catalogo["cruzamentos"]}, preliminares,
                                          multiplo, k, contagens)
            candidata = sih_superficie.do_ano(tabelas, situacao, catalogo, anos)
        # O ataque conjunto precisa de uma candidata que passou sozinha e de uma versão anterior daquele ano.
        if ano not in anos_anteriores:
            conjunto = {"obrigatorio": False, "rodou": False,
                        "motivo": "primeira publicação do ano" if anterior else "nenhuma versão anterior informada"}
        elif not passou:
            conjunto = {"obrigatorio": obrigatorio, "rodou": False, "motivo": "a candidata não passou no teste dela"}
        else:
            conjunto = sih_versoes.conferir_com_a_no_ar(nos, candidata, anterior, catalogo, ano, k,
                                                        jan.ultimo_mes_fechado, motores) | {"obrigatorio": obrigatorio}
        m["ataque_conjunto"] = conjunto
        m["segundos"]["ataque_conjunto"] = round(time.perf_counter() - t, 1)
        t = time.perf_counter()
        situacao["deducao"]["conjunto"] = resumo_do_conjunto(conjunto)
        motivo = sih_particoes.nao_publicavel(situacao)
        if motivo:
            sih_particoes.remover_ano(trabalho / "particoes", ano)
            if deduzir:
                saida["reprovados"][str(ano)] = motivo
            saida["particoes"][str(ano)] = {"arquivos": 0, "bytes": 0, "gzip": 0, "maior": None, "nao_gravada": motivo}
        else:
            tamanhos = gravar_ano(trabalho / "particoes", ano, lambda pasta: gravar_particao(
                sup, ano, pasta, municipios7, tabelas=tabelas), situacao)
            saida["particoes"][str(ano)] = {"arquivos": len(tamanhos), "bytes": sum(v["bytes"] for v in tamanhos.values()),
                                            "gzip": sum(v["gzip"] for v in tamanhos.values()),
                                            "maior": max(tamanhos.items(), key=lambda kv: kv[1]["bytes"]) if tamanhos else None}
            meta, tabs = candidata
            superficie.anos[ano] = meta | {"deducao": situacao["deducao"]}
            superficie.tabelas.update({(ano, cid): t_cid for cid, t_cid in tabs.items()})
        m["particao_gravada"] = not motivo
        m["segundos"]["gravar"] = round(time.perf_counter() - t, 1)
        saida["anos"][str(ano)] = m
        avisar(f"SIH {ano}: {m['internacoes']} internações; dedução: {ded.get('pequenas_reveladas', '-')} contagens "
               f"pequenas reveladas; ataque conjunto: {'passou' if conjunto.get('passou') else conjunto.get('motivo')}; "
               f"{'SEM PARTIÇÃO: ' + motivo if motivo else 'partição gravada'}; {m['segundos']}")
    # A superfície só existe para uma versão que passou inteira: é ela que pode ir para o site.
    arquivo = trabalho / sih_superficie.ARQUIVO
    if deduzir and not saida["reprovados"] and len(superficie.anos) == len(anos):
        saida["superficie"] = sih_superficie.gravar(superficie, arquivo, catalogo)
    else:
        arquivo.unlink(missing_ok=True)
        saida["superficie"] = None
    return saida


def executar(coleta_ibge: dict, catalogo: dict, trabalho: Path, saida: Path, ufs: list[str] | None = None,
             anos: list[int] | None = None, processos: int = 4, origem_local: Path | None = None,
             manter_dbc: bool = False, deduzir: bool = True, listagem: dict | None = None, avisar=print,
             anterior=None, no_ar_consultada: bool = False, motores: list[str] | None = None,
             reaproveitar: bool = True) -> dict:
    """A execução inteira. Devolve a medição, que é o único arquivo gravado fora da pasta de trabalho.

    `anterior` é a superfície da versão publicada antes (sih_superficie.Superficie): nos períodos já fechados,
    a nova herda o padrão de células ocultas dela, para que quem guardou as duas não cruze um padrão com o
    outro, e cada ano que ela tem passa pelo ataque conjunto (sih_versoes). `no_ar_consultada` diz que
    `anterior`, ou a falta dela, veio da consulta ao site (sih_superficie.versao_no_ar), e não de uma pasta
    escolhida à mão.
    Com as mesmas regras e o mesmo algoritmo de supressão da versão anterior, os anos fechados nas duas são
    copiados dela, sem baixar as competências deles (sih_reaproveitamento); `reaproveitar` falso recalcula todos.
    Ano que não passa em todos os testes não vira partição, e a medição o lista em `reprovados`.
    """
    import duckdb

    from datetime import datetime, timezone

    from . import sih_reaproveitamento

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
    plano = sih_reaproveitamento.planejar(anterior, catalogo, jan, anos, listagem, set(ufs) == set(sih_janela.UFS),
                                          reaproveitar and deduzir)
    medicao["reaproveitamento"] = plano
    calcular = [a for a in anos if a not in plano["reaproveitados"]]
    for aviso in plano["avisos"]:
        avisar(aviso)
    arquivos = arquivos_necessarios(jan, calcular, ufs)
    municipios7 = {m["codigo"][:6]: m["codigo"] for m in coleta_ibge["municipios"]}
    da_no_ar = f"{plano['reaproveitados'] or 'nenhum ano'}" + (f" ({plano['motivo']})" if plano["motivo"] else "")
    avisar(f"SIH: {len(arquivos)} arquivos de {len(ufs)} UF(s), competências para os anos {calcular}; "
           f"última completa {jan.ultima_completa}, fechado até {jan.ultimo_mes_fechado}; da versão no ar: {da_no_ar}")
    if arquivos:
        coleta = coletar(listagem, arquivos, trabalho, set(municipios7), catalogo, processos, manter_dbc, origem_local, avisar)
    else:
        coleta = {"arquivos": [], "segundos": 0.0, "bytes_dbc": 0, "bytes_min": 0, "maior_disco_bytes": 0,
                  "processos": processos}
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
    if arquivos:
        caminhos = [str(trabalho / "min" / (a[:-4] + ".parquet")).replace("\\", "/") for a in arquivos]
        con.execute(f"CREATE VIEW aih AS SELECT * FROM read_parquet({caminhos!r})")
    versao_arquivos = max((r["modificado_no_ftp"] for r in coleta["arquivos"]), default=None)
    medicao |= processar_anos(con, "aih", jan, anos, catalogo, trabalho, municipios7, coletado_em, versao_arquivos,
                              deduzir, anterior, no_ar_consultada, motores, avisar, plano["reaproveitados"])
    # Um ano reprovado basta: a versão inteira não pode ser publicada, e o site anterior continua no ar.
    medicao["publicavel"] = bool(deduzir) and not medicao["reprovados"]
    medicao["disco"] = {"trabalho_bytes": _tamanho(trabalho), "min_bytes": _tamanho(trabalho / "min"),
                        "dbc_bytes": _tamanho(trabalho / "dbc"), "particoes_bytes": _tamanho(trabalho / "particoes")}
    medicao["ambiente_fim"] = ambiente()
    medicao["etapas"]["total_s"] = round(time.perf_counter() - inicio, 1)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "medicao.json").write_text(json.dumps(medicao, ensure_ascii=False, indent=1), encoding="utf-8")
    return medicao


