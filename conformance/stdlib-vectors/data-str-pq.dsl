let strpq = str_pq().push(bytes("6100ff"), 2.0).push(bytes("6100ff"), 1.0); t.int(strpq.len()); t.bool(strpq.empty()); t.hex(strpq.peek()); t.hex(strpq.pop()); strpq.clear(); t.bool(strpq.empty());
