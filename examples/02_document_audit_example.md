# Synthetic document-audit example

A comparison slide has columns for Product A and Product B.

DBabel must not assign one product scope to the whole slide. It should establish column/span scope and verify each vendor-specific designation against the matching official source.

If one sentence claims "Product A is 40% faster," terminology may be reviewed, but the percentage claim must be routed to `OUT_OF_SCOPE_CLAIM` unless claim verification is requested.
