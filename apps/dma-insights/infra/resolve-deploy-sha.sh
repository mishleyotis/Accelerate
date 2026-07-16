#!/usr/bin/env bash
# apps/dma-insights/infra/resolve-deploy-sha.sh
#
# Resolve the NEWEST deploy SHA — the tip of the canonical deploy branch on
# origin — and (when the working tree is clean) sync the local checkout to it
# so the image built from the tree MATCHES the SHA tag.
#
# WHY THIS EXISTS (the bde8329 incident):
#   Every deploy path used to tag images from `git rev-parse --short HEAD` of
#   whatever the operator happened to have checked out. A stale clone, a
#   leftover feature branch (e.g. claude/awesome-sagan @ bde8329), or a leaked
#   `SHA` env var then shipped an OLD image even though newer code sat on the
#   deploy branch — and because the old image still existed in gcr.io, the
#   image-existence preflight happily deployed it. This script makes "deploy"
#   mean "deploy the newest committed code on the deploy branch",
#   deterministically, for every entrypoint.
#
# OUTPUT: prints the short SHA to stdout. ALL diagnostics go to stderr, so
#   `SHA="$(bash resolve-deploy-sha.sh)"` captures only the SHA.
#
# KNOBS:
#   DEPLOY_BRANCH=<name>   branch to deploy (default resolution below)
#   ALLOW_DIRTY_DEPLOY=1   permit a dirty tree (its uncommitted changes get
#                          baked into the image under a SHA that does NOT
#                          contain them — emergency hotfix only)
#   NO_SYNC=1              resolve + report only; never touch the working tree
#                          (used by callers that just want the staleness check)
#
# EXIT CODES: 0 ok · 3 not-a-git-repo · 4 deploy branch missing on origin ·
#   5 dirty tree (refused) · 6 checkout failed · 7 fetch failed
#   (network/credentials — DEPLOY_ALLOW_LOCAL_HEAD=1 opts into the
#   local-HEAD fallback instead)
set -euo pipefail

# Canonical deploy branch for this repo. Override with DEPLOY_BRANCH, or set a
# remote default once (`git remote set-head origin <branch>`) and this script
# picks it up automatically — so the hardcoded fallback is only a last resort.
DEFAULT_DEPLOY_BRANCH="claude/deploy-zennify-cloud-run-AUdu6"

err() { echo "resolve-deploy-sha: $*" >&2; }

# Canonical short SHA = the FIRST 7 hex chars of the full commit SHA. This
# matches Cloud Build's $SHORT_SHA (which the build trigger uses to tag the
# images) and is DETERMINISTIC across clones — unlike `git rev-parse --short`,
# whose abbreviation length auto-extends with a clone's object density (the
# `2ee4efa` vs `2ee4efa7` incident), which made the deploy look up an image
# tag the build never produced.
short7() { (git rev-parse "${1:?}" 2>/dev/null || true) | cut -c1-7; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  err "not a git repo — cannot resolve a deploy SHA here"
  exit 3
fi

# Branch precedence: explicit env > remote default (origin/HEAD) > fallback.
branch="${DEPLOY_BRANCH:-}"
if [[ -z "$branch" ]]; then
  if rh="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)"; then
    branch="${rh#origin/}"
  else
    branch="$DEFAULT_DEPLOY_BRANCH"
  fi
fi

# Fetch the deploy branch. A fetch failure is NOT one condition
# (2026-07-04 line audit — the old blanket local-HEAD fallback exited 0
# on BOTH, so a typo'd DEPLOY_BRANCH or expired credentials silently
# deployed a stale checkout: the exact bde8329-class incident this
# script exists to prevent):
#   - branch absent on origin (typo)      → exit 4, loud.
#   - transient network/credential outage → exit 6 UNLESS the operator
#     explicitly opts into the local-HEAD fallback with
#     DEPLOY_ALLOW_LOCAL_HEAD=1 (then loud warning + local sha).
err "fetching origin/$branch …"
if ! git fetch --quiet --prune origin "$branch" 2>/dev/null; then
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    # Remote reachable and the branch exists — the fetch itself failed
    # (shallow-clone edge, transient). Treat as network-class.
    :
  elif git ls-remote origin >/dev/null 2>&1; then
    err "✗ origin is reachable but branch '$branch' does not exist."
    err "  Set DEPLOY_BRANCH=<your deploy branch> (typo?)."
    exit 4
  fi
  if [[ "${DEPLOY_ALLOW_LOCAL_HEAD:-}" == "1" ]]; then
    err "⚠ git fetch origin/$branch failed — DEPLOY_ALLOW_LOCAL_HEAD=1 set,"
    err "  deploying the LOCAL checkout $(short7 HEAD). This may be STALE."
    short7 HEAD
    exit 0
  fi
  err "✗ git fetch origin/$branch failed (network/credentials?)."
  err "  Refusing to guess: a stale local HEAD must never ship silently."
  err "  Fix connectivity, or set DEPLOY_ALLOW_LOCAL_HEAD=1 to deploy the"
  err "  local checkout deliberately."
  exit 7
fi

if ! git rev-parse --verify --quiet "refs/remotes/origin/$branch" >/dev/null; then
  err "✗ origin/$branch not found. Set DEPLOY_BRANCH=<your deploy branch>."
  exit 4
fi
remote_sha="$(git rev-parse "refs/remotes/origin/$branch")"
remote_short="$(short7 "refs/remotes/origin/$branch")"
local_sha="$(git rev-parse HEAD)"

if [[ "$local_sha" == "$remote_sha" ]]; then
  err "✓ already at newest origin/$branch ($remote_short)"
  echo "$remote_short"
  exit 0
fi

# Local HEAD differs from the deploy-branch tip (behind / wrong branch /
# diverged). Report exactly how, then sync so the BUILD ships the newest code.
local_short="$(short7 HEAD)"
if git merge-base --is-ancestor "$local_sha" "$remote_sha" 2>/dev/null; then
  err "local HEAD ($local_short) is BEHIND origin/$branch ($remote_short) — STALE"
else
  err "local HEAD ($local_short) is NOT on origin/$branch ($remote_short)"
fi

if [[ "${NO_SYNC:-}" == "1" ]]; then
  err "NO_SYNC=1 — not touching the tree; reporting newest=$remote_short"
  echo "$remote_short"
  exit 0
fi

if [[ -n "$(git status --porcelain 2>/dev/null)" && "${ALLOW_DIRTY_DEPLOY:-}" != "1" ]]; then
  err "✗ refusing to sync: working tree has uncommitted changes."
  err "  Commit or stash them, or set ALLOW_DIRTY_DEPLOY=1 to ship them under SHA $remote_short."
  exit 5
fi

err "→ syncing local checkout to origin/$branch ($local_short → $remote_short)"
if ! git checkout -B "$branch" "refs/remotes/origin/$branch" >/dev/null 2>&1; then
  err "✗ could not check out origin/$branch"
  exit 6
fi
err "✓ now at newest origin/$branch ($remote_short)"
echo "$remote_short"
