# test_tools.py
"""Verification test — must pass before the server is considered complete."""

import sys
import json

from tools_itms import (
    search_open_calls,
    get_call_detail,
    search_planned_calls,
    search_approved_applications,
    get_application_detail,
    search_projects,
    get_project_detail,
    get_programme_structure,
)

results = []


def test(name, fn, *args, min_length=10, **kwargs):
    try:
        result = fn(*args, **kwargs)
        assert result and len(str(result)) >= min_length, f"Response too short: {result}"
        print(f"  ✅ {name} — {len(str(result))} chars returned")
        results.append((name, True, None))
        return result
    except Exception as e:
        print(f"  ❌ {name} — FAILED: {e}")
        results.append((name, False, str(e)))
        return None


print("\n=== ITMS21+ MCP Server Verification ===\n")

# Test 1: Open calls
r1 = test("search_open_calls (no filter)", search_open_calls, limit=3)

# Test 2: Planned calls
r2 = test("search_planned_calls", search_planned_calls, limit=3)

# Test 3: Approved applications
r3 = test("search_approved_applications", search_approved_applications, limit=3)

# Test 4: Call detail — use a real ID from open calls
call_id = None
if r1:
    try:
        # Parse the output to find an ID
        for line in r1.split("\n"):
            if line.strip().startswith("ID:"):
                call_id = int(line.strip().split(":")[-1].strip())
                break
    except Exception:
        pass

if call_id:
    test(f"get_call_detail (id={call_id})", get_call_detail, call_id)
else:
    print("  ⚠️  get_call_detail — skipped (no ID from open calls)")
    results.append(("get_call_detail", False, "no ID available"))

# Test 5: Application detail — use a real ID from approved apps
app_id = None
if r3:
    try:
        for line in r3.split("\n"):
            if line.strip().startswith("ID:"):
                app_id = int(line.strip().split(":")[-1].strip())
                break
    except Exception:
        pass

if app_id:
    test(f"get_application_detail (id={app_id})", get_application_detail, app_id)
else:
    print("  ⚠️  get_application_detail — skipped (no ID from previous test)")
    results.append(("get_application_detail", False, "no ID available"))

# Test 6: Projects
r6 = test("search_projects (in realisation)", search_projects, in_realisation=True, limit=3)

# Test 7: Project detail — use a real ID from projects
proj_id = None
if r6:
    try:
        for line in r6.split("\n"):
            if line.strip().startswith("ID:"):
                proj_id = int(line.strip().split(":")[-1].strip())
                break
    except Exception:
        pass

if proj_id:
    test(f"get_project_detail (id={proj_id})", get_project_detail, proj_id)
else:
    print("  ⚠️  get_project_detail — skipped (no ID from previous test)")
    results.append(("get_project_detail", False, "no ID available"))

# Test 8: Programme structure
test("get_programme_structure", get_programme_structure)

# Summary
print("\n=== VERIFICATION SUMMARY ===")
passed = [r for r in results if r[1]]
failed = [r for r in results if not r[1]]

for name, ok, err in results:
    status = "✅" if ok else "❌"
    print(f"  {status} {name}" + (f" — {err}" if err else ""))

print(f"\n{len(passed)}/{len(results)} tests passed")

if failed:
    print("\n❌ VERIFICATION FAILED — fix the failing tools before connecting to Intric")
    sys.exit(1)
else:
    print("\n🎉 ALL TESTS PASSED — Server is ready for Intric")
    sys.exit(0)
