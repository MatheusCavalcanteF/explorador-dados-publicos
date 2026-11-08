"""Quais competências do SIH baixar, quais meses já fecharam e quais anos ainda mudam.

O FTP republica as últimas 12 competências de uma vez, e uma competência traz altas de até 5 meses
antes dela. Por isso o mês da alta M só fecha quando todas as competências que podem conter altas
dele saíram da janela: M + defasagem <= última competência - janela. O ano vira partição fechada
quando dezembro fecha. As regras vêm do catálogo (bases.sih.tempo).

Competência e mês são inteiros no formato AAAAMM (202608). A conta é feita em meses corridos.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import dtb

UFS = tuple(sorted(sigla for sigla, _ in dtb.UFS.values()))


def para_meses(aaaamm: int) -> int:
    ano, mes = divmod(aaaamm, 100)
    if not 1 <= mes <= 12:
        raise ValueError(f"Mês inválido em {aaaamm}")
    return ano * 12 + mes - 1


def de_meses(n: int) -> int:
    ano, mes = divmod(n, 12)
    return ano * 100 + mes + 1


def somar(aaaamm: int, meses: int) -> int:
    return de_meses(para_meses(aaaamm) + meses)


def intervalo(de: int, ate: int) -> list[int]:
    return [de_meses(n) for n in range(para_meses(de), para_meses(ate) + 1)]


def de_nome(aamm: str) -> int:
    """Competência do nome do arquivo (RDSP2608.dbc traz "2608"). A série em .dbc começa em 2008."""
    if len(aamm) != 4 or not aamm.isdigit():
        raise ValueError(f"Competência {aamm!r} fora do formato AAMM")
    return 200000 + int(aamm)


@dataclass(frozen=True)
class Janela:
    """O estado do FTP numa execução, e o que ele implica para cada ano."""
    ultima_no_ftp: int          # a competência mais recente, em qualquer UF
    ultima_completa: int        # a mais recente com as 27 UFs; as posteriores esperam
    janela_meses: int
    defasagem_meses: int
    inicio: int                 # primeiro ano publicado

    @property
    def ultima_congelada(self) -> int:
        """Competências até aqui já saíram da janela republicada e não mudam mais."""
        return somar(self.ultima_no_ftp, -self.janela_meses)

    @property
    def ultimo_mes_fechado(self) -> int:
        return somar(self.ultima_congelada, -self.defasagem_meses)

    def mes_fechado(self, mes: int) -> bool:
        return mes <= self.ultimo_mes_fechado

    def ano_fechado(self, ano: int) -> bool:
        return self.mes_fechado(ano * 100 + 12)

    @property
    def ultimo_mes(self) -> int:
        """Último mês da alta que aparece: o da competência mais recente usada."""
        return self.ultima_completa

    def anos(self) -> list[int]:
        return list(range(self.inicio, self.ultimo_mes // 100 + 1))

    def anos_abertos(self) -> list[int]:
        return [a for a in self.anos() if not self.ano_fechado(a)]

    def competencias_do_ano(self, ano: int) -> list[int]:
        """Altas do ano aparecem da competência de janeiro até a de dezembro mais a defasagem."""
        fim = min(somar(ano * 100 + 12, self.defasagem_meses), self.ultima_completa)
        return intervalo(ano * 100 + 1, fim)

    def meses_preliminares(self, ano: int) -> list[int]:
        return [m for m in intervalo(ano * 100 + 1, min(ano * 100 + 12, self.ultimo_mes)) if not self.mes_fechado(m)]


def janela(competencias_por_uf: dict[str, set[int]], tempo: dict, inicio: int) -> Janela:
    """Monta a janela a partir do que o FTP lista. Falta de uma UF numa competência antiga é falha estrutural.

    A competência mais recente costuma sair aos poucos: AC e RR ainda não tinham 2608 em 07/11/2026.
    Ela fica de fora até as 27 UFs chegarem, porque a visão de residência depende de todas.
    """
    faltam = sorted(set(UFS) - set(competencias_por_uf))
    if faltam:
        raise ValueError(f"SIH: nenhum arquivo das UFs {faltam} no FTP")
    ultima = max(max(c) for c in competencias_por_uf.values())
    completas = set.intersection(*(set(c) for c in competencias_por_uf.values()))
    ultima_completa = max(c for c in completas if c <= ultima)
    jan = Janela(ultima, ultima_completa, int(tempo["janela_republicada_meses"]), int(tempo["defasagem_maxima_meses"]), inicio)
    necessarias = intervalo(inicio * 100 + 1, ultima_completa)
    buracos = {uf: [c for c in necessarias if c not in cs] for uf, cs in competencias_por_uf.items()}
    buracos = {uf: cs for uf, cs in buracos.items() if cs}
    if buracos:
        raise ValueError(f"SIH: competências ausentes no FTP antes da última completa ({ultima_completa}): {buracos}")
    return jan
