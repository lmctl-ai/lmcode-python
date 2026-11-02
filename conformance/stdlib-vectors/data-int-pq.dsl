let intpq = int_pq().push(1, 2.0).push(1, 1.0); t.int(intpq.len()); t.bool(intpq.empty()); t.int(intpq.peek()); t.int(intpq.pop()); intpq.clear(); t.bool(intpq.empty());
