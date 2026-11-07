import sys
import duckdb
base, destino = sys.argv[1:3]
duckdb.connect().execute(f"COPY (SELECT * FROM '{base}' ORDER BY ALL) TO '{destino}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, ROW_GROUP_SIZE 2000)")
