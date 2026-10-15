# Fidelidade visual — onde o Qt não alcança o arquivo de design

O arquivo de design (`MOS-Studio (standalone).html`) é HTML/CSS. A interface é
Qt com QSS, que implementa um subconjunto do CSS. Esta lista registra cada
ponto em que o resultado difere do desenho, o que foi feito no lugar e por quê.
Uma linha por item. Nada aqui é "equivalente": é aproximação declarada.

## Tipografia

| Item do design | O que foi feito | Por quê |
|---|---|---|
| Fonte de corpo `Geist` | Cai para `Inter` → `Noto Sans` → `DejaVu Sans` | `Geist` (sans) **não está instalada** nesta máquina; só `Geist Mono` está. As demais do design (`Bricolage Grotesque`, `Geist Mono`, `Instrument Serif`) estão presentes e são usadas. |
| `letter-spacing` em em (`.1em`, `.2em`) | `QFont.setLetterSpacing(PercentageSpacing, …)` via `theme.font()` | O QSS não implementa `letter-spacing`; só a `QFont` tem. A conversão é aproximada: `.1em ≈ 110%`. |
| `text-transform: uppercase` | O texto é maiusculizado no widget (`common.eyebrow`) | O Qt ignora a propriedade no QSS. |
| Tamanhos fracionários (10,5 px, 12,5 px) | Arredondados para inteiros na escala de tokens | `QFont.setPixelSize` é inteiro. |
| Pesos variáveis (Bricolage 500) | Peso 500 pedido à `QFont`; o Qt escolhe o corte mais próximo | A fonte instalada tem cortes fixos (Medium/SemiBold/Bold), não eixo variável. |
| `font-feature-settings: "ss01","cv11"` | Não aplicado | Precisaria de `QFont.setFeature` por fonte; sem efeito visível nas famílias disponíveis. |

## Cor, profundidade e movimento

| Item do design | O que foi feito | Por quê |
|---|---|---|
| `box-shadow` (cartões, painéis, botão em hover) | Omitido | O QSS não tem `box-shadow`. Haveria `QGraphicsDropShadowEffect`, mas ele desliga a aceleração e borra texto em widgets grandes. A separação é feita por linha de 1 px, como no resto do design. |
| `transition` (cor, borda, transformação) | Mudança imediata de estado | O QSS não tem transições. Animar exigiria `QPropertyAnimation` por propriedade e por widget. |
| `transform: translateY(-2px)` no hover do botão primário | Omitido; só a cor muda (`accent` → `accent-glow`) | Sem equivalente em QSS. |
| `animation: pulse` (halo do ponto de execução) | Reimplementado em `PulseDot`, com `QPropertyAnimation` e pintura própria | O ritmo (3 s, ida e volta) é o do design; o halo é pintado em vez de ser `box-shadow`. |
| `backdrop-filter: blur(6px)` | Omitido; fundo sólido `bg-2` | Sem equivalente no Qt widgets. |
| `mask-image` e gradiente radial do fundo da tela inicial | `HeroBackground` pinta o gradiente com `QRadialGradient` e as linhas com `QPainter`; a máscara em si não existe | O Qt não tem `mask-image`. O desvanecimento é obtido com o alfa do próprio gradiente, que chega perto do recorte do design. |
| `filter: drop-shadow` na curva do gráfico | Omitido; a curva é desenhada sem brilho | Custa um segundo passe de pintura a cada repintura, por um realce sutil. |
| `rgba()` nas linhas e véus | Mantido — o QSS aceita `rgba()` | O alfa do CSS (0–1) virou alfa do Qt (0–255) nos tokens. |

## Layout

| Item do design | O que foi feito | Por quê |
|---|---|---|
| Flexbox (`display:flex`, `gap`, `flex:1`) | `QHBoxLayout`/`QVBoxLayout` com `spacing` e fatores de esticar | Os layouts do Qt cobrem o caso; o mapeamento é direto. |
| Grade responsiva (`repeat(auto-fit, minmax(...))`) | Grade de duas colunas fixas no formulário | `QGridLayout` não tem `auto-fit`. A janela tem largura mínima de 1280 px, onde duas colunas sempre cabem. |
| `clamp()` em tamanhos e espaçamentos | Valor único da escala de tokens | Sem equivalente; a janela tem mínimo definido. |
| Barra de título falsa com três círculos | Usa a barra de título do sistema | Reproduzi-la exigiria janela sem moldura e reimplementar arrastar, redimensionar e encaixe. Ver ADR 0001, item 15. |
| Colunas de largura fixa (320 px / 380 px) | `QSplitter` com os mesmos tamanhos iniciais, mas ajustáveis | Ganho de usabilidade sem custo de fidelidade: o estado inicial é o do design. |
| `text-wrap: balance` / `pretty` nos títulos | Quebra normal de linha do Qt | Sem equivalente. |

