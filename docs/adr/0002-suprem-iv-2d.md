# ADR 0002 — SUPREM-IV.GS como motor 2-D

- **Data:** 2026-10-09
- **Situação:** aceita
- **Escopo:** compilação do SUPREM-IV.GS B.9305, camada de dados 2-D e as sete
  telas do motor bidimensional

## Contexto

O MOS-Studio simulava processo em uma dimensão, com o SUPREM-III Release B
(rev. 8628) de Stanford, e levava o perfil ao MINIMOS 6.1. Faltava a seção
transversal: difusão lateral, forma de corrosão, bico de pássaro, junção sob
o espaçador — tudo o que só existe em 2-D.

O SUPREM-IV.GS B.9305 (Stanford/Universidade da Flórida, 1993) resolve isso,
e o código-fonte está disponível. Este ADR registra o que foi decidido para
compilá-lo e integrá-lo, e — principalmente — **as armadilhas do motor que
custaram caro para descobrir**, para não serem redescobertas.

## Decisões

### 1. Compilação 64-bit, em C puro, sem gráficos

O fonte é C de 1993 com partes em Fortran. Esta máquina não tem gfortran nem
bibliotecas de 32 bits. A saída foi compilar em 64 bits, só a parte em C, com
`-std=gnu89 -fcommon -O2 -w -DDEVICE -DSYSV -DNO_F77`.

Com `NO_F77`, `tomcal_()` deixa de ser chamado, e `vector.f`/`toms508.f` são
código específico de CONVEX e CRAY — não entram na compilação de um PC. O
`misc/sint.c` duplica o `check/sint.c` e fica de fora, como o `src/wscript` do
próprio fonte já faz.

**Não há camada gráfica.** Os `gpsup/gpfake.c` são talões vazios: `plot.1d`,
`plot.2d` e `contour` são aceitos pelo motor e não desenham nada. Essa é a
decisão de arquitetura mais consequente deste ADR — ver item 4.

Tudo está em `build_suprem4.sh`, que refaz a instalação do zero.

### 2. Um `patch` obrigatório: `strcpy` sobreposto em `shell/list.c`

O `foreach` do shell produzia lixo (`val=00ee++++0011` em vez de `15 15.5 …`).
A causa é um `strcpy(str, str+1)` com regiões sobrepostas — comportamento
indefinido que funcionava no `strcpy` byte a byte de 1993 e quebra na glibc
moderna, que copia vetorizado.

Corrigido com `memmove` em `patches/suprem4/0001-list-copias-sobrepostas.patch`.
É o único patch necessário, e sem ele o `foreach` dos exemplos de fábrica sai
errado **em silêncio**.

### 3. Um registro de motores, em vez de um `import` fixo

`core/engines.py` descreve cada motor por um `Engine` congelado — como montar
o deck, qual executor usar, que exceção é cancelamento. A interface pede o
motor pelo identificador e não sabe qual binário vai rodar. Foi o que permitiu
o `RunController` servir aos dois sem um `if` por dentro.

### 4. O desenho 2-D sai de números, não do motor

Como não há camada gráfica (item 1), a tela de Resultados 2-D **varre** a
seção com N cortes verticais `print.1d x.value=` e extrai dali os contornos
(marching squares), a junção, as faixas de material e a superfície
(`core/field2d.py`). Quarenta e oito cortes levam frações de segundo.

O efeito colateral é bom: o que aparece na tela é a geometria que o motor
construiu, não uma forma desenhada por conta própria.

Por isso o painel "como este desenho foi obtido" mostra os cortes, e não a
sequência clássica `plot.2d bound fill` / `contour val=(…)`: ela seria o
caminho canônico no SUPREM-IV original, mas aqui não produz nada, e oferecê-la
mandaria o usuário a um beco sem saída.

### 5. Os coeficientes vêm do motor, em duas camadas

A tela de Modelos lê, nesta ordem, o `data/modelrc` (que o motor carrega antes
de qualquer deck) e o `data/suprem.key` (a gramática compilada). A ordem
importa: o `suprem.key` declara `interstitial D.0 = 1e-9` e o `modelrc`
sobrescreve com `1.03e6` — quinze ordens de grandeza.

