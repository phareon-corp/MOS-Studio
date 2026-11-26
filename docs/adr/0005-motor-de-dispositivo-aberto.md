# ADR 0005 — Motor de dispositivo aberto (MOSIM), compatível com o MINIMOS

- **Data:** 2026-11-21
- **Situação:** aceita (primeira versão)
- **Escopo:** `mos_studio/mosim/`, a escolha de motor na tela de Dispositivo,
  as dependências numpy/scipy

## Contexto

O MINIMOS 6.1 não pode vir com o programa (ADR 0004): pela licença da TU Wien,
cada usuário precisa baixar o seu. Sem ele, a tela de Dispositivo ficava
inútil. O objetivo pedido: quem trabalha com o MINIMOS deve obter os mesmos
valores com um motor que possa ser distribuído.

## Decisão

1. **Um simulador próprio, em Python (numpy/scipy), que lê os decks do
   MINIMOS e grava as saídas no formato dele** (`.out`, `.ref`, `.iv` e o PIF
   dos mapas). A interface lê essas saídas sem mudança.
2. **Os modelos vêm do manual do MINIMOS 6 e da literatura**, nunca do
   código-fonte do MINIMOS:
   - mobilidade (eqs. 2.1–2.19 do manual), n_i e E_g (2.38–2.43), funções
     trabalho da chave GATE, velocidades de saturação;
   - equações: Poisson no domínio todo (silício e isolante) e continuidade
     dos minoritários com Scharfetter–Gummel; majoritários com quase-Fermi
     constante; sem geração–recombinação. É o modelo "2-D" do manual; o
     MODEL=THRES usa o mesmo laço;
   - perfil analítico das diretivas PROFILE/IMPLANT: gaussiana implantada,
     difusão com superfície refletora (solução exata), borda lateral em erfc.
3. **O que o manual não diz foi medido na saída do MINIMOS**, rodando-o como
   caixa-preta numa instalação licenciada e ajustando formas físicas
   conhecidas aos números:
   - Rp e ΔRp por elemento e energia (polinômios em ln E, erro < 5·10⁻⁵), o
     recuo do pico por espessura de óxido, D0 e Ea da difusividade
     (`implante.json`);
   - detalhes de implementação da mobilidade que mudam o resultado: a força
     normal S é o campo vertical **local** em cada nó (média dos dois
     intervalos vizinhos; na interface, só o do silício); μ^LIS nunca passa
     de μ^LI; a força motriz é |∇φn| com cada componente tomada como a média
     dos módulos das diferenças vizinhas;
   - regras de decks: só um recozimento de fonte/dreno (o D é o do elemento
     da diretiva com TEMP/TIME), XOFF desloca a máscara, o critério de
     corrente do limiar é 10⁻⁷·W/L A, o dreno é o laço interno do STEP, as
     mensagens de erro para decks que o MINIMOS recusa.
4. **Escolha de motor na tela**: com o MINIMOS instalado, o usuário escolhe;
   sem ele, o aberto é o padrão (`motor_dispositivo` na configuração).

## Verificação (contra o MINIMOS 6.1, mesmos decks)

| caso | MINIMOS | MOSIM |
|---|---|---|
| dopagem, 12 decks | — | erro mediano 10⁻⁴; ≤ 1 % fora dos pontos de compensação |
| Vth, 8 decks de canal longo (THRES) | — | diferença de −0,008 a +0,017 V |
| Vth PMOS (L = 5 µm) | −0,717 V | −0,710 V |
| ID × UG, NMOS L = 10 µm, acima do limiar | — | 0,1 % a 2 % |
| exa2d (L = 0,85 µm, UD = 4 V), na malha do MINIMOS | 4,71·10⁻⁵ A | 4,70·10⁻⁵ A |
| exa2d, na malha do MOSIM | 4,71·10⁻⁵ A | 4,46·10⁻⁵ A |

O próprio MINIMOS para o laço do limiar quando o passo previsto cai abaixo de
0,01 V; o valor que ele imprime carrega essa incerteza.

## Segunda etapa (2026-11-25): malha, AVAL, transiente, SOI, perfis externos

Tudo abaixo foi medido contra o MINIMOS rodando como caixa-preta: os decks de
`minimos-run/examples`, 57 variantes geradas do exa2d (L, UD, UG, óxido,
dopagem) e os registros que o próprio MINIMOS grava (`.ref` com cada linha de
malha inserida e o valor da função de peso; `.out` com os mapas de potencial,
campos, quase-Fermi, portadores, mobilidades e geração; `.tra`).

### Malha adaptativa (`malha.py`)

O resultado do MINIMOS carrega o erro de discretização da malha grossa dele
(no exa2d, +4 % sobre o valor refinado). Para dar os mesmos números, o MOSIM
reproduz a malha, não a convergência:

- **BWF de potencial** = max Δψ / DP, em **volts** (DPXC = DPYC = 0,7 V no
  canal, DPXD = DPYD = 1,25 V fora): nos registros do exa2d a razão
  Δψ/BWF dentro do canal é 27,0 V_T = 0,70 V em todos os intervalos;
  intervalo com BWF > 1 é dividido **ao meio** (os registros mostram a linha
  nova no ponto médio), até PGMI = 0,25·10⁻⁷ cm.
- **BWF de dopagem** = DOPX·max Δasinh(C/2nᵢ) (0,35), só no modo THRES
  (nos decks 2-D a malha do MINIMOS não refina a junção); divisão **áurea**
  (pares 0,0213 + 0,0131 µm nas malhas dele), até DGMI = 20·10⁻⁷ cm.
- **Suavização**: vizinhos crescem no máximo φ²; é o que preenche o meio de
  um canal longo (0,15 → 0,243 → 0,393 → 0,637 → 1,03 µm no E190618a).
