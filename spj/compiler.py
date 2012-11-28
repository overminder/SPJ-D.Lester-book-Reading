#class Stack(list): pass
from spj.errors import InterpError
from spj.evaluator import State, datHeap, Dump, NSupercomb, NPrim

def compile(program):
    sc_defs = program + prelude_defs
    (initial_heap, env) = build_initial_heap(sc_defs)
    try:
        addr_of_main = env['main']
    except KeyError:
        raise InterpError('compile: main is not defined')
    initial_stack = [addr_of_main]
    return State(initial_stack, Dump(), initial_heap, env)

def build_initial_heap(sc_defs):
    heap = datHeap
    env = {}
    # populate SCs
    for sc_def in sc_defs:
        node = NSupercomb(sc_def.name, sc_def.args, sc_def.body)
        env[sc_def.name] = heap.alloc(node)
    # populate primitives
    from spj import primitive
    for name, prim_func in primitive.module.functions.items():
        node = NPrim(prim_func)
        env[name] = heap.alloc(node)
    #
    return (heap, env)

prelude = '''
false = Pack{1, 0};
true = Pack{2, 0};

cons = Pack{1, 2};
nil = Pack{2, 0};

compose f g x = f (g x);

id x = x;
'''

from spj.parser import read_program
prelude_defs = read_program(prelude)

