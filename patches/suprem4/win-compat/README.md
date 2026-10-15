# Camada de compatibilidade POSIX para o SUPREM-IV no Windows

O fonte é C de 1993 escrito para Unix. O que ele usa de POSIX, porém, é
estreito e está todo em caminhos acessórios — levantado grepando o fonte
inteiro:

| símbolo | onde | para quê |
|---|---|---|
| `times()`, `struct tms` | 28 usos, em `implant/`, `dbase/`, `diffuse/` | medir tempo de CPU para o relatório |
| `fork()`, `wait()` | `shell/do_action.c`, `shell/parser.c` | rodar um comando em segundo plano (`&`) |
| `getpwuid`, `getpwnam` | `xsupr4/Graph.c` | achar o `~` do usuário |
| `sys/file.h`, `sys/param.h` | `diffuse/solve.c`, `include/sysdep.h` | só pelos `#include` |

Nenhum deles participa do cálculo. O `xsupr4/` nem é compilado (é a camada
X11, substituída por talões — ver `build_suprem4.sh`), e o MOS-Studio nunca
usa `&`: o shell em segundo plano não tem como ser acionado pela interface.

Por isso a camada aqui é de cabeçalhos vazios mais um punhado de funções, em
vez de remendos no fonte nesses pontos. O fonte original fica intocado nessa
parte, e o build do Linux não muda em nada.

## As duas coisas que não são funções

O `win_compat.c` também tem um construtor que roda antes do `main` e ajusta
duas coisas do ambiente que o fonte presume existir:

- **`_fmode = _O_BINARY`.** O `suprem.uk` é binário e o fonte o abre com um
  `open()` sem `O_BINARY`, porque no Unix não existe outra coisa. Sem isto o
  arquivo sai com CRLF (67.559 bytes em vez de 67.535) e o motor o recusa. É
  um construtor, e não a variável `_CRT_fmode` que a documentação antiga
  sugere: nesta versão do mingw-w64, atribuir `_CRT_fmode` não surte efeito.
- **`HOME`, a partir de `USERPROFILE`.** O fonte monta o caminho do
  `~/.supremrc` a partir de `HOME`, que no Windows não existe. O patch
  `0003` impede que a ausência derrube o processo; isto é o outro lado, para
  que o arquivo de preferências do usuário continue sendo lido.

## O que NÃO cabe aqui

Os quatro defeitos de portabilidade do próprio motor são remendos no fonte,
em `patches/suprem4/0002` a `0005`, e não camada de compatibilidade: valem
igual no Linux, onde funcionavam por sorte. O mais consequente é o `0004`, o
`param` declarado `int` — ver `docs/adr/0003-versao-de-windows.md`.
