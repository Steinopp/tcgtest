#!/usr/bin/env python3
"""
git push helper you can run from PyCharm (Python).

Usage:
  python src/git_push.py "your commit message"
If no message is given, we use a timestamp.

What it does:
  - verifies you're in a git repo
  - stages all changes (adds/removes)
  - commits with your message
  - fetches and pulls with --rebase
  - pushes to the current branch (sets upstream if needed)
"""

import subprocess, sys, shlex, datetime, os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def run(cmd, check=True, capture=False):
    if capture:
        return subprocess.run(cmd, cwd=REPO_ROOT, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return subprocess.run(cmd, cwd=REPO_ROOT, check=check)

def git(*args, check=True, capture=False):
    return run(["git", *args], check=check, capture=capture)

def main():
    # 0) are we in a repo?
    try:
        git("rev-parse", "--is-inside-work-tree")
    except subprocess.CalledProcessError:
        print("Error: not a git repository. Run this from within your project.")
        sys.exit(1)

    # 1) warn about big dirs if not ignored (optional)
    for p in [".venv", "data/catalog/images", "outputs", "runtime"]:
        if (REPO_ROOT / p).exists():
            try:
                git("check-ignore", "-q", p)
            except subprocess.CalledProcessError:
                print(f"Note: '{p}' exists and is not ignored. Consider adding it to .gitignore if you don't want it in git.")

    # 2) commit message
    msg = sys.argv[1] if len(sys.argv) > 1 else f"auto: update {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"

    # 3) stage changes
    git("add", "-A")

    # 4) if nothing to commit, exit
    status = git("status", "--porcelain", capture=True)
    if status.stdout.strip() == "":
        print("No changes to commit. Nothing to push.")
        return

    # 5) commit
    try:
        git("commit", "-m", msg)
    except subprocess.CalledProcessError:
        # could be hooks or nothing staged; continue anyway
        pass

    # 6) current branch
    branch = git("rev-parse", "--abbrev-ref", "HEAD", capture=True).stdout.strip()

    # 7) ensure origin exists
    try:
        git("remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        print("No 'origin' remote set.")
        print("Add it once with one of:")
        print("  git remote add origin git@github.com:Steinopp/tcgtest.git")
        print("  OR")
        print("  git remote add origin https://github.com/Steinopp/tcgtest.git")
        sys.exit(1)

    # 8) rebase onto remote
    try:
        git("fetch", "origin", branch)
        git("pull", "--rebase", "origin", branch)
    except subprocess.CalledProcessError:
        print("Rebase had conflicts. Resolve them, then run:")
        print("  git rebase --continue")
        print(f"  python src/git_push.py {shlex.quote(msg)}")
        sys.exit(1)

    # 9) push (set upstream if none)
    has_upstream = git("rev-parse", "--symbolic-full-name", "--verify", "-q", "@{u}", check=False).returncode == 0
    if has_upstream:
        git("push")
    else:
        git("push", "-u", "origin", branch)

    print(f"✅ Pushed to origin/{branch}")

if __name__ == "__main__":
    main()

