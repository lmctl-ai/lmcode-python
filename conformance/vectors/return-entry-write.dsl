$return.body = 1;
@step
fn write(x: int) -> int implements Step { $return.value = x; return x + 1; }
