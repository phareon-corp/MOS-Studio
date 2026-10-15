# ADR 0003 — Versão de Windows

- **Data:** 2026-10-14
- **Situação:** aceita, com uma limitação declarada (ver "Consequências")
- **Escopo:** porte do SUPREM-IV.GS para Windows, pacote autossuficiente,
  instalador e verificação em Windows de verdade

## Contexto

O MOS-Studio existia só no Linux. A interface é PySide6 e já era portável; o
que amarrava eram os três motores nativos — SUPREM-III, SUPREM-IV.GS e
MINIMOS 6.1 — e a ausência de qualquer forma de instalar o programa no
Windows.

Este ADR registra três coisas: o que foi decidido, **os quatro bugs de
portabilidade que o motor de 1993 tinha escondidos** (e que só apareceram no
Windows de verdade), e o que ficou de fora.

## Decisões

### 1. Compilação cruzada do motor, a partir do Linux

O `build_suprem4_windows.sh` compila o SUPREM-IV.GS com
`x86_64-w64-mingw32-gcc`. Nada é compilado dentro do Windows.

O motivo é que o Linux já é onde o fonte é clonado, remendado e testado
(ADR 0002). Compilar lá mantém *uma* receita de build, versionada, com os
mesmos patches valendo para os dois sistemas. Um toolchain instalado à mão
dentro de uma máquina virtual seria um segundo ambiente a manter, invisível
para o histórico do projeto.

Uma camada de compatibilidade POSIX de quatro funções entra no lugar do que o
mingw não tem — `times()`, `fork()`, `wait()`, `getpwuid()`/`getpwnam()`.
Nenhuma delas está no caminho do cálculo; o levantamento de onde o fonte as
usa está em `patches/suprem4/win-compat/README.md`.

Duas coisas dessa camada merecem destaque:

- **modo binário por padrão.** O arquivo de chaves compilado (`suprem.uk`) é
  binário e o fonte o abre com um `open()` simples, sem `O_BINARY`, porque no
  Unix não existe outra coisa. No Windows o padrão é modo texto: cada `0x0A`
  vira `0x0D 0x0A`. Medido: o mesmo `suprem.uk` saía com 67.559 bytes em vez
  de 67.535, e o motor o recusava. A correção é um construtor que põe
  `_fmode = _O_BINARY` antes do `main` — e **não** a variável `_CRT_fmode`
  que a documentação antiga sugere, que nesta versão do mingw-w64 não surte
  efeito.
- **`__USE_MINGW_ANSI_STDIO=1`.** O `printf` do msvcrt imprime expoente com
  três dígitos (`6.1e-015`), herança do MSVC antigo. Com a macro, o
  `printf` do próprio mingw é usado e a saída fica idêntica à do Linux.

### 2. Os quatro bugs de portabilidade do motor

Todos estão em `patches/suprem4/`, todos valem nos dois sistemas, e nenhum é
um remendo específico de Windows: são defeitos reais que o Linux perdoava.

#### `0002` — tipos de tempo

`misc/cpu.c` redeclara `extern long time();` e guarda o resultado num `long`.
No Linux de 64 bits `long` e `time_t` têm o mesmo tamanho e funciona por
acaso. No Windows `long` tem 32 bits, `time_t` tem 64, e o compilador recusa.

#### `0003` — `HOME` ausente

O fonte lê `getenv("HOME")` em dois lugares e usa o resultado sem conferir se
veio nulo. Um deles é `strcpy(dot_name, getenv("HOME"))`, em `main.c`. No
Windows a variável não existe — o equivalente é `USERPROFILE` — e o processo
morria lendo do endereço zero, logo depois de carregar o arquivo de chaves,
**sem nenhuma mensagem**: a saída ainda estava no buffer.

#### `0004` — `param` declarado `int` (o bug que importava)

O parser chama cada comando assim, em `shell/do_action.c`:

```c
command[index].func( par, cards[command[index].param] );
```

O segundo argumento é um `struct par_str *`. Mas **58 funções de carta, em 48
arquivos, o recebem declarado `int param`** — um comentário no `mesh/rect.c`
chega a chamá-lo de "magic cookie for the parser". Como as funções são
chamadas por um ponteiro sem protótipo (`PTR_FUNC`), o compilador nunca viu a
incompatibilidade.

