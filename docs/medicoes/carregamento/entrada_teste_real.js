// Entrada dos testes em host real: a mesma do motor, mais o registro de arquivo por URL.
import * as duckdb from '@duckdb/duckdb-wasm';
import './entrada.js';
window.registrar = async (nome, url, direto) => { await window.__db.registerFileURL(nome, url, duckdb.DuckDBDataProtocol.HTTP, direto); };
