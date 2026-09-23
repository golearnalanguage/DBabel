# Search and retrieval strategy

## 1. Search objective
The goal is not to find the most frequent wording. The goal is to find evidence appropriate to the candidate's scope.

## 2. Query construction
Start with the narrowest useful query:

`"term" + vendor + product + version + domain + source-type keyword`

Then broaden deliberately:
1. remove source-type keyword;
2. remove version only if no same-version result exists;
3. search the vendor's documentation domain directly;
4. search applicable standards body when concept appears standardized;
5. search reputable terminology/reference resources for triangulation.

## 3. Source opening
After discovery, open/read the source itself. Do not base adjudication solely on a search snippet.

## 4. In-document verification
Search the opened source for:
- exact term;
- spelling/casing variants;
- full form / acronym;
- nearby definition;
- product/version header;
- release note indicating rename/deprecation.

## 5. Conflict handling
If two authoritative sources disagree:
- check product/version/time scope;
- check whether one is UI and one prose style;
- check whether one describes a related rather than identical concept;
- preserve both if unresolved;
- return `REVIEW` rather than majority voting.

## 6. Search stopping conditions
Stop external research when:
- direct authoritative same-scope evidence resolves the candidate;
- additional sources are only repeating the same evidence;
- the user forbids external research;
- the remaining ambiguity cannot be resolved without unavailable/private material.
