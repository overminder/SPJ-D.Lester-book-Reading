#include "Rts.h"

typedef struct {
    NODE_HEADER;
    intptr_t copiedTo;
} GcNode;

typedef Node *(*GcCopier)(Node *, GMState *);

#define DECL_GC_COPIER(name) \
    static name ## Node * \
    copy ## name ## Node(name ## Node *, GMState *);
    NODE_TYPE_LIST(DECL_GC_COPIER)
#undef DECL_GC_COPIER

#define MK_GC_HANDLER(name) \
    (GcCopier) copy ## name ## Node,
    static GcCopier gcHandlerTable[] = {
        0,
        NODE_TYPE_LIST(MK_GC_HANDLER)
        0
    };
#undef MK_GC_HANDLER

#define MK_SIZE_TABLE(name) \
    sizeof(name ## Node),
    static size_t nodeSizeTable[] = {
        0,
        NODE_TYPE_LIST(MK_SIZE_TABLE)
        0
    };
#undef MK_SIZE_TABLE

static inline Node *
copyNode(Node *node, GMState *state) {
    GcCopier handler = gcHandlerTable[node->typeTag];
    return handler(node, state);
}

#define DEFAULT_VARSIZE_COPY_IMPL(typeName, size, doInterior) \
    if (node->gcMark == GC_COPIED_FROM) { \
        node = (typeName ## Node *) ((GcNode *) node)->copiedTo; \
    } \
    else { \
        memcpy((void *) state->gc.copyPtr, node, size); \
        node->gcMark = GC_COPIED_FROM; \
        ((GcNode *) node)->copiedTo = state->gc.copyPtr; \
        \
        node = (typeName ## Node *) state->gc.copyPtr; \
        node->gcMark = GC_COPIED_TO; \
        state->gc.copyPtr += size; \
        doInterior \
    }

#define DEFAULT_COPY_IMPL(typeName, doInterior) \
    DEFAULT_VARSIZE_COPY_IMPL(typeName, sizeof(typeName ## Node), doInterior)

#define DO_NOTHING (void) 0;

#define DEF_GC_COPIER(name) \
    static name ## Node * \
    copy ## name ## Node(name ## Node *node, GMState *state)

DEF_GC_COPIER(Int) {
    DEFAULT_COPY_IMPL(Int, DO_NOTHING);
    return node;
}

DEF_GC_COPIER(Ap) {
    DEFAULT_COPY_IMPL(Ap,
        node->func = copyNode(node->func, state);
        node->arg = copyNode(node->arg, state);
    );
    return node;
}

DEF_GC_COPIER(Indirect) {
    DEFAULT_COPY_IMPL(Indirect,
        node->dest = copyNode(node->dest, state);
    );
    return node;
}

#define SC_NODE_SIZE(node) \
    (sizeof(SupercombNode) + \
    ((SupercombNode *) node)->numOfInstr * sizeof(Instr))

DEF_GC_COPIER(Supercomb) {
    size_t scSize = SC_NODE_SIZE(node);
    DEFAULT_VARSIZE_COPY_IMPL(Supercomb, scSize, DO_NOTHING);
    return node;
}

DEF_GC_COPIER(Dump) {
    /* Check invariant on currSc (see Dump's def in Rts.h) */
    ASSERT(node->currSc->typeTag == SupercombNodeType);

    DEFAULT_COPY_IMPL(Dump,
        node->currSc = copySupercombNode(node->currSc, state);
    );
    return node;
}

void
openCollector(GMState *state, size_t size) {
#ifdef GMACH_GC_DEBUG
    state->gc.fromSpace = (intptr_t) malloc(size);
    state->gc.allocPtr = state->gc.fromSpace;
#else
    state->gc.fromSpace = (intptr_t) malloc(size * 2);
    state->gc.allocPtr = state->gc.fromSpace;
    state->gc.toSpace = state->gc.fromSpace + size;
#endif
    state->gc.mallocBase = (void *) state->gc.fromSpace;
    state->gc.heapSize = size;
}

void
closeCollector(GMState *state) {
    free(state->gc.mallocBase);
    state->gc.fromSpace = 0;
    state->gc.toSpace = 0;
    state->gc.heapSize = 0;
    state->gc.mallocBase = NULL;
    state->gc.allocPtr = 0;
}

intptr_t
collectGarbage(GMState *state, size_t size) {
    intptr_t i;
    intptr_t addr;
    intptr_t lastSize;
    intptr_t tmp;
    Node *ptr;
    Node **iter;
    intptr_t pcOffset = state->interp.pc - state->interp.currSc->code;

    /* Initialize the copying process */
#ifdef GMACH_GC_DEBUG
    state->gc.toSpace = (intptr_t) malloc(state->gc.heapSize);
#endif
    state->gc.copyPtr = state->gc.toSpace;

    /* Check invariant on currSc (see GMState's def in Rts.h) */
    ASSERT(state->interp.currSc->typeTag == SupercombNodeType);

    /* Copy globals */
    for (i = 0; state->interp.globals[i]; ++i) {
        ptr = state->interp.globals[i];
        /* Might be a CAF */
        state->interp.globals[i] = copyNode(ptr, state);
    }

    /* Copy current supercomb */
    state->interp.currSc = copySupercombNode(state->interp.currSc, state);
    state->interp.pc = state->interp.currSc->code + pcOffset;

    for (iter = state->interp.stack; iter < state->interp.stackPtr; ++iter) {
        *iter = copyNode(*iter, state);
    }

    for (addr = state->gc.toSpace; addr < state->gc.copyPtr; addr += lastSize) {
        ptr = (Node *) addr;
        if (ptr->typeTag == SupercombNodeType) {
            lastSize = SC_NODE_SIZE(ptr);
        }
        else {
            lastSize = nodeSizeTable[ptr->typeTag];
        }
        ptr->gcMark = GC_UNREACHABLE;
    }

    allocPtr = state->gc.allocPtr = state->gc.copyPtr + size;
    allocLimit = state->gc.toSpace + state->gc.heapSize;
    if (allocPtr > allocLimit) {
        BARF("Out of heap");
    }
    tmp = state->gc.fromSpace;
    state->gc.fromSpace = state->gc.toSpace;
    state->gc.toSpace = tmp;
#ifdef GMACH_GC_DEBUG
    free((void *) state->gc.toSpace);
#endif
    return allocPtr - size;
}

