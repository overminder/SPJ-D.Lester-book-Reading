#include "Rts.h"

static inline int
opHasArg(uint8_t op) {
    return op > OpUnwind;
}

static void
showNodeLite(Node *node) {
    switch (node->typeTag) {
    case IntNodeType:
        printf("%ld", ((IntNode *) node)->intVal);
        break;
    case ApNodeType:
        printf("Ap");
        break;
    case IndirectNodeType:
        printf("Ind");
        break;
    case SupercombNodeType:
        printf("Sc #%d", ((SupercombNode *) node)->globalIndex);
        break;
    case DumpNodeType:
        printf("Dump #%d", ((DumpNode *) node)->depth);
        break;
    default:
        fprintf(stderr, "type = %d\n", node->typeTag);
        BARF("invalid node type");
    }
}

static void
showInstr(Instr *instr) {
#define OP(name) \
    #name,
    static char *opNames[] = {
        "BeforeFirstOp",
        #include "OpcodeDef.inc"
        "AfterLastOp"
    };
#undef OP

    printf("(%s", opNames[instr->opcode]);
    if (opHasArg(instr->opcode)) {
        printf(" %d", instr->oparg);
    }
    printf(")");
}

static void
debugDispatch(GMState *state, Instr *pc, Node **stackPtr) {
    Node **node;
    printf("Instr=");
    showInstr(pc);
    printf(", stack(lhs is top)=[");
    for (node = stackPtr - 1; node >= state->interp.stack; --node) {
        if (node != stackPtr - 1) {
            printf(",");
        }
        showNodeLite(*node);
        if ((*node)->typeTag == DumpNodeType) {
            break;
        }
    }
    printf("]\n");
}

/* Big endian */
static inline int32_t
readInt32(FILE *f) {
    int32_t out;
    int8_t repr[4];
    if (fread(repr, 4, 1, f) != 1) {
        BARF("not enough");
    }
    out = repr[0] << 24
        | repr[1] << 16
        | repr[2] << 8
        | repr[3];
    return out;
}

static inline int64_t
readInstr(FILE *f) {
    Instr out;
    out.opcode = fgetc(f);
    if (opHasArg(out.opcode)) {
        out.oparg = readInt32(f);
    }
    else {
        out.oparg = 0;
    }
    return out.as_i64;
}

static void *
allocFromState(GMState *state, size_t size) {
    intptr_t ptr = state->gc.allocPtr;
    state->gc.allocPtr += size;
    if (state->gc.allocPtr > state->gc.fromSpace + state->gc.heapSize) {
        /* no enough space, alloc failed */
        state->gc.allocPtr -= size;
        return NULL;
    }
    else {
        return (void *) ptr;
    }
}

static SupercombNode *
readSCNode(FILE *f, int32_t nth, GMState *state) {
    int64_t i;
    int64_t arity = readInt32(f);
    int64_t numOfInstr = readInt32(f);
    SupercombNode *sc = allocFromState(state,
                                       sizeof(*sc) +
                                       sizeof(Instr) * numOfInstr);
    if (!sc) {
        BARF("heap exhausted when building initial state");
    }
    sc->gcMark = GC_UNREACHABLE;
    sc->typeTag = SupercombNodeType;
    sc->arity = arity;
    sc->globalIndex = nth;
    sc->numOfInstr = numOfInstr;
    for (i = 0; i < numOfInstr; ++i) {
        sc->code[i].as_i64 = readInstr(f);
    }
    return sc;
}

GMState *
loadFile(FILE *f) {
    int64_t numOfSC, i;
    GMState *state = malloc(sizeof(*state));
    openCollector(state, 64 * 1024);

    numOfSC = readInt32(f);
    state->interp.globals = malloc(sizeof(Node *) * (1 + numOfSC));
    for (i = 0; i < numOfSC; ++i) {
        state->interp.globals[i] = (Node *) readSCNode(f, i, state);
    }
    state->interp.globals[i] = NULL;

    state->interp.stackPtr = state->interp.stack;
    state->interp.currSc = (SupercombNode *) state->interp.globals[0];
    state->interp.pc = state->interp.currSc->code;
    return state;
}

