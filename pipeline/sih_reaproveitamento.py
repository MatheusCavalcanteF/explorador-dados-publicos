"""Anos fechados do SIH lidos da versão no ar, em vez de recalculados das fontes a cada execução.

Decidido em 11/11/2026. A superfície publicada registra com que regras foi calculada (sih_superficie.CALCULO):
o SHA-256 das regras do SIH no catálogo e o número do algoritmo de supressão no código
(supressao.ALGORITMO_DE_SUPRESSAO). Se os dois baterem com os desta execução, o ano que já estava fechado na
versão no ar, e continua fechado, é copiado dela como está: sem baixar as competências dele, sem supressão e
sem ataque conjunto. Fechado, ele não muda mais, e a versão no ar já passou em todos os testes com as mesmas
regras. Se algum dos dois mudar, nenhum ano é reaproveitado: todos são recalculados das fontes, com a herança
do padrão da versão no ar, e o ataque conjunto decide o que pode ir ao ar.

Mesmo com as regras iguais, o ano é recalculado quando o FTP regravou algum arquivo dele depois da versão no
ar (o ataque conjunto confere que o fechado não mudou), quando o que a página mostra dele mudaria, e quando a
execução tem só parte das UFs. Antes de copiar um ano, a versão no ar é conferida: um ano que ela diz fechado
não pode ter célula preliminar ou arredondada, nem contagem visível de 1 a k-1, e tem de fechar com as
próprias somas sem revelar nada. Se não passar, a execução para antes da coleta, com o motivo.
"""
from __future__ import annotations

import hashlib
import json

from . import sih_coleta, sih_janela, sih_superficie, supressao
from .sih_superficie import ErroDeSuperficie


