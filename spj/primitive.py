import functools

from pypy.rlib.objectmodel import specialize
from pypy.rlib.unroll import unrolling_iterable

from spj.errors import InterpError
#from spj.utils import write_str
from spj.timrun import (BasePrimOp, Take, PushCode, PushArg, Enter,
                        Return, Cond, W_Value, W_Int)

class PrimOpManager(object):
    def __init__(self):
        "NOT_RPYTHON"
        self.ops = {}
        self.scs = {}
        self.codefrags = []

    def add_op(self, name, prim_op):
        "NOT_RPYTHON"
        self.ops[name] = prim_op

    def add_codefrag(self, code):
        "NOT_RPYTHON"
        i = len(self.codefrags)
        self.codefrags.append(code)
        return i

    def add_sc(self, name, sc):
        "NOT_RPYTHON"
        self.scs[name] = sc

def mk_prim_op(name, func, argtypes):
    "NOT_RPYTHON"
    func._always_inline_ = True
    arity = len(argtypes)
    #
    class PrimOp(BasePrimOp):
        def to_s(self):
            return '#<PrimOp:%s>' % name

        def get_arity(self):
            return arity

        def call(self, state, args_w):
            assert len(args_w) == arity
            for i, argtype in enumerate(argtypes):
                w_arg = args_w[i]
                if not isinstance(w_arg, argtype):
                    raise InterpError('%s: type error' % self.to_s())
            w_result = func(args_w)
            return w_result
    #
    PrimOp.__name__ = 'PrimOp:%s' % name
    return PrimOp()

module = PrimOpManager()

def register(name, argtypes, make_func=True):
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
        if make_func:
            if argtypes == [W_Int, W_Int]:
                auxcode1 = [prim_op, Return()]
                i1 = module.add_codefrag(auxcode1)
                auxcode2 = [PushCode(i1), PushArg(0), Enter()]
                i2 = module.add_codefrag(auxcode2)
                sc = [Take(2), PushCode(i2), PushArg(1), Enter()]
            elif argtypes == [W_Int]:
                auxcode1 = [prim_op, Return()]
                i1 = module.add_codefrag(auxcode1)
                sc = [Take(1), PushCode(i1), PushArg(0), Enter()]
            else:
                assert 0, 'dont know how to make sc for %s' % prim_op.to_s()
            module.add_sc(name, sc)
        return prim_op
    return decorator

def make_unboxer(value_type):
    "NOT_RPYTHON"
    if value_type == W_Int:
        return lambda w_int: w_int.ival
    if value_type == W_Value:
        return lambda w_val: w_val
    else:
        assert 0, 'dont know how to unwrap this type: %s' % value_type

@specialize.argtype(0)
def box(v):
    if isinstance(v, int): # including bool
        return W_Int(v)
    elif isinstance(v, W_Value):
        return v
    assert 0

def mk_binary_op(name, py_op, value_types):
    "NOT_RPYTHON"
    code = '''
def wrap(a, b):
    return a %(py_op)s b ''' % locals()
    d = {}
    exec code in d
    f = d['wrap']
    f._always_inline_ = True
    register(name, value_types)(f)

for name in '+ - * / < <= > >= =='.split():
    mk_binary_op(name, name, [W_Int, W_Int])

mk_binary_op('/=', '!=', [W_Int, W_Int])

@register('negate', [W_Int])
def int_negate(a):
    return -a

# add if
def add_if():
    true_code = [PushArg(1), Enter()]
    false_code = [PushArg(2), Enter()]
    i1 = module.add_codefrag(true_code)
    i2 = module.add_codefrag(false_code)

    cond_code = [Cond(i1, i2)]
    i0 = module.add_codefrag(cond_code)

    sc = [Take(3), PushCode(i0), PushArg(0), Enter()]
    module.add_sc('if', sc)
add_if()