## Controles

| Item do design | O que foi feito | Por quê |
|---|---|---|
| Barra de rolagem personalizada | Estilizada em QSS (10 px, alça arredondada, sem setas) | Chega perto; o Qt não permite remover a área de recuo em todos os estilos. |
| Campo com unidade dentro da moldura | A unidade é um rótulo ao lado do `QLineEdit`, dentro da mesma linha | `QLineEdit` não aceita filho posicionado; o conjunto fica visualmente equivalente. |
| Pílulas de escolha (segmented) | `QPushButton` marcáveis num `QButtonGroup`, estilo `[variant="segment"]` | Equivalente funcional e visual. |
| Linha do deck com fundo realçado ao selecionar | O cursor vai para a linha; o realce de bloco inteiro não é pintado | `QPlainTextEdit` suporta `ExtraSelection`; ficou de fora desta etapa para não competir com o destaque de sintaxe. |
| Arrastar etapa com a linha "fantasma" do design | Arrastar nativo do `QListWidget` (linha de inserção padrão) | O indicador do Qt é suficiente e não exige pintura própria. |

## Gráficos

| Item do design | O que foi feito | Por quê |
|---|---|---|
| Curvas de espécies (boro tracejado, dopante, líquido) | Implementado: a visão "Espécies" desenha uma curva por dopante presente na receita, com a cor do token de cada espécie | Precisava de um `PRINT` por dopante no deck derivado, que `deck.dopants_in_steps` resolve. |
| Marcas do eixo x em valores redondos | Passo "bonito" (1, 2 ou 5 × 10ⁿ) calculado a partir dos dados | O design mostra um perfil fixo; aqui o eixo acompanha a profundidade real simulada. |
| Visão de camadas (pilha de materiais colorida) | Implementado em `widgets/layer_stack.py`, com a espessura proporcional e a cor por material | — |
| Sombra sob a área da curva (`filter: drop-shadow`) nos gráficos novos (I-V, Deal-Grove) | Omitido; curva e pontos sem brilho | Mesmo motivo do perfil: um segundo passe de pintura por um realce sutil. |
| Gradiente suave sob a curva I-V | Preenchimento omitido; só a linha e os pontos | O design pede gradiente vertical com alfa; traçá-lo exigiria um `QLinearGradient` por repintura, e a leitura da curva não melhora. |
| Mapa 2-D com escala de cor contínua | `FieldMap` interpola entre os tokens `nfill` e `accent`, célula a célula da malha do motor | A malha do MINIMOS não é uniforme (é fina na superfície e nos contatos); pintar célula a célula preserva o refinamento, que uma imagem reamostrada perderia. |

## Telas concluídas depois da primeira etapa

| Item do design | O que foi feito | Por quê |
|---|---|---|
| Cartões da biblioteca com prévia do perfil | Implementado; a prévia é uma corrida real do motor, em cache (`core/preview.py`) | O design mostra um traçado decorativo; aqui ele é o perfil que a receita produz de verdade. |
| Barra de progresso dentro dos cartões e do painel do herói | `_FilledBar`, pintada com `QPainter` | O QSS pinta `QProgressBar`, mas não com a altura de 2 px e o raio do design. |
| Texto claro sobre o fundo escuro do herói (no tema claro) | Variantes `[onhero]` no QSS, mais `theme.mark(..., onhero=True)` | No Qt, a cor vinda do QSS vence a paleta do widget: sem a variante, o texto do herói ficava invisível no tema claro. |
| Abas do painel de dispositivo (Curva I-V / Mapas 2-D / Deck) | `QTabWidget` com `documentMode`, estilizado pelos tokens | Equivalente funcional; o Qt não reproduz a borda inferior parcial do design. |
| Menu do projeto no cabeçalho | `QMenu` nativo, estilizado em QSS | O design desenha um painel flutuante próprio; o menu nativo traz teclado e acessibilidade de graça. |

## Observações

- Os tokens de cor, tipografia, espaçamento, raio e dimensão foram extraídos
  do CSS do arquivo de design e vivem em `mos_studio/ui/theme/tokens.py`. Um
  teste (`tests/test_theme.py`) falha se qualquer widget escrever uma cor ou
  uma família tipográfica literal.
- Os dois temas do design (claro, que é o padrão, e escuro) estão
  implementados e cobertos por teste.
- Nenhum efeito foi inventado: onde o design não pede, não há sombra,
  gradiente nem animação.
