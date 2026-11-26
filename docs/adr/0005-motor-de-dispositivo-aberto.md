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

## Consequências e limites conhecidos

- **Canal curto em MODEL=2-D:** a física bate (mesma malha, mesma corrente),
  mas o MINIMOS usa uma malha grossa e adaptativa própria, e a corrente
  depende dela. No exa2d a diferença é de 5 %; a malha fina converge para
  4,38·10⁻⁵ A. Reproduzir o algoritmo de malha do MINIMOS é o próximo passo.
- **Ainda não suportado:** MODEL=AVAL/HOT/MC, MESFET (TINS=0), GaAs, SOI
  (FILM), PROFILE FILE=1-D/2-D, NS (pré-deposição), ASYM, transiente, AC.
  O deck é recusado com mensagem clara.
- **Tempo:** um ponto leva de 1 a 15 s (o MINIMOS leva frações de segundo);
  uma varredura longa leva minutos.
- numpy e scipy passam a ser dependências (instalar.sh, pacote de Windows).
- Testes: `tests/test_mosim.py`; a comparação ao vivo com o MINIMOS roda só
  onde ele estiver instalado.
