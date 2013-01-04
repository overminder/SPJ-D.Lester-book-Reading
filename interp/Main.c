#include "Rts.h"

static void
usage(char *progName) {
    fprintf(stderr, "usage: %s inputFile\n", progName);
}

int
main(int argc, char **argv) {
    char *fileName;
    FILE *handle;
    GMState *state;

    if (argc != 2) {
        usage(argv[0]);
        exit(1);
    }

    fileName = argv[1];
    if (0 == strcmp(fileName, "-")) {
        handle = stdin;
    }
    else {
        handle = fopen(fileName, "r");
    }

    if (!handle) {
        perror(fileName);
        exit(1);
    }

    state = loadFile(handle);
    if (handle != stdin) {
        fclose(handle);
    }

    evaluate(state);
    showState(state);
    closeState(state);

    return 0;
}

