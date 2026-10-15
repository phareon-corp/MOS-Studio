; Instalador do MOS-Studio para Windows.
;
; Compilado com o NSIS, rodando no Linux (ver empacotar/instalador_windows.py).
; Recebe por /D: VERSAO, PACOTE (a pasta montada), ICONE e SAIDA.
;
; DECISÕES QUE VALE EXPLICAR
; -------------------------
; 1. INSTALA SEM PEDIR SENHA DE ADMINISTRADOR.
;    O destino é %LOCALAPPDATA%\Programs\MOS-Studio, dentro do perfil de quem
;    instalou. Pedir elevação faria o Windows mostrar o aviso amarelo de
;    "aplicativo de editor desconhecido" — o pacote não é assinado —, e muita
;    gente para aí. Também evita que o programa fique em Program Files, que é
;    somente leitura: o MOS-Studio grava as simulações em resultados\, ao
;    lado de si mesmo, como no Linux.
;
; 2. A DESINSTALAÇÃO PERGUNTA ANTES DE APAGAR AS SIMULAÇÕES.
;    resultados\ é trabalho do usuário, não arquivo de programa. Apagar sem
;    avisar seria perder dados; deixar para trás sem avisar seria lixo
;    silencioso. Então pergunta.
;
; 3. NÃO ASSOCIA EXTENSÕES NEM MEXE NO PATH.
;    Nada que o usuário não tenha pedido. O que o instalador cria é o que ele
;    remove.

Unicode true
ManifestDPIAware true

!ifndef VERSAO
  !define VERSAO "2.0.0"
!endif
!ifndef PACOTE
  !error "falta /DPACOTE=<pasta do pacote montado>"
!endif
!ifndef SAIDA
  !define SAIDA "MOS-Studio-instalador.exe"
!endif

!define NOME      "MOS-Studio"
!define EMPRESA   "SyncField Corporation"
!define CHAVE_REG "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NOME}"

Name "${NOME} ${VERSAO}"
OutFile "${SAIDA}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\${NOME}"
InstallDirRegKey HKCU "Software\${NOME}" "InstallDir"
SetCompressor /SOLID lzma
; O pacote tem 108 MB de binários já comprimidos (DLLs do Qt, .pyd); um
; dicionário grande é o que faz diferença no tamanho final.
SetCompressorDictSize 64

VIProductVersion "0.0.0.0"
VIAddVersionKey /LANG=1046 "ProductName"     "${NOME}"
VIAddVersionKey /LANG=1046 "ProductVersion"  "${VERSAO}"
VIAddVersionKey /LANG=1046 "FileVersion"     "${VERSAO}"
VIAddVersionKey /LANG=1046 "CompanyName"     "${EMPRESA}"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do ${NOME}"
VIAddVersionKey /LANG=1046 "LegalCopyright"  "${EMPRESA}"

!include "MUI2.nsh"
; GetSize, para dizer ao Windows quanto a instalação ocupa.
!include "FileFunc.nsh"

!ifdef ICONE
  !define MUI_ICON "${ICONE}"
  !define MUI_UNICON "${ICONE}"
!endif
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${NOME}.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o ${NOME} agora"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\LEIA-ME.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Ler o LEIA-ME"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "PortugueseBR"

; ---------------------------------------------------------------- instalação

