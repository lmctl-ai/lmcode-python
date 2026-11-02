switch (bound(-2)) { case -2: { t.str("negative"); } case 1: { t.str("wrong"); } default: { t.str("wrong"); } }
switch ("hello") { case "miss": { t.str("wrong"); } default: { t.str("fallback"); } }
switch (t.status()) { case Status.OPTIMAL: { t.str("optimal"); } case Status.UNKNOWN: { t.str("wrong"); } }
