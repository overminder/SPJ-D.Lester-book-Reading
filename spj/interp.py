from pypy.rlib import jit
from pypy.rlib.objectmodel import we_are_translated
from pypy.rlib.unroll import unrolling_iterable

from spj.errors import InterpError

STACKSIZE = 8
DUMPSIZE = 1024

class Dump(object):
    _immutable_fields_ = ['pc', 'code', 'stackitems[*]']
    def __init__(self, pc, code, stackitems):
        self.pc = pc
        self.code = code
        self.stackitems = stackitems

class State(object):
    _virtualizable2_ = ['code', 'pc', 'stackptr', 'dumpptr',
                        'stack[*]', 'dump', 'env', 'names']
    _immutable_fields_ = ['stack', 'dump', 'env', 'names[*]']
    def __init__(self, initcode, env=None, names=None):
        self.stack = [None] * STACKSIZE
        self.stackptr = 0 # first empty slot in the stack
        self.dump = [None] * DUMPSIZE
        self.dumpptr = 0
        self.code = initcode
        self.pc = 0
        self.env = env
        self.names = names[:]

    def push(self, addr):
        index = self.stackptr
        assert index >= 0
        self.stack[index] = addr
        self.stackptr = index + 1

    def pop(self):
        self.stackptr -= 1
        index = self.stackptr
        assert index >= 0
        res = self.stack[index]
        self.stack[index] = None
        return res

    def ref(self, i):
        assert i >= 0
        index = self.stackptr - i - 1
        if index < 0:
            raise InterpError('ref(%d): no such item' % i)
        return self.stack[index]

    def setnth(self, i, addr):
        assert i >= 0
        index = self.stackptr - i - 1
        if index < 0:
            raise InterpError('setnth(%d): no such item' % i)
        self.stack[index] = addr

    @jit.unroll_safe
    def save_dump(self):
        stackitems = [None] * self.stackptr
        for i in xrange(self.stackptr):
            stackitems[i] = self.stack[i]
            self.stack[i] = None
        self.stackptr = 0
        self.dump[self.dumpptr] = Dump(self.pc, self.code, stackitems)
        self.dumpptr += 1

    @jit.unroll_safe
    def restore_dump(self):
        self.dumpptr -= 1
        dump = self.dump[self.dumpptr] 
        pc, code, stackitems = dump.pc, dump.code, dump.stackitems
        self.dump[self.dumpptr] = None
        self.pc = pc
        self.code = code
        # push old items
        self.clean_stack()
        self.stackptr = len(stackitems)
        for i in xrange(len(stackitems)):
            self.stack[i] = stackitems[i]

    @jit.unroll_safe
    def clean_stack(self):
        for i in xrange(self.stackptr):
            self.stack[i] = None

    def eval(self):
        from spj.jitdriver import driver
        self = jit.hint(self, promote=True,
                              access_directly=True)
        while True:
            driver.jit_merge_point(pc=self.pc, code=self.code,
                                   state=self)
            if self.is_final():
                break
            self.step()
        return self.ref(0)

    def is_final(self):
        return self.pc >= len(self.code)

    def decode_u8(self):
        u8 = read_code(self.code, self.pc) # Shall we use this?
        self.pc += 1
        return ord(u8)

    def decode_i16(self):
        lo = self.decode_u8()
        hi = self.decode_u8()
        if hi > 127:
            hi -= 256
        return (hi << 8) | lo

    def step(self):
        op = self.decode_u8()
        #print opcode_names[op]
        if we_are_translated():
            for i, opname in opdescr:
                if i == op:
                    getattr(self, opname)()
                    break
        else:
            # list lookup
            opdescr_not_translated[op](self)

    @jit.unroll_safe
    def UNWIND(self):
        top_addr = self.ref(0)
        top = top_addr.deref()
        while True:
            if isinstance(top, NInt) or isinstance(top, NConstr):
                if self.dumpptr:
                    self.restore_dump()
                    self.push(top_addr)
                break
            elif isinstance(top, NAp):
                top_addr = top.func
                top = top_addr.deref()
                self.push(top_addr)
                continue
            elif isinstance(top, NGlobal):
                arity = top.arity
                if self.stackptr - 1 < arity:
                    if self.dumpptr:
                        # We are evaluating a sc with not enough args,
                        # which must be caused by a partially applied
                        # primitive function.
                        ak = self.stack[0]
                        self.restore_dump()
                        self.push(ak)
                        return
                    else:
                        raise InterpError('UNWIND: not enough args for %s' %
                                          top.name)
                if arity == 0:
                    pass # No need to get argument for CAFs
                else:
                    self.pop() # Throw away the SC
                    args = [None] * arity
                    last_addr = None # shut off pypy error :(
                    for i in xrange(arity):
                        last_addr = self.pop()
                        last_node = last_addr.deref()
                        assert isinstance(last_node, NAp)
                        args[i] = last_node.arg
                    self.push(last_addr) # This node will be updated
                    for i in xrange(arity - 1, -1, -1):
                        self.push(args[i]) # reversely
                # Enter
                self.code = top.code
                self.pc = 0
                break
            elif isinstance(top, NIndirect):
                points_to = top.addr
                self.setnth(0, points_to)
                top_addr = points_to
                top = top_addr.node
                continue
            else:
                assert 0

    def PUSH_GLOBAL(self):
        oparg = self.decode_i16()
        addr = read_env(self.env, self.names, oparg)
        self.push(addr)

    def PUSH_INT(self):
        oparg = self.decode_i16()
        value = NInt(oparg)
        addr = Addr(value)
        self.push(addr)

    def PUSH_ARG(self):
        oparg = self.decode_i16()
        addr = self.ref(oparg)
        self.push(addr)

    @jit.unroll_safe
    def POP(self):
        oparg = self.decode_i16()
        for _ in xrange(oparg):
            self.pop()

    def UPDATE(self):
        oparg = self.decode_i16()
        src = self.pop()
        dest = self.ref(oparg)
        dest.update(NIndirect(src))

    def MKAP(self):
        func = self.pop()
        arg = self.pop()
        ap_node = NAp(func, arg)
        addr = Addr(ap_node)
        self.push(addr)

    @jit.unroll_safe
    def SLIDE(self):
        oparg = self.decode_i16()
        top = self.pop()
        for _ in xrange(oparg):
            self.pop()
        self.push(top)

    @jit.unroll_safe
    def ALLOC(self):
        oparg = self.decode_i16()
        for _ in xrange(oparg):
            addr = Addr(null_node)
            self.push(addr)

    @jit.unroll_safe
    def EVAL(self):
        a = self.pop()
        self.save_dump()
        self.pc = len(self.code)
        self.clean_stack()
        self.push(a)
        self.UNWIND()

    def COND(self):
        oparg = self.decode_i16()
        top = self.pop().deref()
        assert isinstance(top, NInt)
        if top.ival == 0:
            self.pc += oparg
        # Can Enter Jit?

    def JUMP(self):
        oparg = self.decode_i16()
        self.pc += oparg


