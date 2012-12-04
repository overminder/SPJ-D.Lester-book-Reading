
compose2 f g x = f (g x x)

=>

compose2 f g x = let tup = (f, g, x) in
  f (c2 tup)

c1 (_, g, x) = g x x

therefore,

code(compose2) = [Take 3, Push $ Label "c1", Enter $ Arg 1]
code(c1) = [Push $ Arg 3, Push $ Arg 3, Enter $ Arg 2]
