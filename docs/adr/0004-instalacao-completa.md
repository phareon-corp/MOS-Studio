# ADR 0004 — Instalação completa, com os motores

- **Data:** 2026-11-19
- **Situação:** aceita
- **Escopo:** o que o `instalar.sh` e o instalador de Windows entregam; de
  onde vêm os motores; o MINIMOS

## Contexto

Quem clonava o repositório num computador novo e rodava o `instalar.sh`
ficava sem interface e sem motores. O instalador só **conferia**: dizia que
faltava o PySide6 e sugeria `pip install --user PySide6` — que o Ubuntu e o
Debian recentes recusam (PEP 668, "externally-managed-environment"). Não
compilava nenhum motor; o SUPREM-IV exigia rodar outro script, e o
SUPREM-III e o MINIMOS dependiam de fontes que "não podiam ser
redistribuídos". No Windows só havia o SUPREM-IV.

Três fatos mudaram o quadro:

1. **O SUPREM-III e o SUPREM-IV podem ser redistribuídos.** A página de
   software antigo do grupo de TCAD de Stanford publica os dois com a nota
   "Except for commercial resale, lease, license or other commercial
   transactions, permission is hereby given to use, copy, modify, and
   distribute this software". O `.gitignore` e o README diziam o contrário
   ("all rights reserved" no cabeçalho do fonte), mas a nota de
   distribuição é a que vale.
2. **O MINIMOS não pode.** A TU Wien o entrega de graça só a usuários
   registrados, e a licença diz que ele "shall be kept confidential by
   LICENSEE and are not to be disclosed or transferred to any party".
3. **O zip do MINIMOS para Windows já traz o `mm_pl.exe` compilado** (Compaq
   Visual Fortran, 1999, só depende do `KERNEL32`).

## Decisões

### 1. O fonte dos motores de Stanford vai no repositório

`fontes/` guarda o `relB.8628.tar.Z` (SUPREM-III, como Stanford o publica)
e o SUPREM-IV da Cogenda num commit fixo (`eb25a07`, contra o qual os
`patches/` foram feitos), conferidos por `SHA256SUMS`. São 2 MB. A
alternativa era baixar na hora, mas o servidor de Stanford é de 2004 e o
tarball do GitHub muda de hash quando é recomprimido.

### 2. O `instalar.sh` instala e compila tudo

Em cinco etapas: pacotes do sistema pelo gerenciador da distribuição (dnf,
apt, pacman, zypper — com `sudo`, só se faltar algo), um ambiente Python
próprio em `~/.local/share/mos-studio/venv` com o PySide6, os motores, o
lançador e uma conferência que monta a janela inteira. Rodar de novo pula o
que está pronto.

A lista de pacotes inclui as bibliotecas que o plugin `xcb` do Qt 6 carrega
(`xcb-cursor` é a que mais falta numa instalação nova; sem ela a janela não
abre e não diz por quê). O instalador confere com `ldd` o plugin que
efetivamente veio na roda do PySide6.

### 3. O pacote de Linux leva fonte, não binário

Um binário de Fortran compilado numa distribuição depende da `libgfortran`
e da `glibc` dela. Compilar na máquina de quem instala leva dois minutos e
funciona em qualquer uma.

### 4. O instalador de Windows leva o SUPREM-III

Compilação cruzada com `mingw64-gcc-gfortran`, ligação estática (sem DLL do
gfortran). Os coeficientes `S3cof0`/`S3uky0` são gerados rodando o motor —
o que não dá para fazer com um `.exe` no Linux — e por isso são copiados do
build nativo: o formato sem formatação do gfortran é o mesmo nos dois
sistemas. Conferido na VM: a mesma receita dá a mesma espessura de óxido
(0,2260 µm) e dopagem integrada igual até o 4º dígito.

### 5. O MINIMOS vem do zip do usuário

`core/importar_minimos.py`, usado pelo `instalar.sh` (que procura o zip em
`~/Downloads` ou recebe `--minimos ZIP`), por `mos-studio
--instalar-minimos ZIP` e por um botão na tela de Dispositivo. No Windows
copia o `mm_pl.exe` do zip; no Linux compila o fonte do zip com o
`build_minimos.sh`.

## Defeitos encontrados no caminho

- **GCC 15 não compila o SUPREM-III.** O Fedora 42+ compila C em C23 por
  padrão, onde `char *getenv();` declara uma função de zero argumentos, e a
  chamada `getenv(nome)` vira erro. O Ubuntu 24.04 (GCC 13) passava.
  `build_suprem.sh` passa `-std=gnu89` aos Makefiles.
- **Caminho de mais de 80 caracteres derrubava o SUPREM-III**, no Linux e no
  Windows. O nome dos arquivos de dados cabe num `character*80`
  (`opnfl-L.f`); acima disso o genii parava com "ERROR # 33 — File system
  error #2 ... formatted specification file". Bastava clonar numa pasta
  funda, ou ter um nome de usuário comprido no Windows. Agora os dados são
  copiados para a pasta de trabalho de cada execução e passados pelo nome
  curto (276 KB; não vão para `resultados/`). Há teste de regressão.
- **O `mm_pl.exe` original abortava sem console.** O runtime do Compaq
  escreve a unidade 6 no `CONOUT$`; o programa roda o motor com
  `CREATE_NO_WINDOW`, e a primeira escrita dava `forrtl: severe (38)`.
  Com `FORT6` apontando para um arquivo, a unidade 6 vira um arquivo comum.
- **O diagnóstico sem tela esperava para sempre** por um clique num diálogo
  invisível (plataforma `offscreen`), e o instalador ficava parado no fim.

## Verificação

- contêineres limpos de **Fedora 44** e **Ubuntu 24.04**, com usuário comum
  e `sudo`, a partir só do conteúdo do repositório: o `instalar.sh` termina
  com os três motores prontos e `empacotar/testar_motores.py` roda uma
  simulação curta em cada um;
- **Windows 11** na VM: `testar_instalador.py` (ciclo completo) e
  `testar_motores_windows.py`, que instala numa pasta de caminho longo,
  instala o MINIMOS pelo zip e simula nos três motores.

## Consequências

- O programa funciona inteiro nos dois sistemas; o único passo manual que
  sobra é trazer o zip do MINIMOS, e isso é imposição da licença.
- `LEIA-ME_engine.txt` saiu (descrevia a pasta `suprem-run/` pronta da era
  do DOSBox); `INSTALACAO.txt` virou um resumo do README.
