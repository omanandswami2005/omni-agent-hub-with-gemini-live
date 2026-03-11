"""Temporary script to run tests and capture results."""
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Use --junitxml with absolute path
xml_path = os.path.join(os.getcwd(), "test-results.xml")
out_path = os.path.join(os.getcwd(), "test-output.txt")

with open(out_path, "w") as outf:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-v",
         f"--junitxml={xml_path}"],
        stdout=outf,
        stderr=subprocess.STDOUT,
        timeout=300,
    )

print(f"EXIT_CODE={proc.returncode}")
print(f"XML_EXISTS={os.path.exists(xml_path)}")
print(f"OUT_SIZE={os.path.getsize(out_path)}")

if os.path.exists(xml_path):
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ts = root.find("testsuite") if root.tag != "testsuite" else root
    tests = int(ts.get("tests", 0))
    failures = int(ts.get("failures", 0))
    errors = int(ts.get("errors", 0))
    skipped = int(ts.get("skipped", 0))
    print(f"RESULTS: {tests} tests, {failures} failures, {errors} errors, {skipped} skipped")
    passed = tests - failures - errors - skipped
    print(f"PASSED: {passed}")
    if failures > 0 or errors > 0:
        for tc in ts.iter("testcase"):
            failure = tc.find("failure")
            error = tc.find("error")
            if failure is not None:
                print(f"FAIL: {tc.get('classname')}::{tc.get('name')}")
                print(f"  {failure.get('message', '')[:300]}")
            if error is not None:
                print(f"ERROR: {tc.get('classname')}::{tc.get('name')}")
                print(f"  {error.get('message', '')[:300]}")
