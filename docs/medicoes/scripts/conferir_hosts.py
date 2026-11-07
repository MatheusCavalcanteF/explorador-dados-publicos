"""Tamanho do motor no pacote e no CDN, e resposta do Cloudflare Pages a Range fora do navegador.

Uso: python -I conferir_hosts.py <dist_do_duckdb_wasm> <saida.json>
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DIST, SAIDA = Path(sys.argv[1]), Path(sys.argv[2])
VERSAO = json.loads((DIST.parent / "package.json").read_text(encoding="utf-8"))["version"]
CDN = f"https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@{VERSAO}/dist/duckdb-eh.wasm"
CLOUDFLARE = ["https://naidan.pages.dev/assets/app-E39mwzM7.js", "https://pxweb2.pages.dev/assets/index-DrB5y3zi.js", "https://query-json.pages.dev/assets/index-BmlMqrip.js"]


def pedir(url, metodo, cabecalhos):
    req = urllib.request.Request(url, method=metodo, headers={"User-Agent": "medicao-etapa0", **cabecalhos})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            corpo = r.read() if metodo == "GET" else b""
            c = r.headers
            return {"status": r.status, "content_length": c.get("Content-Length"), "content_encoding": c.get("Content-Encoding"), "content_range": c.get("Content-Range"), "accept_ranges": c.get("Accept-Ranges"), "server": c.get("Server"), "bytes_recebidos": len(corpo)}
    except urllib.error.HTTPError as e:
        return {"status": e.code}
    except Exception as e:
        return {"erro": repr(e)[:160]}


def pedir_curl(url):
    # O jsDelivr responde por mais de uma CDN, e o tamanho comprimido muda conforme a que atende
    saida = subprocess.run(["curl", "-sS", "-m", "30", "-I", "-H", "Accept-Encoding: br", url], capture_output=True, text=True).stdout
    cabecalhos = dict(l.split(": ", 1) for l in saida.splitlines() if ": " in l)
    cab = {k.lower(): v for k, v in cabecalhos.items()}
    return {"content_length": cab.get("content-length"), "content_encoding": cab.get("content-encoding"), "server": cab.get("server"), "atendido_por": cab.get("x-served-by")}


res = {"coletado_em": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "motor": {"versao": VERSAO, "wasm_bruto_bytes": (DIST / "duckdb-eh.wasm").stat().st_size, "url_cdn": CDN,
       "cdn_com_brotli": pedir(CDN, "HEAD", {"Accept-Encoding": "br"}), "cdn_com_brotli_curl": pedir_curl(CDN)}}
res["cloudflare_range_fora_do_navegador"] = {u: {"aceita_gzip": pedir(u, "GET", {"Range": "bytes=0-1023", "Accept-Encoding": "gzip"}), "identity": pedir(u, "GET", {"Range": "bytes=0-1023", "Accept-Encoding": "identity"})} for u in CLOUDFLARE}
SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
