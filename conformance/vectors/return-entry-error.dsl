$return.body = 1;
@step
fn write(x: int) -> int implements Step {
  $return.value = x;
  fail("entry fault after write");
  return x + 1;
}
