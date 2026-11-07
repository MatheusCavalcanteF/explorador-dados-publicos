"""Baixa os RD de 2025 das UFs fora SP, com 4 conexões, e grava só as colunas usadas nas medições."""
import ftplib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


import datasus_dbc
import pyarrow as pa
import pyarrow.parquet as pq

LIB, DESTINO_DBC, DESTINO_MIN, SAIDA = map(Path, sys.argv[1:5])
sys.path.insert(0, str(LIB))
from dbf_reader import read_dbf_bytes  # noqa: E402

UFS = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE TO".split()
MESES = [f"25{m:02d}" for m in range(1, 13)]
COLUNAS = [
    "ANO_CMPT", "MES_CMPT", "IDENT", "CNES", "MUNIC_MOV", "MUNIC_RES", "DIAG_PRINC", "DT_INTER", "DT_SAIDA",
    "DIAS_PERM", "VAL_TOT", "MORTE", "COBRANCA", "ESPEC", "CAR_INT", "SEXO", "IDADE", "COD_IDADE", "COMPLEX",
    "RACA_COR", "PROC_REA",
]
DIR_FTP = "/dissemin/publicos/SIHSUS/200801_/Dados"
DESTINO_DBC.mkdir(parents=True, exist_ok=True)
DESTINO_MIN.mkdir(parents=True, exist_ok=True)


def baixar(nome: str) -> dict:
    alvo = DESTINO_DBC / nome
    inicio = time.perf_counter()
    for tentativa in range(4):
        try:
            with ftplib.FTP("ftp.datasus.gov.br", timeout=120) as ftp:
                ftp.login()
                ftp.cwd(DIR_FTP)
                ftp.voidcmd("TYPE I")
                tamanho = ftp.size(nome)
                if not (alvo.exists() and alvo.stat().st_size == tamanho):
                    parcial = alvo.with_suffix(".part")
                    with parcial.open("wb") as fh:
                        ftp.retrbinary(f"RETR {nome}", fh.write)
                    if parcial.stat().st_size != tamanho:
                        raise OSError(f"{nome}: tamanho divergente")
                    parcial.replace(alvo)
            break
        except ftplib.all_errors as exc:
            if tentativa == 3:
                return {"nome": nome, "erro": str(exc)}
            time.sleep(5 * 2**tentativa)
    download_s = time.perf_counter() - inicio

    parquet = DESTINO_MIN / (alvo.stem + ".parquet")
    if not parquet.exists():
        dados = datasus_dbc.decompress_bytes(alvo.read_bytes())
        df = read_dbf_bytes(dados, alvo.stem + ".dbf", columns=COLUNAS)
        tabela = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(tabela, parquet, compression="zstd")
    return {"nome": nome, "dbc_bytes": alvo.stat().st_size, "download_s": round(download_s, 1), "linhas": pq.read_metadata(parquet).num_rows}


nomes = [f"RD{uf}{m}.dbc" for uf in UFS for m in MESES]
inicio = time.perf_counter()
resultados = []
with ThreadPoolExecutor(max_workers=4) as pool:
    futuros = {pool.submit(baixar, n): n for n in nomes}
    for i, f in enumerate(as_completed(futuros), 1):
        try:
            r = f.result()
        except Exception as exc:  # um arquivo ruim não pode parar a coleta
            r = {"nome": futuros[f], "erro": repr(exc)}
        resultados.append(r)
        if i % 26 == 0 or "erro" in r:
            print(i, "de", len(nomes), r, f"{time.perf_counter() - inicio:.0f}s", flush=True)

resumo = {"conexoes": 4, "segundos_de_relogio": round(time.perf_counter() - inicio), "o_que_o_tempo_inclui": "baixar e converter para Parquet os arquivos que ainda não estavam na pasta", "arquivos": resultados}
(SAIDA / "rd_brasil_coleta.json").write_text(json.dumps(resumo, indent=1), encoding="utf-8")
erros = [r for r in resultados if "erro" in r]
print("fim", len(resultados), "erros", len(erros), f"{time.perf_counter() - inicio:.0f}s", "linhas", sum(r.get("linhas", 0) for r in resultados), "MB", round(sum(r.get("dbc_bytes", 0) for r in resultados) / 1e6, 1))
for e in erros:
    print(e)
