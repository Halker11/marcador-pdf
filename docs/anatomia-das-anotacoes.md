# Anatomia das anotações do Adobe Acrobat

Tabela obtida por engenharia reversa: marcações feitas à mão no Acrobat 26.2.0 (pt-BR)
foram abertas com PyMuPDF e os dicionários PDF comparados campo a campo com os gerados
por código, até zerar as divergências.

Este arquivo explica por que o código faz coisas aparentemente arbitrárias (o
`font-size:-14.0pt`, por exemplo, é assim mesmo) e o que observar antes de acrescentar
um tipo de marcação novo.

## Mapa ferramenta → anotação

| Ferramenta no Acrobat | Subtype | `/Subj` | `/IT` | Cor |
|---|---|---|---|---|
| Riscar | `StrikeOut` | `Riscado` | — | vermelho `.972549 .392151 .392151` |
| Substituir texto selecionado | `Caret` (pai) | `Texto digitado` | `/Replace` | vermelho |
| ↳ acompanha | `StrikeOut` (filho) | `Riscado` | `/StrikeOutTextEdit` | vermelho |
| Inserir texto | `Caret` | `Texto digitado` | — | magenta `.752945 .215683 .768631` |
| Adicionar comentário de texto | `Text` (`/Name /Comment`) | `Comentário do texto` | — | roxo `.588242 .262741 .988235` |
| Realçar com nota | `Highlight` | `Comentário do texto` | `/HighlightNote` | roxo, opacidade .4 |
| Linha | `Line` | `Linha` | — | vermelho `.858826 .203918 .145096` |

## Substituir é um par agrupado, não uma anotação

O `StrikeOut` filho aponta para o `Caret` pai com `/IRT <xref> 0 R` e `/RT /Group`.
É esse par que faz o Acrobat mostrar **um** item no painel de Comentários em vez de dois.
Sem ele a marcação funciona, mas polui o painel com o dobro de linhas, e em um livro de
120 páginas isso inviabiliza a revisão.

O texto novo vai no `/Contents` do Caret. O StrikeOut filho fica **sem** `/Contents`.

## Campos que o Acrobat grava e o PyMuPDF não

Faltando qualquer um destes, a marcação abre mas se comporta como estrangeira: sem data
no painel, sem janela de nota, sem poder receber resposta.

- `/NM`: identificador único (UUID). O PyMuPDF gera `fitz-A0`, `fitz-A1`…, que **se repetem
  entre páginas**. Isso quebra o encadeamento de respostas e a seleção no painel.
- `/CreationDate` e `/M`: formato `D:AAAAMMDDHHMMSS-03'00'`.
- `/Popup`: a janela da nota.
- `/RC`: texto rico em XML; o Acrobat 26.2 grava `font-size:-14.0pt`, com sinal negativo mesmo.
- `/Subj`: o rótulo que aparece no painel, no idioma da instalação.

## Codificação de acentos

O `/Subj` e o `/T` precisam de escape octal Latin-1, como o Acrobat grava:

```
correto:  (Coment\341rio do texto)
errado:   (Coment\303\241rio do texto)     <- UTF-8; o Acrobat lê o rótulo torto
```

Fora do Latin-1, a saída é uma string hexadecimal UTF-16BE: `<FEFF...>`.

## Quebras de linha no caret

O Acrobat grava a quebra como `\r` (parágrafo = `\r\r`), escapada dentro da string. Gravada
crua, o PyMuPDF a regrava como `\n`.

