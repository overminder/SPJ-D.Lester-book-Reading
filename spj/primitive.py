import functools

from pypy.rlib.objectmodel import specialize
from pypy.rlib.unroll import unrolling_iterable

from spj.evaluator import NInt

class PrimManager(object):
    def __init__(self):
        self.functions = {}

    def add_function(self, prim_func):
        self.functions[prim_func.name] = prim_func

class PrimFunction(object):
    def __init__(self, name, func, argtypes):
        self.name = name
        self.func = func
        self.argtypes = argtypes
        self.arity = len(argtypes)

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

def register(name, argtypes):
    def decorator(function):
        # MAGIC!
        arity = len(argtypes)
        arityrange = unrolling_iterable(range(arity))
        #
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
        prim_func = PrimFunction(name, wrapped, argtypes)
        module.add_function(prim_func)
        return prim_func
    return decorator

@specialize.argtype(0)
def unwrap_data_node(data_node):
    if isinstance(data_node, NInt):
        return data_node.ival
    assert 0

@specialize.argtype(0)
def wrap_interp_value(v):
    if isinstance(v, int):
        return NInt(v)
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

