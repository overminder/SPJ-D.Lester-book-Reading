from spj import language
from spj.errors import InterpError
from spj.config import CONFIG

class Addr(language.W_Root):
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

class NIndirect(Node):
    def __init__(self, addr):
        self.addr = addr

    def to_s(self):
        return '#<NIndirect %s>' % self.addr.to_s()

class NPrim(Node):
    def __init__(self, prim_func):
        self.prim_func = prim_func

    def to_s(self):
        return '#<NPrim %s>' % self.prim_func.name

class NData(Node):
    def __init__(self, tag, components):
        self.tag = tag
        self.components = components

    def to_s(self):
        return '#<NData %d>' % self.tag

    def is_data(self):
        return True

class Dump(object):
    def __init__(self):
        self.saved_stacks = []

    def push(self, stack):
        self.saved_stacks.append(stack)

    def pop(self):
        return self.saved_stacks.pop()

    def is_not_empty(self):
        return not self.is_empty()

    def is_empty(self):
        return len(self.saved_stacks) == 0

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
        assert isinstance(addr, Addr)
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
        self.indirect_steps = 0
        self.prim_steps = 0
        self.instantiate_count = 0
        self.alloc_count = 0
        self.dump_pushes = 0
        self.dump_pops = 0

    def ppr(self, p):
        p.writeln('#<Stat #%d>' % self.steps)
        with p.block(2):
            p.writeln('SC Steps = %d' % self.sc_steps)
            p.writeln('Ap Steps = %d' % self.ap_steps)
            p.writeln('Indirect Steps = %d' % self.indirect_steps)
            p.writeln('Prim Steps = %d' % self.prim_steps)
            p.writeln('Instantiate Count = %d' % self.instantiate_count)
            p.writeln('Alloc Count = %d' % self.alloc_count)
            p.writeln('Dump push/pops = %d/%d' %
                      (self.dump_pushes, self.dump_pops))

class StateStore(object):
    def __init__(self):
        self.last_state = None

store = StateStore()

