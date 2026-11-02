let text = str_repeat(bytes("5b"), 135); let pattern = str_repeat(bytes("5b"), 1048576);
t.bool(str_match(text, pattern));
