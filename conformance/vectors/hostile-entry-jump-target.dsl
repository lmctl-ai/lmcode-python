@visit
fn visit(node: Thing) -> void implements Visit {
  if (node.id() == 0) {
    t.int(1);
  } else {
    t.int(2);
  }
}
