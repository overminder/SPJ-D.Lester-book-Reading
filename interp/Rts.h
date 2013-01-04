#ifndef RTS_H
#define RTS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>

#define STACK_SIZE 1024

#define OP(name) \
    Op ## name,
typedef enum {
    OpBeforeFirst = 0,
    #include "OpcodeDef.inc"
    OpAfterLast
} OpCode;
#undef OP

typedef enum {
    GC_UNREACHABLE,
    GC_COPIED_FROM,
    GC_COPIED_TO
} GcMark;

typedef union {
    struct {
        uint8_t opcode;
        int32_t oparg;
    };
    int64_t as_i64;
} Instr;

#define NODE_HEADER     \
    int8_t typeTag;     \
    int8_t gcMark;      \
    int16_t obSize;     \
    int32_t bar;        \

#define NODE_TYPE_LIST(V) \
    V(Int) \
    V(Ap) \
    V(Indirect) \
    V(Supercomb) \
    V(Dump)

typedef struct {
    NODE_HEADER;
} Node;

typedef struct {
    NODE_HEADER;
    int64_t intVal;
} IntNode;

typedef struct {
    NODE_HEADER;
    Node *func;
    Node *arg;
} ApNode;

typedef struct {
    NODE_HEADER;
    Node *dest;
} IndirectNode;

typedef struct {
    NODE_HEADER;
    int16_t arity;
    int16_t globalIndex;
    int32_t numOfInstr;
    Instr code[];
} SupercombNode;

typedef struct {
    NODE_HEADER;
    Node **stackPtr;
    SupercombNode *currSc;  /* Invariant: the same as GMState.interp.currSc */
    int32_t pcOffset;
    int32_t depth;
} DumpNode;

#define MK_NODE_TYPE(name) \
    name ## NodeType,
typedef enum {
    BeforeFirstNodeType = 0,
    NODE_TYPE_LIST(MK_NODE_TYPE)
    AfterLastNodeType
} NodeType;
#undef MK_NODE_TYPE

typedef struct {
    struct interp {
        Node **stackPtr;
        Instr *pc;
        SupercombNode *currSc;  /* For debug/gc's purpose.
                                   Invariant: when collection's triggered,
                                   currSc should always be a ScNode,
                                   e.g., it cannot be inplace-modified
                                   by OpUpdate to become a IndirectNode. */
        Node **globals;
        Node *stack[STACK_SIZE];
    } interp;
    struct gc {
        intptr_t allocPtr;
        intptr_t fromSpace;
        intptr_t toSpace;
        intptr_t heapSize;
        intptr_t copyPtr;
        void *mallocBase;
    } gc;
} GMState;

static inline void
MkIntNode(IntNode *node, int64_t intVal) {
    node->gcMark = GC_UNREACHABLE;
    node->typeTag = IntNodeType;
    node->intVal = intVal;
}

static inline void
MkApNode(ApNode *node, Node *func, Node *arg) {
    node->gcMark = GC_UNREACHABLE;
    node->typeTag = ApNodeType;
    node->func = func;
    node->arg = arg;
}

static inline void
MkIndirectNode(IndirectNode *node, Node *dest) {
    node->gcMark = GC_UNREACHABLE;
    node->typeTag = IndirectNodeType;
    node->dest = dest;
}

static inline void
MkDumpNode(DumpNode *node, Node **stackPtr, SupercombNode *currSc,
           Instr *pc, int64_t depth) {
    node->gcMark = GC_UNREACHABLE;
    node->typeTag = DumpNodeType;
    node->stackPtr = stackPtr;
    node->currSc = currSc;
    node->pcOffset = pc - currSc->code;
    node->depth = depth;
}

GMState *loadFile(FILE *);
void evaluate(GMState *);
void showState(GMState *);
void closeState(GMState *);

register intptr_t allocPtr asm("%rbx");
register intptr_t allocLimit asm("%r12");

void openCollector(GMState *, size_t);
void closeCollector(GMState *);
intptr_t collectGarbage(GMState *, size_t);

#define BARF(wat) \
    fprintf(stderr, "%s:%d:%s: Fatal error: %s\n", \
            __FILE__, __LINE__, __func__, wat); \
    exit(1)

#define ASSERT(wat) \
    do { \
        WHEN_DEBUG( \
            if (!(wat)) { \
                fprintf(stderr, "%s:%d:%s: Assertion failed: %s\n", \
                        __FILE__, __LINE__, __func__, #wat); \
                exit(1); \
            } \
        ) \
    } while (0)

#ifdef GMACH_DEBUG
# define WHEN_DEBUG(x) x
#else
# define WHEN_DEBUG(x)
#endif

#ifdef GMACH_DEBUG_VERBOSE
# define WHEN_DEBUG_VERBOSE(x) x
#else
# define WHEN_DEBUG_VERBOSE(x)
#endif

#endif  /* RTS_H */
