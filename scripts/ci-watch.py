#!/usr/bin/env python3
"""Hand failed TDLib update runs to a T3 thread on this Mac.

GitHub cannot reach a local T3 server, so a LaunchAgent polls the failed runs of
.github/workflows/tdlib-update.yml and sends each new one to one fixing thread:
the thread from the previous failure while it is not archived, else a new one.

  ./scripts/ci-watch.py tick        # one poll (what the LaunchAgent runs)
  ./scripts/ci-watch.py install     # install and start the LaunchAgent
  ./scripts/ci-watch.py uninstall
"""

import datetime as dt
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "levochkaa/TDLibKit"
WORKFLOW = "tdlib-update.yml"
LABEL = "app.lev.tdlibkit-ci-watch"
STATE_DIR = Path.home() / ".local/state/tdlibkit-ci-watch"
STATE = STATE_DIR / "state.json"
PLIST = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
LOOKBACK = dt.timedelta(days=2)

PROMPT = """\
TDLib update CI failed: {url}
Run {run_id}, attempt {attempt}, commit {sha}, started {created}.

Fix it so the next scheduled run publishes the update:
1. `gh run view {run_id} --repo {repo} --log-failed | tail -n 300`. If a later run of
   {workflow} already succeeded, stop and say it is no longer relevant.
2. Classify: infra (runner, network, Xcode image, cache) or code (upstream TDLib build
   or schema change, our scripts, tests, size limit). README.md «Updating TDLib» explains
   update.py and release.py.
3. Infra: say what failed. On attempt 1 rerun with `gh run rerun {run_id} --repo {repo} --failed`;
   on a later attempt do not rerun again, report to Lev instead.
4. Code: reproduce locally with `./scripts/update.py --ref <tdlib sha from the log>`, fix,
   commit on main. Do not push and do not publish a release; report and wait for Lev.
5. If a tag or release was already published by the failed run, never move or replace it.
"""


def log(message):
    print(f"{dt.datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def run(*args, stdin=None):
    return subprocess.run(args, input=stdin, check=True, text=True, capture_output=True).stdout


def load_state():
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {"seen": {}, "thread_id": None}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def live_thread(thread_id):
    if not thread_id:
        return False
    threads = json.loads(run("t3", "thread", "list", "--project", str(ROOT), "--json"))
    return any(thread["threadId"] == thread_id for thread in threads)


def deliver(state, failure):
    message = PROMPT.format(repo=REPO, workflow=WORKFLOW, run_id=failure["databaseId"],
                            attempt=failure["attempt"], sha=failure["headSha"],
                            created=failure["createdAt"], url=failure["url"])
    if live_thread(state["thread_id"]):
        run("t3", "thread", "send", state["thread_id"], "-", stdin=message)
        log(f"sent run {failure['databaseId']} to thread {state['thread_id']}")
        return
    output = run("t3", "thread", "start", "--title", f"TDLib update failed: run {failure['databaseId']}",
                 str(ROOT), "-", stdin=message)
    state["thread_id"] = output.strip().splitlines()[-1].strip()
    log(f"started thread {state['thread_id']} for run {failure['databaseId']}")


def tick():
    state = load_state()
    failures = json.loads(run(
        "gh", "run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--status", "failure",
        "--limit", "20", "--json", "databaseId,attempt,headSha,url,createdAt"))
    since = dt.datetime.now(dt.timezone.utc) - LOOKBACK
    for failure in sorted(failures, key=lambda item: item["createdAt"]):
        key = f"{failure['databaseId']}:{failure['attempt']}"
        created = dt.datetime.fromisoformat(failure["createdAt"].replace("Z", "+00:00"))
        if key in state["seen"] or created < since:
            continue
        deliver(state, failure)
        state["seen"][key] = failure["createdAt"]
        save_state(state)
    cutoff = (since - LOOKBACK).isoformat()
    state["seen"] = {key: at for key, at in state["seen"].items() if at >= cutoff}
    save_state(state)


def install():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "tick"],
        "StartInterval": 600,
        "RunAtLoad": True,
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                                 "HOME": str(Path.home())},
        "StandardOutPath": str(STATE_DIR / "log.txt"),
        "StandardErrorPath": str(STATE_DIR / "log.txt"),
    }
    uninstall(quiet=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], check=True)
    print(f"Installed {PLIST}; log: {STATE_DIR / 'log.txt'}")


def uninstall(quiet=False):
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    if PLIST.exists():
        PLIST.unlink()
    if not quiet:
        print(f"Removed {LABEL}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    actions = {"tick": tick, "install": install, "uninstall": uninstall}
    if command not in actions:
        sys.exit(__doc__)
    try:
        actions[command]()
    except subprocess.CalledProcessError as error:
        sys.exit(f"{' '.join(error.cmd)} failed ({error.returncode}): {error.stderr.strip()}")