No Linux funciona por sorte: o binário não é PIE, os dados estáticos e o heap
do `brk` ficam nos primeiros megabytes, e os 32 bits de cima do ponteiro são
zero. Truncar não perde nada.

No Windows de 64 bits o heap fica acima de 4 GB. O truncamento joga fora a
metade de cima e a primeira função que usa a lista morre:

```
EXCECAO codigo=0xC0000005 (violacao de acesso, leitura)
endereco=0x8371A300   <- os 32 bits de baixo de um ponteiro do heap
```

Depois da troca de tipo, o fonte inteiro compila para Windows com
`-Wint-conversion -Wpointer-to-int-cast -Wint-to-pointer-cast
-Wincompatible-pointer-types` **sem um único aviso de conversão entre inteiro
e ponteiro**. É o que dá confiança de que não há um segundo truncamento
escondido.

#### `0005` — `main` sem `return`

`main` tem tipo implícito `int` e termina sem `return`. O que o processo
devolve é indefinido; no Linux sobrava zero, no Windows sobrava 1. O
`core/suprem4.py` trata código diferente de zero como falha, então **toda**
simulação no Windows seria recusada com uma mensagem inventada, apesar de a
saída estar correta.

### 3. O wine serve para compilar, não para validar

Os dois primeiros bugs apareceram no compilador. O terceiro e o quarto não:
**o `0004` é invisível sob wine**, porque o heap do wine também cai embaixo
de 4 GB. O binário rodava no wine e morria no Windows.

A conclusão virou regra: o wine entra para rodar o compilador do NSIS (um
programa de Windows que só lê um script e escreve um .exe) e como teste de
fumaça rápido durante o build. **Quem diz se o pacote presta é a máquina
virtual de Windows.**

### 4. Pacote autossuficiente, montado no Linux, sem PyInstaller

O PyInstaller precisaria rodar dentro do Windows: ele embute o interpretador
da máquina onde roda. Em vez disso, `empacotar/montar_windows.py` monta o
pacote à mão a partir de peças oficiais, no Linux:

- a distribuição *embeddable* do python.org (um .zip, sem instalador);
- as rodas `win_amd64` do PySide6-Essentials e do shiboken6, do PyPI;
- o `suprem4-run-win/` compilado aqui;
- um lançador `MOS-Studio.exe` de cem linhas de C, com ícone e ficha de
  versão.

Cada peça baixada tem o SHA-256 conferido contra um valor fixado no script.

O Qt é podado por **fecho transitivo**, e não por uma lista mantida à mão: o
script lê a tabela de importação de cada binário que fica (os três módulos
que a interface usa — `QtCore`, `QtGui`, `QtWidgets` — e os plugins) e segue
as dependências dentro do pacote. Uma lista escrita à mão envelheceria a cada
versão do PySide6. Resultado: 212 MB caem para 79 MB, 108 MB no total.

O caminho dos dados não precisou de nada especial: `mos_studio/paths.py` já
procurava os motores ao lado do pacote, e o motor vai para `suprem4-run/`,
exatamente o nome que ele procura.

### 5. O lançador usa `python.exe`, não `pythonw.exe`

O caminho óbvio seria o `pythonw.exe`, a versão sem console. Mas com ele o
processo nasce sem saída padrão: `sys.stdout` e `sys.stderr` valem `None`, e
qualquer erro desaparece — o usuário clica e nada acontece. Foi assim que o
primeiro `MOS-Studio.exe` falhou no teste da VM: o relatório de diagnóstico
morria num `AttributeError` ao escrever em `None`.

A decisão é `python.exe` com `CREATE_NO_WINDOW`: também não abre console, e
aí dá para apontar a saída para um arquivo. Toda execução grava
`ultima-execucao.log` ao lado do programa.

### 6. `--diagnostico`: a voz do programa quando ele não abre

`mos_studio/diagnostico.py` monta a janela principal inteira, confere os três
motores, encerra as threads e escreve um relatório — em arquivo, porque no
Windows pode não haver console. Existe por causa do Windows, mas vale nos
dois sistemas: no Linux é a ação "Diagnóstico da instalação" no menu de
contexto do ícone; no Windows, um atalho no menu Iniciar.

É também o que a máquina virtual executa para dizer se o pacote ficou bom.

### 7. Instalador por usuário, sem pedir senha de administrador

