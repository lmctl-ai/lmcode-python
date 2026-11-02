let m=float_map().set("nan",math_sqrt(-1.0)).set("z",-0.0); let ks=m.keys(); let vs=m.values(); t.hex(ks.at(0)); t.hex(ks.at(1)); t.bool(vs.at(0)!=vs.at(0)); t.float(vs.at(1));
