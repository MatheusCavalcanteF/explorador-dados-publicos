"""Partições publicáveis do SIH: a pasta de um ano, a situação gravada com ela e o pacote que vai para a Release.

Cada ano fica em `ano=AAAA/`, com um Parquet por cruzamento e UF, as margens publicadas e um
`situacao.json`: o que foi publicado, o que não foi e por quê, os testes e cada arquivo com tamanho e
SHA-256. Quem lê confere arquivo por arquivo com essa lista.

Só existe partição de ano que passou em todos os testes (nao_publicavel). O pacote de um ano é um .zip
sem compressão, e a leitura dele só extrai o que a situação lista. Este módulo não depende de
requirements-sih.txt: o Publicar o usa para baixar a versão no ar.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

from .contrato import ErroDeContrato

SITUACAO = "situacao.json"


class ErroDeParticao(ErroDeContrato):
    """As partições de um ano não batem com a situação gravada junto delas."""


def nao_publicavel(situacao: dict) -> str | None:
    """Por que as partições de um ano não podem ser publicadas, ou None quando podem.

    O teste de dedução tem de ter rodado e dado zero, em internações e em óbitos, e o ataque conjunto com
    a versão no ar, quando há versão no ar daquele ano, também.
    """
    deducao = situacao.get("deducao") or {}
    if not deducao.get("rodou"):
        return "o teste de dedução não rodou"
    if not deducao.get("passou"):
        return f"o teste de dedução revelou {deducao.get('pequenas_reveladas', 'alguma')} contagem(ns) de internações"
    if not deducao.get("obitos_passou"):
        return "o teste de dedução revelou contagens de óbitos"
    conjunto = deducao.get("conjunto") or {}
    if conjunto.get("rodou") and not conjunto.get("passou"):
        return f"o ataque conjunto com a versão no ar não passou: {conjunto.get('motivo', 'sem motivo registrado')}"
    if conjunto.get("obrigatorio") and not conjunto.get("rodou"):
        return f"o ataque conjunto com a versão no ar não rodou: {conjunto.get('motivo', 'sem motivo registrado')}"
    return None


def remover_ano(particoes: Path, ano: int) -> None:
    """Tira a pasta de um ano, e as sobras de uma troca interrompida."""
    for nome in (f"ano={ano}", f".ano={ano}.novo", f".ano={ano}.antigo"):
        if (particoes / nome).exists():
            shutil.rmtree(particoes / nome)


def gravar_ano(particoes: Path, ano: int, gravar, situacao: dict) -> dict:
    """Troca o conjunto inteiro de partições de um ano, de uma vez.

    `gravar(pasta)` escreve os arquivos do ano numa pasta nova e devolve o que gravar_particao devolve. A
    situação do ano (o que foi publicado, o que não foi e por quê) vai junto, com a lista de arquivos, e só
    então a pasta nova toma o lugar da antiga: um cruzamento que deixou de passar não deixa sobra, e quem
    lê nunca vê metade de uma versão e metade de outra. A troca são duas renomeações de pasta.

    Situação que não pode ser publicada não é gravada: para com erro antes de escrever qualquer arquivo.
    """
    motivo = nao_publicavel(situacao)
    if motivo:
        raise ErroDeParticao(f"Ano {ano}: {motivo}; nenhuma partição publicável é gravada")
    final = particoes / f"ano={ano}"
    novo, antigo = particoes / f".ano={ano}.novo", particoes / f".ano={ano}.antigo"
    for pasta in (novo, antigo):
        if pasta.exists():
            shutil.rmtree(pasta)
    novo.mkdir(parents=True)
    arquivos = gravar(novo)
    situacao = situacao | {"arquivos": {nome: {c: v for c, v in info.items() if c != "gzip"}
                                        for nome, info in sorted(arquivos.items())}}
    (novo / SITUACAO).write_text(json.dumps(situacao, ensure_ascii=False, indent=1), encoding="utf-8")
    if final.exists():
        final.rename(antigo)
    novo.rename(final)
    if antigo.exists():
        shutil.rmtree(antigo)
    return arquivos


def ler_situacao(particoes: Path, ano: int, conferir: bool = True) -> dict:
    """A situação de um ano e a conferência dos arquivos que ela lista: cada um tem de existir, com o mesmo
    tamanho e SHA-256. Arquivo ausente é erro; ausência de linha dentro de um arquivo (município sem
    hospital, mês sem internação) não é. Arquivo a mais, que a situação não lista, não é lido."""
    pasta = Path(particoes) / f"ano={ano}"
    caminho = pasta / SITUACAO
    if not caminho.exists():
        raise ErroDeParticao(f"{pasta}: sem situacao.json; não dá para saber o que foi publicado em {ano}")
    situacao = json.loads(caminho.read_text(encoding="utf-8"))
    if "arquivos" not in situacao:
        raise ErroDeParticao(f"{caminho}: sem a lista de arquivos do ano")
    for cid in situacao["publicados"]:
        if not any(nome.startswith(cid + "/") for nome in situacao["arquivos"]):
            raise ErroDeParticao(f"{caminho}: {cid} consta como publicado, mas nenhum arquivo dele está na lista")
    if conferir:
        for nome, info in situacao["arquivos"].items():
            arquivo = pasta / nome
            if not arquivo.exists():
                raise ErroDeParticao(f"{arquivo}: listado em situacao.json de {ano}, mas ausente")
            bruto = arquivo.read_bytes()
            if len(bruto) != info["bytes"] or hashlib.sha256(bruto).hexdigest() != info["sha256"]:
                raise ErroDeParticao(f"{arquivo}: diferente do que situacao.json de {ano} registra")
    return situacao


def ler_publicada(particoes: Path, ano: int) -> dict:
    """A situação de um ano que foi publicado: além de conferir os arquivos (ler_situacao), recusa a que não
    poderia ter ido ao ar, porque uma versão assim não serve de base para a seguinte."""
    situacao = ler_situacao(particoes, ano)
    motivo = nao_publicavel(situacao)
    if motivo:
        raise ErroDeParticao(f"{Path(particoes) / f'ano={ano}'}: consta como versão publicada, mas {motivo}")
    return situacao


def anos_na_pasta(particoes: Path) -> list[int]:
    return sorted(int(p.name[4:]) for p in Path(particoes).glob("ano=*") if p.is_dir())


def empacotar(particoes: Path, ano: int) -> bytes:
    """O .zip de um ano para a Release: a situação e os arquivos que ela lista, conferidos antes, em ordem
    fixa e sem data, para o mesmo ano dar sempre os mesmos bytes."""
    situacao = ler_publicada(particoes, ano)
    pasta = Path(particoes) / f"ano={ano}"
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_STORED) as z:
        for nome in [SITUACAO, *sorted(situacao["arquivos"])]:
            z.writestr(zipfile.ZipInfo(nome, date_time=(1980, 1, 1, 0, 0, 0)), (pasta / nome).read_bytes())
    return saida.getvalue()


def desempacotar(pacote: bytes, particoes: Path, ano: int) -> dict:
    """Abre o pacote de um ano em `particoes/ano=AAAA` e confere tudo com a situação que veio nele.

    O pacote vem de fora: só os nomes que a situação lista são extraídos, cada um tem de ficar dentro da
    pasta do ano, e nada além deles pode estar no .zip. Qualquer diferença para, sem deixar a pasta.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(pacote))
    except zipfile.BadZipFile as erro:
        raise ErroDeParticao(f"Pacote do SIH de {ano}: não é um .zip ({erro})") from None
    with z:
        nomes = z.namelist()
        if SITUACAO not in nomes:
            raise ErroDeParticao(f"Pacote do SIH de {ano}: sem situacao.json")
        try:
            situacao = json.loads(z.read(SITUACAO).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as erro:
            raise ErroDeParticao(f"Pacote do SIH de {ano}: situacao.json ilegível ({erro})") from None
        if not isinstance(situacao, dict) or situacao.get("ano") != ano or not isinstance(situacao.get("arquivos"), dict):
            raise ErroDeParticao(f"Pacote do SIH de {ano}: situacao.json é de outro ano ou não lista os arquivos")
        esperados = set(situacao["arquivos"]) | {SITUACAO}
        if set(nomes) != esperados or len(nomes) != len(esperados):
            raise ErroDeParticao(f"Pacote do SIH de {ano}: os arquivos do .zip não são os que a situação lista")
        remover_ano(particoes, ano)
        pasta = (Path(particoes) / f"ano={ano}").resolve()
        try:
            for nome in sorted(esperados):
                destino = (pasta / nome).resolve()
                if pasta not in destino.parents or "\\" in nome or nome.startswith("/"):
                    raise ErroDeParticao(f"Pacote do SIH de {ano}: caminho fora da pasta do ano ({nome!r})")
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(z.read(nome))
            return ler_publicada(particoes, ano)
        except Exception:
            remover_ano(particoes, ano)
            raise
