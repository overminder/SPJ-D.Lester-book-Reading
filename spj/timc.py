from spj.errors import InterpError
from spj.language import W_Root, W_EAp, W_EInt, W_EVar, ppr
from spj.timrun import (State, Take, Enter, Return, PushInt, PushLabel,
                        PushArg, PushCode, PushVInt, Cond, Closure)
from spj.primitive import module

def compile(prog):
    cc = ProgramCompiler()
    cc.compile_program(prog)
    #ppr(cc)

    initcode = [PushLabel('main'), Enter()]
    initstack = [Closure('<init>', [], None)]
    return State(initcode,
                 None,
                 initstack,
                 cc.globalenv,
                 cc.codefrags)

class ProgramCompiler(W_Root):
    def __init__(self):
        self.codefrags = module.codefrags[:]
        self.globalenv = module.scs.copy()

    def ppr(self, p):
        p.writeln('<ProgCompiler>')
        with p.block(2):
            p.writeln('Supercombinators:')
            p.write_dict(self.globalenv.items())
            p.newline(2)
            p.writeln('Anonymous codes:')
            for i, code in enumerate(self.codefrags):
                p.write('%d:' % i)
                p.writeln(code)
            p.writeln('')

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
        if sc.arity != 0:
            self.emit(Take(sc.arity))
        local_env = mk_func_env(sc.args)
        self.compile_r(sc.body, local_env)

    # Compile apply e to args (sort of like unwind)
    def compile_r(self, expr, env):
        # First try to compile as arith
        if self.compile_b(expr, env, [Return()]):
            return
        if isinstance(expr, W_EAp):
            self.compile_a(expr.a, env)
            self.compile_r(expr.f, env)
        elif isinstance(expr, W_EInt) or isinstance(expr, W_EVar):
            self.compile_a(expr, env)
            self.emit(Enter())
        else:
            raise InterpError('compile_r(%s): not implemented' % expr.to_s())

    # Compile atomic expression (addressing mode?)
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

    # eval <expr> inline, push the result then jump to <cont>
    # Return True if <expr> is successfully compiled inlined, False otherwise
    def compile_b(self, expr, env, cont, use_fallback=False):
        if isinstance(expr, W_EAp):
            revargs = [] # [argn, ..., arg1]
            iterexpr = expr
            while isinstance(iterexpr, W_EAp):
                revargs.append(iterexpr.a)
                iterexpr = iterexpr.f
            func = iterexpr
            if (isinstance(func, W_EVar) and func.name in module.ops
                and len(revargs) == module.ops[func.name].get_arity()):
                cont = [module.ops[func.name]] + cont
                # We can just inline the arith
                for i in xrange(len(revargs) - 1, -1, -1):
                    arg = revargs[i]
                    cc = Compiler(self.progcc, '<cont for %s>' % func.name)
                    cc.compile_b(arg, env, cont, use_fallback=True)
                    cont = cc.code
                for instr in cont:
                    self.emit(instr)
                return True
            elif (isinstance(func, W_EVar) and func.name == 'if' and 
                  len(revargs) == 3):
                condexpr = revargs[2]
                trueexpr = revargs[1]
                falseexpr = revargs[0]
                cc1 = Compiler(self.progcc, '<cont for true>')
                cc1.compile_r(trueexpr, env)
                truecode = cc1.code
                truefrag = self.progcc.add_code(truecode)

                cc2 = Compiler(self.progcc, '<cont for false>')
                cc2.compile_r(falseexpr, env)
                falsecode = cc2.code
                falsefrag = self.progcc.add_code(falsecode)

                newcont = [Cond(truefrag, falsefrag)] + cont
                self.compile_b(condexpr, env, newcont)
                return True
        elif isinstance(expr, W_EInt):
            self.emit(PushVInt(expr.ival))
            for instr in cont:
                self.emit(instr)
            return True
        # Otherwise
        if use_fallback:
            i = self.progcc.add_code(cont)
            self.emit(PushCode(i))
            self.compile_r(expr, env)
        return False


def mk_func_env(args):
    d = {}
    for i, name in enumerate(args):
        d[name] = i
    return d

