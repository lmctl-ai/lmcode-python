let j = json_parse(bytes("7b226e223a3132332c2261223a5b747275652c6e756c6c5d7d")); t.hex(j.kind()); t.int(j.len()); t.int(j.get("n").as_int()); t.bool(j.get("a").at(0).as_bool()); t.hex(j.to_json());
