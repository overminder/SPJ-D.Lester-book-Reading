from spj.utils import contextmanager
from pypy.rlib.objectmodel import specialize

class W_Root(object):
    def __repr__(self):
        return self.to_s()

    def to_s(self):
        return '#<Root>'

    def ppr(self, p):
        p.write(self.to_s())

class W_ScDefn(W_Root):
    def __init__(self, name, args, body):
        self.name = name
        self.args = args
        self.body = body

    def to_s(self):
        return '#<ScDefn %s>' % self.name

    def ppr(self, p):
        start = p.line_width
        p.write(self.name)
        for arg in self.args:
            p.write(' ')
            p.write(arg)
        p.write(' = ')
        with p.block(p.line_width - start):
            p.write(self.body)
            p.writeln(';')

class W_Expr(W_Root):
    def to_s(self):
        return '#<Expr>'

class W_EVar(W_Expr):
    def __init__(self, name):
        self.name = name

    def to_s(self):
        return '#<EVar %s>' % self.name

    def ppr(self, p):
        p.write(self.name)

class W_EInt(W_Expr):
    def __init__(self, ival):
        self.ival = ival

    def to_s(self):
        return '#<EInt %d>' % self.ival

    def ppr(self, p):
        p.write(self.ival)

class W_EAp(W_Expr):
    def __init__(self, f, a):
        self.f = f
        self.a = a

    def to_s(self):
        return '#<EAp %s %s>' % (self.f, self.a)

    def ppr(self, p):
        p.write(self.f)
        p.write(' ')
        p.write(self.a)

# Just another var.
class W_EPrimOp(W_EVar):
    def __init__(self, name):
        W_EVar.__init__(self, name)

    def to_s(self):
        return '#<EPrimOp (%s)>' % self.name

    def ppr(self, p):
        p.write('(%s)' % self.name)

class W_ELet(W_Expr):
    def __init__(self, defns, expr, isrec=False):
        self.defns = defns
        self.expr = expr
        self.isrec = isrec

    def to_s(self):
        buf = []
        for (name, e) in self.defns:
            buf.append('%s = %s' % (name, e))
        recstr = 'rec' if self.isrec else ''
        return '#<ELet%s [%s] %s>' % (recstr, '; '.join(buf), self.expr)

    def ppr(self, p):
        recstr = 'let' + ('rec' if self.isrec else '') + ' '
        p.write(recstr)
        with p.block(len(recstr)):
            first, rest = self.defns[0], self.defns[1:]
            (name, expr) = first
            p.write(name)
            p.write(' = ')
            p.write(expr)
            p.writeln(';')

            for (name, expr) in rest:
                p.write(name)
                p.write(' = ')
                p.write(expr)
                p.writeln(';')

            p.dedent(3)
            p.write('in ')
            p.indent(3)
            p.write(self.expr)

class W_EConstr(W_Expr):
    def __init__(self, tag, arity):
        self.tag = tag
        self.arity = arity

    def to_s(self):
        return '#<W_EConstr {%d, %d}>' % (self.tag, self.arity)

    def ppr(self, p):
        p.write('Pack{%d, %d}' % (self.tag, self.arity))

# ppr
class PrettyPrinter(object):
    def __init__(self, stream):
        self.stream = stream
        self.indent_width = 0
        self.line_not_written = True
        self.line_width = 0

    def write_s(self, s):
        self.line_width += len(s)
        self.stream.write(s)

    @specialize.argtype(1)
    def write(self, obj):
        if self.line_not_written:
            self.write_s(' ' * self.indent_width)
            self.line_not_written = False
        if isinstance(obj, W_Root):
            obj.ppr(self)
        else:
            self.write_s(str(obj))

    def indent(self, val):
        self.indent_width += val

    def dedent(self, val):
        self.indent(-val)

    def newline(self):
        self.write_s('\n')
        self.line_width = 0
        self.line_not_written = True

    @specialize.argtype(1)
    def writeln(self, obj):
        self.write(obj)
        self.newline()

    @contextmanager
    def block(self, indent=2):
        self.indent(indent)
        yield
        self.dedent(indent)

def ppr(ast, out=None):
    from pypy.rlib.streamio import fdopen_as_stream
    if not out:
        out = fdopen_as_stream(1, 'w')
    PrettyPrinter(out).write(ast)
    out.flush()