Isso importa quando a diagramação importa os comentários do PDF no InDesign e aceita as
inserções e substituições: o InDesign aplica o `/Contents` do caret tal como está. Por isso
o caret deve carregar **só o texto que entra no livro**. Recados para a diagramação ("é
legenda", "vai acima da tabela") vão num comentário separado, ao lado.

## Geometria do caret

O caret é uma figura vetorial única escalada por um parâmetro `s`. Os 13 coeficientes do
traçado foram conferidos em duas amostras manuais independentes e batem até a quarta casa:

```
largura = 12.727·s      altura = 10·s       espessura do traço = s
Rect  = [cx − larg/2 − s,  base − s,  cx + larg/2 + s,  base + alt + s]
RD    = [s s s s]
BBox  = [−s, −s, larg + s, alt + s]         Matrix = [1 0 0 1 s s]
```

Dois pontos onde é fácil errar:

- **`cx` é o centro do caret, não a borda.** Ancorar pelo canto esquerdo joga a marca para a
  direita do ponto de inserção, e isso se vê a olho nu.
- **`base` é a base da linha de texto**, em coordenadas PDF (origem embaixo). O `search_for`
  do PyMuPDF devolve coordenadas de página (origem em cima); a conversão é feita com
  `~pagina.transformation_matrix`.

`s` é proporcional ao corpo do texto: `s = altura_da_linha × (0.52887 / 9.616)`, calibrado
em texto de 8 pt. As duas amostras manuais eram ambas de 8 pt (`s` de 0.52887 e 0.540009,
variação atribuída ao ponto do clique), então a proporcionalidade é inferência razoável,
não medição. Um caret refeito à mão no Acrobat sai com 20×14 pt, o tamanho padrão dele.

## A armadilha do PyMuPDF: geometria desfeita

Criar uma anotação nova faz o PyMuPDF regravar as anteriores da mesma página a partir do
estado em cache, **desfazendo em silêncio** qualquer `set_rect` ou escrita bruta de
geometria feita antes. Por isso `marcar.py` acumula os ajustes de caret em `self._carets`
e só os aplica em `salvar()`, quando nada mais vai ser criado.

Um tipo de marcação novo que precise de geometria própria deve seguir o mesmo padrão:
agendar, não aplicar na hora.

Pelo mesmo motivo, para trocar só o texto de uma anotação já gravada, use
`annot.set_info(content=novo)` e salve **sem** chamar `annot.update()`: ele reconstrói a
aparência e o `/Rect` do caret volta para 20×14.

## A armadilha do `garbage` ao salvar

`doc.save(..., garbage=3)` ou `4` manda o PyMuPDF **fundir objetos idênticos**. Depois de
remover as anotações de uma página, o array `/Annots` dela fica vazio, e arrays vazios são
idênticos entre si. Resultado: dezenas de páginas passam a apontar para **um único** array.
O arquivo abre normal e nada parece errado. Mas quando alguém marca uma dessas páginas no
Acrobat, a anotação entra no array compartilhado e aparece em todas as outras.

Foi assim que 16 marcações feitas à mão em duas páginas apareceram em 42.

- Salvar sempre com `garbage=1` (ou 0). Nunca 3 ou 4.
- Ao gerar uma "cópia limpa" removendo anotações, idem.
- `marcador-pdf reparar` diagnostica e desfaz o compartilhamento sem perder marcação
  nenhuma: cada anotação sabe sua página pelo `/P`.

## Linha

O que o Acrobat 26.2 grava para a ferramenta Linha, usada aqui para o X de página excluída:

| Chave | Valor |
|---|---|
| `/Subtype` | `/Line`, com `/Subj` `Linha`; sem `/IT`, sem `/Contents`, sem `/RC`, **sem `/BS`** (largura 1 implícita), sem `/LE` |
| `/L` | `[x1 y1 x2 y2]` em coordenadas PDF (origem embaixo) |
| `/Rect` | `/L` expandido em **5,5 pt** em cada lado |
| `/C` | `.858826 .203918 .145096` (não é o vermelho do riscado) |
| `/F` | 4 |
| `/AP /N` | Form XObject: `BBox` = `Rect`, `Matrix` `[1 0 0 1 -x0 -y0]`, `Resources <</ProcSet[/PDF]>>`, conteúdo `r g b RG\nx1 y1 m\nx2 y2 l\nS\n` (sem `w`) |
| `/Popup` | `F 28`, `Open false`, `Rect` encostado na borda direita da página, 184 × 92 pt |

O PyMuPDF (`add_line_annot`) grava `/BS <</W 1>>`, `Rect` = `L` ± 1 e `1 w` no AP.
`Marcador.excluir_pagina()` corrige tudo no salvamento e reescreve o objeto sem `/BS`,
porque `xref_set_key(…, "null")` deixaria `/BS null` no dicionário.

## Riscos que "somem" no Acrobat

Riscos que não aparecem de perto mas existem no arquivo (texto pequeno sobre fundo) costumam
ser cache de exibição: fechar e reabrir o arquivo resolve. Antes de concluir isso, confira
com `xref_stream` do `/AP` que os traços estão lá.
