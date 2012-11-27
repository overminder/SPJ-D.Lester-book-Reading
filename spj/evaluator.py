from spj import language
from spj.errors import InterpError

class Addr(object):
    def __init__(self, ival):
        self.ival = ival

    def to_s(self):
        return '#%d' % self.ival

class Node(language.W_Root):
    def to_s(self):
        return '#<Node>'

    def is_data(self):
        return False

class NAp(Node):
    def __init__(self, a1, a2):
        self.a1 = a1
        self.a2 = a2

    def to_s(self):
        return '#<NAp>'

class NSupercomb(Node):
    def __init__(self, name, args, body):
        self.name = name
        self.args = args
        self.body = body

    def to_s(self):
        return '#<NSupercomb %s>' % self.name

class NInt(Node):
    def __init__(self, ival):
        self.ival = ival

    def is_data(self):
        return True

    def to_s(self):
        return '#<NInt %d>' % self.ival

class Dump(object):
    pass

class Heap(object):
    def __init__(self):
        self.next_addr = 1
        self.free_list = []
        self.addr_map = {}

    def alloc(self, node):
        if self.free_list:
            addr = self.free_list.pop()
        else:
            addr = Addr(self.next_addr)
            self.next_addr += 1
        self.addr_map[addr] = node
        return addr

    def free(self, addr):
        if addr in self.addr_map:
            del self.addr_map[addr]
            self.free_list.append(addr)
        else:
            raise InterpError('Heap.free: no such addr %s' % addr)

    def lookup(self, addr):
        try:
            return self.addr_map[addr]
        except KeyError:
            raise InterpError('Heap.lookup: no such addr %s' % addr)

    def update(self, addr, node):
        if addr in self.addr_map:
            self.addr_map[addr] = node
        else:
            raise InterpError('Heap.update: no such addr %s' % addr)

class Stat(language.W_Root):
    def __init__(self):
        self.steps = 0
        self.sc_steps = 0
        self.ap_steps = 0
        self.instantiate_count = 0
        self.alloc_count = 0

    def ppr(self, p):
        p.writeln('#<Stat #%d>' % self.steps)
        with p.block(2):
            p.writeln('SC Steps = %d' % self.sc_steps)
            p.writeln('Ap Steps = %d' % self.ap_steps)
            p.writeln('Instantiate Count = %d' % self.instantiate_count)
            p.writeln('Alloc Count = %d' % self.alloc_count)

class State(language.W_Root):
    def __init__(self, stack, dump, heap, env):
        self.stack = stack
        self.dump = dump
        self.heap = heap
        self.env = env
        self.stat = Stat()

    def ppr(self, p):
        p.writeln('Eval-State')
        with p.block(2):
            p.write('Stack: [')
            if not self.stack:
                pass
            else:
                first, rest = self.stack[0], self.stack[1:]
                p.write(self.heap.lookup(first))
                for addr in rest:
                    p.write(', ')
                    p.write(self.heap.lookup(addr))
            p.writeln(']')
            p.writeln(self.stat)

    def eval(self):
        while not self.is_final():
            language.ppr(self)
            self.step()
        language.ppr(self)
        return self.heap.lookup(self.stack[-1])

    def is_final(self):
        if len(self.stack) == 1:
            return self.heap.lookup(self.stack[-1]).is_data()
        elif len(self.stack) == 0:
            raise InterpError('State.is_final: empty stack!')
        else:
            return False

    def step(self):
        self.stat.steps += 1
        top_addr = self.stack[-1]
        top_node = self.heap.lookup(top_addr)
        self.dispatch(top_node)

    def dispatch(self, node):
        if isinstance(node, NInt):
            self.num_step(node.ival)
        elif isinstance(node, NAp):
            self.ap_step(node.a1, node.a2)
            self.stat.ap_steps += 1
        elif isinstance(node, NSupercomb):
            self.sc_step(node.name, node.args, node.body)
            self.stat.sc_steps += 1
        else:
            raise InterpError('State.dispatch: unknown node %s' % node)

    def num_step(self, ival):
        raise InterpError('State.num_step: number applied as a function!')

    def ap_step(self, a1, a2):
        self.stack.append(a1)

    def sc_step(self, name, args, body):
        arg_bindings = self.get_args(name, args)
        env = self.extend_env(arg_bindings)
        result_addr = self.instantiate(body, env)
        for _ in xrange(len(args) + 1):
            self.stack.pop() # drop argc + 1 stack items
        self.stack.append(result_addr)

    def instantiate(self, body, env):
        self.stat.instantiate_count += 1
        if isinstance(body, language.W_EInt):
            self.stat.alloc_count += 1
            return self.heap.alloc(NInt(body.ival))
        elif isinstance(body, language.W_EAp):
            e1, e2 = body.f, body.a
            a1 = self.instantiate(e1, env)
            a2 = self.instantiate(e2, env)
            self.stat.alloc_count += 1
            return self.heap.alloc(NAp(a1, a2))
        elif isinstance(body, language.W_EVar):
            try:
                return env[body.name]
            except KeyError:
                raise InterpError('Undefined name: %s' % body.name)
        else:
            raise InterpError('Not implemented type: %s' % body)

    def get_args(self, name, args):
        # firstly check whether argc is enough
        if len(self.stack) - 1 < len(args):
            raise InterpError('State.get_args: not enough args for %s.\n'
                              'stack has %d, but need %d' %
                              (name, len(self.stack) - 1, len(args)))

        res = []
        for i, arg in enumerate(args):
            addr = self.stack[-2 - i] # ignore the top (which is the SC)
            node = self.heap.lookup(addr)
            if isinstance(node, NAp):
                res.append((arg, node.a2))
            else:
                raise InterpError('State.get_args: not a NAp: %s' % node)
        return res

    def extend_env(self, bindings):
        env = self.env.copy()
        for (name, addr) in bindings:
            env[name] = addr
        return env

