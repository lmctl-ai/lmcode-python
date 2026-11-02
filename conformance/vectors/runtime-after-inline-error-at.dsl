fn inner() -> string { return "caller fault"; }
fail(
  inner()
);
