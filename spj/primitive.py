import functools

from pypy.rlib.objectmodel import specialize
from pypy.rlib.unroll import unrolling_iterable

from spj.errors import InterpError
from spj.utils import write_str
from spj.evaluator import Node, NInt, NData, NAp

class PrimManager(object):
    def __init__(self):
        self.functions = {}

    def add_function(self, prim_func):
        self.functions[prim_func.name] = prim_func

class BaseFunction(object):
    def __init__(self, name, arity, strictargs):
        self.name = name
        self.arity = arity
        self.strictargs = strictargs

    def call(self, args):
        raise NotImplementedError

class PrimFunction(BaseFunction):
    def __init__(self, name, func, argtypes, strictargs):
        BaseFunction.__init__(self, name, len(argtypes), strictargs)
        self.func = func
        self.argtypes = argtypes

    def call(self, args):
        assert len(args) == self.arity
        for i, argtype in enumerate(self.argtypes):
            arg = args[i]
            if not isinstance(arg, argtype):
                raise InterpError('PrimFunction(%s).call: type error'
                                  % self.name)
        return self.func(args)

class PrimConstr(BaseFunction):
    def __init__(self, tag, arity):
        BaseFunction.__init__(self, 'Constr', arity, [False] * arity)
        self.tag = tag

    def call(self, args):
        assert len(args) == self.arity
        return NData(self.tag, args)

module = PrimManager()

def register(name, argtypes, strictargs=None):
    # MAGIC!
    arity = len(argtypes)
    arityrange = range(arity)
    unwrappers = [make_unwrapper(arg) for arg in argtypes]
    ipairs = unrolling_iterable(zip(arityrange, unwrappers))
    if not strictargs:
        strictargs = [True] * arity # default to full strict
    def decorator(function):
        @functools.wraps(function)
        def wrapped(args):
            assert len(args) == arity
            tupleargs = ()
            for i, unwrapper in ipairs:
                x = args[i]
                assert isinstance(x, argtypes[i])
                tupleargs += (unwrappers[i](x), )
            result = function(*tupleargs)
            return wrap_interp_value(result)
        prim_func = PrimFunction(name, wrapped, argtypes, strictargs)
        module.add_function(prim_func)
        return prim_func
    return decorator

def make_unwrapper(node_type):
    if node_type == NInt:
        return lambda node: node.ival
    if node_type == NData:
        return lambda node: node
    if node_type == Node:
        return lambda node: node
    else:
        assert 0, 'dont know how to unwrap this'

@specialize.argtype(0)
def wrap_interp_value(v):
    if isinstance(v, bool): # True instanceof int lol
        if v:
            tag = 2
        else:
            tag = 1
        return NData(tag, [])
    elif isinstance(v, int):
        return NInt(v)
    elif isinstance(v, Node):
        return v
    assert 0

def mk_binary_op(name, py_op, node_types):
    code = '''
def wrap(a, b):
    return a %(py_op)s b
''' % locals()
    d = {}
    exec code in d
    register(name, node_types)(d['wrap'])

for name in '+ - * / < <= > >= =='.split():
    mk_binary_op(name, name, [NInt, NInt])

mk_binary_op('/=', '!=', [NInt, NInt])

@register('negate', [NInt])
def int_negate(a):
    return -a

def is_true(node):
    if node.tag == 1: # False
        return False
    elif node.tag == 2:
        return True
    else:
        raise InterpError('is_true: tag out of range (%d)' % node.tag)

@register('if', [NData, Node, Node], [True, False, False])
def prim_if(cond, if_true, if_false):
    if is_true(cond):
        return if_true
    else:
        return if_false

@register('&&', [NData, NData])
def prim_and(lhs, rhs):
    return is_true(lhs) and is_true(rhs)

@register('casePair', [NData, Node, Node], [True, False, False])
def case_pair(p, if_cons, if_nil):
    if p.tag == 2: # nil
        return if_nil
    elif p.tag == 1: # pair
        from spj.evaluator import datHeap
        a0 = datHeap.alloc(if_cons)
        a1 = datHeap.alloc(NAp(a0, datHeap.alloc(p.components[0])))
        return NAp(a1, datHeap.alloc(p.components[1]))
    else:
        raise InterpError('casePair: tag out of range (%d)' % p.tag)

@register('printInt', [NInt, Node], [True, False])
def print_int(i, cont):
    write_str(str(i))
    return cont

@register('printComma', [Node], [False])
def print_comma(cont):
    write_str(',')
    return cont

@register('printNl', [Node], [False])
def print_comma(cont):
    write_str('\n')
    return cont

