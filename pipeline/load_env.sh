#!/bin/bash
# Export pipeline/env/common.env and the current branch's environment file
# (main -> prod, dev -> dev) to the later steps of a GitHub Actions job.
set -euo pipefail

case "$GITHUB_REF_NAME" in
    main) env=prod ;;
    dev)  env=dev ;;
    *)    echo "No environment for branch $GITHUB_REF_NAME" >&2; exit 1 ;;
esac

grep -hv -e '^[[:space:]]*#' -e '^[[:space:]]*$' \
    pipeline/env/common.env "pipeline/env/$env.env" >> "$GITHUB_ENV"
