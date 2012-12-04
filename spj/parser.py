from spj import language
from pypy.rlib.parsing.makepackrat import (PackratParser, BacktrackException,
        Status)

def ensure_int(s):
    assert s
    return boxed_int(int(s))

def mk_scdefn(lhs, rhs):
    (name, args) = lhs[0], lhs[1:]
    return language.W_ScDefn(name, args, rhs)

def mk_var(v):
    return language.W_EVar(v)

def mk_int(i):
    return language.W_EInt(i)

def mk_ap(f, a):
    return language.W_EAp(f, a)

def mk_alt(tag, components, body):
    return language.W_EAlt(tag, components, body)

def mk_case(expr, alts):
    return language.W_ECase(expr, alts)

def mk_defn(v, e):
    return pair(v, e)

def mk_binaryop(op, lhs, rhs):
    return mk_ap(mk_ap(mk_primop(op), lhs), rhs)

def mk_primop(op):
    return language.W_EPrimOp(op)

def mk_let(defns, e, isrec):
    defns_unpacked = [defn.unpack() for defn in defns]
    return language.W_ELet(defns_unpacked, e, isrec)

def mk_constr(tag, arity):
    return language.W_EConstr(tag, arity)

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

    COMMA:
        IGNORE*
        `,`;

    SEMICOLON:
        IGNORE*
        `;`;

    LET:
        IGNORE*
        `let`;

    LETREC:
        IGNORE*
        `letrec`;

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

    PACK:
        IGNORE*
        `Pack`;

    ARROW:
        IGNORE*
        '->';

    VARNAME:
        IGNORE*
        name = `[_a-z][_a-zA-Z0-9']*`
        if {name not in ['let', 'letrec', 'in', 'case', 'of', 'pack']}
        return {name}
      | IGNORE*
        '('
        name = binop
        IGNORE*
        ')'
        return {name};

    INT:
        IGNORE*
        s = `[0-9]+`
        return {ensure_int(s)};

    LPAREN:
        IGNORE*
        '(';

    RPAREN:
        IGNORE*
        ')';

    LBRACE:
        IGNORE*
        '{';

    RBRACE:
        IGNORE*
        '}';

    scdefn:
        lhs = VARNAME+
        EQUALS
        rhs = expr
        SEMICOLON+
        return {mk_scdefn(lhs, rhs)};

    expr:
        LETREC
        defn_list = defn+
        IN
        e0 = expr
        return {mk_let(defn_list, e0, True)}
      | LET
        defn_list = defn+
        IN
        e0 = expr
        return {mk_let(defn_list, e0, False)}
      | CASE
        e = expr
        OF
        alts = alt+
        return {mk_case(e, alts)}
      | LAMBDA
        lhs = VARNAME+
        ARROW
        rhs = expr
        return {mk_lambda(lhs, rhs)}
      | e = expr
        a = aexpr
        return {mk_ap(e, a)}
      | e1 = expr
        op = binop
        e2 = aexpr
        return {mk_binaryop(op, e1, e2)}
      | aexpr;

    caseexpr:
        CASE
        expr
        OF;

    defn:
        v0 = VARNAME
        EQUALS
        e0 = expr
        SEMICOLON+
        return {mk_defn(v0, e0)};

    aexpr:
        v = VARNAME
        return {mk_var(v)}
      | n = INT
        return {mk_int(n.as_int())}
      | PACK
        LBRACE
        tag = INT
        COMMA
        arity = INT
        RBRACE
        return {mk_constr(tag.as_int(), arity.as_int())}
      | LPAREN
        e = expr
        RPAREN
        return {e};

    binop:
        relop | arithop | boolop | otherop;

    arithop:
        IGNORE* '+'
      | IGNORE* '-'
      | IGNORE* '*'
      | IGNORE* '/';

    relop:
        IGNORE* '<='
      | IGNORE* '<'
      | IGNORE* '=='
      | IGNORE* '/='
      | IGNORE* '>='
      | IGNORE* '>';

    boolop:
        IGNORE* '&&'
      | IGNORE* '||';

    otherop:
        IGNORE* '.';

    alt:
        IGNORE* '<'
        tag = INT
        IGNORE* '>'
        components = VARNAME*
        ARROW
        body = expr
        SEMICOLON
        return {mk_alt(tag.as_int(), components, body)};

    program:
        c = scdefn+
        EOF
        return {c};
    """

def read_program(source):
    try:
        result = Parser(source).program()
        assert result
        return result
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

# Another workaround
class boxed_int(object):
    def __init__(self, ival):
        self.ival = ival

    def as_int(self):
        return self.ival
