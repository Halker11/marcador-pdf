# -*- coding: utf-8 -*-
"""Grava marcações de revisão em PDF replicando o que o Adobe Acrobat grava.

Tabela obtida por engenharia reversa de marcações feitas à mão no Acrobat 26.2.0 (pt-BR):

  ferramenta                      anotação                      /Subj                 /IT
  Riscar                          StrikeOut                     Riscado               --
  Substituir texto selecionado    Caret (pai)                   Texto digitado        /Replace
                                  + StrikeOut (filho, /IRT + /RT /Group)  Riscado     /StrikeOutTextEdit
  Inserir texto                   Caret                         Texto digitado        --
  Adicionar comentário de texto   Text (/Name /Comment, 24x24)  Comentário do texto   --
  Realçar com nota                Highlight                     Comentário do texto   /HighlightNote
  Linha                           Line (/L, sem /BS)            Linha                 --

Os detalhes de cada dicionário estão em docs/anatomia-das-anotacoes.md.
"""
import datetime
import html
import re
import uuid

import pymupdf

VERMELHO = (.972549, .392151, .392151)         # riscar / substituir
MAGENTA = (.752945, .215683, .768631)          # inserir texto
ROXO = (.588242, .262741, .988235)             # comentário de texto / realce
VERMELHO_LINHA = (.858826, .203918, .145096)   # ferramenta Linha
_MARGEM_LINHA = 5.5                            # /Rect da Linha = /L expandido em 5.5 pt
APIVER = "Acrobat:26.2.0"

# Caret do Acrobat: figura única escalada por s (coeficientes conferidos em 2 amostras manuais).
_COEF = [.5557, .6667, 12.727, 12.1718, 7.3920, 6.1694, 6.6139, 1.9778, 8.6668, 10.0, 6.0582, 4.6686, 1.6673]
_LARG, _ALT = 12.727, 10.0
_NOTA = 24.0   # nota adesiva do Acrobat: 24x24, bico no canto inferior direito


def _escala(altura_linha):
    """s calibrado em 0.52887 para linha de 9.616 pt (texto de 8 pt); proporcional à fonte."""
    return max(.30, min(1.20, altura_linha * (.52887 / 9.616)))


def _agora():
    t = datetime.datetime.now().astimezone()
    z = t.strftime("%z")
    return t.strftime("D:%Y%m%d%H%M%S") + z[:3] + "'" + z[3:] + "'"


def _s(x):
    """String literal PDF; acentos em escape octal Latin-1, como o Acrobat grava."""
    if any(ord(c) > 255 for c in x):
        return "<FEFF" + x.encode("utf-16-be").hex().upper() + ">"
    out = []
    for c in x:
        if c in "\\()":
            out.append("\\" + c)
        elif c == "\r":
            out.append("\\r")      # o Acrobat grava a quebra escapada; crua, o PyMuPDF a regrava como \n
        elif c == "\n":
            out.append("\\n")
        elif ord(c) < 128:
            out.append(c)
        else:
            out.append("\\%03o" % ord(c))
    return "(" + "".join(out) + ")"


def _rc(txt):
    """Rich text (/RC) do comentário. Trechos entre <i>…</i> saem em itálico; o /Contents fica sem as marcas."""
    def span(t, estilo):
        t = html.escape(t).replace("\n", "&#10;").replace("\r", "&#13;")
        return ('<span dir="ltr" style="font-size:-14.0pt;text-align:left;'
                'color:#000000;font-weight:normal;font-style:' + estilo + '">' + t + "</span>")
    partes = re.split(r"(<i>.*?</i>)", txt, flags=re.S)
    c = "".join(span(x[3:-4], "italic") if x.startswith("<i>") else span(x, "normal") for x in partes if x)
    return ('<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:APIVersion="' + APIVER + '" '
            'xfa:spec="2.0.2" ><p dir="ltr">' + c + "</p></body>")


