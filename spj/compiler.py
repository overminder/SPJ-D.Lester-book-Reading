#class Stack(list): pass
from spj.errors import InterpError
from spj.evaluator import State, Heap, Dump, NSupercomb

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
    heap = Heap()
    env = {}
    for sc_def in sc_defs:
        node = NSupercomb(sc_def.name, sc_def.args, sc_def.body)
        env[sc_def.name] = heap.alloc(node)
    return (heap, env)

prelude_defs = []

