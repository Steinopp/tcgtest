#!/usr/bin/env python3
"""
Interactive Git helper for your tcgtest repo.

Menu:
  1) Push new commit
     - Stages all changes, prompts for a message, commits, pulls with --rebase, then pushes.
  2) Pull latest (fetch + rebase)
     - Gets origin/<current-branch> and rebases local changes on top.
  3) Revert a specific commit (safe undo)
     - Shows recent commits; you choose one to revert. Creates a new "revert" commit.
  4) Reset branch to an earlier commit (DANGEROUS: force-push)
     - Shows recent commits; you choose a target to hard reset to, then force-push with lease.
       This rewrites history for everyone. Only use if you really intend to delete recent commits
       from the remote history (e.g., you "pushed by mistake").

Notes:
- Works in the current git repo; make sure you run it from inside your project.
- Avoid committing big binary folders (e.g., data/catalog/images, outputs, runtime); use .gitignore.
"""

import subprocess
import sys
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def run(cmd, check=True, capture=False):
    return subprocess.run(
        cmd, cwd=REPO_ROOT, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None
    )

def git(*args, check=True, capture=False):
    return run(["git", *args], check=check, capture=capture)

def ensure_repo():
    try:
        git("rev-parse", "--is-inside-work-tree")
    except subprocess.CalledProcessError:
        print("❌ Not a git repository. Run this from inside your project.")
        sys.exit(1)

def current_branch():
    return git("rev-parse", "--abbrev-ref", "HEAD", capture=True).stdout.strip()

