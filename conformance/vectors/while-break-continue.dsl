let i = 0;
while (twice(i) < 8) {
  i = i + 1;
  if (i == 2) { continue; }
  if (i == 4) { break; }
  t.int(i);
}
for (j in range(0, 4)) {
  while (j < 2) { t.int(10 + j); break; }
  switch (j) { case 0: { continue; } case 1: { break; } default: { t.int(j); } }
}
let n = 0;
while (n < 2) { for (k in range(0, 2)) { t.int(20 + k); break; } n = n + 1; }
