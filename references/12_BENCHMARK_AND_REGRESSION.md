# Benchmark and regression

DBabel tests the **method**, not a bundled terminology dictionary.

Recommended evaluation dimensions:
- candidate extraction precision/recall on a separately licensed/owned gold set;
- classification accuracy;
- vendor/product/version scope accuracy;
- protected-token error rate;
- recommendation precision;
- false auto-correction rate;
- evidence coverage;
- evidence relevance;
- cross-vendor contamination rate;
- technical-claim routing accuracy;
- round-trip file integrity;
- human acceptance rate.

Public repository regression cases should be synthetic and focus on workflow logic.
