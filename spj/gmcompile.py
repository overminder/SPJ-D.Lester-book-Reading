from pypy.rlib.objectmodel import specialize

from spj.utils import write_str
from spj.errors import InterpError
from spj.language import (W_Root, W_EVar, W_EInt, W_EAp, W_ELet, ppr,
        W_EConstr, W_ECase, W_EAlt)
from spj.interp import (State, Addr, NGlobal, Op, prim_funcs,
        primop_descrs)

# ast -> state
def compile(ast):
    initcode, env, names = build_initial_heap(ast)
    return State(initcode, env, names)

# As usual.

def build_initial_heap(ast):
    env = {}
    name_dict = {}
    # alloc primitives
    for hs_rator, sc_node in prim_funcs.items():
        env[hs_rator] = Addr(sc_node)
    # add user-defined funcs
    for sc_defn in ast:
        emitter = SCCompiler(sc_defn, name_dict)
        emitter.compile_sc()
        sc_node = emitter.make_sc_node()
        #ppr(sc_node)
        env[sc_node.name] = Addr(sc_node)

    # setup call to main
    main_cc = SCCompiler(None, name_dict)
    main_cc.emit_oparg(Op.PUSH_GLOBAL, main_cc.intern_name('main'))
    main_cc.emit_op(Op.EVAL)
    initcode = main_cc.code[:] # make sure not resized

    # make an array
    names = [None] * len(name_dict)
    for name, i in name_dict.iteritems():
        names[i] = name
    return initcode, env, names

