from spj.errors import InterpError
from spj.language import W_Root, ppr

class Addr(W_Root):
    def __init__(self, node):
        self.node = node

    def deref(self):
        return self.node

    def to_s(self):
        return '#<Addr -> %s>' % self.node.to_s()

class Heap(object):
    def __init__(self):
        pass

    def alloc(self, node):
        return Addr(node)

    def free(self, addr):
        pass

    def lookup(self, addr):
        assert isinstance(addr, Addr)
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
    def __init__(self, code, stack, heap, env, stat):
        self.pc = 0
        self.code = code
        self.stack = stack
        self.heap = heap
        self.env = env
        self.stat = stat
        self.curr_sc_name = '(nosc)'

    def to_s(self):
        return '#<GmState>'

    def ppr(self, p):
        try:
            instr = self.code[self.pc].to_s()
        except IndexError:
            instr = '(done)'
        p.writeln('GmState @%s %s' % (self.curr_sc_name, instr))
        p.writeln('Stack: [%s]' % ', '.join([
            self.heap.lookup(a).to_s() for a in self.stack]))
        with p.block(2):
            p.writeln(self.stat)

    def eval(self):
        while not self.is_final():
            ppr(self)
            self.step()
        ppr(self)
        return self.stack[-1]

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
        top = state.heap.lookup(state.stack[-1])
        if isinstance(top, NInt):
            return
        elif isinstance(top, NAp):
            state.pc -= 1 # continue to unwind. we choose not to change
                          # state.code since that may hinder the 
                          # effectiveness of the jit.
            state.stack.append(top.a1)
        elif isinstance(top, NGlobal):
            if len(state.stack) - 1 < top.arity:
                raise InterpError('%s: not enough args for %s' %
                                  (self.to_s(), top.to_s()))
            # Prepare args and enter the new code
            args = take_right(state.stack[:-1], top.arity)
            for i, addr in enumerate(args):
                addr = args[i]
                ap_node = state.heap.lookup(addr)
                assert isinstance(ap_node, NAp)
                args[i] = ap_node.a2

            rest = drop_right(state.stack, top.arity)
            state.stack = rest + args

            state.stat.ncalls += 1
            state.code = top.code
            state.pc = 0
            state.curr_sc_name = top.name
        elif isinstance(top, NIndirect):
            state.pc -= 1
            state.stack[-1] = top.addr
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
        state.stack.append(got)

class Pushint(Instr):
    def __init__(self, ival):
        self.ival = ival

    def to_s(self):
        return '#<Instr:Pushint %d>' % self.ival

    def dispatch(self, state):
        state.stat.nkpushes += 1
        int_node = NInt(self.ival)
        state.stack.append(state.heap.alloc(int_node))

class Push(Instr):
    def __init__(self, index):
        self.index = index

    def to_s(self):
        return '#<Instr:Push %d>' % self.index

    def dispatch(self, state):
        state.stat.nvpushes += 1
        addr = state.stack[-self.index - 1]
        state.stack.append(addr)

class Pop(Instr):
    def __init__(self, howmany):
        self.howmany = howmany

    def to_s(self):
        return '#<Instr:Pop %d>' % self.howmany

    def dispatch(self, state):
        state.stat.npops += 1
        slice_to = len(state.stack) - self.howmany
        assert slice_to >= 0
        state.stack = state.stack[:slice_to]

class Update(Instr):
    def __init__(self, index):
        self.index = index

    def to_s(self):
        return '#<Instr:Update %d>' % self.index

    def dispatch(self, state):
        state.stat.nupdates += 1
        top = state.stack.pop()
        #assert state.stack[-self.index - 1] is not top
        state.heap.update(state.stack[-self.index - 1], NIndirect(top))

class Mkap(Instr):
    def to_s(self):
        return '#<Instr:Mkap>'

    def dispatch(self, state):
        a1 = state.stack.pop()
        a2 = state.stack.pop()
        ap_node = NAp(a1, a2)
        state.stack.append(state.heap.alloc(ap_node))

class Slide(Instr):
    def __init__(self, howmany):
        self.howmany = howmany

    def to_s(self):
        return '#<Instr:Slide %d>' % self.howmany

    def dispatch(self, state):
        top = state.stack.pop()
        slice_to = len(state.stack) - self.howmany
        assert slice_to >= 0
        state.stack = state.stack[:slice_to]
        state.stack.append(top)

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
        if self.addr.deref() is self:
            return '#<GmIndirect (loop)>'
        else:
            return '#<GmIndirect -> %s>' % self.addr.to_s()

