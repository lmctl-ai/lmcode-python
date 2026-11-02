fn helper(x: int) -> int { return x + 2; }
@step
fn increment(x: int) -> int implements Step { return helper(x); }
