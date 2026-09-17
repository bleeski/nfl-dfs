#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# The Linux launcher. Windows uses ./nfl.ps1 and .venv; this uses .venv-linux.
# Never mix the two in one session.
#
# A container may mount this repository on a filesystem that cannot host a
# virtual environment (no symlink or hardlink support) or that has no free space
# for a managed interpreter. These overrides relocate the runtime without
# changing any default and without touching the Windows launcher.
venv_root="${NFL_DFS_VENV_DIR:-$project_root/.venv-linux}"
task_cache="${NFL_DFS_UV_CACHE_DIR:-$project_root/.uv-cache-linux}"
python_exe="$venv_root/bin/python"
command_name="${1:-run}"
if [ "$#" -gt 0 ]; then
    shift
fi

cd "$project_root"
export UV_CACHE_DIR="$task_cache"
export UV_PROJECT_ENVIRONMENT="$venv_root"
if [ -n "${NFL_DFS_UV_PYTHON_DIR:-}" ]; then
    export UV_PYTHON_INSTALL_DIR="$NFL_DFS_UV_PYTHON_DIR"
fi

if [ "$command_name" = "setup" ]; then
    if ! command -v uv >/dev/null 2>&1; then
        printf '%s\n' '{"status":"DO_NOT_UPLOAD","error":"uv is unavailable","message":"Install or enable uv, then rerun: sh ./nfl.sh setup"}' >&2
        exit 2
    fi
    uv sync --all-groups --locked --python 3.13.7
fi

if [ ! -x "$python_exe" ]; then
    printf '%s\n' '{"status":"DO_NOT_UPLOAD","error":"project environment is missing","message":"Run: sh ./nfl.sh setup"}' >&2
    exit 2
fi

if [ "$command_name" = "test" ]; then
    # Both writable roots pytest needs are pinned to per-user temp locations, for
    # the same reason nfl.ps1 pins them: a mounted repository has left the
    # default basetemp and the repo-local .pytest_cache unreadable before, which
    # fails every test at fixture setup rather than on its merits.
    #
    # basetemp carries the process id because pytest DELETES basetemp at the
    # start of every run. Two suites sharing one path means the second wipes the
    # first mid-flight, and the file-writing tests fail for a reason that has
    # nothing to do with the code. Measured 2026-09-17: two concurrent runs
    # produced three phantom failures in test_classic_review_c3[20], [150] and
    # test_cowork_rerun_regressions. Several Claude Code instances work this
    # repository, so that collision is expected rather than exotic.
    #
    # cache_dir stays shared. pytest does not clear it at startup, and keeping
    # one path is what makes `--lf` and `--ff` work across runs.
    pytest_tmp="${NFL_DFS_PYTEST_TMP:-${TMPDIR:-/tmp}/nfl-dfs-pytest/$$}"
    pytest_cache="${NFL_DFS_PYTEST_CACHE:-${TMPDIR:-/tmp}/nfl-dfs-pytest-cache}"
    exec "$python_exe" -m pytest --basetemp "$pytest_tmp" -o "cache_dir=$pytest_cache" "$@"
fi

exec "$python_exe" -m nfl_dfs.cli "$command_name" "$@"
