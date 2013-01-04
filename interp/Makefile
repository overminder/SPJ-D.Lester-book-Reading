BIN = Main-c
INCS = $(shell find . -name "*.h") OpcodeDef.inc
OBJS = $(shell find . -name "*.c" | sed s/\.c/.o/)
CFLAGS = -O3 -g $(PROFILE) -Wall $(DEBUGFLAGS)
LDFLAGS = -O3 -g $(PROFILE)
PROFILE = 
ASMFLAGS = -O3
DEBUGFLAGS = -D NGMACH_DEBUG -D NGMACH_DEBUG_VERBOSE -D NGMACH_GC_DEBUG

all : $(BIN)

asmref : Interpreter.s

$(BIN) : $(OBJS)
	gcc $^ $(LDFLAGS) -o $@

%.o : %.c $(INCS)
	gcc $< -c $(CFLAGS) -o $@

%.s : %.c $(INCS)
	gcc $< -c -S $(ASMFLAGS) -o $@

clean :
	rm $(OBJS)
	rm $(BIN)

