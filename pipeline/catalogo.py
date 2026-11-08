"""Leitura e validação do catálogo. Um catálogo inconsistente para o pipeline antes de qualquer coleta."""
from __future__ import annotations

from pathlib import Path

import yaml

CAMINHO = Path(__file__).resolve().parent.parent / "catalogo" / "catalogo.yaml"
TIPOS_DE_ACESSO = {"exato", "tabela", "arquivo", "receita"}
LICENCA_NAO_DECLARADA = "nao-declarada-na-origem"


class ErroDeCatalogo(ValueError):
    """O catálogo contradiz as próprias regras."""


def carregar(caminho: Path = CAMINHO) -> dict:
    catalogo = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    validar(catalogo)
    return catalogo


def validar(catalogo: dict) -> None:
    if not isinstance(catalogo, dict) or catalogo.get("versao") != 1:
        raise ErroDeCatalogo("Catálogo sem versão 1")
    temas = catalogo.get("temas") or {}
    bases = catalogo.get("bases") or {}
    metricas = catalogo.get("metricas") or {}
    if not temas or not metricas:
        raise ErroDeCatalogo("Catálogo sem temas ou sem métricas")
    limites = catalogo.get("limites") or {}
    for chave in ("pagina_html_kb", "arquivo_mib"):
        valor = limites.get(chave)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
            raise ErroDeCatalogo(f"limites.{chave} deve ser um número positivo")
    for nome, base in bases.items():
        origem = str((base.get("coleta") or {}).get("origem", ""))
        if not base.get("nome") or not base.get("orgao") or not origem.startswith(("https://", "http://", "ftp://")):
            raise ErroDeCatalogo(f"Base {nome}: sem nome, órgão ou coleta.origem")
        # A licença vai para o JSON-LD de cada página: sem ela, ou declarada sem endereço, não publica.
        licenca = base.get("licenca") or {}
        if not licenca.get("id") or not licenca.get("atribuicao"):
            raise ErroDeCatalogo(f"Base {nome}: licenca precisa de id e atribuicao")
        if licenca["id"] != LICENCA_NAO_DECLARADA and not str(licenca.get("url", "")).startswith("https://"):
            raise ErroDeCatalogo(f"Base {nome}: licença {licenca['id']} declarada precisa do endereço em licenca.url")
        revisao = base.get("revisao")
        if revisao is not None:
            if "municipio" in revisao:
                _validar_trava(nome, revisao)
            elif not isinstance(revisao.get("aviso_variacao_pct"), (int, float)):
                raise ErroDeCatalogo(f"Base {nome}: revisao.aviso_variacao_pct deve ser um número")
        supressao = base.get("supressao") or {}
        if supressao.get("aplica") and (not isinstance(supressao.get("k"), int) or supressao["k"] < 2):
            raise ErroDeCatalogo(f"Base {nome}: supressao.k deve ser um inteiro de 2 para cima")
        if "margens_complementar" in supressao and supressao["margens_complementar"] not in ("conhecidas", "todas"):
            raise ErroDeCatalogo(f"Base {nome}: supressao.margens_complementar deve ser conhecidas ou todas")
        if "motivo_por_celula" in supressao and not isinstance(supressao["motivo_por_celula"], bool):
            raise ErroDeCatalogo(f"Base {nome}: supressao.motivo_por_celula deve ser true ou false")
        criterio = supressao.get("criterio_publicacao")
        if criterio is not None and not all(_numero(criterio.get(c)) and criterio[c] <= 100 for c in
                                            ("internacoes_ocultas_pct_max", "celulas_ocultas_pct_max")):
            raise ErroDeCatalogo(f"Base {nome}: criterio_publicacao precisa dos dois percentuais, de 0 a 100")
        preliminares = base.get("preliminares")
        if preliminares is not None:
            multiplo = preliminares.get("arredondar_multiplo")
            if isinstance(multiplo, bool) or not isinstance(multiplo, int) or multiplo < 2:
                raise ErroDeCatalogo(f"Base {nome}: preliminares.arredondar_multiplo deve ser um inteiro de 2 para cima")
            if not set(preliminares.get("contagens") or []) <= {"internacoes", "obitos"}:
                raise ErroDeCatalogo(f"Base {nome}: preliminares.contagens só aceita internacoes e obitos")
        versoes = base.get("versoes")
        if versoes is not None and (set(versoes) - {"herdar_padrao_fechado", "ataque_conjunto_obrigatorio",
                                                    "situacao_fixa_no_ano_aberto"}
                                    or not all(isinstance(v, bool) for v in versoes.values())):
            raise ErroDeCatalogo(f"Base {nome}: versoes só aceita as três regras, como true ou false")
    for nome, metrica in metricas.items():
        onde = f"Métrica {nome}"
        if metrica.get("tema") not in temas:
            raise ErroDeCatalogo(f"{onde}: tema {metrica.get('tema')!r} fora da lista fixa")
        etiquetas = metrica.get("etiquetas")
        if not isinstance(etiquetas, list) or not set(etiquetas) <= set(temas):
            raise ErroDeCatalogo(f"{onde}: etiquetas ausentes ou fora da lista fixa")
        if metrica["tema"] in etiquetas:
            raise ErroDeCatalogo(f"{onde}: o tema principal não pode repetir nas etiquetas")
        if "formula" in metrica:
            # Calculada: cada parcela é outra métrica do catálogo, com a própria fonte.
            parcelas = metrica.get("fontes") or []
            if not parcelas or any(p not in metricas or p == nome for p in parcelas):
                raise ErroDeCatalogo(f"{onde}: métrica calculada precisa listar as métricas de que depende")
            continue
        if metrica.get("base") not in bases:
            raise ErroDeCatalogo(f"{onde}: base {metrica.get('base')!r} não existe")
        fonte = metrica.get("fonte") or {}
        acesso = fonte.get("acesso") or {}
        if acesso.get("tipo") not in TIPOS_DE_ACESSO:
            raise ErroDeCatalogo(f"{onde}: acesso.tipo deve ser um de {sorted(TIPOS_DE_ACESSO)}")
        if not str(acesso.get("url", "")).startswith("https://") and not str(acesso.get("url", "")).startswith("http://"):
            raise ErroDeCatalogo(f"{onde}: acesso sem url")
        if acesso["tipo"] == "receita" and not acesso.get("receita"):
            raise ErroDeCatalogo(f"{onde}: acesso por receita precisa dos passos em 'receita'")
        if not fonte.get("orgao") or not fonte.get("pesquisa"):
            raise ErroDeCatalogo(f"{onde}: fonte sem órgão ou pesquisa")
        if not metrica.get("ressalvas"):
            raise ErroDeCatalogo(f"{onde}: toda métrica publicada diz suas ressalvas")
    if "cruzamentos" in catalogo:
        _validar_cruzamentos(catalogo)


