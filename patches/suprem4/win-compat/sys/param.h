/* <sys/param.h> no mingw: só o HZ que o sysdep.h espera encontrar. */
#ifndef MOSSTUDIO_SYS_PARAM_H
#define MOSSTUDIO_SYS_PARAM_H
#ifndef HZ
#define HZ 1000          /* casa com o CLOCKS_PER_SEC usado em win_compat.c */
#endif
#endif
