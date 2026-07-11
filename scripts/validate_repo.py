#!/usr/bin/env python3
"""Unified repository quality gate validator.

Part of the meta-infrastructure for agentic-config-hub.
Checks:
1. Python script syntax compilation (py_compile).
2. Agent loop safety audits (loop_auditor.py >= 90).
3. Workflow HITL gate validation (hitl_gate_validator.py == PASS).

Exits 0 on success, 1 on failure.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

def run_command(cmd, capture_output=True):
    """Run a system command and return (returncode, stdout, stderr)."""
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            check=False
        )
        return res.returncode, res.stdout or "", res.stderr or ""
    except Exception as exc:
        return -1, "", str(exc)

def check_python_syntax(repo_root):
    """Find all .py files in scripts/ and skills/*/scripts/ and compile them."""
    python_files = []
    
    # 1. Scripts at root/scripts/
    scripts_dir = repo_root / "scripts"
    if scripts_dir.is_dir():
        python_files.extend(scripts_dir.glob("*.py"))
        
    # 2. Scripts in skills/*/scripts/
    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_scripts = skill_dir / "scripts"
                if skill_scripts.is_dir():
                    python_files.extend(skill_scripts.glob("*.py"))

    results = []
    all_passed = True
    for py_file in sorted(python_files):
        rel_path = py_file.relative_to(repo_root)
        # Skip self-compilation if called during active writing, but safe to compile anyway
        cmd = [sys.executable, "-m", "py_compile", str(py_file)]
        code, stdout, stderr = run_command(cmd)
        passed = (code == 0)
        if not passed:
            all_passed = False
        results.append({
            "file": str(rel_path.as_posix()),
            "passed": passed,
            "error": stderr.strip() if not passed else ""
        })
    return all_passed, results

def check_agents(repo_root):
    """Run loop_auditor.py on all agents/cs-*.md files."""
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        return True, []
        
    agent_files = sorted(list(agents_dir.glob("cs-*.md")))
    auditor_path = repo_root / "skills" / "agentic-system-architect" / "scripts" / "loop_auditor.py"
    
    if not auditor_path.is_file():
        return False, [{"file": "skills/agentic-system-architect/scripts/loop_auditor.py", "passed": False, "score": 0, "error": "Auditor script not found"}]

    results = []
    all_passed = True
    for agent_file in agent_files:
        rel_path = agent_file.relative_to(repo_root)
        # Run loop auditor with JSON output
        cmd = [sys.executable, str(auditor_path), str(agent_file), "--json"]
        code, stdout, stderr = run_command(cmd)
        
        passed = False
        score = 0
        grade = "UNKNOWN"
        error_msg = ""
        
        if code == 0 and stdout:
            try:
                data = json.loads(stdout)
                score = data.get("score", 0)
                grade = data.get("grade", "UNKNOWN")
                # Enforce min-score of 90 (HARDENED)
                passed = (score >= 90)
                if not passed:
                    all_passed = False
                    error_msg = f"Score {score} ({grade}) is below minimum HARDENED threshold of 90."
            except json.JSONDecodeError:
                all_passed = False
                error_msg = "Failed to parse JSON output from loop_auditor.py"
        else:
            all_passed = False
            error_msg = stderr.strip() or f"loop_auditor.py exited with code {code}"
            
        results.append({
            "file": str(rel_path.as_posix()),
            "passed": passed,
            "score": score,
            "grade": grade,
            "error": error_msg
        })
    return all_passed, results

def check_workflows(repo_root):
    """Run hitl_gate_validator.py on all workflows/*.md files (excluding README.md)."""
    workflows_dir = repo_root / "workflows"
    if not workflows_dir.is_dir():
        return True, []
        
    workflow_files = sorted(list(workflows_dir.glob("*.md")))
    workflow_files = [w for w in workflow_files if w.name.lower() != "readme.md"]
    
    validator_path = repo_root / "skills" / "agentic-system-architect" / "scripts" / "hitl_gate_validator.py"
    if not validator_path.is_file():
        return False, [{"file": "skills/agentic-system-architect/scripts/hitl_gate_validator.py", "passed": False, "error": "Validator script not found"}]

    results = []
    all_passed = True
    for wf_file in workflow_files:
        rel_path = wf_file.relative_to(repo_root)
        # Run workflow validator with JSON output
        cmd = [sys.executable, str(validator_path), str(wf_file), "--json"]
        code, stdout, stderr = run_command(cmd)
        
        passed = False
        error_msg = ""
        violations = []
        
        if code == 0 and stdout:
            try:
                data = json.loads(stdout)
                passed = (data.get("result") == "PASS")
                violations = data.get("violations", [])
                if not passed:
                    all_passed = False
                    error_msg = "Workflow contains blocking (CRITICAL or HIGH) violations."
            except json.JSONDecodeError:
                all_passed = False
                error_msg = "Failed to parse JSON output from hitl_gate_validator.py"
        else:
            all_passed = False
            error_msg = stderr.strip() or f"hitl_gate_validator.py exited with code {code}"
            
        results.append({
            "file": str(rel_path.as_posix()),
            "passed": passed,
            "violations_count": len(violations),
            "error": error_msg
        })
    return all_passed, results

def print_human_report(py_passed, py_res, agent_passed, agent_res, wf_passed, wf_res):
    """Print a clean ASCII-safe verification report."""
    print("====================================================================")
    print("REPOSITORY QUALITY GATE - VALIDATION REPORT")
    print("====================================================================")
    
    print("\n1. Python Script Compilation")
    print("-" * 68)
    for r in py_res:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['file']}")
        if not r["passed"]:
            print(f"       Error: {r['error']}")
            
    print("\n2. Agent Loop Safety Audits (Min Score: 90)")
    print("-" * 68)
    for r in agent_res:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['file']} - Score: {r['score']} ({r['grade']})")
        if not r["passed"]:
            print(f"       Error: {r['error']}")
            
    print("\n3. Workflow HITL Gate Validation")
    print("-" * 68)
    if not wf_res:
        print("No workflow configurations found.")
    for r in wf_res:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['file']} - Violations: {r['violations_count']}")
        if not r["passed"]:
            print(f"       Error: {r['error']}")
            
    print("=" * 68)
    overall = py_passed and agent_passed and wf_passed
    print("OVERALL RESULT: " + ("PASS" if overall else "FAIL"))
    print("=" * 68)
    return overall

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="validate_repo.py",
        description="Unified quality gate validator for agentic-config-hub."
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit result as machine-readable JSON instead of text."
    )
    args = parser.parse_args(argv)
    
    # Locate repo root (parent of scripts directory)
    repo_root = Path(__file__).resolve().parent.parent
    
    py_passed, py_res = check_python_syntax(repo_root)
    agent_passed, agent_res = check_agents(repo_root)
    wf_passed, wf_res = check_workflows(repo_root)
    
    overall_passed = py_passed and agent_passed and wf_passed
    
    if args.json:
        report = {
            "passed": overall_passed,
            "python_compilation": {
                "passed": py_passed,
                "results": py_res
            },
            "agent_audits": {
                "passed": agent_passed,
                "results": agent_res
            },
            "workflow_validation": {
                "passed": wf_passed,
                "results": wf_res
            }
        }
        print(json.dumps(report, indent=2))
    else:
        print_human_report(py_passed, py_res, agent_passed, agent_res, wf_passed, wf_res)
        
    return 0 if overall_passed else 1

if __name__ == "__main__":
    sys.exit(main())
