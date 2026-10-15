/* <sys/times.h> para o mingw: o tipo e a função de tempo de CPU.
 *
 * O SUPREM-IV usa times() só para relatar quanto cada etapa levou. A
 * implementação está em win_compat.c e usa GetProcessTimes. */
#ifndef MOSSTUDIO_SYS_TIMES_H
#define MOSSTUDIO_SYS_TIMES_H

#include <time.h>

struct tms {
    clock_t tms_utime;      /* tempo de CPU em modo usuário   */
    clock_t tms_stime;      /* tempo de CPU em modo sistema   */
    clock_t tms_cutime;     /* idem, somando os filhos        */
    clock_t tms_cstime;
};

clock_t times(struct tms *buf);

#endif
