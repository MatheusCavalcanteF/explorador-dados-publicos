"""Confere os resultados e os textos de docs/ antes de irem para o repositório.

1. Caminhos da máquina. Por padrão procura letra de unidade, /home/ e /Users/. O que é próprio de uma máquina,
   como nome de usuário ou pasta temporária, vem por argumento e nunca fica escrito aqui.
2. Valores inteiros de 1 a 4 sob qualquer objeto ou lista que identifique um município real, por valor ou por chave,
   usando a lista de códigos do IBGE. A verificação desce pelos valores aninhados. Chaves que não são contagem de
   pessoas ou eventos estão listadas em NAO_CONTAGEM, e tudo o que for ignorado por causa delas é relatado.
   Município citado só pelo nome, sem código, não é reconhecido.

Uso:
    python -I verificar_resultados.py <pasta_resultados> <municipios.json> [--texto <pasta>] [--termo-local TEXTO ...]

Sai com código 1 se houver problema.
"""
import argparse
import json
import re
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description="Confere caminhos da máquina e contagens pequenas por município.")
parser.add_argument("resultados", type=Path, help="pasta com os JSON de resultado")
parser.add_argument("municipios", help="JSON da API de localidades do IBGE")
parser.add_argument("--texto", type=Path, help="pasta cujos arquivos de texto também são varridos em busca de caminhos")
parser.add_argument("--termo-local", action="append", default=[], metavar="TEXTO", help="termo próprio da máquina, como o nome de usuário; pode repetir")
args = parser.parse_args()

CODIGOS = set()
for m in json.load(open(args.municipios, encoding="utf-8")):
    CODIGOS.add(str(m["id"]))
    CODIGOS.add(str(m["id"])[:6])

# Só os termos locais ignoram maiúsculas: a letra de unidade em minúscula casaria com o d:\d de uma expressão regular
padroes = [r"(?<![A-Za-z])[A-Z]:[\\/]", r"/home/", r"/Users/"] + [f"(?i:{re.escape(t)})" for t in args.termo_local]
CAMINHO = re.compile("|".join(padroes))
URL = re.compile(r"(?:https?|ftp)://\S+")
SUFIXOS_TEXTO = {".py", ".mjs", ".js", ".md", ".json", ".html", ".sh", ".txt", ".yml", ".yaml"}
# Não são contagem de pessoas: meses comparados, requisições HTTP, linhas de relatório fiscal, bytes, status, população,
# e a maior diferença entre duas fontes para o mesmo conjunto de AIHs, que é discrepância, não grupo de pessoas
NAO_CONTAGEM = re.compile(r"^(meses|meses_lidos_do_tabnet|meses_iguais|iguais_data_de_saida|iguais_data_de_internacao|maior_diferenca_saida|maior_diferenca|req|r206|status\d*|bytes.*|dca\d+|rreo.*|pop|uf)$")

problemas = []
ignorados = {}


def eh_municipio(v):
    return not isinstance(v, bool) and isinstance(v, (str, int)) and str(v) in CODIGOS


def tem_municipio(obj):
    if isinstance(obj, dict):
        # A chave também pode ser o código, como em {"3547809": 3}
        return any(eh_municipio(v) for v in obj.values()) or any(eh_municipio(k) for k in obj)
    if isinstance(obj, list):
        return any(eh_municipio(v) for v in obj)
    return False


def varrer(obj, trilha, arq, sob_municipio, chave=None):
    sob = sob_municipio or tem_municipio(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            varrer(v, f"{trilha}/{k}", arq, sob, k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            varrer(v, f"{trilha}[{i}]", arq, sob, chave)
    elif isinstance(obj, int) and not isinstance(obj, bool) and 1 <= obj < 5 and sob:
        if chave and NAO_CONTAGEM.match(str(chave)):
            ignorados[chave] = ignorados.get(chave, 0) + 1
        else:
            problemas.append((arq, trilha, chave, obj))


arquivos = sorted(args.resultados.iterdir())
print("resultados:", len(arquivos), "arquivos; extensões:", sorted({p.suffix for p in arquivos}))
for p in arquivos:
    if p.suffix != ".json":
        problemas.append((p.name, "", "extensão", p.suffix))
        continue
    varrer(json.loads(p.read_text(encoding="utf-8")), "", p.name, False)
print("valores de 1 a 4 ignorados por não serem contagem de pessoas:", ignorados)

varridos = 0
pasta_texto = args.texto or args.resultados
for p in sorted(pasta_texto.rglob("*")):
    if not p.is_file() or p.suffix not in SUFIXOS_TEXTO or p.resolve() == Path(__file__).resolve():
        continue
    varridos += 1
    for n, linha in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        # Endereço web não é caminho da máquina: "https://wiki-sagi.mds.gov.br/home/..." tem /home/.
        if CAMINHO.search(URL.sub("", linha)):
            problemas.append((str(p.relative_to(pasta_texto)), n, "caminho", linha.strip()[:80]))
print("arquivos de texto varridos em busca de caminhos:", varridos, "| termos locais recebidos:", len(args.termo_local))
print("problemas:", len(problemas))
for x in problemas[:30]:
    print(" ", ascii(x)[:200])
sys.exit(1 if problemas else 0)
