@step
fn inner(x: int) -> int implements Step { t.int(x); return x * 2; }
@step
fn outer(x: int) -> int implements Step { return inner(inner(x)) + 1; }