`empacotar/instalador.nsi`, compilado com o NSIS sob wine, instala em
`%LOCALAPPDATA%\Programs\MOS-Studio`. Três razões:

1. não aciona o aviso de elevação, que para muita gente é onde a instalação
   termina (o pacote não é assinado);
2. `Program Files` é somente leitura, e o MOS-Studio grava as simulações em
   `resultados\`, ao lado de si mesmo, como no Linux;
3. tudo que o instalador cria — atalhos, registro — ele remove.

A desinstalação **pergunta** antes de apagar `resultados\`: é trabalho do
usuário, não arquivo de programa. Em modo silencioso, preserva.

### 8. Verificação dentro do Windows, sem tela

A VM de Windows desta máquina é isolada: não enxerga o host pela rede, e a
pasta compartilhada só existe durante uma sessão RDP. O caminho usado é o
`qemu-guest-agent`, que roda programas e escreve arquivos no convidado.
`empacotar/vmagente.py` embrulha isso; `vm-push` e `vm-run` são as
ferramentas de mão.

Dois detalhes que custaram tempo e estão documentados no módulo:

- cada argumento de linha de comando no Linux tem teto de 128 kB
  (`MAX_ARG_STRLEN`), então os arquivos sobem em pedaços de 48 kB de base64;
- a VM tem um vigia que a congela (`managedsave`) depois de dois minutos sem
  cliente RDP, e um build demora mais que isso. O `managedsave` guarda o
  estado inteiro, então o módulo religa a VM e repete o comando; para quem
  chama é só uma pausa.

Dois scripts de teste rodam no Windows de verdade:

- `empacotar/testar_windows.py` — o Python e o Qt do pacote sobem, o
  diagnóstico passa (com e sem o plugin nativo do Qt), o motor simula pelo
  programa, o `MOS-Studio.exe` roda;
- `empacotar/testar_instalador.py` — instala em silêncio, confere os 274
  arquivos, o atalho e a entrada em "Aplicativos instalados", roda o programa
  instalado e desinstala preservando as simulações.

Os dois acharam defeito real. O segundo pegou um erro de salto relativo no
desinstalador (`IfSilent +5` pulava uma instrução além da conta e deixava o
`MOS-Studio.exe` para trás); os desvios do `.nsi` agora são por rótulo.

## Consequências

### O que funciona

O SUPREM-IV.GS roda no Windows com a saída **byte a byte idêntica** à do
Linux no perfil final e na tabela de camadas. As únicas linhas que diferem
são a norma residual do solver já convergido — arredondamento de `libm`, na
terceira casa de um resíduo da ordem de 1e-5 — e as colunas de tempo de CPU.

### O que não funciona: SUPREM-III e MINIMOS 6.1

**Não há versão de Windows desses dois motores, e não pode haver sem o
código-fonte deles.** O que existe nesta máquina são os binários Linux já
compilados (`suprem-run/`, `minimos-run/`); os fontes — `relB_8628_tar.Z` e a
pasta `minimoswin6_1` — não estão aqui, e binários ELF não rodam no Windows.

Consequência para quem usa o pacote de Windows: só o SUPREM-IV (2-D) está
disponível. As telas que dependem dos outros dois avisam que o motor não foi
encontrado, e `engines.default_id()` já escolhe o único instalado. O
`LEIA-ME.txt` do pacote diz isso em voz alta.

Para destravar, bastam os dois arquivos de fonte. Os dois builds já estão
escritos e preparados para Windows: `build_suprem.sh` detecta o sistema e
gera `.exe`, `build_minimos.sh` documenta o caminho MSYS2 MINGW64, e o
`mos_studio/paths.py` já procura `sup3.exe`/`genii.exe` e `mm_pl.exe`. Falta
só o fonte. Para a compilação cruzada seria preciso também o
`mingw64-gcc-gfortran`, que está disponível no Fedora.

### Dívida assumida

- **O pacote não é assinado.** O SmartScreen vai avisar na primeira execução.
  Assinar exige um certificado de autoria de código, que é uma decisão
  comercial, não técnica.
- **A versão do PySide6 está fixada** (6.11.1, a mesma do Linux de
  desenvolvimento) com hash. Atualizar é trocar duas linhas do
  `montar_windows.py` e rodar os testes da VM — de propósito: é o passo que
  tem de ser verificado, não automatizado.
