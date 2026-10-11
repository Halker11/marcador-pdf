# -*- coding: utf-8 -*-
"""Gera a prova fictícia usada no exemplo: duas páginas de um livro didático inventado,
com erros plantados de propósito para a lista de correções ter o que marcar.

Uso:  python exemplos/gerar_exemplo.py
Grava exemplos/prova.pdf, exemplos/prova_marcada.pdf e exemplos/prova_marcada.png.
"""
import json
import pathlib

import pymupdf

from marcador_pdf import Marcador
from marcador_pdf.cli import aplicar

AQUI = pathlib.Path(__file__).parent
AUTOR = "Revisão (exemplo)"

PAGINA_1 = [
    "A água do planeta está sempre em movimento. Com o calor do Sol, a agua dos rios, "
    "lagos e oceanos evapora e sobe para a atmosfera na forma de vapor.",
    "Ao nível do mar, a água pura ferve a 90 °C, mas ela evapora em qualquer temperatura. "
    "Nas camadas mais altas e frias da atmosfera, o vapor se condensa e forma as nuvens.",
    "Quando as gotas ficam pesadas, elas caem na forma de chuva, neve ou granizo. "
    "Esse caminho foi descoberto no ano passado. Parte dessa água escorre para os rios "
    "e parte se infiltra no solo, abastecendo os subterrâneos.",
]
ATIVIDADES = [
    "1. Explique com suas palavras o que é evaporação.",
    "2. Por que as nuvens se formam nas camadas mais altas da atmosfera?",
]


def _texto(pg, y, texto, corpo=11, fonte="helv", altura=60):
    pg.insert_textbox(pymupdf.Rect(60, y, 535, y + altura), texto, fontsize=corpo, fontname=fonte, lineheight=1.35)


def gerar_prova(destino):
    doc = pymupdf.open()

    pg = doc.new_page()                              # A4
    _texto(pg, 50, "CIÊNCIAS  |  6º ano", corpo=8, altura=14)
    _texto(pg, 80, "Capítulo 3: O ciclo da água", corpo=20, fonte="hebo", altura=40)
    y = 130
    for p in PAGINA_1:
        _texto(pg, y, p)
        y += 62
    figura = pymupdf.Rect(60, y + 8, 535, y + 168)
    pg.draw_rect(figura, color=(.6, .6, .6), fill=(.92, .92, .92))
    pg.insert_textbox(pymupdf.Rect(60, y + 78, 535, y + 98), "[ilustração]", fontsize=10,
                      fontname="heit", align=pymupdf.TEXT_ALIGN_CENTER, color=(.45, .45, .45))
    _texto(pg, y + 174, "Figura 1: Etapas do ciclo da água.", corpo=9, fonte="heit", altura=16)
    _texto(pg, y + 210, "Atividades", corpo=14, fonte="hebo", altura=30)
    y += 240
    for q in ATIVIDADES:
        _texto(pg, y, q, altura=20)
        y += 26
    _texto(pg, 790, "42", corpo=9, altura=14)

    pg = doc.new_page()
    _texto(pg, 50, "CIÊNCIAS  |  6º ano", corpo=8, altura=14)
    _texto(pg, 80, "Atividades complementares", corpo=14, fonte="hebo", altura=30)
    _texto(pg, 115, "1. Explique com suas palavras o que é evaporação.", altura=20)
    _texto(pg, 141, "2. Desenhe o caminho da água desde o oceano até a chuva.", altura=20)
    _texto(pg, 790, "43", corpo=9, altura=14)

    doc.save(destino, garbage=1, deflate=True)


def main():
    prova, marcada = AQUI / "prova.pdf", AQUI / "prova_marcada.pdf"
    gerar_prova(prova)

    m = Marcador(prova, AUTOR)
    for item in json.loads((AQUI / "correcoes.json").read_text(encoding="utf-8")):
        aplicar(m, item)
    print(m.salvar(marcada), "marcações em", marcada.name)

    # prévia para o README (desenhada pelo MuPDF; no Acrobat a aparência vem do mesmo /AP)
    pymupdf.open(marcada)[0].get_pixmap(dpi=110).save(AQUI / "prova_marcada.png")


if __name__ == "__main__":
    main()
