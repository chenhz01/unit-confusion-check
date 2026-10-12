# Changelog — unit-confusion-check

All notable changes. Format based on Keep a Changelog; versioning: SemVer.

## [0.1.1] - 2026-10-12

### Added
- Documentation layer: README (problem/how-it-works/quickstart with timing, why-not-X with real anchor citation, fallback plan, trade-offs, limits, FAQ, assumption register), ALIGNMENT.md (rules 85-100 audit), this CHANGELOG, and MIT LICENSE — code itself unchanged this round.

### Verified
- Self-test suite re-run on the release candidate: `python self_test.py` → `SUMMARY: PASS 62/62` (62 cases across functional, exception/CLI, and extreme-edge tiers). No code deltas were needed; the earlier session's implementation passed the full trio of test classes as written.

## [0.1.0] - 2026-10-11

### Added
- AST-based unit-suffix scanner: recognizes `_km/_mi/_ms/_s/_kg/_lb/...` style suffixes over five unit families (length/time/mass/data/temperature).
- Four warning kinds: `mixed_units_in_operation`, `mixed_units_compare`, `unit_mismatch_assignment` (incl. same-base cross-unit), `ambiguous_base` (one base name assigned with multiple units).
- CLI: single file or directory scan, `--json` machine output, exit-code discipline (0 clean / 1 warnings / 2 input error); syntax errors and over-deep nesting reported as findings instead of crashes.
- Self-test suite: 62 cases across functional, exception, and extreme-edge tiers (empty source, 10k-char identifiers, unicode names, 200-level nesting, syntax-error sources).
