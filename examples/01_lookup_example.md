# Synthetic lookup example

User asks: "In Product A documentation, is `sync node` the official term for version 3?"

DBabel should not answer from memory alone. It should:
1. classify the candidate as likely vendor/product terminology;
2. establish Product A + version 3 scope;
3. search/open the official version-3 documentation or UI;
4. compare exact naming and context;
5. return KEEP/REPLACE/REVIEW with source locator.

This example is intentionally synthetic and contains no vendor terminology data.
