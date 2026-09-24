# -*- coding: utf-8 -*-
"""Statics for the nameless-lead repair. Imports the real decision function - no reimplementation."""
import os, sys
os.environ.setdefault("REQUESTS_CA_BUNDLE", "x")
os.environ.setdefault("PIPEDRIVE_API_TOKEN", "x")
os.environ.setdefault("SMARTLEAD_API_KEY", "x")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "repair", os.path.join(os.path.dirname(os.path.abspath(__file__)), "nameless_lead_repair.py"))
mod = importlib.util.module_from_spec(spec)
# the module runs live API work at import; execute only its definitions
src = open(spec.origin, encoding="utf-8").read()
head = src.split("# ---------------------------------------------------------------- 1.")[0]
exec(compile(head, spec.origin, "exec"), mod.__dict__)
choose_name = mod.choose_name

P, F = 0, 0
def t(name, cond, extra=None):
    global P, F
    if cond:
        P += 1; print("  PASS  " + name)
    else:
        F += 1; print("  FAIL  " + name + ("   %r" % (extra,) if extra is not None else ""))

print("\n[1] provider truth wins")
n, s = choose_name("Natalya", "Miasnikova", "pii-fcce19b7@example.invalid")
t("provider first+last used", n == "Person-c3124851", n)
t("source named", s == "smartlead_provider", s)
t("an email-named person does NOT override the provider",
  choose_name("Lara", "Lyberg", "pii-c7524b7a@example.invalid")[0] == "Person-8bb29b7c")

print("\n[2] partial provider data")
t("first only", choose_name("Cher", None, None)[0] == "Cher")
t("last only", choose_name(None, "Garrett, AAP", None)[0] == "Garrett, AAP")
t("empty strings are not a name", choose_name("", "", "pii-5e6b1c2a@example.invalid")[0] is None)

print("\n[3] Pipedrive fallback, but only for a REAL name")
n, s = choose_name(None, None, "Person-ab3144af")
t("real person name accepted", n == "Person-ab3144af" and s == "pipedrive_person", (n, s))

print("\n[4] the refusal — a title is NEVER derived from an address")
for bad in ("pii-fcce19b7@example.invalid", "pii-febd7426@example.invalid", "a@b.c"):
    n, why = choose_name(None, None, bad)
    t("refuses %s" % bad, n is None and "215-name rule" in why, (n, why))
t("refuses when there is nothing at all", choose_name(None, None, None)[0] is None)
t("refuses when the person name is blank", choose_name(None, None, "")[0] is None)

print("\n[5] the refusal is a BLOCK, not a silent skip")
n, why = choose_name(None, None, "x@y.z")
t("a reason is returned, not None", isinstance(why, str) and len(why) > 20, why)

print("\n==== %d passed, %d failed" % (P, F))
sys.exit(1 if F else 0)
