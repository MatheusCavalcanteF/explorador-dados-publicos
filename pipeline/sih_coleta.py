"""Coleta do SIH no FTP do DATASUS: listagem, download e conversão para um Parquet mínimo.

O FTP não tem TLS nem hash, então a integridade é conferida pela estrutura: tamanho igual ao da
listagem (o download vai para um .part até conferir), registros iguais aos do cabeçalho do DBF e o
contrato de cada linha. A versão de cada arquivo é o par tamanho e data da listagem, guardado no
manifesto: arquivo que muda de tamanho não prova que os números mudaram, nem o contrário.

Só as colunas da lista do catálogo saem do .dbf. CEP, nascimento e CPFs nunca são lidos, e N_AIH
serve só para conferir a chave dentro do arquivo: não chega ao Parquet mínimo. O Parquet mínimo
tem uma linha por AIH e nunca sai do runner, nem como artefato; só os agregados suprimidos saem.
"""
from __future__ import annotations

import ftplib
import re
import time
from datetime import datetime
from pathlib import Path

from . import sih_janela
from .contrato import ErroDeContrato

HOST = "ftp.datasus.gov.br"
DIRETORIO = "/dissemin/publicos/SIHSUS/200801_/Dados"
# Listagem no estilo do IIS: "10-16-26  09:12AM   30123456 RDSP2608.dbc" (mês-dia-ano).
_LINHA = re.compile(r"^(\d\d)-(\d\d)-(\d\d)\s+(\d\d):(\d\d)(AM|PM)\s+(\d+)\s+(RD([A-Z]{2})(\d{4})\.dbc)$", re.IGNORECASE)


def ler_listagem(linhas: list[str]) -> dict[str, dict]:
    """Arquivos RD da listagem, por nome. Outros arquivos da pasta (os .zip de 2017) ficam de fora."""
    arquivos = {}
    for linha in linhas:
        m = _LINHA.match(linha.strip())
        if not m:
            continue
        mes, dia, ano, hora, minuto, ampm, tamanho, nome, uf, aamm = m.groups()
        hora = int(hora) % 12 + (12 if ampm.upper() == "PM" else 0)
        uf = uf.upper()
        if uf not in sih_janela.UFS:
            raise ErroDeContrato(f"SIH: UF desconhecida na listagem do FTP: {nome}")
        quando = datetime(2000 + int(ano), int(mes), int(dia), hora, int(minuto))
        arquivos[nome.upper().replace(".DBC", ".dbc")] = {
            "uf": uf, "competencia": sih_janela.de_nome(aamm), "bytes": int(tamanho),
            "modificado_no_ftp": quando.strftime("%Y-%m-%dT%H:%M")}
    if not arquivos:
        raise ErroDeContrato("SIH: a listagem do FTP não trouxe nenhum arquivo RD")
    return arquivos


def competencias_por_uf(arquivos: dict[str, dict]) -> dict[str, set[int]]:
    por_uf: dict[str, set[int]] = {}
    for a in arquivos.values():
        por_uf.setdefault(a["uf"], set()).add(a["competencia"])
    return por_uf


def nome_do_arquivo(uf: str, competencia: int) -> str:
    return f"RD{uf}{competencia % 10000:04d}.dbc"


def conectar(tempo: float = 120) -> ftplib.FTP:
    ftp = ftplib.FTP(HOST, timeout=tempo)
    ftp.login()
    ftp.cwd(DIRETORIO)
    ftp.voidcmd("TYPE I")
    return ftp


def listar(conectar_ftp=conectar) -> dict[str, dict]:
    ftp = conectar_ftp()
    try:
        linhas: list[str] = []
        ftp.retrlines("LIST", linhas.append)
    finally:
        ftp.close()
    return ler_listagem(linhas)


def baixar(nome: str, esperado: int, destino: Path, conectar_ftp=conectar, tentativas: int = 4,
           espera: float = 5.0, dormir=time.sleep) -> Path:
    """Baixa para um .part e só troca pelo definitivo com o tamanho da listagem. Idempotente.

    Um arquivo já baixado com o mesmo tamanho não é baixado de novo. O tamanho é a única conferência
    possível: o FTP não publica hash.
    """
    alvo = destino / nome
    if alvo.exists() and alvo.stat().st_size == esperado:
        return alvo
    destino.mkdir(parents=True, exist_ok=True)
    parcial = alvo.with_suffix(".part")
    ultimo = None
    for tentativa in range(tentativas):
        try:
            ftp = conectar_ftp()
            try:
                with parcial.open("wb") as arquivo:
                    ftp.retrbinary(f"RETR {nome}", arquivo.write)
            finally:
                ftp.close()
            recebido = parcial.stat().st_size
            if recebido != esperado:
                raise ErroDeContrato(f"{nome}: {recebido} bytes recebidos, a listagem diz {esperado}")
            parcial.replace(alvo)
            return alvo
        except (*ftplib.all_errors, ErroDeContrato) as erro:
            ultimo = erro
            if tentativa + 1 < tentativas:
                dormir(espera * 2 ** tentativa)
    parcial.unlink(missing_ok=True)
    raise ErroDeContrato(f"{nome}: download falhou após {tentativas} tentativas ({ultimo})")