class State(language.W_Root):
    def __init__(self, stack, dump, heap, env):
        self.stack = stack
        self.dump = dump
        self.heap = heap
        self.env = env
        self.stat = Stat()
        # XXX hack
        store.last_state = self

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
            self.step()
        language.ppr(self)
        return self.heap.lookup(self.stack[-1])

    def is_final(self):
        if len(self.stack) == 1 and self.dump.is_empty():
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
            self.int_step(node.ival)
        elif isinstance(node, NData):
            self.data_step(node.tag, node.components)
        elif isinstance(node, NAp):
            self.ap_step(node.a1, node.a2)
            self.stat.ap_steps += 1
        elif isinstance(node, NSupercomb):
            self.sc_step(node.name, node.args, node.body)
            self.stat.sc_steps += 1
        elif isinstance(node, NIndirect):
            self.indirect_step(node.addr)
            self.stat.indirect_steps += 1
        elif isinstance(node, NPrim):
            self.prim_step(node.prim_func)
            self.stat.prim_steps += 1
        else:
            raise InterpError('State.dispatch: unknown node %s' % node)

    def int_step(self, ival):
        if len(self.stack) == 1 and self.dump.is_not_empty():
            self.stat.dump_pops += 1
            self.stack = self.dump.pop()
            return
        # Otherwise
        raise InterpError('State.num_step: number applied as a function!')

    def data_step(self, tag, arity):
        # Very similar.
        if len(self.stack) == 1 and self.dump.is_not_empty():
            self.stat.dump_pops += 1
            self.stack = self.dump.pop()
            return
        # Otherwise
        raise InterpError('State.data_step: data applied as a function!')

    def ap_step(self, a1, a2):
        self.stack.append(a1)

    def sc_step(self, name, args, body):
        arg_bindings = self.get_args(name, args)
        root = self.stack[-1 - len(args)]
        env = self.extend_env(arg_bindings)
        self.instantiate_and_update(body, root, env)
        for _ in xrange(len(args)):
            self.stack.pop() # drop sc + (argc - 1) args, leaving root there

    def indirect_step(self, addr):
        self.stack[-1] = addr

    def prim_step(self, prim_func):
        argpairs = self.get_args(prim_func.name, ['unused'] * prim_func.arity)
        arg_addrs = [addr for (unused, addr) in argpairs]
        arg_nodes = []
        for i, arg_addr in enumerate(arg_addrs):
            arg_node = self.heap.lookup(arg_addr)
            if isinstance(arg_node, NIndirect):
                arg_addr = arg_node.addr
                arg_node = self.heap.lookup(arg_node.addr)
            #            
            if prim_func.strictargs[i] and not arg_node.is_data():
                self.stat.dump_pushes += 1
                self.dump.push(self.stack)
                self.stack = [arg_addr]
                return
            arg_nodes.append(arg_node)
        # Call the interp-level prim func here
        for _ in arg_addrs:
            self.stack.pop() # remove the prim and (argc - 1) args
        result_node = prim_func.call(arg_nodes)
        self.heap.update(self.stack[-1], result_node)

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
                raise InterpError('Undefined name: %s (env.keys=%s)' % (
                                   body.name, env.keys()))
        elif isinstance(body, language.W_ELet):
            bindings = []
            for (name, expr) in body.defns:
                addr = self.instantiate(expr, env)
                bindings.append((name, addr))
            new_env = self.extend_env(bindings, env)
            return self.instantiate(body.expr, new_env)
        elif isinstance(body, language.W_EConstr):
            from spj.primitive import PrimConstr
            node = NPrim(PrimConstr(body.tag, body.arity))
            return self.heap.alloc(node)
        else:
            raise InterpError('instantiate: Not implemented: %s' % body)

    def instantiate_and_update(self, body, addr, env):
        self.stat.instantiate_count += 1
        if isinstance(body, language.W_EAp):
            e1, e2 = body.f, body.a
            a1 = self.instantiate(e1, env)
            a2 = self.instantiate(e2, env)
            self.heap.update(addr, NAp(a1, a2))
        elif isinstance(body, language.W_EInt):
            self.heap.update(addr, NInt(body.ival))
        elif isinstance(body, language.W_EVar):
            try:
                found = env[body.name]
            except KeyError:
                raise InterpError('Undefined name: %s (env.keys=%s)' % (
                                   body.name, env.keys()))
            self.heap.update(addr, NIndirect(found))
        elif isinstance(body, language.W_ELet):
            bindings = []
            for (name, expr) in body.defns:
                addr = self.instantiate(expr, env)
                bindings.append((name, addr))
            new_env = self.extend_env(bindings, env)
            self.instantiate_and_update(body.expr, addr, new_env)
        elif isinstance(body, language.W_EConstr):
            from spj.primitive import PrimConstr
            node = NPrim(PrimConstr(body.tag, body.arity))
            self.heap.update(addr, node)
        else:
            raise InterpError('instantiate_and_update: Not implemented: %s' %
                              body)

    def get_args(self, name, args):
        # firstly check whether argc is enough
        if len(self.stack) - 1 < len(args):
            raise InterpError('State.get_args: not enough args for %s.\n'
                              'stack has %d, but need %d' %
                              (name, len(self.stack) - 1, len(args)))
        nstackargs = len(self.stack) - 1

        res = []
        for i, arg in enumerate(args):
            arg_index = nstackargs - 1 - i
            addr = self.stack[arg_index] # ignore the top (which is the SC)
            node = self.heap.lookup(addr)
            if isinstance(node, NAp):
                res.append((arg, node.a2))
            else:
                raise InterpError('State.get_args: not a NAp: %s' % node)
        return res

    def extend_env(self, bindings, env=None):
        if not env:
            env = self.env.copy()
        else:
            env = env.copy()
        for (name, addr) in bindings:
            env[name] = addr
        return env

