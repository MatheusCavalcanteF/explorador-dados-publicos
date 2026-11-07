import * as duckdb from '@duckdb/duckdb-wasm';
window.iniciar = async (filesystem) => {
  const t0 = performance.now();
  const worker = new Worker('/duckdb/duckdb-browser-eh.worker.js');
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate('/duckdb/duckdb-eh.wasm');
  await db.open({ filesystem });
  const con = await db.connect();
  await (await con.query('SELECT 1')).toArray();
  window.__db = db; window.__con = con;
  return performance.now() - t0;
};
window.consultar = async (sql) => {
  const t = performance.now();
  const r = await window.__con.query(sql);
  const linhas = r.toArray().map(x => x.toJSON());
  return { ms: performance.now() - t, linhas: linhas.length, amostra: JSON.parse(JSON.stringify(linhas.slice(0, 1), (k, v) => typeof v === 'bigint' ? Number(v) : v)) };
};