void
closeState(GMState *state) {
    free(state->interp.globals);
    closeCollector(state);
    free(state);
}

void
showState(GMState *state) {
    printf("showState => ");
    showNodeLite(state->interp.stackPtr[-1]);
    printf("\n");
}

void
evaluate(GMState *state) {

#define OP(name) \
    &&Handle ## name,
    static void *jumpTable[] = {
        0,
        #include "OpcodeDef.inc"
        0
    };
#undef OP

    /* Note that since supercomb is also being moved around by the
       GC, we need to save and restore pc during GC as well. */
#define RETURN_FROM_GC() \
    pc = state->interp.pc; \
    currSc = state->interp.currSc; \
    stackPtr = state->interp.stackPtr
#define JUST_ENTER_EVALUATE() \
    RETURN_FROM_GC(); \
    allocPtr = state->gc.allocPtr; \
    allocLimit = state->gc.fromSpace + state->gc.heapSize; \
    stackLimit = state->interp.stack + STACK_SIZE
#define PREPARE_FOR_GC() \
    state->interp.stackPtr = stackPtr; \
    state->interp.currSc = currSc; \
    state->interp.pc = pc
#define SUSPEND_EVALUATE() \
    PREPARE_FOR_GC(); \
    state->gc.allocPtr = allocPtr
#define REALLY_MACRO_STR(x) #x
#define MACRO_STR(x) REALLY_MACRO_STR(x)
#define PUSH(x) \
    if (stackPtr >= stackLimit) { \
        BARF("Interpreter stack overflow.\nConsider enlarge the stack? " \
             "(Current stack size is " MACRO_STR(STACK_SIZE) " nodes.)"); \
    } \
    *stackPtr++ = x
#define POP() *--stackPtr
#define DROP(n) stackPtr -= n
#define NTH_LOCAL(n) stackPtr[-(1 + n)]
#define NTH_GLOBAL(n) globals[n]
#define NUM_OF_STACK_ITEMS() (stackPtr - state->interp.stack)

#define ALLOC_NODE(nodeType, dest) \
    ALLOC(sizeof(nodeType ## Node), Node *, dest)

#define ALLOC(size, ty, dest) \
    dest = (ty) allocPtr; \
    allocPtr += size; \
    if (NEED_GC()) { \
        PREPARE_FOR_GC(); \
        dest = (ty) collectGarbage(state, size); \
        RETURN_FROM_GC(); \
    }

#ifdef GMACH_GC_DEBUG
# define NEED_GC() 1
#else
# define NEED_GC() (allocPtr > allocLimit)
#endif

#define DISPATCH() \
    WHEN_DEBUG_VERBOSE( \
        debugDispatch(state, pc, stackPtr); \
    ) \
    intVal = pc->oparg; \
    ++pc; \
    goto *(jumpTable[pc[-1].opcode])

    /* See HandleUnwind */
#define MK_UNWIND_JUMP_TABLE(name) \
    && Unwind ## name ## Node,

    static void *unwindJumpTable[] = {
        0,
        NODE_TYPE_LIST(MK_UNWIND_JUMP_TABLE)
        0
    };

#undef MK_UNWIND_JUMP_TABLE

    /* Inlined interpreter state */
    Node **stackPtr;
    Node **stackLimit;
    Node **globals = state->interp.globals;
    Instr *pc;
    SupercombNode *currSc;
    int64_t dumpDepth = 0;

    /* Temporary variables */
    Node *x, *v, *w;
    IndirectNode *z;
    int64_t intVal;
    int64_t i;

    JUST_ENTER_EVALUATE();

    /* Indirect-threaded interpreter loop */
    DISPATCH();

HandleMkAp:
    ALLOC_NODE(Ap, w);
    x = POP();
    v = POP();
    MkApNode((ApNode *) w, x, v);
    PUSH(w);
    DISPATCH();

HandlePrimIntAdd:
    ALLOC_NODE(Int, w);
    x = POP();
    v = POP();
    MkIntNode((IntNode *) w,
              ((IntNode *) x)->intVal + ((IntNode *) v)->intVal);
    PUSH(w);
    DISPATCH();

HandlePrimIntSub:
    ALLOC_NODE(Int, w);
    x = POP();
    v = POP();
    MkIntNode((IntNode *) w,
              ((IntNode *) x)->intVal - ((IntNode *) v)->intVal);
    PUSH(w);
    DISPATCH();

HandlePrimIntLt:
    ALLOC_NODE(Int, w);
    x = POP();
    v = POP();
    MkIntNode((IntNode *) w,
              ((IntNode *) x)->intVal < ((IntNode *) v)->intVal);
    PUSH(w);
    DISPATCH();

HandleEval:
    ALLOC_NODE(Dump, w);
    x = POP();
    MkDumpNode((DumpNode *) w, stackPtr, currSc, pc, ++dumpDepth);
    PUSH(w);
    PUSH(x);
    goto HandleUnwind;

HandleUnwind:

#define DISPATCH_UNWIND() \
    goto *(unwindJumpTable[x->typeTag])

    x = NTH_LOCAL(0);
    DISPATCH_UNWIND();

UnwindIntNode:
    if (stackPtr - state->interp.stack == 1) {
        /* Stack is empty: halt the machine */
        SUSPEND_EVALUATE();
        return;
    }
    else {
        w = NTH_LOCAL(1);
        ASSERT(w->typeTag == DumpNodeType);
        ASSERT(dumpDepth == ((DumpNode *) w)->depth);
        --dumpDepth;
        currSc = ((DumpNode *) w)->currSc;
        pc = currSc->code + ((DumpNode *) w)->pcOffset;
        stackPtr = ((DumpNode *) w)->stackPtr;
        PUSH(x);
        DISPATCH();
    }

UnwindApNode:
    x = ((ApNode *) x)->func;
    PUSH(x);
    DISPATCH_UNWIND();

UnwindIndirectNode:
    x = ((IndirectNode *) x)->dest;
    NTH_LOCAL(0) = x;
    DISPATCH_UNWIND();

UnwindSupercombNode:
    currSc = (SupercombNode *) x;
    intVal = currSc->arity;
    if (NUM_OF_STACK_ITEMS() < intVal + 1) {
        fprintf(stderr, "evaluate: not enough arguments for <Sc #%d>\n",
                currSc->globalIndex);
        exit(1);
    }
    for (i = 0; i < intVal; ++i) {
        NTH_LOCAL(i) = ((ApNode *) NTH_LOCAL(i + 1))->arg;
    }
    pc = currSc->code;
    DISPATCH();

UnwindDumpNode:
    BARF("DumpNode unwound: possibly stack underflow?");

#undef DISPATCH_UNWIND

HandlePrimIntCond:
    /* Jump if false */
    x = POP();
    if (((IntNode *) x)->intVal == 0) {
        pc += intVal;
    }
    DISPATCH();

HandleJump:
    pc += intVal;
    DISPATCH();

HandlePushInt:
    ALLOC_NODE(Int, w);
    MkIntNode((IntNode *) w, intVal);
    PUSH(w);
    DISPATCH();

HandlePushLocal:
    w = NTH_LOCAL(intVal);
    PUSH(w);
    DISPATCH();

HandlePushGlobal:
    w = NTH_GLOBAL(intVal);
    PUSH(w);
    DISPATCH();

HandlePop:
    DROP(intVal);
    DISPATCH();

HandleUpdate:
    x = POP();
    MkIndirectNode((IndirectNode *) NTH_LOCAL(intVal), x);
    DISPATCH();

HandleSlide:
    x = POP();
    DROP(intVal);
    PUSH(x);
    DISPATCH();

HandleAlloc:
    ALLOC(sizeof(IndirectNode) * intVal, IndirectNode *, z);
    for (i = 0; i < intVal; ++i) {
        MkIndirectNode(z + i, NULL);
        PUSH((Node *) (z + i));
    }
    DISPATCH();

    return;
}
