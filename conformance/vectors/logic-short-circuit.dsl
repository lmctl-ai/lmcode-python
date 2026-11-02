t.bool(!true);
t.bool(!false);
if (false && yes()) { t.str("not here"); }
t.bool(true || yes());
t.bool(false || true);
t.bool(true && false);
if (yes() || yes()) { t.str("one yes call"); }
