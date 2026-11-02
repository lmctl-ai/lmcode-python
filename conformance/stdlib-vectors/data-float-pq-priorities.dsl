let x=float_pq().push(1.5,2.0).push(2.5,-0.0).push(3.5,0.0); t.float(x.peek()); t.int(x.len()); t.float(x.pop()); t.float(x.pop()); t.float(x.pop()); t.bool(x.empty());
