#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

char buffer[2048];
int idxs[100];
char * parts[100];
char * fixeds[100];
const char * delim = " \t\n";

int find_idx(char ** argv, const char * arg) {
    int idx = 0;
    char * saveptr;
    while (argv[1+idx]) {
        char * argv_i = malloc(strlen(argv[1+idx]));
        strcpy(argv_i, argv[1+idx]);
        argv_i = strtok_r(argv_i, ":", &saveptr);
        if (strcmp(argv_i, arg) == 0) {
            return idx;
        }
        idx += 1;
        free(argv_i);
    }
    return -1;
}

int main(int argc, char ** argv) {
    char * b = &buffer[0];
    char * saveptr;
    size_t len, n = sizeof(buffer);
    len = getline(&b, &n, stdin);
    if (len == -1) return EXIT_SUCCESS;
    int col = 0;
    char * tok = strtok_r(b, delim, &saveptr);
    while (tok) {
        int idx = find_idx(argv, tok);
        idxs[col] = idx;
        tok = strtok_r(0, delim, &saveptr);
        col += 1;
    }
    int ncols = col;
    for (int i = 1; i < argc; i++) {
        char * arg = argv[i];
        strtok_r(arg, ":", &saveptr);
        char * alt = strtok_r(0, ":", &saveptr);
        arg = alt ? alt : arg;
        strtok_r(arg, "=", &saveptr);
        fputs(arg, stdout);
        char * fixed = strtok_r(0, "=", &saveptr);
        if (fixed) fixeds[i] = fixed;
        if (i != argc-1) putchar(' ');
    }
    printf("\n");
    while (-1 != (len = getline(&b, &n, stdin))) {
        for (int i = 0; i < len; i++) buffer[i] = tolower(buffer[i]);
        for (int i = 0; i < ncols; i++) parts[i] = 0;
        int col = 0;
        char * tok = strtok_r(b, delim, &saveptr);
        while (tok) {
            parts[idxs[col]] = tok;
            tok = strtok_r(0, delim, &saveptr);
            col += 1;
        }
        if (col != ncols) {
            fprintf(stderr, "skipping: #cols = %d, expected %d\n", col, ncols);
            continue;
        }
        for (int i = 0; i < ncols; i++) {
            if (fixeds[i]) fputs(fixeds[i], stdout);
            else if (parts[i]) fputs(parts[i], stdout);
            else continue;
            if (i != ncols-1) putchar(' ');
        }
        printf("\n");
    }
}
