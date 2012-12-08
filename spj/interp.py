from pypy.rlib import jit

STACKSIZE = 64 * 1024
DUMPSIZE = 1024

class State(object):
    def __init__(self, initcode, env=None, names=None):
        self.stack = STACKSIZE * [None]
        self.stackptr = 0 # first empty slot in the stack
        self.dump = DUMPSIZE * [None]
        self.dumpptr = 0
        self.code = initcode
        self.pc = 0
        self.env = env
        self.names = names

    def halloc(self, node):
        pass

    def hlookup(self, node):
        pass

    def eval(self):
        while not self.is_final():
            self.step()

    def is_final(self):
        pass

    def decode_u8(self):
        u8 = self.code[self.pc]
        self.pc += 1
        return ord(u8)

    def decode_i16(self):
        lo = self.decode_u8()
        hi = self.decode_u8()
        if hi > 127:
            hi -= 256
        return (hi << 8) | lo

    def step(self):
        op, oparg = self.op_decode()
        for i, opname in opdescr:
            if i == op:
                getattr(self, opname)(oparg)
                break

    def op_decode(self):
        op = self.code[self.pc]
        if self.op_need_arg(op):
            oparg = self.code[self.pc + 1]
            self.pc += 1
        else:
            oparg = 0
        self.pc += 1
        return op, oparg

    def op_need_arg(self, op):
        pass

    @jit.unroll_safe
    def UNWIND(self, _):
        top_addr = self.ref(0)
        top = top_addr.deref()
        while True:
            if isinstance(top, NInt) or isinstance(top, NConstr):
                if self.dumpptr:
                    self.restore_dump()
                    self.push(top_addr)
                break
            elif isinstance(top, NAp):
                top_addr = top.func
                top = top_addr.deref()
                self.push(top_addr)
                continue
            elif isinstance(top, NGlobal):
                arity = top.arity
                if arity == 0:
                    break # No need to do anything for CAFs
                self.pop() # Throw away the SC
                args = [None] * arity
                for i in xrange(arity):
                    last_addr = self.pop()
                    last_node = last_addr.deref()
                    assert isinstance(last_node, NAp)
                    args[i] = last_node.arg
                self.push(last_addr) # This node will be updated
                for arg in args:
                    self.push(arg)
                # Enter
                self.code = top.code
                self.pc = pc
                break
            elif isinstance(top, NIndirect):
                points_to = top.addr
                self.setnth(0, points_to)
                continue

    def PUSH_GLOBAL(self, oparg):
        name = self.names[oparg]
        addr = self.env.getitem(name)
        self.push(addr)

    def PUSH_INT(self, oparg):
        value = NInt(oparg)
        addr = Addr(value)
        self.push(addr)

    def PUSH_ARG(self, oparg):
        addr = self.ref(oparg)
        self.push(addr)

    @jit.unroll_safe
    def POP(self, oparg):
        for _ in xrange(oparg):
            self.pop()

    def UPDATE(self, oparg):
        src = self.pop()
        dest = self.ref(oparg)
        dest.update(NIndirect(src))

    def MKAP(self, _):
        a1 = self.pop()
        a2 = self.pop()
        ap_node = NAp(a1, a2)
        addr = Addr(ap_node)
        self.push(addr)

    @jit.unroll_safe
    def SLIDE(self, oparg):
        top = self.pop()
        for _ in xrange(oparg):
            self.pop()
        self.push(top)

    def ALLOC(self, oparg):
        for _ in xrange(oparg):
            addr = Addr(null_node)
            self.push(addr)

    def EVAL(self, _):
        a = self.pop()
        self.save_dump()
        self.pc = 0
        self.code = [chr(UNWIND)]
        self.clean_stack()
        self.push(a)

    def COND(self, then):
        otherwise = self.decode_i16()
        top = self.pop().deref()
        assert isinstance(top, NInt)
        if top.ival == 0:
            code = self.codestore[otherwise]
        else:
            code = self.codestore[then]
        self.inject_code(code)
