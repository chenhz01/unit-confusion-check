#!/usr/bin/env python3
"""unit-confusion-check: static scan for unit-suffix naming violations in
Python source -- variables carrying _km/_mi/_ms/_s/_kg style suffixes, with
warnings for mixed-unit operations, unit-mismatched assignments, and the
same base name used with different units. AST-based, pure stdlib."""

import argparse
import ast
import json
import os
import re
import sys

UNITS = {
    "km", "mi", "m", "ft", "yd", "in",
    "ms", "s", "sec", "min", "hr", "h", "us",
    "kg", "lb", "g", "oz", "t",
    "kb", "mb", "gb", "tb",
    "c", "f", "k",
}
SUFFIX_RE = re.compile(r"^(?P<base>[A-Za-z_][A-Za-z0-9]*)_(?P<unit>[A-Za-z]{1,2})$")
BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
CMP_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)


def split_unit(name):
    """Return (base, unit) if name ends with a known unit suffix, else None."""
    m = SUFFIX_RE.match(name or "")
    if m and m.group("unit").lower() in UNITS:
        return m.group("base"), m.group("unit").lower()
    return None


def _unit_names_in(node):
    """Yield (name, base, unit) for every unit-suffixed Name loaded in node."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            u = split_unit(n.id)
            if u:
                out.append((n.id, u[0], u[1]))
    return out


class UnitVisitor(ast.NodeVisitor):
    def __init__(self):
        self.warnings = []   # kind, line, detail
        self.assign_units = {}   # base -> set of units seen in assignments
        self.all_units = {}      # var name -> (base, unit, line)

    def _warn(self, kind, line, detail):
        self.warnings.append({"kind": kind, "line": line, "detail": detail})

    def visit_Assign(self, node):
        targets = [t for t in node.targets if isinstance(t, ast.Name)]
        rhs = _unit_names_in(node.value)
        for t in targets:
            u = split_unit(t.id)
            if u:
                base, unit = u
                self.assign_units.setdefault(base, set()).add(unit)
                self.all_units[t.id] = (base, unit, node.lineno)
                for _, rbase, runit in rhs:
                    if rbase == base and runit != unit:
                        self._warn("unit_mismatch_assignment", node.lineno,
                                   "'%s' (base '%s') assigned from '%s' unit: %s vs %s"
                                   % (t.id, base, _, runit, unit))
                    elif rbase != base and runit != unit:
                        self._warn("unit_mismatch_assignment", node.lineno,
                                   "'%s' carries unit %s but value carries unit %s ('%s')"
                                   % (t.id, unit, runit, _))
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, BIN_OPS):
            names = _unit_names_in(node)
            units = sorted({(b, u) for _, b, u in names})
            if len({u for _, u in units}) > 1:
                self._warn("mixed_units_in_operation", node.lineno,
                           "operation mixes units %s: %s"
                           % ("/".join(sorted({u for _, u in units})),
                              ", ".join(sorted({n for n, _, _ in names}))))
        self.generic_visit(node)

    def visit_Compare(self, node):
        if any(isinstance(op, CMP_OPS) for op in node.ops):
            nodes = [node.left] + list(node.comparators)
            names = []
            for sub in nodes:
                names.extend(_unit_names_in(sub))
            units = {u for _, _, u in names}
            if len(units) > 1:
                self._warn("mixed_units_compare", node.lineno,
                           "comparison mixes units %s: %s"
                           % ("/".join(sorted(units)),
                              ", ".join(sorted({n for n, _, _ in names}))))
        self.generic_visit(node)

    def _check_collection(self, node):
        names = _unit_names_in(node)
        units = {u for _, _, u in names}
        if len(units) > 1:
            self._warn("mixed_units_in_collection", node.lineno,
                       "collection mixes units %s: %s"
                       % ("/".join(sorted(units)),
                          ", ".join(sorted({n for n, _, _ in names}))))
        self.generic_visit(node)

    visit_List = _check_collection
    visit_Tuple = _check_collection
    visit_Set = _check_collection

    def finish(self):
        for base, units in self.assign_units.items():
            if len(units) > 1:
                self._warn("ambiguous_base", 0,
                           "base name '%s' used with multiple units: %s"
                           % (base, "/".join(sorted(units))))


def scan_source(code, filename="<source>"):
    """Parse Python source and return warning dicts. Syntax errors are
    reported as a 'syntax_error' warning, not an exception."""
    try:
        tree = ast.parse(code, filename=filename)
    except SyntaxError as exc:
        return [{"kind": "syntax_error", "line": exc.lineno or 0,
                 "detail": "cannot parse %s: %s" % (filename, exc.msg)}]
    except RecursionError:
        return [{"kind": "parse_error", "line": 0,
                 "detail": "nesting too deep to parse %s" % filename}]
    v = UnitVisitor()
    try:
        v.visit(tree)
    except RecursionError:
        return [{"kind": "parse_error", "line": 0,
                 "detail": "nesting too deep to scan %s" % filename}]
    v.finish()
    seen, unique = set(), []
    for w in v.warnings:
        key = (w["kind"], w["line"], w["detail"])
        if key not in seen:
            seen.add(key)
            unique.append(w)
    return unique


def scan_path(path):
    """Scan a .py file or a directory tree of .py files."""
    warnings = []
    if os.path.isfile(path):
        files = [path]
    elif os.path.isdir(path):
        files = []
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames.sort()
            for fn in sorted(filenames):
                if fn.endswith(".py"):
                    files.append(os.path.join(dirpath, fn))
    else:
        raise FileNotFoundError(path)
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                code = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        warnings.extend(scan_source(code, filename=f))
    return warnings


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="unit-confusion-check",
        description="Static scan for unit-suffix naming violations (_km/_ms/_kg): mixed-unit ops, mismatched assignments, ambiguous bases.",
    )
    p.add_argument("path", help="a .py file or a directory to scan")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    try:
        warnings = scan_path(args.path)
    except FileNotFoundError:
        print("error: path not found: %s" % args.path, file=sys.stderr)
        return 2

    counts = {}
    for w in warnings:
        counts[w["kind"]] = counts.get(w["kind"], 0) + 1
    if args.json:
        print(json.dumps({"warnings": warnings, "total": len(warnings),
                          "counts": counts}, ensure_ascii=False, indent=2))
    else:
        print("total=%d" % len(warnings))
        for k in sorted(counts):
            print("  %-26s %d" % (k, counts[k]))
        for w in warnings:
            print("  %s:%d [%s] %s" % (w.get("file", ""), w["line"], w["kind"], w["detail"]))
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
