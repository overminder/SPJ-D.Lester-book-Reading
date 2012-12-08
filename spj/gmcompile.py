from pypy.rlib.objectmodel import specialize

from spj.utils import write_str
from spj.errors import InterpError
from spj.language import (W_Root, W_EVar, W_EInt, W_EAp, W_ELet, ppr,
        W_EConstr, W_ECase, W_EAlt)
from spj.gmachine import (State, datHeap, Stat, NGlobal, Pushglobal, unwind,
        Slide, Pushint, mkap, Push, Pop, Update, Alloc, eval_instr, Cond,
        Jump, Pack, Split, CaseJump)

def compile(ast):
    (heap, env) = build_initial_heap(ast)
    return State(initial_code, [], [], heap, env, Stat())

# As usual.
initial_code = [Pushglobal('main'), eval_instr]

def build_initial_heap(ast):
    heap = datHeap
    from spj.primitive import module
    env = {}
    # add primitives
    for name, sc_node in module.scs.items():
        env[name] = heap.alloc(sc_node)
    # add user-defined funcs
    for sc_defn in ast:
        emitter = SCCompiler(sc_defn)
        emitter.compile_sc()
        sc_node = emitter.make_sc_node()
        #ppr(sc_node)
        env[sc_node.name] = heap.alloc(sc_node)
    return (heap, env)

class SCCompiler(object):
    def __init__(self, sc_defn):
        self.code = []
        self.sc_defn = sc_defn

    def make_sc_node(self):
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
        self.compile_e(expr, local_env)
        self.emit(Update(len(local_env)))
        self.emit(Pop(len(local_env)))
        self.emit(unwind)

    # strict compilation scheme
    def compile_e(self, expr, local_env):
        if isinstance(expr, W_EInt):
            self.emit(Pushint(expr.ival))
            return
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
            self.compile_e(expr.expr, let_env)
            self.emit(Slide(ndefns))
            return
        elif isinstance(expr, W_EAp):
            from spj.primitive import module
            if self.try_compile_prim_ap(expr, module.ops, local_env):
                return
            elif self.try_compile_if(expr, local_env):
                return
            elif self.try_compile_constr(expr, local_env):
                return
        elif isinstance(expr, W_ECase):
            self.compile_e(expr.expr, local_env)
            alt_codes = []
            alt_codes = self.compile_d(expr.alts, local_env)
            self.emit(CaseJump(alt_codes))
            return

        # Otherwise
        self.compile_c(expr, local_env)
        self.emit(eval_instr)

    def try_compile_if(self, expr, env):
        args = [] # [arg.n, arg.n-1, ..., arg.1]
        while isinstance(expr, W_EAp):
            # unwind the spine and get the args
            args.append(expr.a)
            expr = expr.f
        if not isinstance(expr, W_EVar):
            return False
        if expr.name != 'if':
            return False # not a if
        if len(args) != 3:
            raise InterpError('try_compile_if(%s): argcount mismatch.' % 
                    expr.to_s())
        #
        self.compile_e(args[2], env) # get the cond
        cond_instr = Cond(-1)
        self.emit(cond_instr)
        pc_after_cond = len(self.code)

        self.compile_e(args[1], env) # compile the then
        jump_instr = Jump(-1)
        self.emit(jump_instr)
        pc_before_else = len(self.code)

        self.compile_e(args[0], env) # compile the then
        pc_after_else = len(self.code)

        # [eval-expr, Cond, eval-then, J->end, eval-else, PC]
        # pc-after-cond = 2, pc-before-else = 4,
        # pc-after-else = 5
        # ^ Patch them.
        cond_instr.offset = pc_before_else - pc_after_cond
        jump_instr.offset = pc_after_else - pc_before_else
        return True

    def try_compile_prim_ap(self, expr, prim_ops, env):
        # return True if successfully compiled, or False otherwise
        args = [] # [arg.n, arg.n-1, ..., arg.1]
        while isinstance(expr, W_EAp):
            # unwind the spine and get the args
            args.append(expr.a)
            expr = expr.f
        if not isinstance(expr, W_EVar):
            return False
        if expr.name not in prim_ops:
            return False # no such instr
        instr = prim_ops[expr.name]
        if instr.get_arity() != len(args):
            # partially applied, should use prim func instead.
            # XXX: \x -> x + 1 is better than ((+) 1)
            return False
        # stack[..] -> [.., arg.n, ..., arg.1]
        for arg in args:
            self.compile_e(arg, env)
            env = arg_offset(1, env) # this
        self.emit(instr)
        return True

    def try_compile_constr(self, expr, env):
        args = [] # [arg.n, arg.n-1, ..., arg.1]
        while isinstance(expr, W_EAp):
            # unwind the spine and get the args
            args.append(expr.a)
            expr = expr.f
        if not isinstance(expr, W_EConstr):
            return False
        if len(args) != expr.arity:
            raise InterpError('%s: arity mismatch' % expr.to_s())
        for arg in args:
            self.compile_c(arg, env)
            env = arg_offset(1, env)
        self.emit(Pack(expr.tag, expr.arity))
        return True

    # lazy compilation scheme
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

    def compile_d(self, alts, env):
        # -> [(int, [code])]
        saved_code = self.code
        case_codes = []
        for alt in alts:
            self.code = []
            self.compile_a(alt, env)
            case_codes.append((alt.tag, self.code))
        self.code = saved_code
        return case_codes

    def compile_a(self, alt, env):
        self.emit(Split(alt.arity))
        new_env = arg_offset(alt.arity, env)
        for i, v in enumerate(alt.components):
            new_env[v] = i
        self.compile_e(alt.body, new_env)
        self.emit(Slide(alt.arity))

def arg_offset(i, env):
    d = {}
    for k, v in env.items():
        d[k] = v + i
    return d

