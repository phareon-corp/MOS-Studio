# Fontes dos motores de Stanford

Os dois arquivos desta pasta são o código-fonte original dos simuladores de
processo que o `instalar.sh` compila. Ficam no repositório para que a
instalação não dependa de servidores dos anos 1990 continuarem no ar.

| Arquivo | O que é | De onde veio |
|---|---|---|
| `suprem3-relB.8628.tar.Z` | SUPREM-III, Release B.8628 (1-D) | <http://www-tcad.stanford.edu/oldftp_sw/Suprem-III/relB.8628.tar.Z> |
| `suprem4-cogenda-eb25a07.tar.gz` | SUPREM-IV.GS com os remendos da Cogenda (2-D) | <https://github.com/cogenda/suprem4>, commit `eb25a07` |

`SHA256SUMS` confere os dois; os scripts `build_suprem.sh` e
`build_suprem4.sh` recusam um arquivo com hash diferente.

## Licença

Os dois estão sob a mesma nota de Stanford, publicada na página de
software antigo do grupo de TCAD
(<http://www-tcad.stanford.edu/tcad/programs/oldftpable.html>):

> © Copyright (1994) The Board of Trustees of the Leland Stanford Junior
> University. Except for commercial resale, lease, license or other
> commercial transactions, permission is hereby given to use, copy, modify,
> and distribute this software. STANFORD MAKES NO REPRESENTATIONS OR
> WARRANTIES OF ANY KIND CONCERNING THIS SOFTWARE.

Ou seja: podem ser copiados e redistribuídos, desde que não sejam vendidos
nem licenciados comercialmente.

## E o MINIMOS?

Não está aqui, e não pode estar. O MINIMOS 6.1 é da TU Wien, que o entrega
de graça só a usuários registrados, com uma licença que proíbe repassá-lo.
Quem tem o `minimoswin6.1.zip` o instala com `./instalar.sh --minimos ZIP`
(ou pelo botão na tela de Dispositivo). Registro:
<https://www.iue.tuwien.ac.at/software/download/download-area>.