O `suprem.key` também dá a **unidade** de cada parâmetro e o valor padrão de
cada `switch`, o que tornou possível montar a tela sem uma tabela escrita à
mão. Só o que o usuário altera entra no deck.

## As armadilhas do motor

Todas conferidas contra o binário compilado.

### Nomes de parâmetro são truncados em onze caracteres

`include/check.h` declara `char name[12]`. O `keyread` trunca ao compilar o
`suprem.uk`, e o motor depois **recusa o nome completo**:

```
method interstitial  →  parameter interstitial does not exist for this command
method interstitia   →  aceito
deposit … concentration=1e18  →  recusado;  conc=1e18  →  aceito
```

Nomes de *cartão* não sofrem disso: `interstitial silicon D.0=1e6` passa
inteiro. `core/keyfile.py` guarda o nome já truncado, e por isso tudo que a
interface emite é aceito.

### `diffuse temp` é em Celsius, apesar do que o `suprem.key` diz

A gramática declara "degrees Kelvin"; `diffuse.c` soma 273 ao valor lido.
O valor correto a escrever é o Celsius.

### Não existe ambiente `inert`

O motor responde `parameter inert does not exist for this command`. O ambiente
inerte é `nitrogen` ou `argon`.

### Não existe cartão `impurity`

O cartão é o nome da espécie: `arsenic silicon Dix.0=0.0666`. E as espécies
não têm os mesmos parâmetros — o fósforo difunde por vacância (`Dvx`, `Dvm`) e
**não aceita `Fi`**.

### Um cabeçalho desconhecido é executado pelo sistema operacional

O shell do SUPREM-IV entrega ao `/bin/sh` o que não reconhece como cartão nem
embutido. Conferido: `rm -rf` digitado no Console executaria de verdade. Daí a
verificação `suprem4.unknown_cards()` antes de mandar qualquer linha, tanto no
deck quanto no Console.

### `define` contamina o resto da sessão, e não há volta

Depois de `define temp 1000`, **todo** comando com a palavra `temp` é
reescrito:

```
diffuse temp=950  →  diffuse 1000=950  →  parameter 1000 does not exist
undef temp        →  can not find macro  1000
```

O próprio argumento do `undef` é substituído antes. A única saída é reiniciar
a sessão — e é por isso que o Console tem esse botão em destaque.

### `print.1d layers` precisa de `x.value` em 2-D

Sem ele, o comando cai no modo de interface (BND, em `print_1d.c`) e imprime
espessuras zeradas em vez da pilha vertical. E antes de qualquer `print.1d` é
preciso um `select`, senão o motor responde `Z variable is out of date w/r to
mesh`.

### A coluna "thickness" do `print.1d layers` é posição de interface

Não é espessura. Conferido: 0,075 µm de óxido depositado mais 15 min de O₂
seco a 1000 °C num substrato de 0,5 µm dão as linhas −0,079 / 0,003 / 0,500 —
ou seja, óxido de 0,082 µm e silício de 0,497 µm, e não 0,079 / 0,003 / 0,500.
A primeira linha é o topo da pilha, não uma camada.

### `z=doping` é dopagem **ativa**

Logo depois de um `implant`, mostra só o substrato. Medido: 5×10¹⁵ cm⁻² de
arsênio aparecem como 1,9×10²⁰ cm⁻³ em `z=arsenic` e **zero** em `z=doping`
até um tratamento térmico ativá-los. `recipe4.warnings()` avisa.

### A malha é progressão geométrica, não interpolação linear

`dvpram()`, em `mesh/rect.c`: entre duas linhas o passo cresce por uma razão
fixa, limitada a `interval.r` = 1,5, com `n = int(log(hr/hl)/log(r) + 0.5)`
nós interiores. A interpolação linear do espaçamento erraria a contagem em
cerca de 10%. `core/mesh.py` transcreve a função; conferido contra
`initialize line.data` com erro máximo de 4,7×10⁻⁷ µm, que é o limite da
impressão de seis casas do motor.

### O óxido guarda B/A só para ⟨111⟩