def ensure_origin():
    try:
        git("remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        print("❌ No 'origin' remote set.")
        print("Add it once with one of:")
        print("  git remote add origin git@github.com:Steinopp/tcgtest.git")
        print("  OR")
        print("  git remote add origin https://github.com/Steinopp/tcgtest.git")
        sys.exit(1)

def has_uncommitted_changes():
    out = git("status", "--porcelain", capture=True).stdout.strip()
    return out != ""

def list_recent_commits(n=20):
    # Format: <hash> <short-time> <subject>
    log_fmt = r"%h %ad %s"
    out = git("log", f"-n{n}", f"--date=short", f"--pretty=format:{log_fmt}", capture=True).stdout
    lines = [l for l in out.splitlines() if l.strip()]
    commits = []
    for l in lines:
        parts = l.split(" ", 2)
        if len(parts) >= 3:
            commits.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
    return commits

def push_new_commit():
    # Warn if big dirs not ignored
    for p in [".venv", "data/catalog/images", "outputs", "runtime"]:
        full = (REPO_ROOT / p)
        if full.exists():
            # If not ignored, gently warn
            ret = git("check-ignore", "-q", p, check=False)
            if ret.returncode != 0:
                print(f"⚠️  Note: '{p}' exists and is not ignored. Consider adding to .gitignore if you don't want it in git.")

    msg = input("Commit message (leave blank for auto timestamp): ").strip()
    if not msg:
        msg = f"auto: update {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"

    git("add", "-A")
    # Check if anything staged
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("No changes staged. Nothing to commit.")
        return

    try:
        git("commit", "-m", msg)
    except subprocess.CalledProcessError:
        print("Commit failed (pre-commit hook or something else).")
        return

    br = current_branch()
    ensure_origin()
    print(f"Fetching origin/{br}…")
    git("fetch", "origin", br, check=False)

    print("Rebasing onto origin…")
    try:
        git("pull", "--rebase", "origin", br)
    except subprocess.CalledProcessError:
        print("❌ Rebase had conflicts. Resolve them, then:")
        print("   git rebase --continue")
        print("   (then re-run this push)")
        return

    # Push (set upstream if needed)
    upstream = git("rev-parse", "--symbolic-full-name", "--verify", "-q", "@{u}", check=False)
    if upstream.returncode == 0:
        git("push")
    else:
        git("push", "-u", "origin", br)
    print(f"✅ Pushed to origin/{br}")

def pull_latest():
    br = current_branch()
    ensure_origin()
    print(f"Fetching origin/{br}…")
    git("fetch", "origin", br, check=False)

    print("Rebasing local changes onto origin…")
    try:
        git("pull", "--rebase", "origin", br)
        print("✅ Up to date with origin.")
    except subprocess.CalledProcessError:
        print("❌ Rebase had conflicts. Resolve them, then run:")
        print("   git rebase --continue")

def choose_commit(commits, prompt="Select commit by number"):
    if not commits:
        print("No commits found.")
        return None
    print("\nRecent commits:")
    for i, c in enumerate(commits, 1):
        print(f"  {i:>2}: {c['hash']}  {c['date']}  {c['subject']}")
    while True:
        choice = input(f"{prompt} (1-{len(commits)}) or 'q' to cancel: ").strip().lower()
        if choice == "q":
            return None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(commits):
                return commits[idx-1]
        print("Invalid choice. Try again.")

def revert_commit():
    ensure_origin()

    # guard: clean worktree
    dirty = has_uncommitted_changes()
    if dirty:
        print("Your working tree has uncommitted changes.")
        print("Choose how to proceed:")
        print("  1) Commit all changes as a WIP, then revert")
        print("  2) Stash all changes temporarily, then revert (will 'stash pop' after)")
        print("  3) Abort (do nothing)")
        choice = input("Select 1/2/3: ").strip()
        if choice == "1":
            git("add", "-A")
            git("commit", "-m", "WIP before revert")
        elif choice == "2":
            # -u includes untracked files
            git("stash", "push", "-u", "-m", "pre-revert")
        else:
            print("Cancelled.")
            return

    commits = list_recent_commits(30)
    c = choose_commit(commits, "Revert which commit")
    if not c:
        print("Cancelled.")
        # if we stashed, leave it there for safety
        return

    print(f"About to revert {c['hash']} - \"{c['subject']}\"")
    confirm = input("Proceed with a non-fast-forward revert (creates a new commit)? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    try:
        git("revert", "--no-edit", c["hash"])
    except subprocess.CalledProcessError:
        print("❌ Revert produced conflicts.")
        print("Fix files, then:")
        print("   git add <fixed files>")
        print("   git revert --continue")
        print("If you need to back out:")
        print("   git revert --abort")
        return

    # if we stashed earlier, try to pop now
    # check if there is a stash and if the last message matches "pre-revert"
    st_list = git("stash", "list", capture=True).stdout.splitlines()
    if any("pre-revert" in s for s in st_list):
        print("Applying stashed changes (stash pop)…")
        pop = git("stash", "pop", check=False, capture=True)
        print(pop.stdout)
        if "CONFLICT" in (pop.stdout or ""):
            print("Stash pop caused conflicts; resolve them, then:")
            print("   git add <fixed files>")
            print("   git commit -m \"Apply stashed changes after revert\"")
            # don’t push yet; let user resolve
            return
        else:
            # make a commit to capture the popped changes cleanly
            if has_uncommitted_changes():
                git("add", "-A")
                git("commit", "-m", "Apply stashed changes after revert")

    # push the revert (and possibly the post-pop commit)
    br = current_branch()
    try:
        git("push")
        print(f"✅ Reverted {c['hash']} and pushed to origin/{br}")
    except subprocess.CalledProcessError:
        print("❌ Push failed. Resolve issues and push manually.")



def reset_to_commit_force():
    """
    Dangerous: hard-resets the branch to a chosen commit and force-pushes.
    Only use if you *really* want to remove pushed commits from remote history.
    """
    ensure_origin()

    if has_uncommitted_changes():
        print("❌ Working tree has uncommitted changes. Commit/stash/discard before resetting.")
        return

    commits = list_recent_commits(30)
    c = choose_commit(commits, "Reset branch to which commit (all newer commits will be removed)")
    if not c:
        print("Cancelled.")
        return

    br = current_branch()
    print("\n⚠️  DANGER: This will rewrite history for the remote branch.")
    print(f"    Branch: {br}")
    print(f"    New tip: {c['hash']}  {c['date']}  {c['subject']}")
    print("    Action: git reset --hard <hash>  +  git push --force-with-lease")
    print("    If others have pulled the newer commits, they will have to fix their local repos.")
    confirm = input("Type EXACTLY 'FORCE' to proceed: ").strip()
    if confirm != "FORCE":
        print("Cancelled.")
        return

    try:
        git("reset", "--hard", c["hash"])
        git("push", "--force-with-lease", "origin", br)
        print(f"✅ Reset to {c['hash']} and force-pushed to origin/{br}")
    except subprocess.CalledProcessError:
        print("❌ Reset or push failed. You may need to fix manually.")

def main():
    ensure_repo()
    while True:
        print("\n=== Git Manager ===")
        print("1) Push new commit")
        print("2) Pull latest (fetch + rebase)")
        print("3) Revert a specific commit (safe undo)")
        print("4) Reset branch to an earlier commit (DANGEROUS: force push)")
        print("q) Quit")
        choice = input("Select an option: ").strip().lower()
        if choice == "1":
            push_new_commit()
        elif choice == "2":
            pull_latest()
        elif choice == "3":
            revert_commit()
        elif choice == "4":
            reset_to_commit_force()
        elif choice == "q":
            break
        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()
