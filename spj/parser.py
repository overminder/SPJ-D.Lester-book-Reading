from spj import language
from pypy.rlib.parsing.makepackrat import (PackratParser, BacktrackException,
        Status)

def mk_scdefn(lhs, rhs):
    (name, args) = lhs[0], lhs[1:]
    return language.W_ScDefn(name, args, rhs)

def mk_var(v):
    return language.W_EVar(v)

def mk_int(istr):
    assert istr is not None
    i = int(istr)
    return language.W_EInt(i)

def mk_ap(f, a):
    return language.W_EAp(f, a)

def mk_defn(v, e):
    return pair(v, e)

def mk_binaryop(op, lhs, rhs):
    return mk_ap(mk_ap(mk_primop(op), lhs), rhs)

def mk_primop(op):
    return language.W_EPrimOp(op)

def mk_let(defns, e):
    defns_unpacked = [defn.unpack() for defn in defns]
    return language.W_ELet(defns_unpacked, e)

def mk_lambda(lhs, rhs):
    raise NotImplementedError

class Parser(PackratParser):
    r"""
    EOF:
        IGNORE*
        !__any__;

    COMMENT:
        `--.*[\n]`;

    IGNORE:
        `[ \r\t\n]+`
        return {None}
      | COMMENT+
        return {None};

    EQUALS:
        IGNORE*
        `=`;

    DEF_BREAK:
        IGNORE*
        `;`;

    LET:
        IGNORE*
        `let`;

    IN:
        IGNORE*
        `in`;

    CASE:
        IGNORE*
        `case`;

    OF:
        IGNORE*
        `of`;

    LAMBDA:
        IGNORE*
        '\';

    ARROW:
        IGNORE*
        `->`;

    VARNAME:
        IGNORE*
        `[_a-z][_a-zA-Z0-9']*`;

    INT:
        IGNORE*
        `[0-9]+`;

    LPAREN:
        IGNORE*
        '(';

    RPAREN:
        IGNORE*
        ')';

    scdefn:
        lhs = VARNAME+
        EQUALS
        rhs = expr
        DEF_BREAK+
        return {mk_scdefn(lhs, rhs)};

    expr:
        e = expr
        a = aexpr
        return {mk_ap(e, a)}
      | e1 = expr
        op = binop
        e2 = expr
        return {mk_binaryop(op, e1, e2)}
      | LET
        defn_list = defn+
        IN
        e0 = expr
        return {mk_let(defn_list, e0)}
      | LAMBDA
        lhs = VARNAME+
        ARROW
        rhs = expr
        return {mk_lambda(lhs, rhs)}
      | aexpr;

    defn:
        v0 = VARNAME
        EQUALS
        e0 = expr
        DEF_BREAK+
        return {mk_defn(v0, e0)};

    aexpr:
        v = VARNAME
        return {mk_var(v)}
      | n = INT
        return {mk_int(n)}
      | LPAREN
        e = expr
        RPAREN
        return {e};

    binop:
        arithop | relop | boolop;

    arithop:
        IGNORE* '+'
      | IGNORE* '-'
      | IGNORE* '*'
      | IGNORE* '/';

    relop:
        IGNORE* '<'
      | IGNORE* '<='
      | IGNORE* '=='
      | IGNORE* '/='
      | IGNORE* '>='
      | IGNORE* '>';

    boolop:
        IGNORE* '&&'
      | IGNORE* '||';

    program:
        c = scdefn+
        EOF
        return {c};
    """

def read_program(source):
    try:
        return Parser(source).program()
    except BacktrackException as e:
        if e.error:
            print e.error.nice_error_message(source=source)
        raise

# Workaround for tuple cannot be none
class pair(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def unpack(self):
        return self.x, self.y

