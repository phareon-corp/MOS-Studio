# ADR 0001 — Migração do MOS-Studio para PySide6

- **Data:** 2026-10-06
- **Situação:** aceita
- **Escopo:** primeira etapa da migração (estrutura, tema, janela principal e
  a receita de processo de ponta a ponta)

## Contexto

O MOS-Studio era um único `suprem3.py` de 2.900 linhas em Tkinter, com o
backend dos dois motores Fortran (SUPREM-III de Stanford e MINIMOS 6.1)
misturado à interface. A migração é para PySide6 com QSS, guiada por um
arquivo de design em HTML, tendo o Linux como alvo imediato e o Windows como
alvo da fase seguinte.

Este ADR registra as decisões que foram tomadas sem consulta, durante a
implementação. Em cada uma, a escolha foi a mais conservadora disponível.

## Decisões

### 1. `core/` e `ui/` vivem dentro do pacote `mos_studio/`

O pedido falava em "módulos em `core/`" e "um arquivo de tema em `ui/theme/`",
e também que o app abrisse com `python -m mos_studio`. As duas coisas só
convivem se `core/` e `ui/` forem subpacotes de `mos_studio/`. Ficaram em
`mos_studio/core/` e `mos_studio/ui/theme/`.

### 2. O backend foi movido, não reescrito — e há teste que prova isso

As funções de deck, parsing e orquestração foram transplantadas com a lógica
intacta; mudaram só a forma (tipos, docstrings, nomes públicos sem `_`).

Para que "não alterar a lógica" seja verificável e não uma promessa,
`tests/legacy.py` carrega as funções do `suprem3.py` original num namespace
isolado e os testes comparam as duas implementações sobre os artefatos reais
do repositório. Na migração, a comparação cobriu **115 arquivos de saída** e
**90 decks**, com zero divergências.

Consequência: enquanto `suprem3.py` existir no repositório, esses testes rodam;
quando ele for removido, eles se auto-pulam (`skipUnless`).

### 3. DOSBox saiu inteiro, inclusive do código

O pedido admitia manter o caminho DOSBox "se for trivial". Não é: ele depende
de uma pasta `suprem_engine/` com `S3GEN.EXE` e `SUPREM3.EXE` que **não existe
no repositório**, e de um verificador de integridade de executável MS-DOS
(`check_exe_integrity`) que só faz sentido para aqueles binários. Os quatro
executáveis em uso são ELF x86-64 nativos e rodam direto.

Manter código morto que ninguém pode exercitar é pior que removê-lo: ele
envelhece sem teste e confunde quem lê. O caminho DOSBox não foi migrado. O
`suprem3.py` original segue versionado no commit de rede de segurança, caso
alguém precise dele.

### 4. PLOT sai do catálogo, mas continua sendo gerado e lido

PLOT não está em `recipe.STEP_TYPES`, então não há como montá-lo pela
interface — era o defeito a corrigir. Mas `deck.step_to_code` e
`deck.parse_in_file` continuam tratando PLOT, para que um deck legado que o
contenha ainda faça a viagem de ida e volta sem perder linhas. Corrigir o
defeito no catálogo (interface) em vez de no gerador (backend) mantém a
paridade de comportamento do item 2.

O catálogo explica a ausência, em vez de omiti-la em silêncio.

### 5. A rolagem por roda do mouse não tem código nenhum

O defeito antigo era um `bind("<MouseWheel>")`, evento que o X11 não emite. No
Qt a rolagem é do próprio widget. A decisão é a ausência de decisão: nenhum
tratamento manual de evento de roda foi escrito, e a lista de etapas usa
`QListWidget` com `ScrollPerPixel`.

### 6. A configuração vai para o diretório do usuário; os resultados, não

