#!/usr/bin/env bash
# The evidence engine's place in the release: runs from the CI deploy job
# AFTER infra/deploy.sh, on every merge to the default branch. It creates
# nothing unless infra/evidence-engine/APPROVAL.json clears the owner's
# threshold (approval_check.py); until then it prints why and exits 0, so
# the release of web/api/mcp is never held by the engine's gate.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if out="$(python3 "$HERE/approval_check.py")"; then
  echo "evidence engine: $out"
  export EE_DEPLOY_APPROVED=1
  bash "$HERE/deploy-evidence.sh"
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "::error title=Evidence engine deploy failed::deploy-evidence.sh exited $rc (web/api/mcp already shipped above)"
  fi
  exit $rc
else
  rc=$?
  if [ $rc -eq 3 ]; then
    echo "evidence engine: not deployed — $out"
    echo "::notice title=Evidence engine not deployed::$out"
    exit 0
  fi
  echo "::error title=Evidence engine gate error::approval_check.py exited $rc: $out"
  exit $rc
fi