class Addr(object):
    def __init__(self, node):
        self.update(node)

    def deref(self):
        return self.node

    def update(self, node):
        self.node = node

    def unwrap(self):
        count = 0
        node = self.deref()
        while isinstance(node, NIndirect):
            if count > 100:
                raise InterpError('<loop> in NIndirect')
            node = node.addr.deref()
            count += 1
        return node


class Node(object):
    def to_s(self):
        return '#<Node>'

    def __repr__(self):
        return self.to_s()

class NInt(Node):
    _immutable_fields_ = ['ival']
    def __init__(self, ival):
        self.ival = ival

    def to_s(self):
        return '#<NInt %d>' % self.ival

class NAp(Node):
    _immutable_fields_ = ['func', 'arg']
    def __init__(self, func, arg):
        self.func = func
        self.arg = arg

class NGlobal(Node):
    _immutable_fields_ = ['name', 'arity', 'code[*]']
    def __init__(self, name, arity, code):
        self.name = name
        self.arity = arity
        self.code = code

    def to_s(self):
        return '#<NGlobal %s>' % self.name

    def __repr__(self):
        return '#<NGlobal %s>' % self.name

class NIndirect(Node):
    _immutable_fields_ = ['addr']
    def __init__(self, addr):
        self.addr = addr

class NConstr(Node):
    pass

null_node = NIndirect(None)

def read_code(code, pc):
    return code[pc]

@jit.elidable
def read_env(env, names, i):
    return env[names[i]]

# more opcode definitions

arith_ops = {}
def mk_arith_ops():
    hs_rator_names = {
        '+': 'ADD',
        '-': 'SUB',
        '*': 'MUL',
        '/': 'DIV',
        '<': 'LT',
        '<=': 'LE',
        '>': 'GT',
        '>=': 'GE',
        '/=': 'NE',
        '==': 'EQ',
    }

    for hs_rator in '+ - * / < <= > >= /= =='.split():
        if hs_rator == '/=':
            py_rator = '!='
        else:
            py_rator = hs_rator
        code = '''
def f(self):
    lhs = self.pop().deref()
    rhs = self.pop().deref()
    assert isinstance(lhs, NInt)
    assert isinstance(rhs, NInt)
    result = NInt(lhs.ival %(py_rator)s rhs.ival)
    self.push(Addr(result)) '''
        d = {'NInt': NInt, 'Addr': Addr} # This, since func capture their
                                         # globals in Python.
        exec code % locals() in d
        f = d['f']
        f.__name__ = 'PRIM_%s' % hs_rator_names[hs_rator]
        setattr(State, f.__name__, f)
        arith_ops[hs_rator] = f.__name__
#
mk_arith_ops()

# Hack to create opcode mapping with all the dispatch functions
opcode_names = []
for name in State.__dict__:
    if all(c.isupper() or c == '_' for c in name):
        opcode_names.append(name)

opdescr = unrolling_iterable(enumerate(opcode_names))

opdescr_not_translated = [getattr(State, name) for name in opcode_names]

# provides a mapping for name -> opcode-value
class Op(object):
    for i, name in enumerate(opcode_names):
        vars()[name] = i
    del i
    del name

# XXX we define prim func and descr for compiler to use in the end
def mk_binary_code(op):
    template = [Op.PUSH_ARG, 1, 0,
                Op.EVAL,
                Op.PUSH_ARG, 1, 0,
                Op.EVAL,
                op,
                Op.UPDATE,   2, 0,
                Op.POP,      2, 0,
                Op.UNWIND]
    return map(chr, template)

# primitive functions for initial env.
prim_funcs = {hs_rator: NGlobal(name, 2, mk_binary_code(getattr(Op, name)))
               for hs_rator, name in arith_ops.iteritems()}

prim_funcs['if'] = NGlobal('PRIM_IF', 3,
                           map(chr, [Op.PUSH_ARG, 0, 0,
                                     Op.EVAL,
                                     Op.COND,     6, 0,
                                     Op.PUSH_ARG, 1, 0,
                                     Op.JUMP,     3, 0,
                                     Op.PUSH_ARG, 2, 0,
                                     Op.UPDATE,   3, 0,
                                     Op.POP,      3, 0,
                                     Op.UNWIND]))

class OpDescr(object):
    def __init__(self, op, arity):
        self.op = op
        self.arity = arity

primop_descrs = {hs_rator: OpDescr(getattr(Op, name), 2)
                 for hs_rator, name in arith_ops.iteritems()}