def _ap_caret(s, cor):
    """Content stream idêntico ao que o Acrobat grava para o caret."""
    c0, c1, W, c3, c4, c5, c6, c7, c8, H, c10, c11, c12 = [k * s for k in _COEF]
    k = "%.6f %.6f %.6f" % cor
    return ("%s RG\n%.4f w\n%s rg\n%.4f %.4f m\n0 %.4f l\n0 0 l\n%.4f 0 l\n%.4f %.4f l\n%.4f %.4f l\n"
            "%.4f %.4f %.4f %.4f %.4f %.4f c\n%.4f %.4f l\n%.4f %.4f l\n%.4f %.4f l\n"
            "%.4f %.4f %.4f %.4f %.4f %.4f c\nh\nf\nS\n"
            % (k, s, k, c0, c1, c1, W, W, c1, c3, c1,
               c4, c1, c5, c7, c6, c8, c6, H, c10, H, c10, c8, c6, c7, c11, c1, c12, c1))


def _quebras(texto):
    """Quebras de linha como o Acrobat grava no caret: \\r (parágrafo = \\r\\r)."""
    return (texto or "").replace("\r\n", "\n").replace("\r", "\n").strip().replace("\n", "\r")


def _R(x):
    return x.rect if isinstance(x, pymupdf.Quad) else x


def _ponto_bico(pg, x, y):
    """Canto superior esquerdo da nota para que o bico (canto inferior direito) caia em (x, y)."""
    return pymupdf.Point(max(0, min(x - _NOTA, pg.rect.width - _NOTA)), max(0, y - _NOTA))


def juntar_por_linha(rects, folga=12.0):
    """Como o Acrobat: UMA faixa contínua por linha, do 1º ao último caractere selecionado.
    Retângulos de palavras da mesma linha viram um só, para o risco não ficar picotado entre
    as palavras. Só junta se a distância for de espaço entre palavras (< `folga` pt), para não
    emendar colunas diferentes. Quads (texto rotacionado) passam intactas."""
    quads = [r for r in rects if isinstance(r, pymupdf.Quad)]
    rs = [pymupdf.Rect(r) for r in rects if not isinstance(r, pymupdf.Quad)]
    if len(rs) < 2:
        return quads + rs
    linhas = []
    for r in sorted(rs, key=lambda r: ((r.y0 + r.y1) / 2, r.x0)):
        cy = (r.y0 + r.y1) / 2
        for ln in linhas:
            ly = (ln[0].y0 + ln[0].y1) / 2
            if abs(cy - ly) < 0.5 * min(r.height, ln[0].height):
                ln.append(r)
                break
        else:
            linhas.append([r])
    out = []
    for ln in sorted(linhas, key=lambda l: min(r.y0 for r in l)):
        ln.sort(key=lambda r: r.x0)
        seg = pymupdf.Rect(ln[0])
        for r in ln[1:]:
            if r.x0 - seg.x1 < folga:
                seg |= r
            else:
                out.append(seg)
                seg = pymupdf.Rect(r)
        out.append(seg)
    return quads + out


def _rects_por_linha(pg, rects):
    """Uma região alta (título em duas linhas lido como um bloco só) viraria UM quad, e o
    Acrobat traça o risco no meio do bloco, entre as linhas. Quebra cada retângulo nas
    linhas de texto que ele contém, uma quad por linha."""
    out = []
    for r in rects:
        if isinstance(r, pymupdf.Quad):     # quad de texto rotacionado: passa inteiro
            out.append(r)
            continue
        r = pymupdf.Rect(r)
        linhas = []
        for b in pg.get_text("dict", clip=r)["blocks"]:
            for l in b.get("lines", []):
                lb = pymupdf.Rect(l["bbox"]) & r
                if lb.is_empty or lb.height < 3 or not "".join(sp["text"] for sp in l["spans"]).strip():
                    continue
                lb.x0, lb.x1 = r.x0, r.x1
                if linhas and abs(linhas[-1].y0 - lb.y0) < 2:
                    linhas[-1] |= lb
                else:
                    linhas.append(lb)
        out.extend(linhas if len(linhas) > 1 else [r])
    return juntar_por_linha(out)