def regras_sha256(catalogo: dict) -> str:
    """SHA-256 de tudo o que o pipeline do SIH lê do catálogo: a base, as dimensões e os cruzamentos dela, as
    margens publicadas e as referências. Qualquer mudança conta, inclusive de texto: recalcular é sempre seguro."""
    dimensoes = {d: v for d, v in catalogo["dimensoes"].items() if v.get("base") == "sih"}
    regras = {"base": catalogo["bases"]["sih"], "dimensoes": dimensoes,
              # A ordem dos cruzamentos conta: a mãe vem antes das filhas, e a supressão segue essa ordem.
              "cruzamentos": [c for c in catalogo["cruzamentos"] if set(c["dimensoes"]) <= set(dimensoes)],
              "margens_publicadas": catalogo.get("margens_publicadas"), "referencias": catalogo.get("referencias")}
    texto = json.dumps(regras, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def calculo(catalogo: dict) -> dict:
    """O que a superfície desta execução registra sobre o próprio cálculo."""
    return {"regras_sha256": regras_sha256(catalogo), "algoritmo_de_supressao": supressao.ALGORITMO_DE_SUPRESSAO}


def _fechado_na_versao(meta: dict, ano: int, onde: str) -> bool:
    """Se o ano já estava fechado quando a versão no ar foi calculada. A situação diz isso de dois jeitos, pelo
    último mês fechado e pela lista de meses preliminares, e os dois têm de concordar."""
    ultimo = meta.get("ultimo_mes_fechado")
    if not isinstance(ultimo, int) or not isinstance(meta.get("preliminares"), list):
        raise ErroDeSuperficie(f"{onde}: a situação do ano não diz até que mês estava fechado")
    fechado = ultimo >= ano * 100 + 12
    if fechado == bool(meta["preliminares"]):
        raise ErroDeSuperficie(f"{onde}: a situação do ano se contradiz: fechado até {ultimo}, com os meses "
                               f"preliminares {meta['preliminares'][:3]}")
    return fechado


def _regravados(listagem: dict, jan: sih_janela.Janela, ano: int, desde) -> list[str]:
    """Arquivos com altas do ano que o FTP regravou depois da versão dos arquivos de quando o ano foi calculado."""
    nomes = [sih_coleta.nome_do_arquivo(uf, c) for uf in sih_janela.UFS for c in jan.competencias_do_ano(ano)]
    return sorted(n for n in nomes if n not in listagem or not isinstance(desde, str)
                  or listagem[n]["modificado_no_ftp"] > desde)


def conferir_ano(no_ar: sih_superficie.Superficie, ano: int, catalogo: dict) -> None:
    """Confere um ano fechado da versão no ar antes de copiá-lo. Para com ErroDeSuperficie se ele não puder ser
    o que um pipeline com estas regras publicou: célula preliminar ou arredondada, contagem visível de 1 a k-1,
    soma que não fecha, ou contagem de 1 a k-1 dedutível só com o que o próprio ano mostra."""
    from . import sih_versoes
    k = int(catalogo["bases"]["sih"]["supressao"]["k"])
    meta, onde = no_ar.anos[ano], f"Versão no ar do SIH, {ano}"
    tabelas = {cid: no_ar.tabelas[ano, cid] for cid in meta["superficie"]}
    for cid, medidas in meta["superficie"].items():
        df = tabelas[cid].to_pandas()
        if df["preliminar"].any():
            raise ErroDeSuperficie(f"{onde}: {cid} tem célula preliminar num ano fechado")
        for medida in medidas:
            valor, oculto, arredondado = sih_superficie.COLUNAS[medida]
            if df[arredondado].any():
                raise ErroDeSuperficie(f"{onde}: {cid} tem {medida} arredondada num ano fechado")
            visivel = df.loc[~df[oculto], valor]
            pequenas = int(((visivel >= 1) & (visivel < k)).sum())
            if pequenas:
                raise ErroDeSuperficie(f"{onde}: {cid} mostra {pequenas} contagem(ns) de {medida} de 1 a {k - 1}")
    for medida in sih_superficie.COLUNAS:
        p = sih_versoes.montar_versoes([("no ar", (meta, tabelas))], None, catalogo, ano, k, medida)
        try:
            r = sih_versoes.por_intervalos(p)
        except sih_versoes.ErroDeVersoes as erro:
            raise ErroDeSuperficie(f"{onde}: o ano não fecha com as próprias somas. {erro}") from None
        if r.total:
            raise ErroDeSuperficie(f"{onde}: {r.total} contagem(ns) de {medida} de 1 a {k - 1} dedutíveis só com o "
                                   "que o ano mostra")


def planejar(no_ar: sih_superficie.Superficie | None, catalogo: dict, jan: sih_janela.Janela, anos: list[int],
             listagem: dict, todas_as_ufs: bool = True, ativo: bool = True) -> dict:
    """Quais anos desta execução são copiados da versão no ar, e por que os outros não são.

    Devolve `calculo` (o desta execução), `calculo_no_ar`, `valido` (se as regras e o algoritmo batem e a
    execução pode reaproveitar), `motivo` (por que não), `reaproveitados`, o motivo de cada ano em `anos` e os
    `avisos` para o log. Roda antes da coleta: os anos reaproveitados não têm competência baixada.
    """
    atual = calculo(catalogo)
    plano = {"calculo": atual, "calculo_no_ar": no_ar.calculo if no_ar else None, "valido": False, "motivo": None,
             "reaproveitados": [], "anos": {}, "avisos": []}
    if no_ar is None:
        plano["motivo"] = "nenhuma versão no ar"
    elif not ativo:
        plano["motivo"] = "reaproveitamento desligado nesta execução"
    elif not todas_as_ufs:
        plano["motivo"] = "execução com parte das UFs"
    elif no_ar.calculo is None:
        plano["motivo"] = "a versão no ar não registra as regras com que foi calculada"
    elif no_ar.calculo["regras_sha256"] != atual["regras_sha256"]:
        plano["motivo"] = "as regras do SIH no catálogo mudaram desde a versão no ar"
    elif no_ar.calculo["algoritmo_de_supressao"] != atual["algoritmo_de_supressao"]:
        plano["motivo"] = (f"o algoritmo de supressão mudou desde a versão no ar (de {no_ar.calculo['algoritmo_de_supressao']} "
                           f"para {atual['algoritmo_de_supressao']})")
    if plano["motivo"]:
        return plano
    plano["valido"] = True
    for ano in anos:
        meta, onde = no_ar.anos.get(ano), f"Versão no ar do SIH, {ano}"
        if meta is None:
            motivo = "a versão no ar não tem o ano"
        elif not jan.ano_fechado(ano):
            motivo = "ano aberto"
        elif not _fechado_na_versao(meta, ano, onde):
            motivo = "fechou depois da versão no ar"
        elif regravados := _regravados(listagem, jan, ano, meta.get("versao_dos_arquivos")):
            motivo = (f"o FTP regravou {len(regravados)} arquivo(s) do ano depois da versão no ar, de "
                      f"{meta.get('versao_dos_arquivos')} (por exemplo, {regravados[0]})")
            plano["avisos"].append(f"SIH {ano}, fechado: {motivo}; o ano é recalculado, e o ataque conjunto confere "
                                   "que o período fechado não mudou")
        else:
            mantido = sih_superficie.detalhe_mantido(catalogo, ano, anos, no_ar)
            mostra = {c: m for c, m in sih_superficie.cruzamentos_do_ano(catalogo, ano, anos, mantido).items()
                      if c in meta["publicados"]}
            if mostra != meta["superficie"] or mantido != meta.get("detalhe_mantido", []):
                motivo = "o que a página mostra do ano mudaria"
            else:
                conferir_ano(no_ar, ano, catalogo)
                motivo = None
        if motivo is None:
            plano["reaproveitados"].append(ano)
            motivo = "fechado na versão no ar e nesta: copiado dela"
        plano["anos"][str(ano)] = motivo
    return plano
