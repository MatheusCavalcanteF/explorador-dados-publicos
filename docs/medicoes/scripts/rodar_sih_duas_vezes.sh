#!/bin/sh
# Roda o SIH duas vezes para conferir a idempotência da supressão.
S="$1"  # pasta de trabalho
P="$2"  # pasta data do projeto de origem
cd "$S/scripts" || exit 1

for r in r1 r2; do
  rm -f "$S/dados/sih/aih3.duckdb"
  "$S/venv/Scripts/python.exe" -I "$S/scripts/medir_sih.py" "$P/converted" "$S/dados/sih/min" "$P/reference/cid10.parquet" "$S/dados/ibge/sidra_6579.json" "$S/saida" "$S/dados/sih/aih3.duckdb" > "$S/saida/sih_$r.log" 2>&1
  tail -1 "$S/saida/sih_$r.log" | cut -c1-160
  cp "$S/saida/sih_agregados.json" "$S/saida/sih_agregados_$r.json"
done