`config.json` passou a morar em `$XDG_CONFIG_HOME/mos-studio/` (ou
`%APPDATA%\mos-studio\` no Windows), e `config.migrate_legacy()` importa, uma
vez e sem apagar nada, um `config.json` antigo que esteja ao lado do programa.

As **saídas de simulação continuam em `resultados/`**, dentro do repositório.
O arquivo de design fala numa pasta de trabalho `~/Simulações`, mas isso faz
parte de "projetos salvos", que é de outra etapa; mover as 107 execuções
existentes agora seria uma mudança de escopo com risco de perder histórico.

### 7. O log de depuração saiu da pasta do programa

A versão antiga escrevia `debug_log.txt` ao lado do executável. Agora cada
execução grava seu próprio `execucao.log` dentro da pasta de resultados
daquela execução, onde o log tem contexto e não polui a instalação.

### 8. A detecção de junção recebe um limiar derivado do perfil

`detect_junctions` foi movida com o padrão herdado (`min_mag=1e16`), e há teste
de paridade sobre ele. Mas esse padrão foi calibrado para substratos
pesadamente dopados: num diodo sobre substrato de 1e15 cm⁻³ o lado p nunca
alcança o limiar, e a junção — que existe — não é encontrada.

Em vez de mexer na função, foi acrescentada `junction_threshold(perfil)`, que
deriva o limiar do próprio perfil (um décimo da magnitude do substrato, com
piso de 1e13 e teto de 1e16). A interface chama a função com esse limiar.

Efeito medido sobre as 61 saídas reais com tabela de perfil: 21 passaram a
exibir a junção, todas com uma única junção de profundidade plausível; nenhuma
passou a exibir junções espúrias.

### 9. Erros do motor aparecem na tela, não em caixa de diálogo

O arquivo de design mostra a falha do SUPREM-III como uma faixa dentro da
própria área de trabalho. Além de ser o desenho pedido, isso resolveu um
problema concreto: um `QMessageBox.exec()` modal trava a aplicação quando não
há ninguém para clicar, inclusive nos testes automatizados.

### 10. O deck herda `stdin` fechado

Os binários são headless e nunca devem esperar teclado. Todos os processos do
motor são lançados com `stdin=subprocess.DEVNULL`, para que um deck que o
`genii` não entenda falhe depressa em vez de travar a interface.

### 11. Cancelamento por `Popen`, não por `subprocess.run`

A orquestração precisava de cancelamento (requisito desta etapa). Cada binário
passou a rodar em `Popen` com o processo guardado, para que `cancel()` possa
encerrá-lo de outra thread. A sequência, o `cwd`, o ambiente e os argumentos
continuam idênticos aos da versão anterior.

### 12. Os testes usam `unittest`, não `pytest`

`pytest` não está instalado nesta máquina e a tarefa não pedia para instalar
dependências. A suíte usa `unittest` da biblioteca padrão, com arquivos
`test_*.py` e classes `TestCase` — que o `pytest` também coleta, se um dia for
adicionado.

### 13. Gráficos com `QPainter`, sem matplotlib

O perfil de dopagem é desenhado por um widget próprio, a partir dos tokens do
tema. Evita uma dependência pesada, acompanha o tema claro/escuro e reproduz o
desenho do arquivo de design (grade fina, expoentes sobrescritos, linha
tracejada da junção).

### 14. Todas as áreas do design estão implementadas

A primeira etapa deixou Dispositivo e Oxidação como telas que apenas diziam o
que faltava. A migração foi concluída: Início, Processo, Resultados,
Dispositivo e Oxidação são telas de verdade, e a tela de Resultados lista as
execuções, compara duas e percorre a evolução por etapa.

### 15. Sem barra de título falsa

O arquivo de design desenha uma barra de janela com três círculos. Num
aplicativo Qt real, essa barra é do sistema operacional. Desenhar uma cópia
exigiria janela sem moldura e reimplementar arrastar, redimensionar e encaixe
— muito risco para um detalhe decorativo. Usa-se a barra nativa.

### 16. A pasta de trabalho é `~/Simulações`, e o legado não se move

As execuções novas vão para `~/Simulações/execucoes/` (a pasta é configurável
na tela de Início). As 107 execuções que a versão anterior deixou em
`resultados/` **não são movidas**: `workspace.import_legacy()` apenas as
registra no índice, e elas continuam onde estão. Mover pastas de resultados de
alguém para arrumar a própria organização seria arriscar o histórico sem
necessidade; registrar é reversível, mover não é.

### 17. A ponte SUPREM → MINIMOS passa pelo card analítico, e diz isso

O caminho que o design sugere — entregar ao MINIMOS a matriz de dopagem
binária do SUPREM por `PROFILE FILE=2-D` — **aborta dentro desta compilação do
motor**: o cálculo avança, monta a malha e então para com
`STOP *** MINIMOS ABORT ***` e um diagnóstico sem nome de módulo
(`IN MODULE , LINE 860`). Os fontes Fortran não acompanham o binário, então não
há como localizar a falha. A função que gera o arquivo
(`minimos.write_2d_profile`) ficou no núcleo, testada, mas não ligada à
interface.

A ponte real (`core/bridge.py`) extrai da receita e do perfil medido as
grandezas que o card analítico `PROFILE` aceita — dopagem de substrato, espécie
e dose de fonte/dreno, energia, temperatura e tempo de recozimento — e deixa o
MINIMOS reconstruir o perfil. Isso é uma **re-simulação a partir de
parâmetros**, não o transporte do perfil ponto a ponto, e a interface não finge
o contrário: o painel da ponte mostra a origem de cada número, o rodapé carrega
a ressalva, e a profundidade de junção do SUPREM aparece ao lado da do MINIMOS
para que a diferença fique medida.

### 18. Três defeitos do gerador de deck do MINIMOS, corrigidos

A primeira etapa moveu `build_deck` sem alterar a lógica, como pedido. Ao
ligá-la à interface, três defeitos apareceram na prática e foram corrigidos,
porque cada um deles derruba o motor:

- **`UG` ausente** no card `BIAS` faz o `MODEL=2-D` morrer com `SIGSEGV`
  depois de montar a malha. O gerador agora sempre emite `UG`, com zero como
  padrão. (Os sete exemplos do motor que usam `MODEL=2-D` todos trazem `UG`;
  foi assim que a causa apareceu.)
- **Dreno em exatamente zero** causa o mesmo `SIGSEGV`. O gerador usa um piso
  de 0,1 V (`minimos.UD_MINIMO`), que não muda a curva de forma visível.
- **PMOS forçado ao caminho `FILE=2-D`**: o gerador antigo decidia pelo canal,
  então todo PMOS caía no caminho que aborta. Agora o canal escolhe a espécie
  (`AS` para NMOS, `B` para PMOS) e o arquivo 2-D só sai se for pedido
  explicitamente (`dopfile=True`).

### 19. `TIME` do card `PROFILE` é em segundos; o app antigo rotulava minutos

O `suprem3.py` mostrava esse campo como “recoz. min:” com o valor 2700. Os
exemplos do próprio motor usam `TIME=2700` para 45 minutos: a unidade é
**segundo**. O rótulo antigo estava errado. A chave passou a ser `anneal_s`
(`anneal_min` segue aceito como alias, para não quebrar a paridade com o
arquivo antigo), e a ponte converte os minutos da receita.

Isto não é cosmético: passar 30 (minutos) onde o motor espera segundos produz
um recozimento curto demais para formar junção, e o motor morre com `SIGSEGV`
em vez de reclamar.

### 20. A vírgula nos tempos de oxidação: entre dígitos é decimal

No campo de tempos da tela de Oxidação, a vírgula faz dois papéis em
português. A regra adotada, anunciada no próprio campo: vírgula **entre
dígitos** é marca decimal (`0,5`); vírgula seguida de espaço, ponto e vírgula
ou espaço separam itens (`10, 30; 60 120`). Sem a regra, `0,5` viraria dois
tempos — 0 e 5 — sem o usuário perceber. O caso ambíguo `60,120` resolve-se
como um tempo (60,12 min), de forma consistente.

### 21. A evolução por etapa é calculada em segundo plano

A série de corridas derivadas que alimenta a visão de evolução pode demorar
mais que a simulação principal. Ela roda numa thread própria: o resultado
aparece imediatamente, e a tela de Resultados recarrega quando a série termina.
Se falhar, a execução segue válida sem ela, e o rodapé diz por quê.

### 22. As receitas da biblioteca foram corrigidas contra o motor

As receitas da tela de Início são a primeira coisa que o usuário roda, então
todas foram validadas no motor de verdade, e três estavam quebradas:
`diodo-pn` e `oxidacao` imprimiam tabelas de zeros (o `PRINT` vinha depois da
deposição do metal/óxido — a impressão de concentração foi movida para antes),
`fonte-dreno-nmos` batia no Erro 150 do motor em `DEPOSITION POLYSILI` (os
passos de polisilício saíram), e `poco-n` excedia os 500 nós de malha. Um
teste (`tests/test_library.py`) agora falha se qualquer receita da biblioteca
não passar pela validação, estourar a malha ou não imprimir resultado.

A validação da receita passou a recusar malha acima de
`recipe.MAX_GRID_POINTS` (500), com o passo sugerido — o motor respondia a
isso com “Maximum number of grid points exceeded”, que não dizia o que fazer.

### Dois erros do leitor de saída, achados ao escrever o exemplo 1-D

Nenhum dos dois aparecia nas receitas da biblioteca, porque todas corroem o
óxido antes de imprimir o perfil. Um processo de porta de MOS não corrói — o
óxido de porta é o produto — e aí os dois apareceram juntos.

**O perfil morria na primeira linha de concentração nula.** No óxido a dopagem
ativa é zero, e a tabela do `PRINT CONCENTRATION` começa com linhas de
`0.00000E+00`. O leitor encerrava a tabela ali, porque testava a presença de
letras na linha — e o `E` do expoente conta como letra. Resultado: todo deck
que imprime com óxido ainda sobre a lâmina perdia o perfil **inteiro**, não
um pedaço. Agora os números são retirados da linha antes do teste de texto.

**O eco do deck virava camada.** O `parse_layers` procurava o nome de um
material em qualquer linha; o log do motor ecoa o deck, e `DEPOSITION POLYSILI
THICKNES=0.35` entrava como uma camada de polissilício de 0,35 µm. Como o
`OUTPUT.OUT` vem antes do arquivo de camadas na ordem alfabética, era esse eco
que a tela mostrava, no lugar da pilha de verdade. Agora o leitor exige o
cabeçalho da tabela e o formato de linha — número, material, espessura —, e só
encerra depois de ter lido alguma camada, porque o cabeçalho ocupa duas
linhas.

### O eixo do perfil tem um teto de décadas

Um perfil por espécie cai a valores como 10⁻²⁸ cm⁻³ longe da superfície, que é
zero numérico do motor. O eixo logarítmico abria quarenta e oito décadas e
espremia a curva inteira numa faixa de poucos pixels no topo. O piso agora
fica oito décadas abaixo do pico (`profile_chart.MAX_DECADES`): de 10²⁰ a
10¹², que é tudo o que um perfil de dopagem tem a dizer.

### Os mapas do MINIMOS: a cor estava quebrada e a superfície 3-D sumiu

Duas coisas, e as duas eram regressões da migração.

**O mapa 2-D era um retângulo chapado.** A escala ia do token `nfill` ao
`accent`, e os dois têm o **mesmo** RGB — `nfill` é o accent com alfa 77, e a
interpolação descartava o alfa. O parâmetro de mistura não mudava nada. Os
dados sempre estiveram certos (grade 23×33, potencial de −0,40 a +2,55 V); era
só a tinta.

A escala agora é **divergente**, porque os quatro campos do PIF têm sinal e o
zero significa alguma coisa: a fronteira da depleção, o ponto onde o campo
inverte. Dois polos e um neutro no meio — azul negativo, laranja positivo,
nunca uma matiz no meio, nunca um arco-íris —, a faixa simétrica em torno do
zero e o zero marcado na barra de cor. O par foi validado: ΔE 27,3 em
protanopia e 36,4 em visão normal, ambos os polos acima de 3:1 contra as duas
superfícies.

**A superfície 3-D não existia mais.** O app antigo tinha uma aba "Superfície
3D" que desenhava o mesmo PIF com o `plot_surface` do matplotlib; a migração
trouxe só o mapa visto de cima. Como o app novo não usa matplotlib, a
superfície foi refeita com QPainter: a grade é projetada por azimute e
elevação e pintada quadrilátero a quadrilátero, de trás para a frente
(algoritmo do pintor), com a mesma escala divergente do mapa.

Duas decisões valem registro. O enquadramento sai da **projeção**, não de uma
constante: o tamanho na tela muda com o ângulo, e uma escala fixa deixava a
vista de lado ocupando um quinto da área. E a altura é **linear** mesmo para
campos que o mapa 2-D mostra em log — achatar o eixo esconderia justamente o
relevo que a superfície existe para mostrar.

### O deck do MINIMOS passou a ser editável

Dava para montar o deck pelos campos, e só. Agora o painel do deck entra em
modo manual como o da receita do SUPREM, e há dois caminhos para simular algo
que o processo não gerou: **abrir um `.inp`** do disco, e **abrir um
resultado** (`fort.30` com os mapas, `fort.61` com a curva) para ver sem rodar
o motor.

Junto disso, a ponte passou a dizer o que **não** veio da receita. Um corte de
porta não tem fonte nem dreno, e a ponte preenchia com os padrões do motor em
silêncio: o MINIMOS simulava um transistor com fonte/dreno inventada e nada na
tela dizia isso.

## Consequências

- `suprem3.py` continua no repositório, sem ser importado pelo aplicativo
  novo, servindo de referência e de base para os testes de paridade
  (`tests/legacy.py` executa funções dele num namespace isolado e compara os
  resultados com os do núcleo novo). É a razão para mantê-lo.
- A pasta `resultados/` fica fora do controle de versão e deixou de ser o
  destino das execuções novas, que vão para a pasta de trabalho. As 107
  anteriores continuam lá e aparecem no índice depois de importadas.
- O `MODEL=2-D` do MINIMOS funciona por inteiro nesta compilação — curva de
  transferência, curva de saída e mapas 2-D de potencial, carga espacial e
  campo elétrico. Os mapas são pintados direto do PIF, porque o visualizador
  externo que os desenhava (`plotmtv`) não existe mais.
- O que **não** funciona é `PROFILE FILE=2-D` (item 17). Se um dia os fontes
  do motor aparecerem, é o primeiro lugar a investigar: `write_2d_profile` já
  gera o arquivo e tem teste.
- Divergências entre o arquivo de design e o que o Qt alcança estão listadas,
  uma por linha, em `docs/fidelidade-visual.md`.
