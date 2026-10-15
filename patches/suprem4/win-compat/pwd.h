/* <pwd.h> para o mingw. Só a camada X11 (não compilada) consulta o registro
 * de usuário; as funções existem para o caso de alguém compilar aquela parte. */
#ifndef MOSSTUDIO_PWD_H
#define MOSSTUDIO_PWD_H

struct passwd {
    char *pw_name;
    char *pw_dir;
};

struct passwd *getpwuid(int uid);
struct passwd *getpwnam(const char *nome);
int getuid(void);

#endif
