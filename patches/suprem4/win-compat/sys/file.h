/* <sys/file.h> não existe no mingw. O fonte só o inclui; nada do que ele
 * declara é usado fora da camada X11, que não é compilada. */
#ifndef MOSSTUDIO_SYS_FILE_H
#define MOSSTUDIO_SYS_FILE_H
#include <fcntl.h>
#endif
