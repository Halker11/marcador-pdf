# -*- coding: utf-8 -*-
"""Linha de comando: marcar um PDF a partir de uma lista de correções em JSON, conferir e reparar."""
import argparse
import json
import sys

from .conferir import conferir
from .marcar import Marcador
from .reparar import reparar


def aplicar(m, item):
    """Aplica uma correção da lista. No JSON, `pagina` é o número da página no PDF (base 1)."""
    pagina = item["pagina"] - 1
    if not 0 <= pagina < len(m.doc):
        raise LookupError("pág. %d: o PDF só tem %d páginas" % (item["pagina"], len(m.doc)))
    acao = item["acao"]
    if acao == "riscar":
        m.riscar(pagina, item["trecho"])
    elif acao == "substituir":
        m.substituir(pagina, item["trecho"], item["novo"])
    elif acao == "inserir":
        m.inserir(pagina, item["trecho"], item["texto"], antes=item.get("antes", False))
    elif acao == "comentar":
        if "trecho" in item:
            m.comentar(pagina, item["trecho"], item["texto"])
        else:
            m.comentar_em_ponto(pagina, item["texto"], item["x"], item["y"])
    elif acao == "excluir_pagina":
        m.excluir_pagina(pagina)
        if item.get("texto"):
            m.comentar_em_ponto(pagina, item["texto"], 40, 40)
    else:
        raise ValueError("ação desconhecida: %r" % acao)


def _marcar(a):
    with open(a.correcoes, encoding="utf-8") as f:
        correcoes = json.load(f)
    m = Marcador(a.pdf, a.autor, data=a.data)
    falhas = []
    for i, item in enumerate(correcoes, 1):
        try:
            aplicar(m, item)
        except (LookupError, KeyError, ValueError) as e:
            falhas.append("item %d: %s" % (i, e.args[0] if isinstance(e, LookupError) else repr(e)))
    n = m.salvar(a.saida)
    print("%d marcações gravadas em %s" % (n, a.saida))
    if falhas:
        print("%d correções NÃO aplicadas:" % len(falhas))
        for x in falhas:
            print("  -", x)
        return 1
    return 0


def _conferir(a):
    if a.referencia and not a.autor_ref:
        sys.exit("--referencia exige --autor-ref")
    try:
        resumo, problemas = conferir(a.pdf, a.autor, a.referencia, a.autor_ref)
    except ValueError as e:
        sys.exit(str(e))
    print("\n".join(resumo))
    print()
    if problemas:
        print("%d divergências:" % len(problemas))
        for x in problemas:
            print("  -", x)
        return 1
    print("nenhuma divergência estrutural.")
    print("falta conferir a olho: aparência do traço e acerto editorial de cada marcação.")
    return 0


def _reparar(a):
    comp, refeitas, depois, visiveis = reparar(a.entrada, a.saida)
    print("arrays compartilhados antes:", comp or "nenhum")
    print("arrays refeitos (refs por página):", refeitas)
    print("arrays compartilhados depois:", depois or "nenhum")
    print("anotações visíveis por página:", visiveis)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="marcador-pdf", description=__doc__)
    sub = p.add_subparsers(dest="comando", required=True)

    s = sub.add_parser("marcar", help="aplica uma lista de correções (JSON) num PDF")
    s.add_argument("pdf")
    s.add_argument("correcoes", help="arquivo JSON com a lista de correções")
    s.add_argument("-o", "--saida", required=True)
    s.add_argument("--autor", required=True, help="nome que aparece no painel de Comentários")
    s.add_argument("--data", help="data fixa das marcações, AAAAMMDD (padrão: hoje)")
    s.set_defaults(func=_marcar)

    s = sub.add_parser("conferir", help="confere a estrutura das marcações de um autor")
    s.add_argument("pdf")
    s.add_argument("--autor", required=True)
    s.add_argument("--referencia", help="PDF com marcações feitas à mão no Acrobat")
    s.add_argument("--autor-ref", help="autor das marcações manuais no PDF de referência")
    s.set_defaults(func=_conferir)

    s = sub.add_parser("reparar", help="desfaz arrays /Annots compartilhados entre páginas")
    s.add_argument("entrada")
    s.add_argument("saida")
    s.set_defaults(func=_reparar)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
