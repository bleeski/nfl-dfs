#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# A Cowork session may mount this repository on a filesystem that cannot host a
# virtual environment (no symlink or hardlink support) or that has no free space
# for a managed interpreter. These overrides relocate the runtime without
# changing any default and without touching the Windows launcher.
venv_root="${NFL_DFS_VENV_DIR:-$project_root/.cowork-venv}"
task_cache="${NFL_DFS_UV_CACHE_DIR:-$project_root/.cowork-uv-cache}"
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
        printf '%s\n' '{"status":"DO_NOT_UPLOAD","error":"uv is unavailable","message":"Install or enable uv in the Cowork runtime, then rerun: sh ./nfl.sh setup"}' >&2
        exit 2
    fi
    uv sync --all-groups --locked --python 3.13.7
fi

if [ ! -x "$python_exe" ]; then
    printf '%s\n' '{"status":"DO_NOT_UPLOAD","error":"project environment is missing","message":"Run: sh ./nfl.sh setup"}' >&2
    exit 2
fi

if [ "$command_name" = "test" ]; then
    exec "$python_exe" -m pytest "$@"
fi

exec "$python_exe" -m nfl_dfs.cli "$command_name" "$@"