- **Malha inicial**: L/6 seções sob a porta (GFILL), passos áureos nos
  contatos (idênticos aos do MINIMOS no exa2d: −0,9068 … 1,7568 µm), em y a
  **mesma sequência absoluta** em todo deck (0; 1,62; 2,80; 4,72; 6,63;
  9,74 nm…) e o fundo no degrau áureo de xj + 2·W_dep (acerta 22 de 25).
- **Regras observadas, não do manual**: com canal invertido, as linhas de
  0,62; 1,24; 2,07 e 3,53 nm (sempre as mesmas); no fim, redistribuição das
  linhas sob a porta por equidistribuição de |∂ψ/∂x| + 1,3 V/µm (a malha
  final do MINIMOS tem linhas que nunca foram inseridas — 0,667; 0,675;
  0,683 µm no estrangulamento do exa2d).
- A posição exata de cada linha pesa ±0,5 % na corrente; a densidade por
  região, até 6 %.

Resultado: limiares a ±0,013 V nos 11 decks THRES; exa2d +0,3 %; 57 variantes
2-D com mediana de 1,2 %. Os canais de 0,5 µm com porta baixa erram mais, e o
próprio MINIMOS varia até 24 % neles só de refinar a malha. E 10× mais rápido
que a malha fina anterior (1–2 s por ponto).

### AVAL (`bipolar.py`)

Poisson + elétrons + lacunas por Newton acoplado, SRH (2.27), Auger (2.28),
superfície (2.29) e, no SOI, a interface de trás (2.30); ionização por
impacto (2.31–2.34) com o fator de profundidade β(y) = 1 + F·exp(−y/D),
em subciclo, como o "avalanche subcycle" do manual. Os parâmetros são os
padrões do manual (AN = 9,2·10⁵, BN = 2,02·10⁶, AP = 1,7·10⁷, BP = 3,2·10⁶,
F = 2,2, D = 1,5·10⁻⁶ cm): aplicados sobre a solução do próprio MINIMOS
(mapas do `.out`), reproduzem a geração dele dentro de 5 % (AN = 0, só
lacunas) e com viés médio de 3 % em ln.

Dois achados que custaram tempo:
- o **amortecimento do Newton tem de ser por nó**: com limite global, um único
  nó de lacunas a 10⁻¹⁷·nᵢ trava o passo inteiro e o "resultado" sai sem
  convergir (corrente de substrato 25× menor);
- a corrente de terminal no contato n+ é a diferença de números enormes: fonte
  e dreno usam o **método integral** (função-peso 1 na difusão, 0 fora), que o
  manual também cita; o ruído cai de 3·10⁻¹⁴ A para 10⁻²² A.

Resultado: exavl ID −3,7 %, IB −13 %; 42 variantes AVAL com ID a 1,2 %
(mediana) e IB a 13–22 % nos regimes de dreno alto, onde ele importa.

### Transiente (`transiente.py`)

Ondas constante, trapezoidal e de três níveis (seção 1.4). Os passos de
tempo são os do MINIMOS — idênticos no extra.inp (37 instantes): Δt =
T_rampa·ΔU/|A| nas rampas e crescimento de 1,5× nos patamares. Euler
implícito no modelo de dois portadores; corrente = condução + deslocamento
(derivada da carga induzida em cada contato). No extra.inp, as 72 correntes
acima de 10⁻¹¹ A têm diferença mediana de 1,4 % (máx. 8,9 %). Saída `.tra`
no formato da unidade NUMTRA e médias no período no `.ref`.

### SOI

Silício só no filme (FILM), isolante enterrado com KBULK, fundo livre (o
MINIMOS não põe eletrodo atrás: o potencial na base varia de 0,5 a 2,3 V
ao longo de x), corpo flutuante. exsoi: 2-D −5 %, AVAL −8,5 %, e o aumento
de corrente pelo corpo flutuante aparece (+26 % contra +31 %).

### Perfis

`PROFILE FILE=2-D` e `FILE=1-D` (formato do capítulo 4), `NS` (pré-
deposição: NS·erfc(y/2√(Dt)), fósforo no canal N e boro no P) e `ASYM`. O
FILE=2-D é justamente onde o MINIMOS desta compilação aborta; no MOSIM ele
viabiliza a **ponte direta**: com o motor aberto, a tela de Dispositivo grava
o perfil do canal calculado pelo SUPREM num arquivo FILE=2-D (fonte e dreno
continuam vindo dos parâmetros) e o simula ponto a ponto. Ida e volta do
perfil do exa2d pelo arquivo: 0,6 % na corrente.

## Consequências e limites conhecidos

- **Ainda não suportado** (o deck é recusado com mensagem clara, nunca
  roda calado com física faltando): MODEL=HOT e MC, MESFET (TINS=0) e GaAs,
  tunelamento banda a banda (RECOMB MTUN), armadilhas dinâmicas de
  interface e volume (bombeamento de carga), análise AC.
- **Perto da ruptura** (MOS e m78, dispositivos desligados a 10–13 V) o MOSIM
  dispara a avalanche onde o MINIMOS ainda tem multiplicação ~13×: as
  lacunas no pico de campo chegam a 600× menos que no MINIMOS; não
  resolvido. O m78 derruba o próprio MINIMOS.
- **Tempo:** 1–2 s por ponto no 2-D, 2–15 s no AVAL, ~1,5 min num transiente
  de 37 passos (o MINIMOS leva frações de segundo).
- numpy e scipy passam a ser dependências (instalar.sh, pacote de Windows).
- Testes: `tests/test_mosim.py`; a comparação ao vivo com o MINIMOS roda só
  onde ele estiver instalado.
