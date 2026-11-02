let x=str_pq().push(bytes("6100ff"),2.0).push(bytes("6200fe"),-0.0).push(bytes("6300fd"),0.0); t.hex(x.peek()); t.int(x.len()); t.hex(x.pop()); t.hex(x.pop()); t.hex(x.pop()); t.bool(x.empty());
