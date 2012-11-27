
class InterpError(Exception):
    def __init__(self, what):
        Exception.__init__(self)
        self.what = what

