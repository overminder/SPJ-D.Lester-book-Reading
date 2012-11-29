from spj.errors import InterpError
from spj.language import W_Root, ppr

class Addr(W_Root):
    def __init__(self, node):
        self.node = node

    def deref(self):
        return self.node

    def to_s(self):
        return '#<Addr -> %s>' % self.node.to_s()

    def ppr(self, p):
        p.write('#<Addr -> ')
        p.write(self.node)
        p.write('>')

null_addr = None

class Heap(object):
    def __init__(self):
        pass

    def alloc(self, node):
        return Addr(node)

    def free(self, addr):
        pass

    def lookup(self, addr):
        assert isinstance(addr, Addr), '%s' % addr.to_s()
        return addr.deref()

    def update(self, addr, node):
        addr.node = node

datHeap = Heap()

class Stat(W_Root):
    def __init__(self):
        self.instr_count = 0
        self.ncalls = 0
        self.nkpushes = 0
        self.nvpushes = 0
        self.npops = 0
        self.nupdates = 0

    def to_s(self):
        return '#<GmStat>'

    def ppr(self, p):
        p.writeln('#<GmState %d>' % self.instr_count)
        with p.block(2):
            p.writeln('calls = %d' % self.ncalls)
            p.writeln('constant pushes = %d' % self.nkpushes)
            p.writeln('variable pushes = %d' % self.nvpushes)
            p.writeln('pops = %d' % self.npops)
            p.writeln('updates = %d' % self.nupdates)

class State(W_Root):
    def __init__(self, code, stack, dump, heap, env, stat):
        self.pc = 0
        self.code = code
        self._stack = stack
        self.dump = dump # :: [(pc, code, sc_name, stack)]
        self.heap = heap
        self.env = env # {name -> addr}
        self.stat = stat
        self.sc_name = '(nosc)'

    def stack_push(self, addr):
        assert isinstance(addr, Addr), addr.to_s()
        self._stack.append(addr)

    def stack_pop(self):
        return self._stack.pop()

    def to_s(self):
        return '#<GmState>'

    def ppr(self, p):
        try:
            instr = self.code[self.pc].to_s()
        except IndexError:
            instr = '(done)'
        p.writeln('GmState @%s %s' % (self.sc_name, instr))
        #
        p.write('Stack: [')
        for i, addr in enumerate(self._stack):
            node = self.heap.lookup(addr)
            if i != 0: # not the first
                p.write(', ')
            p.write(node)
        p.writeln(']')
        #
        s = 'Dump: {'
        p.write(s)
        with p.block(len(s)):
            for i, (pc, code, sc_name, stack) in enumerate(self.dump):
                p.write('SC: ')
                p.write(sc_name)
                p.write(', ')
                p.write('Code: ')
                if pc < len(code):
                    p.write(code[pc])
                    p.write('..., ')
                else:
                    p.write('[], ')
                p.write('Stack: ')
                if stack:
                    p.write(stack[-1])
                    p.write('...')
                else:
                    p.write('[]')
                p.write('; item %d' % i)
                if i != len(self.dump) - 1:
                    p.newline()
            p.writeln('}')
        with p.block(2):
            p.writeln(self.stat)

    def eval(self):
        while not self.is_final():
            #ppr(self)
            self.step()
        #ppr(self)
        return self._stack[-1]

    def is_final(self):
        if self.pc == len(self.code):
            return True
        else:
            return False

    def step(self):
        instr = self.code[self.pc]
        self.pc += 1
        self.stat.instr_count += 1
        instr.dispatch(self)

# G-machine instructions
class Instr(W_Root):
    def dispatch(self, state):
        raise NotImplementedError

class Unwind(Instr):
    def to_s(self):
        return '#<Instr:Unwind>'

    def dispatch(self, state):
        top_addr = state._stack[-1]
        top = state.heap.lookup(top_addr)
        if isinstance(top, NInt):
            if state.dump:
                (pc, code, sc_name, stack) = state.dump.pop()
                state.pc = pc
                state.code = code
                state.sc_name = sc_name
                state._stack = stack
                state.stack_push(top_addr)
            else:
                return
        elif isinstance(top, NAp):
            state.pc -= 1 # continue to unwind. we choose not to change
                          # state.code since that may hinder the 
                          # effectiveness of the jit.
            state.stack_push(top.a1)
        elif isinstance(top, NGlobal):
            if len(state._stack) - 1 < top.arity:
                raise InterpError('%s: not enough args for %s' %
                                  (self.to_s(), top.to_s()))
            # Prepare args and enter the new code
            args = take_right(state._stack[:-1], top.arity)
            for i, addr in enumerate(args):
                addr = args[i]
                ap_node = state.heap.lookup(addr)
                assert isinstance(ap_node, NAp)
                args[i] = ap_node.a2

            rest = drop_right(state._stack, top.arity)
            state._stack = rest + args

            state.stat.ncalls += 1
            state.code = top.code
            state.pc = 0
            state.sc_name = top.name
        elif isinstance(top, NIndirect):
            state.pc -= 1
            state._stack[-1] = top.addr
        else:
            raise InterpError('%s: node %s not implemented' % (
                self.to_s(), top.to_s()))
#

def drop_right(lis, n):
    slice_to = len(lis) - n
    assert slice_to >= 0
    return lis[:slice_to]

def take_right(lis, n):
    slice_from = len(lis) - n
    assert slice_from >= 0
    return lis[slice_from:]

