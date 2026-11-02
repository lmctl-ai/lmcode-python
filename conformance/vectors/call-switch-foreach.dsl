@step
fn flow(x: int) -> int implements Step { let n = 0; for (item in xs) { n = n + item; } switch (x) { case 1: { n = n + 100; } default: { } } return n; }
