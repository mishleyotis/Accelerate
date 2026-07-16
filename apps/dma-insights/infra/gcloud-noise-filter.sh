#!/usr/bin/env bash
# gcloud-noise-filter.sh — SOURCE this (do not execute) to silence ONE
# known-benign gcloud stderr line for the current shell + child bash
# processes:
#
#   Regional Access Boundary HTTP request failed after retries:
#   response_data={'error': {'code': 404, 'message': 'Account not found
#   for email: <federated id>|<user>', 'status': 'NOT_FOUND'}}, ...
#
# WHY IT APPEARS (verified against google-auth sources, 2026-07-04):
# gcloud's bundled google-auth performs a Regional Access Boundary
# (trust boundary) lookup on every token refresh; Cloud Shell's
# federated identities ("f631843d16|user@…") have no RAB account, so
# the lookup 404s. The failure is NON-FATAL BY DESIGN (google-auth
# falls back to a no-op trust boundary and the command proceeds), but
# google-auth 2.51.0–2.55.0 log it at WARNING — once per gcloud call.
# google-auth 2.55.1 demoted the line to DEBUG; once Cloud Shell's
# gcloud bundles >= 2.55.1 this filter is a no-op and can be removed.
#
# WHAT THIS DOES: wraps `gcloud` in a function that drops EXACTLY that
# line from stderr (everything else — real warnings, errors, exit
# codes — passes through untouched). `export -f` propagates the wrapper
# to child bash processes, and every deploy entrypoint ALSO sources
# this file so standalone runs are covered.
#
# Stdout is NEVER touched (load-from-secret-manager --emit-exports and
# resolve-deploy-sha stdout-purity contracts stay intact), and this
# file prints nothing when sourced.
if ! declare -f gcloud >/dev/null 2>&1; then
  gcloud() {
    command gcloud "$@" \
      2> >(grep -v "Regional Access Boundary HTTP request failed after retries" >&2)
  }
  export -f gcloud 2>/dev/null || true
fi
