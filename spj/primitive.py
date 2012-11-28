import functools

from pypy.rlib.objectmodel import specialize
from pypy.rlib.unroll import unrolling_iterable

from spj.evaluator import Node, NInt

class PrimManager(object):
    def __init__(self):
        self.functions = {}

    def add_function(self, prim_func):
        self.functions[prim_func.name] = prim_func

class PrimFunction(object):
    def __init__(self, name, func, argtypes, strictargs):
        self.name = name
        self.func = func
        self.argtypes = argtypes
        self.arity = len(argtypes)
        self.strictargs = strictargs

    def call(self, args):
        assert len(args) == self.arity
        for i, argtype in enumerate(self.argtypes):
            arg = args[i]
            if not isinstance(arg, argtype):
                from spj.errors import InterpError
                raise InterpError('PrimFunction(%s).call: type error'
                                  % self.name)
        return self.func(args)

module = PrimManager()

def register(name, argtypes, strictargs=None):
    # MAGIC!
    arity = len(argtypes)
    arityrange = unrolling_iterable(range(arity))
    if not strictargs:
        strictargs = [True] * arity
    def decorator(function):
        @functools.wraps(function)
        def wrapped(args):
            assert len(args) == arity
            tupleargs = ()
            for i in arityrange:
                x = args[i]
                assert isinstance(x, argtypes[i])
                tupleargs += (unwrap_data_node(x), )
            result = function(*tupleargs)
            return wrap_interp_value(result)
        prim_func = PrimFunction(name, wrapped, argtypes, strictargs)
        module.add_function(prim_func)
        return prim_func
    return decorator

@specialize.argtype(0)
def unwrap_data_node(data_node):
    if isinstance(data_node, NInt):
        return data_node.ival
    elif isinstance(data_node, Node):
        return data_node # the prim func doesn't need this arg to be unwrapped
    assert 0

@specialize.argtype(0)
def wrap_interp_value(v):
    if isinstance(v, int):
        return NInt(v)
    elif isinstance(v, Node):
        return v
    assert 0

@register('+', [NInt, NInt])
def int_add(a, b):
    return a + b

@register('-', [NInt, NInt])
def int_sub(a, b):
    return a - b

@register('*', [NInt, NInt])
def int_mul(a, b):
    return a * b

@register('/', [NInt, NInt])
def int_div(a, b):
    return a / b

@register('negate', [NInt])
def int_negate(a):
    return -a

@register('if_not_zero', [NInt, Node, Node], [True, False, False])
def int_if(cond, if_nonzero, if_zero):
    if cond:
        return if_nonzero
    else:
        return if_zero