Section "${NOME}" SecPrograma
  SectionIn RO
  ; Atalhos e desinstalação no perfil de quem está instalando, não no "todos
  ; os usuários" — coerente com o destino da instalação.
  SetShellVarContext current

  SetOutPath "$INSTDIR"
  ; Arquivos que a execução gera e que não devem viajar no instalador.
  File /r /x "diagnostico.txt" /x "ultima-execucao.log" /x "__pycache__" "${PACOTE}\*.*"

  ; A pasta das simulações é criada aqui para existir já na primeira abertura.
  CreateDirectory "$INSTDIR\resultados"

  CreateDirectory "$SMPROGRAMS\${NOME}"
  CreateShortcut "$SMPROGRAMS\${NOME}\${NOME}.lnk" \
    "$INSTDIR\${NOME}.exe" "" "$INSTDIR\${NOME}.exe" 0 \
    SW_SHOWNORMAL "" "Simulação de processos e dispositivos semicondutores"
  CreateShortcut "$SMPROGRAMS\${NOME}\Diagnóstico do ${NOME}.lnk" \
    "$INSTDIR\${NOME}.exe" "--diagnostico" "$INSTDIR\${NOME}.exe" 0 \
    SW_SHOWNORMAL "" "Verifica a instalação e mostra um relatório"
  CreateShortcut "$SMPROGRAMS\${NOME}\Desinstalar o ${NOME}.lnk" \
    "$INSTDIR\Desinstalar.exe"

  WriteRegStr HKCU "Software\${NOME}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\${NOME}" "Version" "${VERSAO}"

  ; A entrada em "Aplicativos instalados" do Windows.
  WriteRegStr   HKCU "${CHAVE_REG}" "DisplayName"     "${NOME}"
  WriteRegStr   HKCU "${CHAVE_REG}" "DisplayVersion"  "${VERSAO}"
  WriteRegStr   HKCU "${CHAVE_REG}" "Publisher"       "${EMPRESA}"
  WriteRegStr   HKCU "${CHAVE_REG}" "DisplayIcon"     "$INSTDIR\${NOME}.exe"
  WriteRegStr   HKCU "${CHAVE_REG}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${CHAVE_REG}" "UninstallString" "$\"$INSTDIR\Desinstalar.exe$\""
  WriteRegStr   HKCU "${CHAVE_REG}" "QuietUninstallString" "$\"$INSTDIR\Desinstalar.exe$\" /S"
  WriteRegDWORD HKCU "${CHAVE_REG}" "NoModify" 1
  WriteRegDWORD HKCU "${CHAVE_REG}" "NoRepair" 1
  ; Tamanho em kB, para a lista de aplicativos mostrar quanto ocupa.
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${CHAVE_REG}" "EstimatedSize" "$0"

  WriteUninstaller "$INSTDIR\Desinstalar.exe"
SectionEnd

Section /o "Atalho na área de trabalho" SecAtalho
  SetShellVarContext current
  CreateShortcut "$DESKTOP\${NOME}.lnk" "$INSTDIR\${NOME}.exe" "" \
    "$INSTDIR\${NOME}.exe" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPrograma} \
    "O programa, o simulador SUPREM-IV e tudo de que eles precisam."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAtalho} \
    "Põe também um atalho na área de trabalho."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ------------------------------------------------------------ desinstalação

Section "Uninstall"
  SetShellVarContext current

  ; As simulações do usuário são tratadas à parte do resto (ver a nota 2 no
  ; topo). Em modo silencioso (/S) ficam, que é o mais conservador.
  ;
  ; Os desvios são por rótulo, e não por "+n". Com números relativos um
  ; ``IfSilent +5`` saltava uma instrução além da conta e a desinstalação
  ; silenciosa deixava o MOS-Studio.exe para trás — foi assim que o teste na
  ; máquina virtual pegou o erro. Rótulo não tem como errar a contagem.
  IfSilent manter_simulacoes
  IfFileExists "$INSTDIR\resultados\*.*" 0 manter_simulacoes
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Apagar também as simulações guardadas em:$\n$\n$INSTDIR\resultados$\n$\nResponder Não deixa a pasta no disco." \
    IDNO manter_simulacoes
  RMDir /r "$INSTDIR\resultados"
  manter_simulacoes:

  Delete "$INSTDIR\${NOME}.exe"
  Delete "$INSTDIR\LEIA-ME.txt"
  Delete "$INSTDIR\diagnostico.txt"
  Delete "$INSTDIR\ultima-execucao.log"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\lib"
  RMDir /r "$INSTDIR\mos_studio"
  RMDir /r "$INSTDIR\suprem4-run"
  RMDir /r "$INSTDIR\data"
  ; Só remove a pasta se estiver vazia: se o usuário escolheu guardar as
  ; simulações, elas continuam ali.
  RMDir "$INSTDIR"

  Delete "$DESKTOP\${NOME}.lnk"
  RMDir /r "$SMPROGRAMS\${NOME}"

  DeleteRegKey HKCU "${CHAVE_REG}"
  DeleteRegKey HKCU "Software\${NOME}"
SectionEnd
