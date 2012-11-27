
main = id 1;

id x = x;

k x y = x;

k1 x y = y;

s f g x = f x (g x);

compose f g x = f (g x);

-- apply f twice
twice f = compose f f;

