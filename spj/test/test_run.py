import pytest
import random

from spj.parser import read_program
from spj.gmcompile import compile
from spj.interp import NIndirect, NInt
from spj.errors import InterpError

def assert_eval_to_int(source, ival):
    node = eval_source(source).unwrap()
    assert isinstance(node, NInt)
    assert node.ival == ival

def eval_source(source):
    ast = read_program(source)
    state = compile(ast)
    return state.eval()

class TestRun(object):
    def test_just_1(self):
        for _ in xrange(10):
            i = random.randint(-10000, 10000)
            assert_eval_to_int('main = %d;' % i, i)

    def test_prim_add(self):
        for _ in xrange(10):
            a = random.randint(-10000, 10000)
            b = random.randint(-10000, 10000)
            assert_eval_to_int('main = %d + %d;' % (a, b), a + b)

    def test_func_add(self):
        for _ in xrange(10):
            a = random.randint(-10000, 10000)
            b = random.randint(-10000, 10000)
            assert_eval_to_int('''
            main = (+) %(a)s %(b)s;
            ''' % locals(), a + b)

    def test_prim_if(self):
        assert_eval_to_int('main = if 0 123 456;', 456)
        assert_eval_to_int('main = if 1 123 456;', 123)

    def test_func_if(self):
        assert_eval_to_int('main = myIf 0 123 456; myIf = if;', 456)
        assert_eval_to_int('main = myIf 1 123 456; myIf = if;', 123)

    def test_skk(self):
        source = '''
        s f g x = f x (g x);
        k x y = x;
        k1 x y = y;
        main = s k k 1;
        '''
        assert_eval_to_int(source, 1)

    def test_fibo(self):
        source = '''
        main = fibo 10;
        fibo n = if (n < 2)
                    n
                    ((fibo (n - 1)) + (fibo (n - 2)));
        '''
        assert_eval_to_int(source, 55)

