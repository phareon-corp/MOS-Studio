/* Implementação da camada POSIX do SUPREM-IV no Windows.
 *
 * Três funções, nenhuma delas no caminho do cálculo. Ver o README ao lado
 * para o levantamento de onde o fonte as usa. */

#include <windows.h>
#include <time.h>
#include <fcntl.h>
#include <stdlib.h>
#include "sys/times.h"
#include "pwd.h"

/* MODO BINÁRIO POR PADRÃO, E HOME — as duas coisas que o Windows não dá de
 * graça e o fonte presume.
 *
 * MODO BINÁRIO — a correção mais importante desta camada.
 *
 * O arquivo de chaves compilado (``suprem.uk``) é binário e o fonte o abre
 * com um ``open()`` simples, sem O_BINARY, porque no Unix não existe outra
 * coisa. No Windows o padrão é modo texto: cada 0x0A vira 0x0D 0x0A na
 * escrita e volta na leitura. Medido: o mesmo ``suprem.uk`` saía com 67.559
 * bytes em vez de 67.535, e o motor recusava com "unable to read or open the
 * unformatted key file".
 *
 * ``_fmode`` vale para todo descritor aberto depois. Os arquivos de texto não
 * sofrem: ficam com fim de linha LF, que os leitores do MOS-Studio já
 * normalizam.
 *
 * É um construtor, e não a variável ``_CRT_fmode`` que a documentação antiga
 * sugere: conferido nesta versão do mingw-w64, atribuir ``_CRT_fmode`` não
 * surte efeito — o ``suprem.uk`` continuava saindo com 67.559 bytes. O
 * construtor roda antes do ``main`` e resolve. */
__attribute__((constructor))
static void ambiente_unix(void)
{
    _fmode = _O_BINARY;

    /* HOME, para o ``~/.supremrc`` do usuário.
     *
     * O motor monta o caminho desse arquivo a partir de HOME, que no Windows
     * não existe — o equivalente é USERPROFILE. O patch 0003 já impede que a
     * ausência derrube o processo; isto é o outro lado, para que o arquivo
     * de preferências do usuário continue sendo lido aqui como no Linux.
     * Se USERPROFILE também faltar, fica sem HOME e o motor pula o arquivo. */
    if (getenv("HOME") == NULL) {
        const char *perfil = getenv("USERPROFILE");

        if (perfil != NULL)
            _putenv_s("HOME", perfil);
    }
}

/* Converte um FILETIME (unidades de 100 ns) para clock_t na base de
 * CLOCKS_PER_SEC, que é o que o fonte espera de times(). */
static clock_t ft_para_clock(const FILETIME *ft)
{
    ULONGLONG t = ((ULONGLONG)ft->dwHighDateTime << 32) | ft->dwLowDateTime;
    return (clock_t)(t / (10000000ULL / (ULONGLONG)CLOCKS_PER_SEC));
}

/* times(): tempo de CPU do processo.
 *
 * O SUPREM-IV usa isto só para dizer quanto cada etapa levou. Se o Windows
 * recusar a consulta — coisa que não acontece num processo próprio —, cai
 * para clock(), que mede o tempo de parede e serve igual para o relatório. */
clock_t times(struct tms *buf)
{
    FILETIME criacao, saida, kernel, usuario;

    if (buf == 0)
        return (clock_t)clock();

    if (GetProcessTimes(GetCurrentProcess(), &criacao, &saida,
                        &kernel, &usuario)) {
        buf->tms_utime = ft_para_clock(&usuario);
        buf->tms_stime = ft_para_clock(&kernel);
    } else {
        buf->tms_utime = (clock_t)clock();
        buf->tms_stime = 0;
    }
    /* Não há processos filhos: o fork() abaixo nunca cria um. */
    buf->tms_cutime = 0;
    buf->tms_cstime = 0;
    return buf->tms_utime + buf->tms_stime;
}

/* fork(): sempre falha, de propósito.
 *
 * O único uso é ``shell/do_action.c``, para rodar um comando em segundo
 * plano quando a linha termina em ``&``. O padrão ali é
 * ``if (fork() == 0) { ...roda...; exit(0); }``: devolver -1 faz o comando
 * em segundo plano simplesmente não rodar, que é o certo. Devolver 0 seria
 * desastroso — o processo rodaria o trabalho e chamaria exit(), matando o
 * motor no meio de uma simulação.
 *
 * O MOS-Studio nunca manda uma linha com ``&``; a interface não tem como. */
int fork(void)
{
    return -1;
}

/* wait(): companheira do fork() acima.
 *
 * Os dois usos no fonte são ``while ((w = wait(&status)) != pid && w != -1);``
 * logo depois de criar um filho. Como fork() nunca cria um, devolver -1 faz
 * o laço terminar na primeira volta — que é o comportamento certo quando não
 * há filho nenhum para esperar. */
int wait(int *status)
{
    if (status != 0)
        *status = 0;
    return -1;
}

/* getpwuid/getpwnam: só a camada X11 as chama, e ela não é compilada. */
struct passwd *getpwuid(int uid)
{
    static struct passwd p;
    (void)uid;
    p.pw_name = getenv("USERNAME");
    p.pw_dir = getenv("USERPROFILE");
    return (p.pw_dir != 0) ? &p : 0;
}

struct passwd *getpwnam(const char *nome)
{
    (void)nome;
    return getpwuid(0);
}

int getuid(void)
{
    return 0;
}
