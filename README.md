# MOS-Studio

Aplicativo de bancada para **simulação de processos e dispositivos
semicondutores**. Monta a receita de fabricação etapa por etapa — substrato,
oxidação, implantação, difusão, corrosão, deposição —, roda os simuladores de
Stanford e da TU Wien, e mostra o que saiu dali: perfil de dopagem,
profundidade de junção, pilha de camadas, seção transversal 2-D e a curva I-V
do transistor. Desktop, PySide6. Nada de web.

Três motores, uma interface só:

| Motor | O que faz | Origem |
|---|---|---|
| **SUPREM-III** Release B (rev. 8628) | processo em **1-D**: perfil em profundidade | Stanford, 1986 — Fortran |
| **SUPREM-IV.GS** B.9305 | processo em **2-D**: a seção transversal inteira | Stanford / Univ. da Flórida, 1993 — C |
| **MINIMOS 6.1** | **dispositivo**: curva I-V e mapas de campo | TU Wien — Fortran |

O perfil que o SUPREM calcula vira a dopagem do deck do MINIMOS sem passar
por nenhum arquivo intermediário editado à mão.

## Estado

- **Linux**: os três motores funcionam. É o ambiente de desenvolvimento e o
  único em que a suíte inteira roda.
- **Windows**: o aplicativo roda, com instalador próprio, e **só com o
  SUPREM-IV** — ver [Windows](#windows) e
  [Limitações conhecidas](#limitações-conhecidas).
- **Os motores não são versionados neste repositório** — são software de
  terceiros, e o que está aqui são os scripts que os compilam e os remendos
  necessários. Os **pacotes prontos em
  [Releases](https://github.com/phareon-corp/MOS-Studio/releases) já trazem o
  SUPREM-IV compilado**; o SUPREM-III e o MINIMOS continuam dependendo do
  código-fonte deles. Ver [Os motores](#os-motores-e-como-obtê-los).
- Versão publicada: **v2.0.0**, com instalador de Windows e pacote de Linux
  em [Releases](https://github.com/phareon-corp/MOS-Studio/releases).
- Suíte: **856 testes**. Boa parte sobe o motor de verdade, e se auto-pula
  quando ele não está instalado.

| ![Seção transversal, terreno claro](docs/img/resultados2d-claro.png) | ![Seção transversal, terreno escuro](docs/img/resultados2d-escuro.png) |
|---|---|
| Resultados 2-D, terreno **claro** — o padrão | a mesma tela no terreno **escuro** |

As doze telas nos dois terrenos estão em [`docs/img/`](docs/img/), e são
geradas pelo próprio programa (`--capturar`, ver [Usar](#usar)) — não há
recorte feito à mão que possa envelhecer sem ninguém notar.

---

## Sumário

- [Requisitos](#requisitos)
- [Instalar](#instalar)
- [Os motores, e como obtê-los](#os-motores-e-como-obtê-los)
- [Usar](#usar)
  - [As duas dimensões](#as-duas-dimensões)
  - [As doze telas](#as-doze-telas)
- [O que o motor faz, e o que ele finge fazer](#o-que-o-motor-faz-e-o-que-ele-finge-fazer)
- [Quando dá errado](#quando-dá-errado)
- [Limitações conhecidas](#limitações-conhecidas)
- [Onde ficam as coisas](#onde-ficam-as-coisas)
- [Arquitetura](#arquitetura)
- [Testes](#testes)
- [Windows](#windows)
- [Empacotar](#empacotar)
- [Design](#design)
- [Créditos e licença](#créditos-e-licença)

## Requisitos

| O quê | Detalhe |
|---|---|
| Sistema | **Linux** x86-64, ou **Windows 10/11** 64 bits |
| Python | **≥ 3.11**, só para quem instala do código. O pacote de Windows traz o próprio |
| Interface | **PySide6 ≥ 6.5** (desenvolvido e testado com 6.11.1) |
| Para compilar o SUPREM-IV | `gcc`, ou `mingw64-gcc` para o alvo Windows — nada de Fortran, nada de bibliotecas de 32 bits |
| Para compilar o SUPREM-III e o MINIMOS | `gcc-gfortran`, **mais o código-fonte deles**, que não está aqui |

Sem motor nenhum o programa **abre e navega**: cada tela diz qual motor falta
e por quê, em vez de falhar só na hora de rodar.

## Instalar

**Pacote pronto**, em
[Releases](https://github.com/phareon-corp/MOS-Studio/releases) — já traz o
simulador 2-D compilado.

### Linux

```sh
tar xzf mos-studio-2.0.0-linux-x86_64.tar.gz
cd mos-studio-2.0.0-linux-x86_64
pip install --user PySide6          # se ainda não tiver
./instalar.sh                       # lançador, menu e ícone — sem root
```

Ou direto do código, para desenvolver:

```sh
git clone https://github.com/phareon-corp/MOS-Studio.git
cd MOS-Studio
pip install --user PySide6
./build_suprem4.sh                  # compila o simulador 2-D
./instalar.sh
```

O instalador confere Python, PySide6 e os motores **antes** de escrever
qualquer coisa, e cria três arquivos:

| O que | Onde |
|---|---|
| Lançador `mos-studio` | `~/.local/bin/` |
| Entrada de menu | `~/.local/share/applications/io.syncfield.MosStudio.desktop` |
| Ícone | `~/.local/share/icons/hicolor/scalable/apps/` |

O lançador **aponta para este diretório** em vez de copiar o programa. É de
propósito: os motores e o histórico de execuções vivem aqui, e
`workspace.legacy_results_dir()` os procura ao lado do pacote. Uma cópia
envelheceria a cada commit e deixaria de enxergar as execuções antigas. Mover
ou renomear o diretório quebra o lançador — basta rodar `./instalar.sh` de
novo no lugar novo.

`./desinstalar.sh` remove os três. Não toca nas preferências
(`~/.config/mos-studio`) nem nas simulações.

### Windows

Um arquivo só. Instala **por usuário**, sem pedir senha de administrador, e
aparece em "Aplicativos instalados" com desinstalador próprio. Não precisa de
Python: o pacote traz o próprio interpretador, a própria biblioteca gráfica e
o próprio simulador.

```
MOS-Studio-2.0.0-instalador.exe
```

Para **gerar** esse instalador a partir do Linux, ver
[Empacotar](#empacotar).

### Rodar sem instalar

```sh
python -m mos_studio
```

## Os motores, e como obtê-los

**Nenhum dos três simuladores é versionado neste repositório.** São
programas de terceiros, de 1986 a 1993, com cabeçalhos de *"all rights
reserved"*. O que o Git guarda aqui é o que é nosso: os scripts de
compilação, os remendos e a camada de compatibilidade.

Os **pacotes prontos em
[Releases](https://github.com/phareon-corp/MOS-Studio/releases)** trazem o
**SUPREM-IV** já compilado, para que o programa funcione ao instalar. Quem
clona o repositório o compila com um comando. O SUPREM-III e o MINIMOS não
estão em lugar nenhum aqui: dependem do código-fonte deles.

### SUPREM-IV.GS (2-D) — compila sozinho, ou vem pronto

Já está dentro dos pacotes de Releases. Para compilar do zero:

```sh
./build_suprem4.sh
```

Clona o fonte de um espelho público, aplica os cinco remendos de
[`patches/suprem4/`](patches/suprem4/), compila em 64 bits só a parte em C,
gera o arquivo de chaves compilado com o `keyread` e instala em
`suprem4-run/`. No fim roda o exemplo 1 como teste de fumaça.

Os remendos não são adaptações de conveniência. São **quatro defeitos reais
de portabilidade** que o Linux perdoava por sorte, mais um `strcpy` com
regiões sobrepostas que a glibc moderna quebra em silêncio e corrompe todo
`foreach`. Cada arquivo `.patch` começa explicando o quê e o porquê; o mais
consequente está em
[`docs/adr/0003-versao-de-windows.md`](docs/adr/0003-versao-de-windows.md).

### SUPREM-III (1-D) e MINIMOS 6.1 — precisam do fonte

```sh
./build_suprem.sh /caminho/para/relB_8628_tar.Z
./build_minimos.sh /caminho/para/minimoswin6_1
```

Os dois scripts estão prontos e detectam o sistema (geram `.exe` no Windows,
sob MSYS2 MINGW64). O que falta é o código-fonte, que tem de vir de quem o
licenciou. Sem ele, as telas de 1-D e de Dispositivo avisam que o motor não
foi encontrado, e o resto do programa funciona normalmente.

### Onde o programa procura

| Motor | Pastas, na ordem |
|---|---|
| SUPREM-III | `suprem-run/`, `suprem_native/suprem-run/`, `native/suprem-run/` |
| SUPREM-IV | `suprem4-run/`, `suprem4/bin/`, `native/suprem4-run/` |
| MINIMOS | `minimos-run/`, `minimos/bin/`, `minimoswin6_1/bin/`, `bin/` |

Todas relativas ao diretório que contém o pacote `mos_studio/`.

## Usar

```sh
mos-studio                      # abre a janela
mos-studio --tema escuro        # terreno desta sessão
mos-studio --tela malha         # abre direto numa tela
mos-studio --diagnostico        # confere a instalação e escreve um relatório
```

| Opção | O que faz |
|---|---|
| `--tema claro\|escuro` | terreno da sessão; sem isto vale o que ficou salvo nas preferências |
| `--tela NOME` | tela em que abrir (os doze nomes estão no `--help`) |
| `--diagnostico` | não abre a janela: monta tudo, confere os três motores e grava `diagnostico.txt` |
| `--capturar PNG` | *(dev)* salva a janela em PNG e sai; com `{tela}` no nome, percorre as doze telas |
| `--tamanho LxA` | *(dev)* tamanho da janela nas capturas, por exemplo `1600x1000` |

`--diagnostico` existe por causa do Windows, onde o programa é uma janela sem
console: se o Qt não achar um plugin, ou o motor não estiver onde devia, não
há para onde escrever o erro. No Linux é a ação **Diagnóstico da instalação**
no menu de contexto do ícone; no Windows, um atalho no menu Iniciar.

As capturas rodam o motor de verdade e correm num `HOME` descartável, para
que as imagens não mostrem o histórico nem as preferências de quem as gerou:

```sh
python -m mos_studio --capturar docs/img/{tela}-claro.png  --tema claro
python -m mos_studio --capturar docs/img/{tela}-escuro.png --tema escuro
```

### As duas dimensões

A chave **1-D / 2-D** no cabeçalho não troca um "modo de visualização": troca
de **motor**, e com ele a navegação, a receita e o que o botão de execução
faz. São dois simuladores diferentes, com dialetos diferentes, e a interface
diz isso em voz alta em vez de esconder.

|  | 1-D — SUPREM-III | 2-D — SUPREM-IV.GS |
|---|---|---|
| O que calcula | perfil em profundidade | a seção transversal inteira |
| Vê difusão lateral, bico de pássaro, junção sob o espaçador | não | sim |
| Malha | implícita (`DX`, `THICKNES`) | do projeto, cartão a cartão |
| Ponte para o MINIMOS | sim | não (o MINIMOS recebe perfil 1-D) |
| Telas | Processo · Resultados · Dispositivo | Malha · Processo · Resultados · Modelos |
| Ferramentas | Oxidação · Exemplos | Console · Estruturas · Exemplos |

Um projeto guarda as duas ao mesmo tempo: trocar de dimensão não apaga o
trabalho da outra.

Traduzir uma receita de um motor para o outro **perde coisas** — epitaxia,
por exemplo. `Engine.approximations` existe justamente para a tela poder
avisar: esconder seria pior que não ter o segundo motor, porque alguém
compararia dois resultados achando que simulou a mesma coisa.

### As doze telas

Dois roteiros guiados entram pela tela de Início: um passeio de treze passos
pelas telas (também em **F1**) e a montagem do transistor LDD do manual,
etapa por etapa, com a seção transversal crescendo a cada etapa.

| Tela | O que é |
|---|---|
| [Início](docs/img/inicio-claro.png) | motores verificados, projetos recentes e os dois roteiros guiados |
| [Exemplos](docs/img/exemplos-claro.png) | duas receitas 1-D de transistor, editáveis como projeto, e os 18 decks de fábrica do SUPREM-IV |
| [Processo 1-D](docs/img/processo-claro.png) | a receita: etapas tipadas, com unidade, faixa e verificação antes de rodar |
| [Resultados 1-D](docs/img/resultados-claro.png) | perfil por etapa, junção e camadas; marque outras execuções para sobrepor as curvas |
| [Dispositivo](docs/img/dispositivo-claro.png) | MINIMOS: curva I-V, mapas 2-D de campo, superfície 3-D e o deck `.inp` editável |
| [Oxidação](docs/img/oxidacao-claro.png) | Deal-Grove: ajusta os coeficientes contra uma varredura e mostra o R² |
| [Malha 2-D](docs/img/malha-claro.png) | linhas, regiões e contornos, com contagem de nós e tempo estimado **antes** de rodar |
| [Processo 2-D](docs/img/processo2d-claro.png) | a mesma receita, no dialeto do SUPREM-IV |
| [Resultados 2-D](docs/img/resultados2d-claro.png) | seção transversal com contornos de dopagem, corte 1-D em qualquer `x` e a junção ali |
| [Modelos](docs/img/modelos-claro.png) | os coeficientes que o motor vai usar, lidos dele próprio |
| [Console](docs/img/console-claro.png) | o motor em sessão, carta por carta, com a saída crua |
| [Estruturas](docs/img/estrutura-claro.png) | os arquivos que a simulação deixou |

## O que o motor faz, e o que ele finge fazer

Os três simuladores são de outra era e têm armadilhas que custam horas se
ninguém as escrever. Estas estão **conferidas no binário**, e a interface já
trabalha em volta de cada uma. O registro completo está em
[`docs/adr/`](docs/adr/).

### SUPREM-IV.GS

| Armadilha | O que acontece |
|---|---|
| Nomes de **parâmetro** truncam em 11 caracteres (`char name[12]`) | `method interstitial` é recusado, `interstitia` passa; `deposit concentration=` é recusado, `conc=` passa. Nomes de *cartão* não sofrem |
| `diffuse temp` é em **Celsius** | apesar de o próprio arquivo de chaves dizer Kelvin |
| Não existe ambiente `inert`, nem cartão `impurity` | use `nitrogen`/`argon`; o cartão é o nome da espécie (`arsenic silicon Dix.0=…`) |
| **Cabeçalho desconhecido vai para o `/bin/sh`** | um `rm -rf` digitado no Console executaria. `suprem4.unknown_cards()` barra antes de mandar |
| `define temp 1000` reescreve a palavra `temp` em todo comando seguinte | e `undef temp` falha, porque o argumento também é substituído: só reiniciando |
| A coluna *thickness* do `print.1d layers` é **posição de interface** | não espessura; e a primeira linha é o topo da pilha, não uma camada |
| `z=doping` é dopagem **ativa** | um implante só aparece depois de recozer |
| A malha é progressão geométrica, razão ≤ 1,5 | tratá-la como interpolação linear erra ~10% na contagem de nós. `core/mesh.py` transcreve a função do motor |
| **Não há camada gráfica** | `plot.2d` e `contour` são talões vazios. A seção transversal é montada varrendo o dispositivo com cortes `print.1d x.value=` e desenhando a partir dos números |

### MINIMOS 6.1

| Armadilha | O que acontece |
|---|---|
| `MODEL=2-D` segfalha sem `UG` no cartão `BIAS`, ou com dreno exatamente zero | o gerador sempre emite `UG` e usa piso de 0,1 V |
| `TIME` do cartão `PROFILE` é em **segundos** | os exemplos usam 2700 = 45 min. Passar minutos dá recozimento curto demais para formar junção, e o motor morre com SIGSEGV em vez de reclamar |
| `PROFILE FILE=2-D` (perfil binário) **aborta** dentro do motor | a ponte com o SUPREM passa pelo cartão analítico, e a interface diz que é re-simulação, não transporte ponto a ponto |

### Os coeficientes vêm do motor, em duas camadas

A tela de Modelos não traz tabela escrita à mão: lê o `modelrc` primeiro e o
arquivo de chaves depois. Os dois **discordam** — o arquivo de chaves diz
`interstitial D.0 = 1e-9` e o `modelrc` sobrescreve com `1.03e6`. A tela
mostra qual venceu.

## Quando dá errado

| Sintoma | Causa | O que fazer |
|---|---|---|
| O programa não abre e não há mensagem | no Windows não existe console para onde escrever o erro | **Diagnóstico** (menu Iniciar, ou `--diagnostico`); ele grava `diagnostico.txt`, e `ultima-execucao.log` fica ao lado do programa |
| "motor não encontrado" numa tela | o simulador não foi compilado, ou está fora das pastas conhecidas | ver [Os motores](#os-motores-e-como-obtê-los); o diagnóstico diz exatamente qual arquivo falta |
| A junção some com uma malha muito fina | acima de ~9.000 nós o SUPREM-IV cai sozinho | a tela de Malha avisa antes de rodar; refine só onde interessa |
| Uma malha mais fina dá junção mais **rasa** | isso está certo: o valor converge ao refinar (0,172 → 0,149 µm) | confira com `print.1d layers`, que é a conta do próprio motor |
| Um cartão foi recusado e a execução "terminou bem" | o SUPREM-IV sai com código 0 mesmo recusando cartas | por isso `suprem4.engine_errors()` lê a saída em vez de confiar no código de saída; a mensagem aparece na tela |
| O implante não aparece no perfil | `z=doping` é dopagem ativa | recozimento primeiro |
| O MINIMOS morre com SIGSEGV em vez de reclamar | quase sempre é tempo em minutos onde ele espera segundos | ver a tabela acima |
| A execução parece travada numa receita 2-D pesada | pode mesmo levar minutos | a faixa de execução mostra a etapa corrente, e cancela a qualquer momento |

## Limitações conhecidas

- **Os motores não vêm no repositório**
  ([Os motores](#os-motores-e-como-obtê-los)).
- **No Windows só há SUPREM-IV.** SUPREM-III e MINIMOS não têm versão de
  Windows porque o código-fonte deles não acompanha o projeto; com os fontes,
  os dois builds já estão preparados.
- **O SUPREM-IV não desenha.** Toda figura 2-D é remontada de tabelas
  numéricas — é fiel aos números, não é a saída gráfica do motor original.
- **O perfil não é transportado ponto a ponto para o MINIMOS**, e sim
  reconstruído a partir de parâmetros; a tela de Dispositivo diz isso nela
  mesma.
- **Acima de ~9.000 nós o SUPREM-IV cai.** O limite foi encontrado por
  bisseção (10.653 passa, 11.256 segfalha) e está em `core/mesh.py`.
- O SUPREM-III para em **500 pontos de malha**.
- **O pacote de Windows não é assinado**: o SmartScreen avisa na primeira
  execução.

## Onde ficam as coisas

| O quê | Linux | Windows |
|---|---|---|
| Preferências | `~/.config/mos-studio/config.json` | `%APPDATA%\mos-studio\config.json` |
| Simulações | a pasta de trabalho escolhida na tela de Início | idem |
| Saídas ao lado do programa | `resultados/` | `resultados\` |
| Relatório de diagnóstico | `diagnostico.txt` ao lado do programa | idem, mais `ultima-execucao.log` |

A configuração do usuário **nunca** fica ao lado do programa — é a regra
única de [`mos_studio/paths.py`](mos_studio/paths.py).

## Arquitetura

```
mos_studio/
  core/        o núcleo, sem nenhuma dependência de interface
    engines.py     os dois motores de processo sob uma interface só
    suprem.py      SUPREM-III: três binários em cadeia, tabela em arquivo
    suprem4.py     SUPREM-IV: um binário, tabela na saída padrão
    shell4.py      sessão persistente do SUPREM-IV (é o que a tela Console usa)
    minimos.py     MINIMOS: deck, execução e leitura
    bridge.py      o que a receita do SUPREM entrega ao MINIMOS
    recipe.py      recipe4.py    as receitas, por motor
    deck.py        deck4.py      a receita virada deck
    parsers.py     as tabelas do motor viradas números
    mesh.py        a malha 2-D, com a progressão geométrica do próprio motor
    field2d.py     a seção transversal montada a partir dos cortes
    keyfile.py     modelrc.py    models4.py    os coeficientes, lidos do motor
    examples3.py   examples4.py  tour.py       exemplos e roteiros guiados
    oxidation.py   evolution.py  library.py    workspace.py
  ui/
    theme/       tokens do design, fontes e geração do QSS
    screens/     as doze telas
    widgets/     cabeçalho, gráficos, seção transversal, malha, rodapé
  diagnostico.py  o relatório de instalação
  capturas.py     as imagens desta página
  paths.py        onde tudo é lido e escrito
```

Cerca de 20.000 linhas no pacote e 7.500 nos testes.

A interface nunca fala com um motor diretamente: pede ao `core`, que devolve
dados. É por isso que a suíte consegue exercitar quase tudo sem abrir janela.

## Testes

```sh
python -m unittest discover -s tests -t .
```

O `-t .` é obrigatório — sem ele os imports de `tests/legacy.py` falham.
**Não há pytest**, de propósito: a suíte usa só a biblioteca padrão.

**856 testes.** Boa parte **sobe o motor de verdade** e compara números: é
lenta (uns nove minutos) por escolha, e foi assim que as armadilhas da seção
anterior apareceram. Os testes que precisam de um motor, ou do PySide6, se
auto-pulam quando ele não está instalado — então a suíte passa num clone
limpo, só com menos casos.

Uma validação que vale repetir ao mexer na oxidação: a varredura deve dar
B ≈ 0,292 µm²/h contra 0,287 tabelado (Deal & Grove, 1965), com R² = 1,0000.

## Windows

O aplicativo roda igual no Windows 10/11 64 bits. O que muda:

- **só o SUPREM-IV está disponível**
  ([Limitações conhecidas](#limitações-conhecidas));
- a configuração vai para `%APPDATA%` em vez de `~/.config`;
- toda execução grava `ultima-execucao.log` ao lado do programa, porque um
  programa de janela não tem saída padrão para onde reclamar.

Levar o SUPREM-IV para o Windows não foi recompilar e pronto: o motor tinha
**quatro defeitos de portabilidade** escondidos desde 1993, que o Linux
perdoava por sorte. O pior é um ponteiro do parser recebido como `int` em 58
lugares — no Linux o endereço cabe em 32 bits, no Windows o heap fica acima
de 4 GB, e o motor morria lendo um ponteiro truncado **sem mensagem nenhuma**
(a saída ainda estava no buffer).

Depois dos remendos, a saída do Windows é **byte a byte idêntica** à do Linux
no perfil final e na tabela de camadas. As únicas linhas que diferem são a
norma residual do solver já convergido e as colunas de tempo de CPU.

A história inteira, com os endereços e os números, está em
[`docs/adr/0003-versao-de-windows.md`](docs/adr/0003-versao-de-windows.md) —
inclusive por que o **wine não serve para validar**: o defeito do ponteiro é
invisível nele, porque o heap do wine também fica abaixo de 4 GB.

## Empacotar

### O pacote de Linux

```sh
./empacotar/montar_linux.sh        # dist/mos-studio-<versão>-linux-x86_64.tar.gz
```

Leva o programa, os dados, o motor 2-D e o instalador — menos de 1 MB.
**Não** leva um Python próprio: aqui o programa usa o Python e o PySide6 do
sistema, que toda distribuição tem a um comando de distância. Embutir uma
segunda cópia do Qt para repetir o que já está instalado seria desperdício;
o `instalar.sh` confere as duas dependências e diz o que falta.

### O pacote e o instalador de Windows, gerados no Linux

```sh
./build_suprem4_windows.sh            # compila o motor com mingw
./empacotar/montar_windows.py         # monta o pacote    (~108 MB)
./empacotar/instalador_windows.py     # gera o instalador  (~31 MB)
```

Pré-requisitos: `mingw64-gcc` e `wine`. O wine **não roda nada do
MOS-Studio** — só o compilador do NSIS, que lê um script e escreve um `.exe`.

Nada de PyInstaller: ele precisaria rodar dentro do Windows, porque embute o
interpretador da máquina onde roda. O pacote é montado à mão a partir de
peças oficiais — a distribuição *embeddable* do python.org, as rodas
`win_amd64` do PySide6 e do shiboken6, o motor compilado aqui e um lançador
de cem linhas de C. Cada peça baixada tem o SHA-256 conferido contra um valor
fixado no script.

O Qt é podado por **fecho transitivo**, não por uma lista mantida à mão: o
script lê a tabela de importação de cada binário que fica e segue as
dependências dentro do pacote. Uma lista escrita à mão envelheceria a cada
versão do PySide6. São 212 MB que caem para 79 MB.

### Verificar no Windows de verdade

Com uma máquina virtual libvirt chamada `office` rodando o
`qemu-guest-agent`, sem precisar de tela:

```sh
./empacotar/testar_windows.py --enviar   # o pacote sobe e roda lá dentro
./empacotar/testar_instalador.py         # instala, usa e desinstala
```

O primeiro confere que o Python e o Qt do pacote sobem, que o diagnóstico
passa com e sem o plugin nativo do Qt, que o motor simula pelo programa e que
o `MOS-Studio.exe` roda. O segundo faz o ciclo inteiro: instala em silêncio,
confere os arquivos, o atalho no menu Iniciar e a entrada em "Aplicativos
instalados", roda o programa instalado e desinstala **preservando as
simulações**.

Os dois acharam defeito real — entre eles um salto relativo errado no
desinstalador, que deixava o executável para trás.

## Design

Interface no sistema **Phareon** — sistema de design do autor, mantido fora
deste repositório e não publicado. Dois terrenos, claro (o padrão, porque a
bancada trabalha com luz acesa) e escuro, com os mesmos nomes semânticos
resolvidos em [`ui/theme/`](mos_studio/ui/theme/): nenhum widget sabe em que
terreno está, e não há hex no código da interface.

Onde o Qt não alcança o arquivo de design — gradientes animados, transições
em QSS — o desvio está anotado, um a um, em
[`docs/fidelidade-visual.md`](docs/fidelidade-visual.md). A regra é registrar
a diferença, não fingir que ela não existe.

## Créditos e licença

- **SUPREM-III** (Release B, rev. 8628) e **SUPREM-IV.GS** (B.9305) —
  Stanford University e University of Florida. *All rights reserved* nos
  cabeçalhos do fonte. **Não incluídos neste repositório.**
- **MINIMOS 6.1** — Institut für Mikroelektronik, TU Wien. **Não incluído
  neste repositório.**
- **Deal & Grove (1965)** — o modelo de oxidação térmica e a tabela contra a
  qual a tela de Oxidação é validada.
- **Tipografia** — Bricolage Grotesque, Geist, Geist Mono e Instrument Serif,
  todas sob **SIL Open Font License**.

**A licença do código deste repositório ainda não foi definida.** Até que
seja, vale o padrão legal: *todos os direitos reservados*.
