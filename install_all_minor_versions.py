#!/bin/env python3

import argparse
import subprocess
import sys
from typing import List, Tuple, Optional

from semantic_version import Version


def get_versions(cpython_repo_dir: str) -> List[str]:
    return subprocess.check_output(f'git tag'.split(), cwd=cpython_repo_dir).decode().split()


def safe_parse_version(version_str: str) -> Optional[Version]:
    try:
        return Version(version_str)
    except ValueError:
        return None


def normalize_version(version_tag) -> Tuple[str, Version]:
    if version_tag[0] == 'v':
        return version_tag, safe_parse_version(version_tag[1:])
    else:
        return version_tag, safe_parse_version(version_tag)


def get_latest_minor_versions(versions: List[str], minimum_version: str):
    # Drop the leading 'v' and parse where possible:
    versions = [normalize_version(ver) for ver in versions]
    versions = [(version_str, version) for version_str, version in versions if version is not None]

    # Filter minimum version:
    versions = [(version_tag, version) for version_tag, version in versions if version >= Version(minimum_version)]

    # Group by minor version:
    versions_by_minor_version = {f'{version.major}.{version.minor}': [] for version_tag, version in versions}
    for version_tag, version in versions:
        versions_by_minor_version[f'{version.major}.{version.minor}'].append((version_tag, version))

    # Get maximum:
    latest_minor_versions = [max(versions, key=lambda x: x[1]) for _, versions in versions_by_minor_version.items()]

    return latest_minor_versions


def safe_run_process(cmd: str, cwd: str):
    proc = subprocess.Popen(cmd.split(), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode != 0:
        print(f"{proc.returncode}")
        print(out.decode(), file=sys.stdout)
        print(err.decode(), file=sys.stderr)
        raise OSError()


if __name__ == '__main__':
    # TODO(TK): README; push to github

    parser = argparse.ArgumentParser()
    parser.add_argument('--cpython_repo_dir', '-d', type=str, required=True)
    parser.add_argument('--minimum_python_version', '-m', type=str, default='3.0.0')
    parser.add_argument('--pull', action='store_true')
    args = parser.parse_args()

    versions = get_versions(cpython_repo_dir=args.cpython_repo_dir)
    versions = get_latest_minor_versions(versions=versions, minimum_version=args.minimum_python_version)
    version_tags = [version_tag for version_tag, version in versions]

    initial_ref = subprocess.check_output('git rev-parse HEAD'.split(), cwd=args.cpython_repo_dir).decode().strip()
    print(f">>> Initial ref: {initial_ref}")

    if args.pull:
        print(">>> Pulling")
        safe_run_process(cmd='git pull', cwd=args.cpython_repo_dir)
    else:
        print(">>> Skipping pulling")

    for version_tag in sorted(version_tags, reverse=True):
        try:
            print(f">>> Getting {version_tag}")
            safe_run_process(cmd=f'git add -A', cwd=args.cpython_repo_dir)
            safe_run_process(cmd=f'git reset --hard', cwd=args.cpython_repo_dir)
            safe_run_process(cmd=f'git checkout {version_tag}', cwd=args.cpython_repo_dir)

            print(f">>> Configuring {version_tag}")
            safe_run_process(cmd=f'./configure', cwd=args.cpython_repo_dir)

            print(f">>> Cleaning {version_tag}")
            safe_run_process(cmd=f'make clean', cwd=args.cpython_repo_dir)

            print(f">>> Making {version_tag}")
            safe_run_process(cmd=f'make', cwd=args.cpython_repo_dir)

            print(f">>> Installing {version_tag}")
            safe_run_process(cmd=f'make altinstall', cwd=args.cpython_repo_dir)
        except OSError:
            continue

    print(f">>> Restoring head to {initial_ref}")
    subprocess.check_output(f'git checkout {initial_ref}'.split(), cwd=args.cpython_repo_dir)
