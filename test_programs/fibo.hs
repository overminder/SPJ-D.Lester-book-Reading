
false = Pack{1, 0};
true = Pack{2, 0};

fibo n = if (n < 2)
            n
            (fibo (n - 1) + fibo (n - 2));

main = fibo 30;

