/* MOS-Studio.exe — o lançador do pacote de Windows.
 *
 * O pacote traz um Python próprio (a distribuição "embeddable" do
 * python.org) em ``python\`` e as bibliotecas em ``lib\``. Este programa é
 * só a casca que o usuário clica: descobre onde está instalado, prepara o
 * ambiente e entrega o controle ao ``pythonw.exe`` do próprio pacote.
 *
 * POR QUE UM EXECUTÁVEL, E NÃO UM ATALHO PARA O pythonw.exe
 * ---------------------------------------------------------
 *  - O ícone, o nome e a versão aparecem no gerenciador de tarefas e nas
 *    propriedades do arquivo como "MOS-Studio", não como "Python".
 *  - Um atalho só funciona onde o instalador o criou; o .exe funciona
 *    também se a pessoa abrir a pasta e clicar nele, ou fixar na barra de
 *    tarefas, ou copiar o pacote para outro lugar.
 *  - Dá para avisar com uma janela quando algo falta. Pela via do atalho, o
 *    pythonw.exe morre em silêncio: ele não tem console para onde escrever,
 *    e o usuário fica sem nenhuma pista.
 *
 * É compilado como aplicação de janela (``-mwindows``): sem console preto
 * aparecendo atrás da interface.
 *
 * O INTERPRETADOR É O python.exe, NÃO O pythonw.exe
 * -------------------------------------------------
 * O caminho óbvio seria o ``pythonw.exe``, que é a versão sem console. Mas
 * com ele o processo nasce sem saída padrão nenhuma: ``sys.stdout`` e
 * ``sys.stderr`` valem ``None``, e qualquer erro — um traceback de import,
 * uma DLL que falta, o próprio relatório de diagnóstico — desaparece. O
 * usuário clica e nada acontece, sem uma linha para contar o motivo.
 *
 * Então usamos o ``python.exe`` com ``CREATE_NO_WINDOW``: também não abre
 * console, e aí sim dá para apontar a saída para um arquivo. Toda execução
 * grava ``ultima-execucao.log`` ao lado do programa (ou na pasta de
 * configuração do usuário, se a do programa não aceitar escrita). É o que
 * transforma "não abre" em algo diagnosticável. */

#include <windows.h>
#include <shlwapi.h>
#include <stdio.h>

#define MAXCAM 32768  /* teto de caminho longo do Windows, em WCHARs */

/* Mostra um aviso e devolve o código de saída, para o caso de falha. */
static int reclamar(const WCHAR *texto)
{
    MessageBoxW(NULL, texto, L"MOS-Studio", MB_OK | MB_ICONERROR);
    return 1;
}

/* Preenche "destino" com a pasta onde este executável está, sem a barra. */
static int pasta_do_programa(WCHAR *destino, DWORD tamanho)
{
    DWORD n = GetModuleFileNameW(NULL, destino, tamanho);

    if (n == 0 || n >= tamanho)
        return 0;
    /* Corta o nome do arquivo, deixando só o diretório. */
    for (; n > 0; n--) {
        if (destino[n - 1] == L'\\' || destino[n - 1] == L'/') {
            destino[n - 1] = L'\0';
            return 1;
        }
    }
    return 0;
}

/* Abre o arquivo de registro desta execução, herdável pelo processo filho.
 *
 * Tenta primeiro ao lado do programa, que é onde o usuário vai procurar. Se
 * a pasta for somente leitura — uma instalação em Program Files, por
 * exemplo —, cai para a pasta de configuração do usuário. Se nem isso der,
 * devolve INVALID_HANDLE_VALUE e o programa roda sem registro: perder o log
 * é ruim, não abrir é pior. */
static HANDLE abrir_registro(const WCHAR *raiz)
{
    static WCHAR caminho[MAXCAM];
    SECURITY_ATTRIBUTES seguranca;
    HANDLE arquivo;
    const WCHAR *appdata;
    int tentativa;

    ZeroMemory(&seguranca, sizeof(seguranca));
    seguranca.nLength = sizeof(seguranca);
    seguranca.bInheritHandle = TRUE;

    for (tentativa = 0; tentativa < 2; tentativa++) {
        if (tentativa == 0) {
            _snwprintf(caminho, MAXCAM, L"%s\\ultima-execucao.log", raiz);
        } else {
            appdata = _wgetenv(L"APPDATA");
            if (appdata == NULL)
                return INVALID_HANDLE_VALUE;
            _snwprintf(caminho, MAXCAM, L"%s\\mos-studio", appdata);
            CreateDirectoryW(caminho, NULL);
            _snwprintf(caminho, MAXCAM,
                       L"%s\\mos-studio\\ultima-execucao.log", appdata);
        }
        arquivo = CreateFileW(caminho, GENERIC_WRITE,
                              FILE_SHARE_READ | FILE_SHARE_WRITE,
                              &seguranca, CREATE_ALWAYS,
                              FILE_ATTRIBUTE_NORMAL, NULL);
        if (arquivo != INVALID_HANDLE_VALUE)
            return arquivo;
    }
    return INVALID_HANDLE_VALUE;
}


