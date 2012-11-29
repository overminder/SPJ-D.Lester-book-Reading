
sumAdd n s = if (n == 0) s (sumAdd (n - 1) (s + n));

sumAdd2 n = n + (if (n == 0) 0 (sumAdd2 (n - 1)));

main = sumAdd2 10;

