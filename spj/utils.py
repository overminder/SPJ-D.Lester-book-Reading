def contextmanager(func):
    class Man(object):
        def __init__(self, gen):
            self.gen = gen

        def __enter__(self):
            try:
                return self.gen.next()
            except StopIteration:
                assert 0

        def __exit__(self, *argl):
            try:
                self.gen.next()
            except StopIteration:
                return
            assert 0
    def wrap(*argl):
        return Man(func(*argl))
    return wrap

