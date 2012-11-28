main = 3 + add (id 1) 2;

add x y = x + y;

compose f g x = f (g x);

id x = x;

twice f = compose f f;

