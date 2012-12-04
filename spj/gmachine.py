from spj.errors import InterpError
from spj.language import W_Root, ppr
from spj.utils import write_str

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

    def inject_code(self, code):
        # self.code: [passed..., (pc) rest...] -> [(pc) code..., rest...]
        start = self.pc
        assert start >= 0
        self.code = code + self.code[start:]
        self.pc = 0

    def dump_save(self):
        self.dump.append((self.pc, self.code, self.sc_name, self._stack))

    def dump_restore(self):
        (self.pc, self.code, self.sc_name, self._stack) = self.dump.pop()

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
            p.write(node.to_s())
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
                    p.write(stack[-1].to_s())
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
            ppr(self)
            self.step()
        ppr(self)
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
    def to_s(self):
        return '#<Instr>'

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
                state.dump_restore()
                state.stack_push(top_addr)
            else:
                return
        elif isinstance(top, NConstr):
            if state.dump:
                state.dump_restore()
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
                if state.dump:
                    # We are evaluating a sc with not enough args, which must
                    # be caused by a partially applied primitive function.
                    ak = state._stack[0]
                    state.dump_restore()
                    state.stack_push(ak)
                    return
                else:
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
        state.dump_save()
        state.pc = 0
        state.code = only_unwind
        state._stack = [a]

    def to_s(self):
        return '#<Instr:Eval>'

class BasePrimOp(Instr):
    def dispatch(self, state):
        # stack[..., argnode3, argnode2, argnode1] -> stack[..., result]
        if not self.has_enough_args(state):
            raise InterpError('%s: not enough arguments' % self.to_s())
        arity = self.get_arity()
        args_w = [] # :: [argnode1, argnode2, argnode3]
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
        if top.ival == 1:
            state.inject_code(self.then)
            # WTF
        elif top.ival == 0:
            state.inject_code(self.otherwise)
        else:
            raise InterpError('%s: %d seems to be not within bool range' % (
                self.to_s(), top.ival))

    def to_s(self):
        return '#<Instr:Cond>'

class Pack(Instr):
    def __init__(self, tag, arity):
        self.tag = tag
        self.arity = arity

    def dispatch(self, state):
        if len(state._stack) < self.arity:
            raise InterpError('%s: not enough arguments' % self.to_s())
        components = [None] * self.arity
        for i in xrange(self.arity):
            components[i] = state.stack_pop()
        a = state.heap.alloc(NConstr(self.tag, components))
        state.stack_push(a)

    def to_s(self):
        return '#<Instr:Pack %d %d>' % (self.tag, self.arity)

class CaseJump(Instr):
    def __init__(self, cases):
        self.cases = cases # [(int, [Instr])]

    def dispatch(self, state):
        n = state.heap.lookup(state._stack[-1])
        if not isinstance(n, NConstr):
            raise InterpError('%s: %s is not a NConstr' % (
                self.to_s(), n.to_s()))
        for tag, code in self.cases:
            if n.tag == tag:
                state.inject_code(code)
                return
        raise InterpError('%s: no match' % self.to_s())

    def to_s(self):
        return '#<CaseJump [%d]>' % len(self.cases)

class Split(Instr):
    def __init__(self, arity):
        self.arity = arity

    def dispatch(self, state):
        a = state.stack_pop()
        n = state.heap.lookup(a)
        if not isinstance(n, NConstr):
            raise InterpError('%s: %s is not a NConstr' % (
                self.to_s(), n.to_s()))
        if len(n.components) != self.arity:
            raise InterpError('%s: arity mismatch, got %s'
                    % (self.to_s(), n.to_s()))
        for i in xrange(self.arity - 1, -1, -1):
            state.stack_push(n.components[i])

    def to_s(self):
        return '#<Split %d>' % self.arity

class Print(Instr):
    def dispatch(self, state):
        n = state.heap.lookup(state.stack_pop())
        assert isinstance(n, NInt)
        write_str(str(n.ival))

    def to_s(self):
        return '#<Print>'

class PrintData(Instr):
    def dispatch(self, state):
        n = state.heap.lookup(state.stack_pop())
        assert isinstance(n, NConstr)
        write_str('(<%d>' % n.tag)
        for i, addr in enumerate(n.components):
            node = state.heap.lookup(addr)
            write_str(' %s' % node.to_s())
        write_str(')')

    def to_s(self):
        return '#<PrintData>'

class PrintNL(Instr):
    def dispatch(self, state):
        write_str('\n')

    def to_s(self):
        return '#<PrintNL>'

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
        return '#<GmNGlobal %s>' % self.name

    def ppr(self, p):
        p.writeln('#<GmNGlobal %s arity=%d>' % (self.name, self.arity))
        with p.block(2):
            p.write('Code: ')
            p.writeln(self.code)


class NIndirect(Node):
    def __init__(self, addr):
        self.addr = addr

    def to_s(self):
        if not self.addr:
            return '#<GmNIndirect (nil)>'
        elif self.addr.deref() is self:
            return '#<GmNIndirect (loop)>'
        else:
            return '#<GmNIndirect -> %s>' % self.addr.to_s()

    def ppr(self, p):
        p.write('#<GmNIndirect -> ')
        if not self.addr:
            p.write('(nil)')
        elif self.addr.deref() is self:
            p.write('(loop)')
        else:
            p.write(self.addr)
        p.write('>')

class NConstr(Node):
    def __init__(self, tag, components):
        self.tag = tag
        self.components = components

    def to_s(self):
        return '#<GmNConstr %d:%d>' % (self.tag, len(self.components))

null_node = NIndirect(null_addr)

unwind = Unwind()
only_unwind = [unwind]
mkap = Mkap()
eval_instr = Eval()

