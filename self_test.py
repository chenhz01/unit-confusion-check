#!/usr/bin/env python3
"""Self test for unit-confusion-check. Run: python self_test.py
Last line: SUMMARY: PASS n/n"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unit_confusion_check as ucc

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append(name)


def kinds(ws):
    return sorted(w["kind"] for w in ws)


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ucc.main(argv)
    return code, buf.getvalue()


# ---------- functional: split_unit ----------
check("su_km", ucc.split_unit("dist_km") == ("dist", "km"))
check("su_ms", ucc.split_unit("elapsed_ms") == ("elapsed", "ms"))
check("su_kg", ucc.split_unit("weight_kg") == ("weight", "kg"))
check("su_m", ucc.split_unit("height_m") == ("height", "m"))
check("su_gb", ucc.split_unit("size_gb") == ("size", "gb"))
check("su_unknown_unit", ucc.split_unit("thing_qq") is None)
check("su_no_suffix", ucc.split_unit("plain_var") is None)
check("su_empty", ucc.split_unit("") is None)
check("su_none", ucc.split_unit(None) is None)
check("su_case_insensitive", ucc.split_unit("dist_KM") == ("dist", "km"))
check("su_three_letter_no", ucc.split_unit("speed_kmh") is None)

# ---------- functional: clean code ----------
w = ucc.scan_source("x = 1\ny = dist_km + 2.0\n")
check("clean_same_unit_no_warn", w == [])
w = ucc.scan_source("total_km = a_km + b_km\n")
check("clean_addition_same_unit", w == [])
w = ucc.scan_source("if a_ms > b_ms:\n    pass\n")
check("clean_compare_same_unit", w == [])
w = ucc.scan_source("import os\nprint('hello')\n")
check("clean_no_units", w == [])
w = ucc.scan_source("total = 5\n")
check("clean_plain_assign", w == [])
w = ucc.scan_source("speed = dist / time_s\n")
check("clean_lhs_unmarked", w == [])

# ---------- functional: mixed-unit operations ----------
w = ucc.scan_source("bad = dist_km + dist_mi\n")
check("mixed_add_km_mi", "mixed_units_in_operation" in kinds(w))
w = ucc.scan_source("bad = dist_km - dist_m\n")
check("mixed_sub_km_m", "mixed_units_in_operation" in kinds(w))
w = ucc.scan_source("slow = speed_km < speed_mi\n")
check("mixed_compare", "mixed_units_compare" in kinds(w))
w = ucc.scan_source("x = a_s * b_ms\n")
check("mixed_s_ms", "mixed_units_in_operation" in kinds(w))
w = ucc.scan_source("x = a_ms + b_ms + c_ms\n")
check("same_unit_chain_clean", w == [])
w = ucc.scan_source("x = dist_km + 5\n")
check("unit_plus_literal_clean", w == [])

# ---------- functional: unit-mismatched assignment ----------
w = ucc.scan_source("total_ms = elapsed_s\n")
check("mismatch_assign_s_to_ms", "unit_mismatch_assignment" in kinds(w))
w = ucc.scan_source("total_s = elapsed_s\n")
check("match_assign_clean", w == [])
w = ucc.scan_source("weight_lb = weight_kg\n")
check("mismatch_kg_to_lb", "unit_mismatch_assignment" in kinds(w))

# ---------- functional: ambiguous base ----------
w = ucc.scan_source("dist_km = 5\ndist_mi = 8\n")
check("ambiguous_base_detected", "ambiguous_base" in kinds(w))
w = ucc.scan_source("dist_km = 5\ndist_km = 8\n")
check("same_var_no_ambiguous", "ambiguous_base" not in kinds(w))
w = ucc.scan_source("a_km = 1\nb_mi = 2\n")
check("different_bases_no_ambiguous", "ambiguous_base" not in kinds(w))

# ---------- functional: multi-feature scan ----------
src = ("dist_km = 10\n"
       "dist_mi = 16\n"
       "total_ms = elapsed_s + delay_ms\n")
w = ucc.scan_source(src)
check("multi_ambiguous_base", "ambiguous_base" in kinds(w))
check("multi_mixed_op", "mixed_units_in_operation" in kinds(w))
check("multi_mismatch_assign", "unit_mismatch_assignment" in kinds(w))
check("multi_has_line_numbers", all(isinstance(x["line"], int) for x in w))
check("multi_deterministic", w == ucc.scan_source(src))

tmp = tempfile.mkdtemp()
f1 = os.path.join(tmp, "sample.py")
with open(f1, "w", encoding="utf-8") as f:
    f.write("dist_km = 5\ntotal = dist_km + dist_mi\n")
code, out = run_cli([f1, "--json"])
r = json.loads(out)
check("cli_file_json", code == 1 and r["total"] == 1)
check("cli_counts", r["counts"].get("mixed_units_in_operation", 0) == 1)
sub = os.path.join(tmp, "pkg")
os.makedirs(sub, exist_ok=True)
with open(os.path.join(sub, "a.py"), "w", encoding="utf-8") as f:
    f.write("bad = a_km + a_mi\n")
with open(os.path.join(sub, "b.txt"), "w", encoding="utf-8") as f:
    f.write("bad = a_km + a_mi\n")
code, out = run_cli([sub, "--json"])
r = json.loads(out)
check("cli_dir_only_py", code == 1 and all(w["kind"] != "syntax_error" for w in r["warnings"]) and r["total"] >= 1)
clean_py = os.path.join(tmp, "clean.py")
with open(clean_py, "w", encoding="utf-8") as f:
    f.write("x = 1\n")
code, out = run_cli([clean_py])
check("cli_clean_exit0", code == 0 and "total=0" in out)

# ---------- exception paths ----------
w = ucc.scan_source("def broken(:\n")
check("syntax_error_reported", kinds(w) == ["syntax_error"] and w[0]["line"] > 0)
code, out = run_cli([os.path.join(tmp, "missing_dir")])
check("cli_missing_path_exit2", code == 2)
w = ucc.scan_source("")
check("empty_source_no_warn", w == [])
try:
    ucc.scan_path(os.path.join(tmp, "definitely_absent"))
    check("scan_path_missing_raises", False)
except FileNotFoundError:
    check("scan_path_missing_raises", True)
w = ucc.scan_source("dist_km + dist_mi\n")
check("expression_statement_still_scanned", len(w) >= 1)
w = ucc.scan_source("x = (a_km + a_mi) * 2\n")
check("nested_parens_still_scanned", "mixed_units_in_operation" in kinds(w))
w = ucc.scan_source("class C:\n    v_km = 1\n")
check("class_attr_handled", isinstance(w, list))
w = ucc.scan_source("def f(p_km):\n    return p_km * 2\n")
check("param_no_false_positive", w == [])
badenc = os.path.join(tmp, "badenc.py")
with open(badenc, "wb") as f:
    f.write(b"\xff\xfe\x00bad bytes \xff")
check("scan_path_bad_encoding_skipped", ucc.scan_path(badenc) == [])
w = ucc.scan_source("dist_km = 1\ndist_km += 2\n")
check("aug_assign_not_mismatch", "unit_mismatch_assignment" not in kinds(w))

# ---------- extreme edge cases ----------
check("edge_unicode_source", ucc.scan_source("# 中文注释\ndist_km = 5\n") == [])
w = ucc.scan_source("总_公里 = 1\n")
check("edge_unicode_var_no_suffix", w == [])
long_line = "x = " + " + ".join("v_ms" for _ in range(100))
w = ucc.scan_source(long_line)
check("edge_very_long_expression_clean", w == [])
long_mixed = "x = " + " + ".join(("v_ms" if i % 2 == 0 else "v_km") for i in range(100))
w = ucc.scan_source(long_mixed)
check("edge_long_mixed_detected", "mixed_units_in_operation" in kinds(w))
deep_src = "x = " + "(" * 50 + "a_km + a_mi" + ")" * 50
w = ucc.scan_source(deep_src)
check("edge_deep_nesting_detected", "mixed_units_in_operation" in kinds(w))
w = ucc.scan_source("x = " + "(" * 500 + "a_km + a_mi" + ")" * 500)
check("edge_extreme_nesting_reported", kinds(w) in (["mixed_units_in_operation"], ["parse_error"], ["syntax_error"]))
many_vars = "\n".join("v%d_km = %d" % (i, i) for i in range(500))
w = ucc.scan_source(many_vars)
check("edge_500_vars_clean", w == [])
many_amb = "\n".join("d_%s = %d" % (u, i) for i, u in enumerate(["km", "mi", "ft", "yd"]))
w = ucc.scan_source(many_amb)
check("edge_multi_unit_ambiguous", "ambiguous_base" in kinds(w))
w = ucc.scan_source("x = 'dist_km + dist_mi in a string'\n")
check("edge_string_literal_no_warn", w == [])
w = ucc.scan_source("def f():\n    if a_kb > a_mb:\n        return 1\n")
check("edge_compare_in_function", "mixed_units_compare" in kinds(w))
w = ucc.scan_source("result_kb = file_mb * 1024\n")
check("edge_kb_from_mb_mismatch", "unit_mismatch_assignment" in kinds(w))
w = ucc.scan_source("l = [a_km, b_km]\ns = {c_km: 1}\nt = (d_km,)\n")
check("edge_containers_same_unit_clean", w == [])
w = ucc.scan_source("l = [a_km, b_mi]\n")
check("edge_list_mixed_detected", "mixed_units_in_collection" in kinds(w))
emoji_src = "# 🎉\ndist_km = 3\n"
check("edge_emoji_comment_clean", ucc.scan_source(emoji_src) == [])

print()
if FAILED:
    print("FAILED CASES:", ", ".join(FAILED))
print("SUMMARY: PASS %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
