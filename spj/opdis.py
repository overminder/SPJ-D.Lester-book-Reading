from spj.interp import Op, opcode_names

def decode_i16(code, i):
    lo = ord(code[i])
    hi = ord(code[i + 1])
    if hi > 127:
        hi -= 256
    return (hi << 8) | lo

def dis(sc, names):
    print '<Sc %s arity=%d>' % (sc.name, sc.arity)
    i = 0
    pretab = 8
    def write(s):
        s = ' ' * pretab + s
        print s

    while i < len(sc.code):
        op = ord(sc.code[i])
        opname = opcode_names[op]
        if op in [Op.EVAL, Op.UNWIND, Op.MKAP] or opname.startswith('PRIM'):
            # no arg
            write('%3d %-12s' % (i, opname))
            i += 1
        else:
            oparg = decode_i16(sc.code, i + 1)
            # some special cases
            if op in [Op.COND, Op.JUMP]:
                write('%3d %-12s %3d (to %d)' % (
                        i, opcode_names[op], oparg, i + oparg + 3))
            elif op == Op.PUSH_GLOBAL:
                write('%3d %-12s %3d (%s)' % (i, opcode_names[op], oparg,
                    names[oparg]))
            else:
                write('%3d %-12s %3d' % (i, opcode_names[op], oparg))
            i += 3

def jit_getloc(pc, code):
    dumpptr = 0
    op = ord(code[pc])
    opname = opcode_names[op]
    if op in [Op.EVAL, Op.UNWIND, Op.MKAP] or opname.startswith('PRIM'):
        # no arg
        return '%d: %s ;; %d' % (pc, opname, dumpptr)
    else:
        oparg = decode_i16(code, pc + 1)
        # some special cases
        if op in [Op.COND, Op.JUMP]:
            return '%d: %s %d (to %d) ;; %d' % (
                    pc, opname, oparg, pc + oparg + 3, dumpptr)
        else:
            return '%d: %s %d ;; %d' % (
                    pc, opname, oparg, dumpptr)

