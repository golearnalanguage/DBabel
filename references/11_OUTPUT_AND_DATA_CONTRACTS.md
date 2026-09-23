# Output and data contracts

## Human-readable finding
Include:
- location;
- original text/term;
- text role;
- classification;
- vendor/product/version scope;
- concept interpretation;
- decision;
- recommended term/text if applicable;
- reason;
- confidence;
- evidence/source locator;
- conflicts/alternatives;
- technical-claim flag.

## Machine-readable
Use the JSON schemas in `schemas/`. Omit unknown optional fields rather than inventing them.
