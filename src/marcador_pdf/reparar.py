# -*- coding: utf-8 -*-
"""Desfaz arrays /Annots compartilhados entre páginas.

Sintoma: uma marcação feita numa página aparece em dezenas de outras. Causa: salvar com
garbage>=3 (PyMuPDF) funde objetos idênticos, e arrays /Annots vazios são idênticos.
Depois disso, qualquer anotação que o Acrobat acrescente numa dessas páginas vai parar
no array único, e todas as páginas "ganham" a marcação.

As anotações em si continuam corretas (cada uma sabe sua página pelo /P). Este módulo
reconstrói um array por página só com o que pertence a ela.
"""
import collections
import re

import pymupdf


def _dono(doc, xref, xref_pag):
    o = doc.xref_object(xref, compressed=True)
    if re.search(r"/Subtype\s*/Popup", o):
        m = re.search(r"/Parent\s+(\d+)\s+0\s+R", o)
        return _dono(doc, int(m.group(1)), xref_pag) if m else None
    m = re.search(r"/P\s+(\d+)\s+0\s+R", o)
    return xref_pag.get(int(m.group(1))) if m else None


def diagnosticar(doc):
    """Devolve {xref do array: nº de páginas} para os arrays /Annots usados por mais de uma página."""
    arr = collections.Counter()
    for p in doc:
        m = re.search(r"/Annots\s+(\d+)\s+0\s+R", doc.xref_object(p.xref, compressed=True))
        if m:
            arr[m.group(1)] += 1
    return {k: v for k, v in arr.items() if v > 1}


def reparar(entrada, saida):
    """Devolve (compartilhados antes, refs refeitas por página, compartilhados depois, anotações por página)."""
    doc = pymupdf.open(entrada)
    comp = diagnosticar(doc)
    xref_pag = {p.xref: p.number for p in doc}
    refeitas = {}
    for p in doc:
        o = doc.xref_object(p.xref, compressed=True)
        m = re.search(r"/Annots\s+(\d+)\s+0\s+R", o)
        if not m:
            continue
        refs = [int(x) for x in re.findall(r"(\d+)\s+0\s+R",
                                           doc.xref_object(int(m.group(1)), compressed=True))]
        meus = [x for x in refs if _dono(doc, x, xref_pag) == p.number]
        if meus:
            doc.xref_set_key(p.xref, "Annots", "[" + " ".join("%d 0 R" % x for x in meus) + "]")
            refeitas[p.number + 1] = len(meus)
        else:
            doc.xref_set_key(p.xref, "Annots", "null")
    doc.save(saida, garbage=1, deflate=True)       # garbage=1: nunca 3 ou 4
    v = pymupdf.open(saida)
    return comp, refeitas, diagnosticar(v), {p.number + 1: len(list(p.annots()))
                                             for p in v if list(p.annots())}
