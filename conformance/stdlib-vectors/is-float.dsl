t.bool(str_is_float(".5"));
t.bool(str_is_float("1e-999"));
t.bool(str_is_float("inf"));
t.bool(str_is_float(" 1"));
t.bool(str_is_float(bytes("ff")));
