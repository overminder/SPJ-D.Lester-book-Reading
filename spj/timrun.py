from spj.errors import InterpError
from spj.language import W_Root, ppr

class Stat(W_Root):
    def __init__(self):
        self.nsteps = 0
        self.nenters = 0
        self.npushes = 0
        self.ntakes = 0
        self.nclosure_made = 0

    def ppr(self, p):
        p.writeln('TIM Stat @step %d:' % self.nsteps)
        with p.block(2):
            p.writeln('Number of takes: %d' % self.ntakes)
            p.writeln('Number of enters: %d' % self.nenters)
            p.writeln('Number of pushes: %d' % self.npushes)
            p.writeln('Number of closures made: %d' % self.nclosure_made)

class State(W_Root):
    def __init__(self, initcode, frameptr, stack, globalenv, codefrags):
        self.code = initcode
        self.pc = 0
        self.frameptr = frameptr
        self.stack = stack
        self.globalenv = globalenv
        self.codefrags = codefrags
        self.stat = Stat()
        self.curr_closure = None

    def ppr(self, p):
        if self.pc >= len(self.code):
            currinstr = 'X'
        else:
            currinstr =  self.code[self.pc].to_s()
        p.writeln('State %s' % currinstr)
        with p.block(2):
            p.write('Frameptr: ')
            p.writeln(self.frameptr)
            p.write('Stack: ')
            p.writeln(self.stack)
            p.writeln(self.stat)

    def frame_ref(self, n):
        return self.frameptr[n]

    def mk_frameptr(self, nitems):
        self.stat.ntakes += 1
        tup_w = [None] * nitems
        for i in xrange(nitems):
            tup_w[i] = self.stack_pop()
        self.frameptr = tup_w

    def stack_pop(self):
        return self.stack.pop()

    def stack_push(self, cl):
        self.stat.npushes += 1
        self.stack.append(cl)

    def mk_closure(self, name, code, frameptr):
        self.stat.nclosure_made += 1
        return Closure(name, code, frameptr)

    def mk_intclosure(self, ival):
        self.stat.nclosure_made += 1
        return IntClosure(ival)

    def enter_closure(self, cl):
        self.stat.nenters += 1
        self.curr_closure = cl
        self.code = cl.code
        self.pc = 0
        self.frameptr = cl.frameptr

    def codefrag_ref(self, n):
        return self.codefrags[n]

    def eval(self):
        while not self.is_final():
            ppr(self)
            self.step()
        ppr(self)
        return self.curr_closure

    def is_final(self):
        return self.pc >= len(self.code)

    def step(self):
        self.stat.nsteps += 1
        instr = self.code[self.pc]
        self.pc += 1
        instr.dispatch(self)

class Closure(W_Root):
    def __init__(self, name, code, frameptr):
        self.name = name
        self.code = code
        self.frameptr = frameptr

    def to_s(self):
        return '#<Closure %s>' % self.name

class IntClosure(Closure):
    def __init__(self, ival):
        Closure.__init__(self, '<int>', [], None)
        self.ival = ival

    def to_s(self):
        return '#<IntClosure %d>' % self.ival

class Instr(W_Root):
    def dispatch(self, state):
        raise NotImplementedError

    def to_s(self):
        return '#<Instr>'

class Take(Instr):
    def __init__(self, n):
        self.n = n

    def dispatch(self, state):
        if self.n > len(state.stack):
            raise InterpError('%s: too few arguments' % self.to_s())
        state.mk_frameptr(self.n)

    def to_s(self):
        return '#<Take %d>' % self.n

class PushArg(Instr):
    def __init__(self, k):
        self.k = k
    
    def dispatch(self, state):
        state.stack_push(state.frame_ref(self.k))

    def to_s(self):
        return '#<PushArg %d>' % self.k

class PushCode(Instr):
    def __init__(self, n):
        self.n = n

    def dispatch(self, state):
        c = state.mk_closure('<anomymous>', state.codefrag_ref(self.n),
                             state.frameptr)
        state.stack_push(c)

    def to_s(self):
        return '#<PushCode %d>' % self.n

class PushLabel(Instr):
    def __init__(self, name):
        self.name = name

    def dispatch(self, state):
        code = state.globalenv.get(self.name, None)
        if code is None:
            raise InterpError('%s: undefined name' % self.to_s())
        cl = state.mk_closure(self.name, code, state.frameptr)
        state.stack_push(cl)

    def to_s(self):
        return '#<PushLabel %s>' % self.name

class PushInt(Instr):
    def __init__(self, ival):
        self.ival = ival

    def dispatch(self, state):
        cl = state.mk_intclosure(self.ival)
        state.stack_push(cl)

    def to_s(self):
        return '#<PushInt %s>' % self.ival

class Enter(Instr):
    def dispatch(self, state):
        state.enter_closure(state.stack_pop())

    def to_s(self):
        return '#<Enter>'

