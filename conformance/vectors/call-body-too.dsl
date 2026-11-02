@step
fn increment(x: int) -> int implements Step { return x + 1; }
t.int(increment(4));