class Pushglobal(Instr):
    def __init__(self, name):
        self.name = name

    def to_s(self):
        return '#<Instr:Pushglobal %s>' % self.name

    def dispatch(self, state):
        state.stat.nkpushes += 1
        try:
            got = state.env[self.name]
        except KeyError:
            raise InterpError('%s: undeclared global' % self.to_s())
        state.stack_push(got)

class Pushint(Instr):
    def __init__(self, ival):
        self.ival = ival

    def to_s(self):
        return '#<Instr:Pushint %d>' % self.ival

    def dispatch(self, state):
        state.stat.nkpushes += 1
        int_node = NInt(self.ival)
        state.stack_push(state.heap.alloc(int_node))

class Push(Instr):
    def __init__(self, index):
        self.index = index

    def to_s(self):
        return '#<Instr:Push %d>' % self.index

    def dispatch(self, state):
        state.stat.nvpushes += 1
        addr = state._stack[-self.index - 1]
        state.stack_push(addr)

class Pop(Instr):
    def __init__(self, howmany):
        self.howmany = howmany

    def to_s(self):
        return '#<Instr:Pop %d>' % self.howmany

    def dispatch(self, state):
        state.stat.npops += 1
        slice_to = len(state._stack) - self.howmany
        assert slice_to >= 0
        state._stack = state._stack[:slice_to]

class Update(Instr):
    def __init__(self, index):
        self.index = index

    def to_s(self):
        return '#<Instr:Update %d>' % self.index

    def dispatch(self, state):
        state.stat.nupdates += 1
        top = state.stack_pop()
        state.heap.update(state._stack[-self.index - 1], NIndirect(top))

class Mkap(Instr):
    def to_s(self):
        return '#<Instr:Mkap>'

    def dispatch(self, state):
        a1 = state.stack_pop()
        a2 = state.stack_pop()
        ap_node = NAp(a1, a2)
        state.stack_push(state.heap.alloc(ap_node))

class Slide(Instr):
    def __init__(self, howmany):
        self.howmany = howmany

    def to_s(self):
        return '#<Instr:Slide %d>' % self.howmany

    def dispatch(self, state):
        top = state.stack_pop()
        slice_to = len(state._stack) - self.howmany
        assert slice_to >= 0
        state._stack = state._stack[:slice_to]
        state.stack_push(top)

class Alloc(Instr):
    def __init__(self, howmany):
        self.howmany = howmany

    def to_s(self):
        return '#<Instr:Alloc %d>' % self.howmany

    def dispatch(self, state):
        for _ in range(self.howmany):
            addr = state.heap.alloc(null_node)
            state.stack_push(addr)

class Eval(Instr):
    def dispatch(self, state):
        a = state.stack_pop()
        dump_item = (state.pc, state.code, state.sc_name, state._stack)
        state.dump.append(dump_item)
        state.pc = 0
        state.code = only_unwind
        state._stack = [a]

    def to_s(self):
        return '#<Instr:Eval>'

class BasePrimOp(Instr):
    def dispatch(self, state):
        if not self.has_enough_args(state):
            raise InterpError('%s: not enough arguments' % self.to_s())
        arity = self.get_arity()
        args_w = [] # :: [Node]
        for _ in xrange(arity):
            args_w.append(state.heap.lookup(state.stack_pop()))
        self.call(state, args_w)

    def has_enough_args(self, state):
        return len(state._stack) >= self.get_arity()

    def get_arity(self):
        raise NotImplementedError

    def call(self, state, args):
        raise NotImplementedError

class Cond(Instr):
    def __init__(self, then, otherwise):
        self.then = then
        self.otherwise = otherwise

    def dispatch(self, state):
        if not state._stack:
            raise InterpError('%s: not enough arguments' % self.to_s())
        top = state.heap.lookup(state.stack_pop())
        if not isinstance(top, NInt):
            raise InterpError('%s: type error' % self.to_s())
        start = state.pc
        assert start >= 0
        if top.ival == 1:
            # WTF
            state.code = self.then + state.code[start:]
        elif top.ival == 0:
            state.code = self.otherwise + state.code[start:]
        else:
            raise InterpError('%s: %d seems to be not within bool range' % (
                self.to_s(), top.ival))
        state.pc = 0

    def to_s(self):
        return '#<Instr:Cond>'

# G-machine nodes
class Node(W_Root):
    def to_s(self):
        return '#<GmNode>'

class NInt(Node):
    def __init__(self, ival):
        self.ival = ival

    def to_s(self):
        return '#<GmNInt %d>' % self.ival

class NAp(Node):
    def __init__(self, a1, a2):
        self.a1 = a1
        self.a2 = a2

    def to_s(self):
        return '#<GmNAp>'

class NGlobal(Node):
    def __init__(self, name, arity, code):
        self.name = name
        self.arity = arity
        self.code = code

    def to_s(self):
        return '#<GmGlobal %s>' % self.name

class NIndirect(Node):
    def __init__(self, addr):
        self.addr = addr

    def to_s(self):
        if not self.addr:
            return '#<GmIndirect (nil)>'
        elif self.addr.deref() is self:
            return '#<GmIndirect (loop)>'
        else:
            return '#<GmIndirect -> %s>' % self.addr.to_s()

    def ppr(self, p):
        p.write('#<GmIndirect -> ')
        if not self.addr:
            p.write('(nil)')
        elif self.addr.deref() is self:
            p.write('(loop)')
        else:
            p.write(self.addr)
        p.write('>')

null_node = NIndirect(null_addr)

unwind = Unwind()
only_unwind = [unwind]
mkap = Mkap()
eval_instr = Eval()

