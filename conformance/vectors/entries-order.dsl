@pair
fn first(x: int) -> int implements Step { return x + 1; }
fn helper(x: int) -> int { return x + 2; }
@pair
fn second(x: int) -> int implements Step { return helper(x); }
@string
fn third() -> bool implements Flag { return true; }