class Marcador:
    """Abre um PDF e grava marcações de revisão. `pagina` é sempre índice base 0.

    Os métodos que recebem `alvo` localizam o trecho pelo texto da página e levantam
    LookupError se ele não existir ou aparecer mais de uma vez: melhor falhar do que
    marcar o lugar errado em silêncio.
    """

    def __init__(self, caminho, autor, data=None):
        self.doc = pymupdf.open(caminho)
        self.autor = autor
        # data fixa (AAAAMMDD) para todas as marcações; a hora continua sendo a de agora
        self.ts = (_agora()[:2] + data + _agora()[10:]) if data else _agora()
        self.n = 0
        self._carets = []          # ajustes de geometria aplicados só no salvamento
        self._linhas = []          # idem para as Linhas

    # ---------- infraestrutura ----------
    def _sela(self, a, subj, conteudo=None, it=None):
        """Completa a anotação com os campos que o Acrobat grava e o PyMuPDF não."""
        rico = conteudo
        if conteudo:
            conteudo = re.sub(r"</?i>", "", conteudo)      # <i>…</i> só vai para o /RC
        a.set_info(title=self.autor, content=conteudo or "")
        a.set_popup(a.rect)
        a.update()
        d, x = self.doc, a.xref
        d.xref_set_key(x, "NM", _s(str(uuid.uuid4())))
        d.xref_set_key(x, "CreationDate", _s(self.ts))
        d.xref_set_key(x, "M", _s(self.ts))
        d.xref_set_key(x, "Subj", _s(subj))
        d.xref_set_key(x, "T", _s(self.autor))
        if conteudo:
            d.xref_set_key(x, "Contents", _s(conteudo))
            d.xref_set_key(x, "RC", _s(_rc(rico)))
        if it:
            d.xref_set_key(x, "IT", it)
        self.n += 1
        return x

    def _achar(self, pg, alvo):
        r = pg.search_for(alvo)
        if not r:
            raise LookupError("pág. %d: não encontrei %r" % (pg.number + 1, alvo))
        norm = lambda t: " ".join(t.split()).lower()
        if norm(pg.get_text()).count(norm(alvo)) > 1:
            raise LookupError("pág. %d: %r aparece mais de uma vez; use um trecho maior" % (pg.number + 1, alvo))
        qs = pg.search_for(alvo, quads=True)
        # o retângulo de uma linha com tabulações vai além do texto: encolher cada retângulo ao
        # alcance das palavras que ele contém, SEM passar do trecho buscado (a caixa da palavra
        # inclui a pontuação colada, e o risco pegaria um ponto que o texto novo não repõe)
        words = [pymupdf.Rect(w[:4]) for w in pg.get_text("words")]
        out = []
        for k, rc in enumerate(r):
            q = qs[k] if k < len(qs) else None
            if q is not None and abs(q.ul.y - q.ur.y) > 1:   # texto girado: risco ao longo do texto
                out.append(q)
                continue
            dentro = [w for w in words
                      if rc.y0 <= (w.y0 + w.y1) / 2 <= rc.y1 and w.height >= rc.height * 0.5
                      and w.x0 < rc.x1 and w.x1 > rc.x0]
            out.append(pymupdf.Rect(max(rc.x0, min(w.x0 for w in dentro)), rc.y0,
                                    min(rc.x1, max(w.x1 for w in dentro)), rc.y1) if dentro else rc)
        return out

    def _agendar_caret(self, xref, pg, cx_pag, ybase_pag, cor, altura):
        """Guarda a geometria exata; aplicada em salvar() para o PyMuPDF não sobrescrever."""
        inv = ~pg.transformation_matrix
        cx = (pymupdf.Point(cx_pag, 0) * inv).x
        yb = (pymupdf.Point(0, ybase_pag) * inv).y
        self._carets.append((xref, cx, yb, cor, _escala(altura)))

    def _risco(self, pg, rects, it=None):
        a = pg.add_strikeout_annot(rects)
        a.set_colors(stroke=VERMELHO)
        return self._sela(a, "Riscado", it=it)

    def _par_de_substituicao(self, pg, rects, novo):
        """Caret pai + StrikeOut filho agrupados: UM item no painel de Comentários."""
        ult = _R(rects[-1])
        c = pg.add_caret_annot(pymupdf.Point(ult.x1, ult.y0))
        c.set_colors(stroke=VERMELHO)
        xc = self._sela(c, "Texto digitado", novo, it="/Replace")
        self._agendar_caret(xc, pg, ult.x1, ult.y1, VERMELHO, ult.height)
        xs = self._risco(pg, rects, it="/StrikeOutTextEdit")
        self.doc.xref_set_key(xs, "IRT", "%d 0 R" % xc)
        self.doc.xref_set_key(xs, "RT", "/Group")
        return xc

    # ---------- ferramentas ancoradas em texto ----------
    def riscar(self, pagina, alvo):
        """Acrobat: 'Riscar'."""
        pg = self.doc[pagina]
        return self._risco(pg, self._achar(pg, alvo))

    def substituir(self, pagina, alvo, novo):
        """Acrobat: 'Substituir texto selecionado'. Sem texto novo, vira um risco simples."""
        pg = self.doc[pagina]
        r = self._achar(pg, alvo)
        novo = _quebras(novo)
        return self._par_de_substituicao(pg, r, novo) if novo else self._risco(pg, r)

    def inserir(self, pagina, alvo, texto, antes=False):
        """Acrobat: 'Inserir texto'. O caret vai depois de `alvo` (ou antes, com antes=True)."""
        pg = self.doc[pagina]
        r = self._achar(pg, alvo)
        alvo_r = _R(r[0] if antes else r[-1])
        cx = alvo_r.x0 if antes else alvo_r.x1
        a = pg.add_caret_annot(pymupdf.Point(cx, alvo_r.y0))
        a.set_colors(stroke=MAGENTA)
        x = self._sela(a, "Texto digitado", _quebras(texto))
        self._agendar_caret(x, pg, cx, alvo_r.y1, MAGENTA, alvo_r.height)
        return x

    def comentar(self, pagina, alvo, texto):
        """Acrobat: 'Adicionar comentário de texto'. A nota fica acima e à esquerda do trecho,
        com o bico apontando para o início dele."""
        pg = self.doc[pagina]
        r = _R(self._achar(pg, alvo)[0])
        return self.comentar_em_ponto(pagina, texto, r.x0, r.y0, bico=True)

    # ---------- ferramentas sobre uma região ou um ponto ----------
    def comentar_em_ponto(self, pagina, texto, x, y, bico=False):
        """Nota adesiva numa coordenada da página, para quando não há texto onde ancorar.
        x, y em pontos, origem no topo. bico=True: (x, y) é o elemento apontado, e a nota
        fica acima e à esquerda dele."""
        pg = self.doc[pagina]
        a = pg.add_text_annot(_ponto_bico(pg, x, y) if bico else pymupdf.Point(x, y), texto, icon="Comment")
        a.set_colors(stroke=ROXO)
        a.set_opacity(.399994)
        return self._sela(a, "Comentário do texto", texto)

    def riscar_regiao(self, pagina, rects):
        """'Riscar' sobre retângulos já delimitados, um risco por linha de texto."""
        pg = self.doc[pagina]
        return self._risco(pg, _rects_por_linha(pg, rects))

    def substituir_regiao(self, pagina, rects, novo):
        """'Substituir texto selecionado' sobre uma região, em vez de um trecho buscado.
        Serve para tabelas, balões de fala ou uma página inteira reformulada: um único
        riscado cobre todas as linhas que saem e um único caret carrega o texto novo,
        então o painel do Acrobat mostra UM comentário, não dezenas."""
        if not rects:
            raise ValueError("sem região para substituir")
        pg = self.doc[pagina]
        rects = _rects_por_linha(pg, rects)
        novo = _quebras(novo)
        return self._par_de_substituicao(pg, rects, novo) if novo else self._risco(pg, rects)

    def destacar_regiao(self, pagina, rects, texto):
        """Realce com a nota no próprio realce (/IT /HighlightNote), uma faixa por linha."""
        pg = self.doc[pagina]
        a = pg.add_highlight_annot(_rects_por_linha(pg, rects))
        a.set_colors(stroke=ROXO)
        a.set_opacity(.399994)
        return self._sela(a, "Comentário do texto", texto, it="/HighlightNote")

    def excluir_pagina(self, pagina, margem=30.0):
        """Duas 'Linhas' vermelhas nas diagonais da página: um X para a página que sai do livro.
        Devolve os dois xrefs."""
        pg = self.doc[pagina]
        r = pg.rect
        xs = []
        for p1, p2 in (((r.x0 + margem, r.y0 + margem), (r.x1 - margem, r.y1 - margem)),      # \
                       ((r.x0 + margem, r.y1 - margem), (r.x1 - margem, r.y0 + margem))):     # /
            a = pg.add_line_annot(pymupdf.Point(*p1), pymupdf.Point(*p2))
            a.set_colors(stroke=VERMELHO_LINHA)
            a.set_info(title=self.autor)
            a.set_popup(pymupdf.Rect(r.x1, r.height / 2 - 46, r.x1 + 184, r.height / 2 + 46))
            a.update()
            d, x = self.doc, a.xref
            d.xref_set_key(x, "NM", _s(str(uuid.uuid4())))
            d.xref_set_key(x, "CreationDate", _s(self.ts))
            d.xref_set_key(x, "M", _s(self.ts))
            d.xref_set_key(x, "Subj", _s("Linha"))
            d.xref_set_key(x, "T", _s(self.autor))
            d.xref_set_key(x, "F", "4")
            pu = int(d.xref_get_key(x, "Popup")[1].split()[0])
            d.xref_set_key(pu, "F", "28")
            d.xref_set_key(pu, "Open", "false")
            self._linhas.append(x)
            xs.append(x)
            self.n += 1
        return xs

    # ---------- finalização ----------
    def _aplicar_linhas(self):
        d, m_ = self.doc, _MARGEM_LINHA
        for xref in self._linhas:
            L = [float(v) for v in re.findall(r"[-\d.]+", d.xref_get_key(xref, "L")[1])]
            x0, y0 = min(L[0], L[2]) - m_, min(L[1], L[3]) - m_
            x1, y1 = max(L[0], L[2]) + m_, max(L[1], L[3]) + m_
            d.xref_set_key(xref, "Rect", "[%.4f %.4f %.4f %.4f]" % (x0, y0, x1, y1))
            # o Acrobat não grava /BS (nem Contents/RC/LE/IC/CA/Border) na Linha; xref_set_key(..., "null")
            # deixaria "/BS null" no objeto, então o dicionário é reescrito sem essas chaves
            obj = d.xref_object(xref, compressed=True)
            obj = re.sub(r"/(BS|Contents|RC|LE|IC|CA|Border)\s*(<<[^>]*>>|\[[^\]]*\]|\([^)]*\)|null|[\d.]+)", "", obj)
            d.update_object(xref, obj)
            m = re.search(r"/AP\s*<<\s*/N\s+(\d+) 0 R", d.xref_object(xref, compressed=True))
            if not m:
                continue
            ap = int(m.group(1))
            d.xref_set_key(ap, "BBox", "[%.4f %.4f %.4f %.4f]" % (x0, y0, x1, y1))
            d.xref_set_key(ap, "Matrix", "[1 0 0 1 %.4f %.4f]" % (-x0, -y0))
            d.xref_set_key(ap, "Resources", "<</ProcSet[/PDF]>>")
            d.xref_set_key(ap, "FormType", "1")
            d.update_stream(ap, ("%.6f %.6f %.6f RG\n%.4f %.4f m\n%.4f %.4f l\nS\n"
                                 % (VERMELHO_LINHA + (L[0], L[1], L[2], L[3]))).encode("latin1"))

    def _aplicar_carets(self):
        d = self.doc
        for xref, cx, yb, cor, s in self._carets:
            W, H = _LARG * s, _ALT * s
            d.xref_set_key(xref, "Rect", "[%.6f %.6f %.6f %.6f]"
                           % (cx - W / 2 - s, yb - s, cx + W / 2 + s, yb + H + s))
            d.xref_set_key(xref, "RD", "[%.6f %.6f %.6f %.6f]" % (s, s, s, s))
            m = re.search(r"/AP\s*<<\s*/N\s+(\d+) 0 R", d.xref_object(xref, compressed=True))
            if not m:
                continue
            ap = int(m.group(1))
            d.xref_set_key(ap, "BBox", "[%.6f %.6f %.6f %.6f]" % (-s, -s, W + s, H + s))
            d.xref_set_key(ap, "Matrix", "[1 0 0 1 %.6f %.6f]" % (s, s))
            d.update_stream(ap, _ap_caret(s, cor).encode("latin1"))

    def salvar(self, destino):
        """Aplica a geometria agendada e grava. Devolve o número de marcações criadas."""
        self._aplicar_carets()
        self._aplicar_linhas()
        # garbage=1, NUNCA 3 ou 4: a partir de 3 o PyMuPDF funde objetos idênticos, inclusive
        # arrays /Annots vazios, e aí uma marcação feita no Acrobat numa página aparece em
        # todas as que compartilham o array. Ver reparar.py.
        self.doc.save(destino, garbage=1, deflate=True)
        return self.n
