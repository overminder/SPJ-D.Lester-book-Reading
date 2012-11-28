main = letrec x = 1;
              y = x;
           in y;

y f = letrec x = f x;
          in x;

y2 f = f (y2 f);