As taxas linear e parabólica estão tabeladas para ⟨111⟩ e são escaladas pelo
`ori.fac` (0,595 para ⟨100⟩). Só o regime fino (`thinox.*`) é tabelado por
orientação — e o motor recusa `thinox.0` sem `wet/dry` **e** orientação.

### O motor cai acima de cerca de nove mil nós

Bisseccionado com uma malha uniforme e só um `initialize`: **10.653 nós
passam, 11.256 terminam em falha de segmentação** — sem mensagem, sem
resultado. Com um processo de verdade o teto é menor, porque cada deposição
acrescenta nós; o LDD do manual roda até 8.540.

O limite não está numa constante do fonte: as listas de linhas crescem por
`realloc` em `mesh/rect.c`. É o solver que não aguenta. Por isso
`mesh.MAX_SAFE_NODES` é empírico, a tela de Malha avisa antes, e a janela
recusa a execução em vez de gastar minutos para não receber nada.

Refinar também tem um ponto de parada útil. Com o LDD, a junção em x = 0,9 µm
converge assim:

| nós | xj (µm) | tempo |
|---|---|---|
| 1.450 | 0,1545 | 1,5 s |
| 3.139 | 0,1510 | 5,1 s |
| 5.432 | 0,1501 | 12,1 s |
| 8.540 | 0,1491 | 22,4 s |

A malha padrão (450 nós) dá 0,172 µm — **16% a mais que o valor convergido**,
porque a malha grossa espalha o dopante numericamente. A partir de uns 3.000
nós a diferença cai abaixo de 1%, e é isso que `CONVERGED_NODE_COUNT`
registra.

### O motor pode cair

Um `etch done` sem o `etch start` correspondente termina em falha de
segmentação. O executor reconhece o sinal e explica, em vez de mostrar
"código −11".

## Exemplos de fábrica

Quinze dos dezoito decks instalados rodam sem recusa. Três são defeituosos de
origem, e o catálogo (`core/examples4.py`) registra o motivo:

- **exam6** — o `echo` decorativo tem `"< O >"`, que o avaliador de expressão
  recusa; a oxidação em si roda e sai nas três orientações;
- **exam11 e exam12** — pedem `select z=log10(silicon)`, mas neste arquivo de
  chaves `silicon` é nome de material: em GaAs a espécie é `isilicon`. A nota
  de GaAs do próprio fonte contradiz o `suprem.key`.

O **exam5pis** não é defeituoso: só não roda sozinho. Ele continua a estrutura
que o `whole.s4` deixa, e sozinho responde `Pisces mesh i/o error: please
specify a temperature`. Encadeado, grava o `ldd.mesh` corretamente.

Três descrições do roteiro original estavam trocadas e foram corrigidas lendo
os decks: **exam6** é calibração de oxidação (não LOCOS), **exam7** é o LOCOS
(`fullrox` = *full recessed oxide*), e a exportação para o PISCES é o segundo
deck do **exam5**, não o exam8 (que é tensão no nitreto).

### 6. A interface cede largura em degraus, em vez de cortar

O arquivo de design é uma página web e usa `repeat(auto-fit, minmax(min(100%,
Npx), 1fr))` nas grades de cartões e `white-space: nowrap` no cabeçalho. Em
Qt, um `QGridLayout` de colunas fixas e um `QHBoxLayout` fazem o oposto:
espremem os filhos até o texto virar `Proces`, `Resulta`, `Model` — que era
exatamente o que acontecia no **tamanho mínimo da própria janela** (1280×760).

Duas peças resolvem isso:

* `widgets/common.ResponsiveGrid` é o equivalente do `auto-fit`: recalcula o
  número de colunas a cada redimensionamento, a partir de uma largura mínima
  por cartão, e nunca passa do número de itens. Usada nas grades de Exemplos
  (270 px), Estruturas (250 px) e nos dois conjuntos de cartões da tela de
  Início (220 e 300 px).
* O cabeçalho escolhe um de quatro níveis de compactação pela largura
  disponível, nesta ordem de sacrifício: a palavra "ferramentas", os números
  das áreas e, por último, o rótulo longo do botão de execução (`Simular
  processo` → `Simular`, com o nome inteiro no tooltip). A conta vem do
  próprio layout, item a item — estimar a largura de cada peça errava por
  dezenas de pixels.

