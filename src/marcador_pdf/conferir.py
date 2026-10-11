# -*- coding: utf-8 -*-
"""Confere se as marcações geradas se comportam como as feitas à mão no Acrobat.

Sem referência faz a checagem autônoma (campos obrigatórios, /NM únicos, pares agrupados,
geometria do caret). Com um PDF de referência compara campo a campo contra marcações
humanas, que é o teste mais forte: só ele pega diferenças de convenção que a especificação
não determina.
"""
import collections
import re

import pymupdf

OBRIGATORIOS = ["NM", "CreationDate", "M", "Subj", "Popup", "AP", "T"]
COMPARAR = ["Subj", "IT", "RT", "Name", "F", "C", "CA"]
_LARG, _ALT = 12.727, 10.0


def legivel(v):
    """Nomes de autor vêm codificados no PDF: octal Latin-1 ou hexadecimal UTF-16BE."""
    if not v:
        return v
    if v.startswith("<") and v.endswith(">"):
        return bytes.fromhex(v[1:-1]).decode("utf-16-be", "replace").lstrip("﻿")
    if v.startswith("(") and v.endswith(")"):
        v = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), v[1:-1])
        return re.sub(r"\\([()\\])", r"\1", v)
    return v


def campos(obj):
    r = {}
    for k in OBRIGATORIOS + COMPARAR + ["IRT", "RC", "Contents", "Rect", "RD"]:
        m = re.search(r"/" + k + r"\s*(\[[^\]]*\]|\((?:\\.|[^\\)])*\)|<[^>]*>|/\w+|\d+ 0 R|[\d.]+)", obj)
        r[k] = m.group(1) if m else None
    return r


def colher(doc, autor):
    """Lista (página, tipo, xref, campos) das anotações do autor (None = todos)."""
    saida = []
    for pg in doc:
        for a in pg.annots():
            if autor is None or a.info.get("title") == autor:
                saida.append((pg.number + 1, a.type[1], a.xref,
                              campos(doc.xref_object(a.xref, compressed=True))))
    return saida


def num(v):
    return [float(x) for x in re.findall(r"[-\d.]+", v or "")]


def autonoma(doc, marcas):
    problemas = []

    for pag, tipo, xref, c in marcas:
        for k in OBRIGATORIOS:
            if c[k] is None:
                problemas.append(f"pág {pag} {tipo}: falta /{k}")

    vistos = collections.Counter(c["NM"] for _, _, _, c in marcas if c["NM"])
    for nm, n in vistos.items():
        if n > 1:
            problemas.append(f"/NM repetido em {n} anotações: {nm} "
                             f"(quebra respostas e seleção no painel)")

    # todo StrikeOut com /IT /StrikeOutTextEdit precisa apontar para um Caret /Replace.
    # O caret pode ter outro autor (alguém editou o texto no Acrobat): o vínculo é estrutural,
    # então os carets são colhidos de TODOS os autores.
    caretes = {a.xref for pg in doc for a in pg.annots()
               if a.type[1] == "Caret" and doc.xref_get_key(a.xref, "IT")[1] == "/Replace"}
    for pag, tipo, xref, c in marcas:
        if c["IT"] == "/StrikeOutTextEdit":
            if c["RT"] != "/Group":
                problemas.append(f"pág {pag}: riscado de substituição sem /RT /Group")
            alvo = int(c["IRT"].split()[0]) if c["IRT"] else None
            if alvo not in caretes:
                problemas.append(f"pág {pag}: riscado de substituição sem /IRT para o caret "
                                 f"(vai aparecer como dois comentários separados)")
        if c["IT"] == "/Replace" and not c["Contents"]:
            problemas.append(f"pág {pag}: caret de substituição sem o texto novo em /Contents")

    for pag, tipo, xref, c in marcas:
        if tipo != "Caret":
            continue
        rect, rd = num(c["Rect"]), num(c["RD"])
        if not rd:
            problemas.append(f"pág {pag} Caret: falta /RD")
            continue
        s = rd[0]
        larg_esp, alt_esp = _LARG * s + 2 * s, _ALT * s + 2 * s
        larg, alt = rect[2] - rect[0], rect[3] - rect[1]
        if abs(larg - larg_esp) > .01 or abs(alt - alt_esp) > .01:
            problemas.append(f"pág {pag} Caret: geometria fora da forma do Acrobat: "
                             f"{larg:.3f}x{alt:.3f}, esperado {larg_esp:.3f}x{alt_esp:.3f} "
                             f"(s={s:.5f})")
    return problemas


def comparativa(marcas, ref):
    """Compara contra marcações humanas, emparelhando por (tipo, /Subj, /IT)."""
    mapa = {(t, c["Subj"], c["IT"]): c for _, t, _, c in ref}
    problemas, pares = [], 0
    for pag, tipo, xref, c in marcas:
        chave = (tipo, c["Subj"], c["IT"])
        if chave not in mapa:
            problemas.append(f"pág {pag} {tipo} Subj={c['Subj']} IT={c['IT']}: "
                             f"sem equivalente manual para comparar")
            continue
        pares += 1
        alvo = mapa[chave]
        for k in COMPARAR:
            a, b = alvo[k], c[k]
            if k in ("C", "CA"):
                igual = [round(x, 2) for x in num(a)] == [round(x, 2) for x in num(b)]
            else:
                igual = a == b
            if not igual:
                problemas.append(f"pág {pag} {tipo} /{k}: manual={a} gerado={b}")
        for k in ("NM", "CreationDate", "M", "Popup", "RC", "AP", "IRT", "Contents"):
            if (alvo[k] is not None) != (c[k] is not None):
                problemas.append(f"pág {pag} {tipo} /{k}: presença diverge do manual")
    return problemas, pares


def conferir(pdf, autor, referencia=None, autor_ref=None):
    """Devolve (resumo, problemas). `resumo` são linhas de texto para mostrar a quem conferiu."""
    doc = pymupdf.open(pdf)
    marcas = colher(doc, autor)
    if not marcas:
        raise ValueError(f"nenhuma marcação de {autor!r} em {pdf}")

    tipos = collections.Counter(t for _, t, _, _ in marcas)
    resumo = [f"{len(marcas)} marcações de {autor!r}: "
              + ", ".join(f"{n} {t}" for t, n in sorted(tipos.items()))]

    outros = collections.Counter(legivel(c["T"]) for _, _, _, c in colher(doc, None)
                                 if c["T"] and legivel(c["T"]) != autor)
    if outros:
        resumo.append("preservadas de outros autores: "
                      + ", ".join(f"{n} de {t}" for t, n in outros.items()))

    problemas = autonoma(doc, marcas)
    if referencia:
        ref = colher(pymupdf.open(referencia), autor_ref)
        if not ref:
            raise ValueError(f"nenhuma marcação de {autor_ref!r} em {referencia}")
        comp, pares = comparativa(marcas, ref)
        resumo.append(f"comparadas com {len(ref)} marcações manuais de {autor_ref!r}: {pares} pareadas")
        problemas += comp
    return resumo, problemas
