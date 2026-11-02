let a = 1;
let b = a + 1;
a = b * 10;
if (a > 0) {
  let inner = a + b;
  t.int(inner);
}
let inner = 99;
t.int(inner);
t.int(a);