TEMPOS = ("mes", "tri", "ano")


def _numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor > 0


def _validar_trava(nome: str, revisao: dict) -> None:
    municipio, publicacao = revisao.get("municipio") or {}, revisao.get("publicacao") or {}
    if not (_numero(municipio.get("queda_pct")) and _numero(municipio.get("minimo_internacoes"))
            and _numero(publicacao.get("queda_uf_competencia_pct"))):
        raise ErroDeCatalogo(f"Base {nome}: a trava de queda precisa de queda_pct, minimo_internacoes e "
                             "queda_uf_competencia_pct positivos")


def _validar_cruzamentos(catalogo: dict) -> None:
    """Cruzamentos, dimensões, margens e capítulos da CID: o que a supressão e o teste de dedução leem."""
    dimensoes = catalogo.get("dimensoes") or {}
    niveis = {n for d in dimensoes.values() for n in d.get("niveis") or []}
    for nome, d in dimensoes.items():
        if not d.get("niveis"):
            raise ErroDeCatalogo(f"Dimensão {nome}: sem niveis")
        if "codigos" in d:
            # Código da fonte para valor da dimensão; o que não estiver na lista vai para `outros`.
            valores = set(d.get("valores") or [])
            if not set(d["codigos"].values()) | {d.get("outros")} <= valores or d.get("outros") is None:
                raise ErroDeCatalogo(f"Dimensão {nome}: codigos e outros precisam apontar para valores da lista")
    vistos: dict[str, dict] = {}
    for c in catalogo["cruzamentos"]:
        onde = f"Cruzamento {c.get('id')}"
        if not c.get("id") or c["id"] in vistos:
            raise ErroDeCatalogo(f"{onde}: id ausente ou repetido")
        if c.get("tempo") not in TEMPOS:
            raise ErroDeCatalogo(f"{onde}: tempo deve ser um de {TEMPOS}")
        if not c.get("dimensoes") or any(d not in dimensoes for d in c["dimensoes"]):
            raise ErroDeCatalogo(f"{onde}: dimensão fora do catálogo")
        if any(m not in catalogo["metricas"] for m in c.get("metricas") or [None]):
            raise ErroDeCatalogo(f"{onde}: métrica fora do catálogo")
        for chave in ("mae", "herda_trimestre_de"):
            if chave in c and c[chave] not in vistos:
                raise ErroDeCatalogo(f"{onde}: {chave} {c[chave]!r} precisa vir antes na lista")
        if "mae" in c:
            mae = vistos[c["mae"]]
            if not set(mae["dimensoes"]) <= set(c["dimensoes"]) or TEMPOS.index(mae["tempo"]) < TEMPOS.index(c["tempo"]):
                raise ErroDeCatalogo(f"{onde}: a mãe {c['mae']} precisa ser uma soma desta tabela")
        if "herda_trimestre_de" in c:
            mensal = vistos[c["herda_trimestre_de"]]
            if c["tempo"] != "tri" or mensal["tempo"] != "mes" or mensal["dimensoes"][0] != c["dimensoes"][0]:
                raise ErroDeCatalogo(f"{onde}: herda_trimestre_de liga um trimestre a um mês do mesmo município")
        vistos[c["id"]] = c
    for metrica, margens in (catalogo.get("margens_publicadas") or {}).items():
        if metrica not in catalogo["metricas"]:
            raise ErroDeCatalogo(f"Margens de {metrica}: métrica fora do catálogo")
        for margem in margens:
            if any(col not in niveis and col not in TEMPOS for col in margem):
                raise ErroDeCatalogo(f"Margens de {metrica}: coluna fora das dimensões em {margem}")
    faixas = ((catalogo.get("referencias") or {}).get("cid10_capitulos") or {}).get("faixas") or []
    if catalogo["cruzamentos"] and not faixas:
        raise ErroDeCatalogo("referencias.cid10_capitulos sem faixas")
    # Na ordem das categorias, não dos capítulos: o XXII (U04 a U99) vem antes do XX (V01 a Y98).
    anterior = ""
    for numero, inicio, fim, _ in sorted(faixas, key=lambda f: f[1]):
        if not (len(inicio) == len(fim) == 3 and inicio <= fim and inicio > anterior):
            raise ErroDeCatalogo(f"Capítulo {numero} da CID-10: faixa {inicio}-{fim} inválida ou sobreposta")
        anterior = fim
