let n = twice(5);
if (n < 5) {
  t.str("small");
} else if (n < 20) {
  t.str("medium");
} else {
  t.str("large");
}
if (n == 10) {
  t.str("ten");
}
if (n == 11) {
  t.str("eleven");
} else {
  t.str("not eleven");
}