class SCCompiler(object):
    def __init__(self, sc_defn, name_dict):
        self.code = []
        self.sc_defn = sc_defn
        self.name_dict = name_dict

    def intern_name(self, name):
        if name in self.name_dict:
            return self.name_dict[name]
        else:
            i = len(self.name_dict)
            self.name_dict[name] = i
            return i

    def make_sc_node(self):
        return NGlobal(self.sc_defn.name,
                       len(self.sc_defn.args),
                       self.code[:])

    def emit_u8(self, u8):
        index = len(self.code)
        self.code.append('\0')
        self.patch_u8(index, u8)

    def emit_i16(self, i16):
        index = len(self.code)
        self.code.append('\0')
        self.code.append('\0')
        self.patch_i16(index, i16)

    def emit_op(self, u8):
        self.emit_u8(u8)

    def emit_oparg(self, u8, i16):
        self.emit_u8(u8)
        self.emit_i16(i16)

    def patch_u8(self, index, u8):
        self.code[index] = chr(u8)

    def patch_i16(self, index, i16):
        assert -2 ** 15 <= i16 < 2 ** 16
        lo = i16 & 0xff
        self.patch_u8(index, lo)
        hi = (i16 >> 8) & 0xff
        self.patch_u8(index + 1, hi)

    def compile_sc(self):
        local_env = {}
        for (i, name) in enumerate(self.sc_defn.args):
            local_env[name] = i
        self.compile_r(self.sc_defn.body, local_env)

    def compile_r(self, expr, local_env):
        self.compile_e(expr, local_env)
        self.emit_oparg(Op.UPDATE, len(local_env))
        self.emit_oparg(Op.POP, len(local_env))
        self.emit_op(Op.UNWIND)

    # strict compilation scheme
    def compile_e(self, expr, local_env):
        if isinstance(expr, W_EInt):
            self.emit_oparg(Op.PUSH_INT, expr.ival)
            return
        elif isinstance(expr, W_ELet):
            ndefns = len(expr.defns)
            let_env = local_env
            if expr.isrec:
                self.emit_oparg(Op.ALLOC, ndefns)
                let_env = arg_offset(ndefns, let_env)
                for i, (name, form) in enumerate(expr.defns):
                    let_env[name] = ndefns - i - 1
                for i, (name, form) in enumerate(expr.defns):
                    self.compile_c(form, let_env)
                    self.emit_oparg(Op.UPDATE, ndefns - i - 1)
            else:
                for (name, form) in expr.defns:
                    self.compile_c(form, local_env)
                    local_env = arg_offset(1, local_env)
                let_env = arg_offset(ndefns, let_env)
                for i, (name, form) in enumerate(expr.defns):
                    let_env[name] = ndefns - i - 1
            # Finally
            self.compile_e(expr.expr, let_env)
            self.emit_oparg(Op.SLIDE, ndefns)
            return
        elif isinstance(expr, W_EAp):
            from spj.primitive import module
            if self.try_compile_prim_ap(expr, module.ops, local_env):
                return
            elif self.try_compile_if(expr, local_env):
                return
            #elif self.try_compile_constr(expr, local_env):
            #    return
        elif isinstance(expr, W_ECase):
            raise InterpError('compile_e: ECase not supported')
            #self.compile_e(expr.expr, local_env)
            #alt_codes = []
            #alt_codes = self.compile_d(expr.alts, local_env)
            #self.emit(CaseJump(alt_codes))
            #return

        # Otherwise
        self.compile_c(expr, local_env)
        self.emit_op(Op.EVAL)

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
        self.emit_oparg(Op.COND, 0) # place holder
        pc_after_cond = len(self.code)

        self.compile_e(args[1], env) # compile the then
        self.emit_oparg(Op.JUMP, 0) # place holder again
        pc_before_else = len(self.code)

        self.compile_e(args[0], env) # compile the then
        pc_after_else = len(self.code)

        # [eval-expr, bb, Cond, eval-then, J->end, bb, eval-else, PC]
        # pc-after-cond = 2, pc-before-else = 4,
        # pc-after-else = 5
        # ^ Patch them.
        self.patch_i16(pc_after_cond - 2, pc_before_else - pc_after_cond)
        self.patch_i16(pc_before_else - 2, pc_after_else - pc_before_else)
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
        if expr.name not in primop_descrs:
            return False # no such instr
        opdescr = primop_descrs[expr.name]
        if opdescr.arity != len(args):
            # partially applied, should use prim func instead.
            # XXX: \x -> x + 1 is better than ((+) 1)
            return False
        # stack[..] -> [.., arg.n, ..., arg.1]
        for arg in args:
            self.compile_e(arg, env)
            env = arg_offset(1, env) # this
        self.emit_op(opdescr.op)
        return True

    # UNUSED
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
                self.emit_oparg(Op.PUSH_ARG, local_env[expr.name])
            else:
                self.emit_oparg(Op.PUSH_GLOBAL, self.intern_name(expr.name))
        elif isinstance(expr, W_EInt):
            self.emit_oparg(Op.PUSH_INT, expr.ival)
        elif isinstance(expr, W_EAp):
            self.compile_c(expr.a, local_env)
            self.compile_c(expr.f, arg_offset(1, local_env))
            self.emit_op(Op.MKAP)
        elif isinstance(expr, W_ELet):
            ndefns = len(expr.defns)
            let_env = local_env
            if expr.isrec:
                self.emit_oparg(Op.ALLOC, ndefns)
                let_env = arg_offset(ndefns, let_env)
                for i, (name, form) in enumerate(expr.defns):
                    let_env[name] = ndefns - i - 1
                for i, (name, form) in enumerate(expr.defns):
                    self.compile_c(form, let_env)
                    self.emit_oparg(Op.UPDATE, ndefns - i - 1)
            else:
                for (name, form) in expr.defns:
                    self.compile_c(form, local_env)
                    local_env = arg_offset(1, local_env)
                let_env = arg_offset(ndefns, let_env)
                for i, (name, form) in enumerate(expr.defns):
                    let_env[name] = ndefns - i - 1
            # Finally
            self.compile_c(expr.expr, let_env)
            self.emit_oparg(Op.SLIDE, ndefns)
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

