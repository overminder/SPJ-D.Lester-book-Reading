import functools

from pypy.rlib.objectmodel import specialize
from pypy.rlib.unroll import unrolling_iterable

from spj.errors import InterpError
#from spj.utils import write_str
from spj.gmachine import (BasePrimOp, Node, NInt, NGlobal, eval_instr,
                          unwind, Push, Pop, Update, Cond)

class PrimOpManager(object):
    def __init__(self):
        self.ops = {}
        self.scs = {}

    def add_op(self, name, prim_op):
        self.ops[name] = prim_op

    def add_sc(self, name, sc):
        self.scs[name] = sc

def mk_prim_op(name, func, argtypes):
    func._always_inline_ = True
    arity = len(argtypes)
    #
    class PrimOp(BasePrimOp):
        def to_s(self):
            return '#<Instr:%s>' % name

        def get_arity(self):
            return arity

        def call(self, state, args_w):
            assert len(args_w) == arity
            for i, argtype in enumerate(argtypes):
                w_arg = args_w[i]
                if not isinstance(w_arg, argtype):
                    raise InterpError('%s: type error' % self.to_s())
            w_result = func(args_w)
            state.stack_push(state.heap.alloc(w_result))
    #
    PrimOp.__name__ = 'PrimOp/%s' % name
    return PrimOp()

module = PrimOpManager()

def register(name, argtypes):
    "NOT_RPYTHON"
    # MAGIC!
    arity = len(argtypes)
    arityrange = range(arity)
    unboxers = [make_unboxer(arg) for arg in argtypes]
    ipairs = unrolling_iterable(zip(arityrange, unboxers))
    def decorator(function):
        "NOT_RPYTHON"
        @functools.wraps(function)
        def wrapped_func(args):
            assert len(args) == arity
            tupleargs = ()
            for i, unboxer in ipairs:
                x = args[i]
                assert isinstance(x, argtypes[i])
                tupleargs += (unboxers[i](x), )
            result = function(*tupleargs)
            return box(result)
        prim_op = mk_prim_op(name, wrapped_func, argtypes)
        module.add_op(name, prim_op)
        if argtypes == [NInt, NInt]:
            sc = NGlobal(name, 2, [Push(1), eval_instr, Push(1),
                                   eval_instr, prim_op, Update(2),
                                   Pop(2), unwind])
        elif argtypes == [NInt]:
            sc = NGlobal(name, 1, [Push(0), eval_instr, prim_op,
                                   Update(1), Pop(1), unwind])
        else:
            assert 0, 'dont know how to make sc for %s' % prim_op.to_s()
        module.add_sc(name, sc)
        return prim_op
    return decorator

def make_unboxer(node_type):
    "NOT_RPYTHON"
    if node_type == NInt:
        return lambda node: node.ival
    if node_type == Node:
        return lambda node: node
    else:
        assert 0, 'dont know how to unwrap this type: %s' % node_type

@specialize.argtype(0)
def box(v):
    if isinstance(v, int): # including bool
        return NInt(v)
    elif isinstance(v, Node):
        return v
    assert 0

def mk_binary_op(name, py_op, node_types):
    "NOT_RPYTHON"
    code = '''
def wrap(a, b):
    return a %(py_op)s b
''' % locals()
    d = {}
    exec code in d
    f = d['wrap']
    f._always_inline_ = True
    register(name, node_types)(f)

for name in '+ - * / < <= > >= =='.split():
    mk_binary_op(name, name, [NInt, NInt])

mk_binary_op('/=', '!=', [NInt, NInt])

@register('negate', [NInt])
def int_negate(a):
    return -a

# if
module.add_sc('if', NGlobal('if', 3, [Push(0), eval_instr, Cond([Push(1)],
                                                                [Push(2)]),
                                      Update(3), Pop(3), unwind]))

