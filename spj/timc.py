from spj.errors import InterpError
from spj.language import W_EAp, W_EInt, W_EVar
from spj.timrun import (State, Take, Enter, PushInt, PushLabel,
        PushArg, PushCode, Closure)

def compile(prog):
    cc = ProgramCompiler()
    cc.compile_program(prog)

    initcode = [PushLabel('main'), Enter()]
    print cc.globalenv.items()
    print [item for item in enumerate(cc.codefrags)]
    return State(initcode,
                 None,
                 [],
                 cc.globalenv,
                 cc.codefrags)

class ProgramCompiler(object):
    def __init__(self):
        self.codefrags = []
        self.globalenv = {}

    def compile_program(self, prog):
        for sc in prog:
            cc = Compiler(self, sc.name)
            cc.compile_sc(sc)
            self.globalenv[sc.name] = cc.code

    def add_code(self, code):
        i = len(self.codefrags)
        self.codefrags.append(code)
        return i

class Compiler(object):
    def __init__(self, progcc, name='?', initcode=None):
        self.progcc = progcc
        self.name = name
        if initcode is None:
            self.code = []
        else:
            self.code = initcode

    def emit(self, instr):
        self.code.append(instr)

    def compile_sc(self, sc):
        self.emit(Take(sc.arity))
        local_env = mk_func_env(sc.args)
        self.compile_r(sc.body, local_env)

    def compile_r(self, expr, env):
        if isinstance(expr, W_EAp):
            self.compile_a(expr.a, env)
            self.compile_r(expr.f, env)
        elif isinstance(expr, W_EInt) or isinstance(expr, W_EVar):
            self.compile_a(expr, env)
            self.emit(Enter())
        else:
            raise InterpError('compile_r(%s): not implemented' % expr.to_s())

    # Compile atomic expression
    def compile_a(self, expr, env):
        if isinstance(expr, W_EInt):
            self.emit(PushInt(expr.ival))
        elif isinstance(expr, W_EVar):
            if expr.name in env:
                self.emit(PushArg(env[expr.name]))
            else:
                self.emit(PushLabel(expr.name))
        elif isinstance(expr, W_EAp):
            # Create a shared closure
            cc = Compiler(self.progcc, expr.to_s())
            cc.compile_r(expr, env)
            fragindex = self.progcc.add_code(cc.code)
            self.emit(PushCode(fragindex))
        else:
            raise InterpError('compile_a(%s): not implemented' % expr.to_s())

def mk_func_env(args):
    d = {}
    for i, name in enumerate(args):
        d[name] = i
    return d