O `QStackedWidget` do botão de execução também precisou de ajuste: ele
dimensiona pela **maior** das páginas, então a de "executando" — com tempo
decorrido e botão de cancelar — mandava na largura mesmo com o botão simples
em cena. Agora só a página visível conta.

### 7. O cartão dos roteiros guiados segue o design, e se move

O destaque escurece a janela, abre um buraco arredondado em volta do widget e
põe o cartão ao lado — com barra de progresso em segmentos, identificação
numerada (`TOUR · INTERFACE · 3 / 13`), o cartão do deck que o passo ilustra,
a ação pedida precedida de um ponto que pulsa, e um botão que troca de rótulo:
**Pular** enquanto espera a ação, **Concluir** no último passo, **Próximo** no
resto.

A posição é calculada em volta do destaque — ao lado quando o alvo ocupa mais
de 45% da altura, abaixo (ou acima, se não couber) quando é baixo —, nunca
encosta na borda e nunca tapa o que está destacando. Buraco e cartão deslizam
em 0,35 s. Numa janela estreita o cartão cede largura em vez de sair pela
borda.

Com um destaque em cena, a camada deixa o clique passar para a interface de
verdade: é lá que a ação pedida acontece. Sem destaque, o escurecido bloqueia,
porque não há nada para fazer embaixo.

Isso exigiu uma decisão de árvore de widgets. Em Qt, `WA_TransparentForMouseEvents`
faz o teste de acerto **pular o widget inteiro**, filhos incluídos — conferido:
com a camada transparente, `childAt()` encontra o widget destacado embaixo,
mas deixa de encontrar qualquer filho da camada. Com o cartão como filho, os
botões "Voltar" e "Pular" morriam junto. A primeira tentativa contornou isso
ligando e desligando o atributo por 350 ms a cada clique, e o resultado era
pior do que o problema: o primeiro clique só abria a passagem, o segundo
precisava cair dentro da janela de tempo, e o projeto guiado **travava a cada
etapa**.

"Pular" também mudou de sentido. Ele pula o *fazer você mesmo*, não o efeito
do passo: cada passo com ação carrega um `perform` que a executa. Sem isso,
quem clicasse só no botão da direita do começo ao fim terminava o passeio com
o aplicativo ainda na tela de Início — treze cartões falando de telas que
nunca apareceram. Agora o mesmo punhado de cliques abre Malha, Processo,
Resultados, Modelos e Console, e no projeto guiado monta as doze etapas do
LDD.

O cartão é, portanto, **irmão** da camada — os dois filhos da janela, o cartão
erguido acima. Aí a camada pode ficar permanentemente transparente enquanto há
destaque, e o cartão recebe clique normalmente. Um clique por etapa monta as
doze do LDD, e há teste que percorre as doze com cliques de verdade.

### 8. Os dois roteiros se apresentam na tela de Início

O arquivo de design põe um cartão dentro do herói — "NOVO POR AQUI? ·
TUTORIAL INTERATIVO", com um contador de concluídos e uma entrada por
roteiro, cada uma com nome, tamanho ("13 PASSOS · 4 MIN", "EXAM5 · 12
ETAPAS") e uma linha dizendo o que se faz nela. Eram dois links soltos, que
não diziam nada sobre o que havia do outro lado.

Cada entrada é um `QWidget` clicável, não um `QPushButton`: um botão com
layout dentro não adota a altura do próprio conteúdo, e as duas linhas de
texto saíam esmagadas numa tira ilegível. E o cartão mede a própria altura no
`resizeEvent`, porque o `heightForWidth` de um rótulo quebrado só vale se
**todos** os layouts até a janela o repassarem — e a cadeia do herói não
repassa.

## Consequências

- O projeto guarda as **duas** dimensões ao mesmo tempo (`steps` e
  `steps4`/`mesh`/`models`). Trocar de dimensão não apaga o trabalho da outra.
  O formato do arquivo subiu para 2; os de formato 1 continuam abrindo.
- A tela de Dispositivo (MINIMOS) continua só em 1-D: o MINIMOS 6.1 recebe um
  perfil unidimensional.
- O Console mantém um processo do motor vivo. Ele é encerrado quando a janela
  fecha.
