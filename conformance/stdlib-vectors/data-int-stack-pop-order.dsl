let x=int_stack().push(1).push(2).push(3); for (item in x) { t.int(item); } t.int(x.len()); t.int(x.at(1)); t.int(x.pop()); t.int(x.peek()); x.clear(); t.int(x.len());
