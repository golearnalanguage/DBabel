# Master framework

DBabel has three logical layers. None requires a bundled terminology dataset.

```text
                 DBABEL AGENT METHOD
                         |
        +----------------+----------------+
        |                |                |
   Runtime Knowledge  Document Engine   Review Governance
        |                |                |
 User resources       Structure        Evidence rules
 Standards            Context          Decision rules
 Vendor docs          Extraction       QA / audit trail
 Web evidence         Translation      Project candidates
        |                |                |
        +----------------+----------------+
                         |
                 Terminology Judge
                         |
          KEEP / REPLACE / PROTECT
          REVIEW / OUT_OF_SCOPE_CLAIM
```

`Runtime Knowledge` means sources retrieved or supplied for the current task. It is not a DBabel-owned termbase.
