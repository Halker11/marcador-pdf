# -*- coding: utf-8 -*-
import importlib.util
import json
import pathlib

import pymupdf
import pytest

from marcador_pdf import Marcador, conferir
from marcador_pdf.cli import main
from marcador_pdf.reparar import diagnosticar, reparar

EXEMPLOS = pathlib.Path(__file__).parent.parent / "exemplos"
AUTOR = "Revisão de teste"


@pytest.fixture
def prova(tmp_path):
    spec = importlib.util.spec_from_file_location("gerar_exemplo", EXEMPLOS / "gerar_exemplo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    destino = tmp_path / "prova.pdf"
    mod.gerar_prova(destino)
    return destino


def _anotacoes(pdf, pagina=0):
    doc = pymupdf.open(pdf)
    return doc, [(a.type[1], a.xref) for a in doc[pagina].annots()]


def test_substituir_grava_caret_e_riscado_agrupados(prova, tmp_path):
    m = Marcador(prova, AUTOR)
    xc = m.substituir(0, "90 °C", "100 °C")
    saida = tmp_path / "s.pdf"
    assert m.salvar(saida) == 2

    doc, anots = _anotacoes(saida)
    assert sorted(t for t, _ in anots) == ["Caret", "StrikeOut"]
    risco = next(x for t, x in anots if t == "StrikeOut")
    assert doc.xref_get_key(xc, "IT")[1] == "/Replace"
    assert doc.xref_get_key(risco, "IT")[1] == "/StrikeOutTextEdit"
    assert doc.xref_get_key(risco, "RT")[1] == "/Group"
    assert doc.xref_get_key(risco, "IRT")[1] == "%d 0 R" % xc
    assert doc[0].load_annot(xc).info["content"] == "100 °C"


def test_rotulos_saem_em_latin1_octal(prova, tmp_path):
    m = Marcador(prova, AUTOR)
    x = m.comentar(0, "Figura 1", "Trocar a ilustração.")
    saida = tmp_path / "s.pdf"
    m.salvar(saida)
    obj = pymupdf.open(saida).xref_object(x, compressed=True)
    assert "(Coment\\341rio do texto)" in obj
    assert "(Revis\\343o de teste)" in obj


def test_trecho_inexistente_ou_repetido_nao_marca(prova):
    m = Marcador(prova, AUTOR)
    with pytest.raises(LookupError, match="não encontrei"):
        m.riscar(0, "trecho que não existe na página")
    with pytest.raises(LookupError, match="mais de uma vez"):
        m.riscar(0, "atmosfera")
    assert m.n == 0


def test_risco_de_trecho_em_duas_linhas_tem_uma_faixa_por_linha(prova, tmp_path):
    m = Marcador(prova, AUTOR)
    x = m.riscar(0, "Esse caminho foi descoberto no ano passado.")
    saida = tmp_path / "s.pdf"
    m.salvar(saida)
    assert len(pymupdf.open(saida)[0].load_annot(x).vertices) // 4 == 2


def test_excluir_pagina_grava_duas_linhas_sem_bs(prova, tmp_path):
    m = Marcador(prova, AUTOR)
    xs = m.excluir_pagina(1)
    saida = tmp_path / "s.pdf"
    m.salvar(saida)
    doc = pymupdf.open(saida)
    assert len(xs) == 2
    for x in xs:
        obj = doc.xref_object(x, compressed=True)
        assert "/Subtype/Line" in obj and "/BS" not in obj


def test_exemplo_completo_pela_linha_de_comando(prova, tmp_path, capsys):
    saida = tmp_path / "marcada.pdf"
    assert main(["marcar", str(prova), str(EXEMPLOS / "correcoes.json"),
                 "-o", str(saida), "--autor", AUTOR]) == 0
    resumo, problemas = conferir(saida, AUTOR)
    assert problemas == []
    assert resumo[0].startswith("10 marcações")
    assert main(["conferir", str(saida), "--autor", AUTOR]) == 0


def test_conferir_reconhece_autor_com_parenteses(prova, tmp_path):
    m = Marcador(prova, "Revisão (2ª prova)")
    m.riscar(0, "90 °C")
    saida = tmp_path / "s.pdf"
    m.salvar(saida)
    resumo, problemas = conferir(saida, "Revisão (2ª prova)")
    assert problemas == [] and len(resumo) == 1


def test_linha_de_comando_avisa_o_que_nao_aplicou(prova, tmp_path, capsys):
    lista = tmp_path / "c.json"
    lista.write_text(json.dumps([
        {"pagina": 1, "acao": "riscar", "trecho": "isto não está na página"},
        {"pagina": 9, "acao": "riscar", "trecho": "água"},
        {"pagina": 1, "acao": "substituir", "trecho": "90 °C", "novo": "100 °C"},
    ]), encoding="utf-8")
    saida = tmp_path / "marcada.pdf"
    assert main(["marcar", str(prova), str(lista), "-o", str(saida), "--autor", AUTOR]) == 1
    out = capsys.readouterr().out
    assert "2 marcações gravadas" in out and "2 correções NÃO aplicadas" in out


def test_reparar_desfaz_annots_compartilhados(prova, tmp_path):
    doc = pymupdf.open(prova)
    x = doc.get_new_xref()
    doc.update_object(x, "[]")
    for p in doc:
        doc.xref_set_key(p.xref, "Annots", "%d 0 R" % x)
    quebrado = tmp_path / "quebrado.pdf"
    doc.save(quebrado, garbage=1)
    assert diagnosticar(pymupdf.open(quebrado))

    comp, _, depois, _ = reparar(quebrado, tmp_path / "ok.pdf")
    assert comp and not depois