int WINAPI wWinMain(HINSTANCE instancia, HINSTANCE anterior,
                    PWSTR linha_de_comando, int mostrar)
{
    static WCHAR raiz[MAXCAM], interpretador[MAXCAM], comando[MAXCAM];
    static WCHAR aviso[MAXCAM];
    STARTUPINFOW inicio;
    PROCESS_INFORMATION processo;
    HANDLE registro;

    (void)instancia; (void)anterior; (void)mostrar;

    if (!pasta_do_programa(raiz, MAXCAM))
        return reclamar(L"Não consegui descobrir onde o MOS-Studio está "
                        L"instalado.");

    _snwprintf(interpretador, MAXCAM, L"%s\\python\\python.exe", raiz);
    if (GetFileAttributesW(interpretador) == INVALID_FILE_ATTRIBUTES) {
        _snwprintf(aviso, MAXCAM,
                   L"A instalação está incompleta: não encontrei\n\n%s\n\n"
                   L"Reinstale o MOS-Studio.", interpretador);
        return reclamar(aviso);
    }

    /* O diretório de trabalho é a raiz do pacote. É dali que o programa
     * acha os motores (suprem4-run\) e grava as execuções (resultados\),
     * porque ``mos_studio/paths.py`` os procura ao lado do pacote. */
    SetCurrentDirectoryW(raiz);

    /* PYTHONHOME aponta para o Python do pacote, e não para um Python que a
     * pessoa talvez tenha instalado: o pacote tem de rodar igual nas duas
     * situações. O ``python313._pth`` ao lado do interpretador é quem
     * acrescenta a raiz e o ``lib\`` ao sys.path. */
    _snwprintf(comando, MAXCAM, L"%s\\python", raiz);
    SetEnvironmentVariableW(L"PYTHONHOME", comando);
    /* Qualquer PYTHONPATH do ambiente da pessoa misturaria pacotes de outra
     * versão do Python no nosso processo. */
    SetEnvironmentVariableW(L"PYTHONPATH", NULL);
    /* Saída sem buffer: se o programa morrer, a mensagem já saiu. */
    SetEnvironmentVariableW(L"PYTHONUNBUFFERED", L"1");

    /* Repassa os argumentos recebidos — é o que permite abrir um arquivo de
     * receita clicando nele, quando o instalador associa a extensão. */
    _snwprintf(comando, MAXCAM, L"\"%s\" -m mos_studio %s",
               interpretador,
               (linha_de_comando != NULL) ? linha_de_comando : L"");

    ZeroMemory(&inicio, sizeof(inicio));
    inicio.cb = sizeof(inicio);
    ZeroMemory(&processo, sizeof(processo));

    registro = abrir_registro(raiz);
    if (registro != INVALID_HANDLE_VALUE) {
        inicio.dwFlags = STARTF_USESTDHANDLES;
        inicio.hStdInput = NULL;
        inicio.hStdOutput = registro;
        inicio.hStdError = registro;
    }

    /* CREATE_NO_WINDOW: o python.exe é um programa de console, e sem isso
     * uma janela preta pisca atrás da interface. */
    if (!CreateProcessW(NULL, comando, NULL, NULL,
                        (registro != INVALID_HANDLE_VALUE),
                        CREATE_NO_WINDOW, NULL, raiz, &inicio, &processo)) {
        _snwprintf(aviso, MAXCAM,
                   L"Não consegui iniciar o MOS-Studio (erro %lu do Windows "
                   L"ao executar o interpretador).", GetLastError());
        return reclamar(aviso);
    }

    /* Espera o programa terminar e devolve o mesmo código de saída. Assim um
     * script que chame o MOS-Studio vê o resultado real, e a barra de tarefas
     * mostra um processo só enquanto a janela existe. */
    WaitForSingleObject(processo.hProcess, INFINITE);
    {
        DWORD codigo = 0;

        GetExitCodeProcess(processo.hProcess, &codigo);
        CloseHandle(processo.hThread);
        CloseHandle(processo.hProcess);
        if (registro != INVALID_HANDLE_VALUE)
            CloseHandle(registro);
        return (int)codigo;
    }
}
