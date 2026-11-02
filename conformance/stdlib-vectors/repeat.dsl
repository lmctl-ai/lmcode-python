t.hex(str_repeat(bytes("ff00"), 2));
t.int(str_len(str_repeat("a", 0)));
t.int(str_len(str_repeat("", str_to_int("9223372036854775807"))));
