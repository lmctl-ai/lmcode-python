t.bool(str_match("a/b", "a*b"));
t.bool(str_match("é", "?"));
t.bool(str_match("é", "??"));
t.bool(str_match(bytes("ff00"), "??"));
t.bool(str_match("b", "[!a]"));
t.bool(str_match("a", "[z-a]"));
t.bool(str_match("[", "["));
