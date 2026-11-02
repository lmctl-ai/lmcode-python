let x=float_queue().push(1.5).push(2.5).push(3.5); for (item in x) { t.float(item); } t.int(x.len()); t.float(x.at(1)); t.float(x.pop()); t.float(x.peek()); x.clear(); t.int(x.len());
