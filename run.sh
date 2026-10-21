#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN=""
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "[ERROR] No Python interpreter found (.venv/bin/python or python3)." >&2
  exit 1
fi

# ./run.sh clean [--yes]: delete this folder's local test data (your settings,
# the database, the uploaded resume, source keys, reports and documents) so
# the next `./run.sh` starts from onboarding. Only paths inside this folder,
# and only the ones .gitignore keeps out of the repository.
clean_local_data() {
  local yes="${1:-}"
  local targets=(config.yaml config.local.yaml data out logs dork_results.txt job-applications)
  local found=()
  for t in "${targets[@]}"; do
    [[ -e "$SCRIPT_DIR/$t" ]] && found+=("$t")
  done

  # A dashboard started from this folder keeps the database open.
  local pids=()
  for pid in $(pgrep -f "jobdork( .*)? serve" || true); do
    if [[ "$(lsof -a -d cwd -p "$pid" -Fn 2>/dev/null | sed -n 's/^n//p')" == "$(cd "$SCRIPT_DIR" && pwd -P)" ]]; then
      pids+=("$pid")
    fi
  done

  if [[ ${#found[@]} -eq 0 ]]; then
    echo "Nothing to clean: no local test data in $SCRIPT_DIR."
    return 0
  fi
  echo "This permanently deletes, in $SCRIPT_DIR:"
  for t in "${found[@]}"; do echo "  $t"; done
  [[ ${#pids[@]} -gt 0 ]] && echo "and stops the dashboard running from here (pid ${pids[*]})."
  echo ".env is kept."

  if [[ "$yes" != "--yes" ]]; then
    local answer
    read -r -p "Type 'yes' to delete: " answer
    if [[ "$answer" != "yes" ]]; then
      echo "Nothing deleted."
      return 1
    fi
  fi

  if [[ ${#pids[@]} -gt 0 ]]; then
    kill "${pids[@]}" 2>/dev/null || true
    sleep 1
  fi
  for t in "${found[@]}"; do rm -rf -- "${SCRIPT_DIR:?}/$t"; done
  echo "Local test data deleted. Run ./run.sh to start from onboarding."
}

if [[ "${1:-}" == "clean" ]]; then
  shift
  clean_local_data "$@"
  exit $?
fi

if [[ $# -eq 0 ]]; then
  set -- serve
fi

exec "$PYTHON_BIN" -m jobdork "$@"
