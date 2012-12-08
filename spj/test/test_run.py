import random

from spj.parser import read_program
from spj.gmcompile import compile
from spj.gmachine import NIndirect
from spj.errors import InterpError

def eval_source(source):
    ast = read_program(source)
    state = compile(ast)
    result_addr = state.eval()
    result = result_addr.node
    while isinstance(result, NIndirect):
        result = result.addr.node
    return result

def test_just_1():
    for _ in xrange(10):
        i = random.randint(-10000, 10000)
        assert eval_source('main = %d;' % i).ival == i

def test_prim_add():
    for _ in xrange(10):
        a = random.randint(-10000, 10000)
        b = random.randint(-10000, 10000)
        assert eval_source('main = %d + %d;' % (a, b)).ival == a + b

def test_func_add():
    for _ in xrange(10):
        a = random.randint(-10000, 10000)
        b = random.randint(-10000, 10000)
        assert eval_source('''
        main = (+) %(a)s %(b)s;
        ''' % locals()).ival == a + b

def test_prim_if():
    assert eval_source('main = if 0 123 456;').ival == 456
    assert eval_source('main = if 1 123 456;').ival == 123

def test_func_if():
    assert eval_source('main = myIf 0 123 456; myIf = if;').ival == 456
    assert eval_source('main = myIf 1 123 456; myIf = if;').ival == 123

def test_skk():
    source = '''
    s f g x = f x (g x);
    k x y = x;
    k1 x y = y;
    main = s k k 1;
    '''
    assert eval_source(source).ival == 1

def test_fibo():
    source = '''
    main = fibo 10;
    fibo n = if (n < 2)
                n
                ((fibo (n - 1)) + (fibo (n - 2)));
    '''
    assert eval_source(source).ival == 55

