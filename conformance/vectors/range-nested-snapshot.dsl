let n = 3;
for (i in range(0, n)) {
  n = 0;
  for (j in range(0, i + 1)) { t.int(i * 10 + j); }
}
t.int(n);