# Contrato de cada linha, a partir do que os dados de 2021 a 2026 mostraram (76,1 milhões de AIHs,
# competências 2101 a 2608, inspecionadas em 08/11/2026): nenhuma violação em nenhuma regra abaixo.
IDENT = {"1", "5"}
RACA_COR = {"01", "02", "03", "04", "05", "99"}
CAR_INT = {"01", "02", "03", "04", "05", "06"}
# Sexo 1 é masculino; 2 e 3, feminino. O 4 aparece em 276 AIHs e não está no dicionário: vai para
# "ignorado", como qualquer outro código, e a contagem fica no resumo do arquivo.
SEXO_CONHECIDO = {"1", "2", "3"}
COD_IDADE_CONHECIDO = {"2", "3", "4", "5"}


def _contrato(df, nome: str, uf_codigo: str, competencia: int, municipios6: set[str], defasagem: int) -> dict:
    """Confere cada regra e devolve as contagens do resumo. Qualquer violação para o arquivo."""
    import numpy as np
    problemas = {}

    def regra(nome_regra: str, ruins) -> None:
        n = int(np.asarray(ruins).sum())
        if n:
            problemas[nome_regra] = n

    texto = {c: df[c].astype("string").fillna("") for c in
             ("ANO_CMPT", "MES_CMPT", "IDENT", "CNES", "MUNIC_MOV", "MUNIC_RES", "DIAG_PRINC", "DT_INTER",
              "DT_SAIDA", "ESPEC", "CAR_INT", "SEXO", "COD_IDADE", "RACA_COR", "N_AIH")}
    regra("competência diferente da do nome do arquivo", (texto["ANO_CMPT"] + texto["MES_CMPT"]) != str(competencia))
    regra("IDENT fora de {1, 5}", ~texto["IDENT"].isin(IDENT))
    regra("MUNIC_MOV de outra UF", texto["MUNIC_MOV"].str[:2] != uf_codigo)
    regra("MUNIC_MOV fora da lista de municípios", ~texto["MUNIC_MOV"].isin(municipios6))
    regra("MUNIC_RES fora da lista de municípios", ~texto["MUNIC_RES"].isin(municipios6))
    regra("CNES fora do formato de 7 dígitos", ~texto["CNES"].str.fullmatch(r"\d{7}"))
    regra("DIAG_PRINC fora do formato da CID-10", ~texto["DIAG_PRINC"].str.fullmatch(r"[A-Z]\d{2}[0-9A-Z]?"))
    regra("RACA_COR fora do dicionário", ~texto["RACA_COR"].isin(RACA_COR))
    regra("CAR_INT fora do dicionário", ~texto["CAR_INT"].isin(CAR_INT))
    regra("ESPEC fora do formato de 2 dígitos", ~texto["ESPEC"].str.fullmatch(r"\d{2}"))
    import pandas as pd
    saida = pd.to_datetime(texto["DT_SAIDA"], format="%Y%m%d", errors="coerce")
    entrada = pd.to_datetime(texto["DT_INTER"], format="%Y%m%d", errors="coerce")
    regra("DT_SAIDA inválida", saida.isna())
    regra("DT_INTER inválida", entrada.isna())
    regra("DT_INTER depois de DT_SAIDA", (entrada > saida).fillna(False))
    mes_saida = texto["DT_SAIDA"].str[:6].astype("Int64").fillna(0).to_numpy()
    meses = (competencia // 100) * 12 + competencia % 100 - ((mes_saida // 100) * 12 + mes_saida % 100)
    regra("alta depois da competência", meses < 0)
    regra(f"alta mais de {defasagem} meses antes da competência", meses > defasagem)
    for coluna in ("DIAS_PERM", "VAL_TOT", "IDADE", "MORTE"):
        regra(f"{coluna} vazio", df[coluna].isna())
    regra("DIAS_PERM negativo", (df["DIAS_PERM"] < 0).fillna(False))
    regra("VAL_TOT negativo", (df["VAL_TOT"] < 0).fillna(False))
    regra("MORTE fora de {0, 1}", ~df["MORTE"].isin([0, 1]))
    regra("chave (N_AIH, IDENT, DT_SAIDA) repetida",
          pd.DataFrame({"a": texto["N_AIH"], "i": texto["IDENT"], "s": texto["DT_SAIDA"]}).duplicated())
    if problemas:
        lista = "; ".join(f"{k}: {v} linha(s)" for k, v in problemas.items())
        raise ErroDeContrato(f"{nome}: {len(df)} linhas, contrato violado ({lista}). Nada deste arquivo foi usado.")
    return {"sexo_ignorado": int((~texto["SEXO"].isin(SEXO_CONHECIDO)).sum()),
            "idade_ignorada": int((~texto["COD_IDADE"].isin(COD_IDADE_CONHECIDO)).sum())}


def converter(dbc: bytes, nome: str, municipios6: set[str], colunas: list[str], defasagem: int,
              descomprimir=None):
    """Do .dbc ao Parquet mínimo, em memória. Devolve (tabela pyarrow, resumo do arquivo).

    O resumo só tem totais do arquivo inteiro (uma UF numa competência), que vão para o manifesto.
    """
    import pyarrow as pa

    from . import dtb
    from .dbf_reader import DBFFormatError, read_dbf_bytes
    if descomprimir is None:
        import datasus_dbc
        descomprimir = datasus_dbc.decompress_bytes
    m = re.fullmatch(r"RD([A-Z]{2})(\d{4})\.dbc", nome)
    if not m:
        raise ErroDeContrato(f"{nome}: nome fora do padrão RD{{uf}}{{aamm}}.dbc")
    uf, competencia = m[1], sih_janela.de_nome(m[2])
    uf_codigo = next(c for c, (s, _) in dtb.UFS.items() if s == uf)
    try:
        df = read_dbf_bytes(descomprimir(dbc), nome, columns=colunas)
    except (DBFFormatError, KeyError) as erro:
        raise ErroDeContrato(f"{nome}: .dbf ilegível ou sem as colunas do catálogo ({erro})") from None
    if df.empty:
        raise ErroDeContrato(f"{nome}: arquivo sem nenhuma AIH")
    extras = _contrato(df, nome, uf_codigo, competencia, municipios6, defasagem)
    texto = lambda c: df[c].astype("string")
    tabela = pa.table({
        "competencia": pa.array([competencia] * len(df), pa.int32()),
        "ident": pa.array(texto("IDENT").astype(int).to_numpy(), pa.int8()),
        "cnes": pa.array(texto("CNES"), pa.string()),
        "mun_hosp": pa.array(texto("MUNIC_MOV"), pa.string()),
        "mun_res": pa.array(texto("MUNIC_RES"), pa.string()),
        "cid3": pa.array(texto("DIAG_PRINC").str[:3], pa.string()),
        "dt_inter": pa.array(texto("DT_INTER").astype(int).to_numpy(), pa.int32()),
        "dt_saida": pa.array(texto("DT_SAIDA").astype(int).to_numpy(), pa.int32()),
        "dias": pa.array(df["DIAS_PERM"].astype("int64").to_numpy(), pa.int32()),
        "valor": pa.array(df["VAL_TOT"].astype("float64").to_numpy(), pa.float64()),
        "morte": pa.array(df["MORTE"].astype("int64").to_numpy(), pa.int8()),
        "espec": pa.array(texto("ESPEC"), pa.string()),
        "car_int": pa.array(texto("CAR_INT"), pa.string()),
        "sexo": pa.array(texto("SEXO"), pa.string()),
        "idade": pa.array(df["IDADE"].astype("int64").to_numpy(), pa.int16()),
        "cod_idade": pa.array(texto("COD_IDADE"), pa.string()),
        "raca": pa.array(texto("RACA_COR"), pa.string()),
    })
    internacoes = int((tabela["ident"].to_numpy() == 1).sum())
    resumo = {"uf": uf, "competencia": competencia, "aihs": len(df), "internacoes": internacoes,
              "obitos": int(df["MORTE"].sum()), "dias": int(df["DIAS_PERM"].sum()),
              "valor": round(float(df["VAL_TOT"].sum()), 2), **extras}
    return tabela, resumo
