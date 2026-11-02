let floatpq = float_pq().push(1.5, 2.0).push(1.5, 1.0); t.int(floatpq.len()); t.bool(floatpq.empty()); t.float(floatpq.peek()); t.float(floatpq.pop()); floatpq.clear(); t.bool(floatpq.empty());
