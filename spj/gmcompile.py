from pypy.rlib.objectmodel import specialize

from spj.errors import InterpError
from spj.language import W_Root, W_EVar, W_EInt, W_EAp, W_ELet
from spj.gmachine import (State, datHeap, Stat, NGlobal, Pushglobal, Unwind,
        Slide, Pushint, Mkap, Push, Pop, Update, Alloc)

mkap = Mkap()
unwind = Unwind()

def compile(ast):
    (heap, env) = build_initial_heap(ast)
    return State(initial_code, [], heap, env, Stat())

# As usual.
initial_code = [Pushglobal('main'), unwind]

def build_initial_heap(ast):
    heap = datHeap
    env = {}
    for sc_defn in ast:
        emitter = SCCompiler(sc_defn)
        emitter.compile_sc()
        sc_node = emitter.make_sc_node()
        env[sc_node.name] = heap.alloc(sc_node)
    return (heap, env)

class SCCompiler(object):
    def __init__(self, sc_defn):
        self.code = []
        self.sc_defn = sc_defn

    def make_sc_node(self):
        print self.sc_defn, self.code
        return NGlobal(self.sc_defn.name,
                       len(self.sc_defn.args),
                       self.code)

    def emit(self, instr):
        self.code.append(instr)

    def compile_sc(self):
        local_env = {}
        for (i, name) in enumerate(self.sc_defn.args):
            local_env[name] = i
        self.compile_r(self.sc_defn.body, local_env)

    def compile_r(self, expr, local_env):
        self.compile_c(expr, local_env)
        self.emit(Update(len(local_env)))
        self.emit(Pop(len(local_env)))
        self.emit(unwind)

    def compile_c(self, expr, local_env):
        if isinstance(expr, W_EVar):
            if expr.name in local_env: # is local
                self.emit(Push(local_env[expr.name]))
            else:
                self.emit(Pushglobal(expr.name))
        elif isinstance(expr, W_EInt):
            self.emit(Pushint(expr.ival))
        elif isinstance(expr, W_EAp):
            self.compile_c(expr.a, local_env)
            self.compile_c(expr.f, arg_offset(1, local_env))
            self.emit(mkap)
        elif isinstance(expr, W_ELet):
            ndefns = len(expr.defns)
            let_env = local_env
            if expr.isrec:
                self.emit(Alloc(ndefns))
                let_env = arg_offset(ndefns, let_env)
                for i, (name, form) in enumerate(expr.defns):
                    let_env[name] = ndefns - i - 1
                for i, (name, form) in enumerate(expr.defns):
                    self.compile_c(form, let_env)
                    self.emit(Update(ndefns - i - 1))
            else:
                for (name, form) in expr.defns:
                    self.compile_c(form, local_env)
                    local_env = arg_offset(1, local_env)
                let_env = arg_offset(ndefns, let_env)
                for i, (name, form) in enumerate(expr.defns):
                    let_env[name] = ndefns - i - 1
            # Finally
            self.compile_c(expr.expr, let_env)
            self.emit(Slide(ndefns))
        else:
            raise InterpError('compile_c(%s) not implemented' % expr.to_s())

def arg_offset(i, env):
    d = {}
    for k, v in env.items():
        d[k] = v + i
    return d

