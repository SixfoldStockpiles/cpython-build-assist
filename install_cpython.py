#!/bin/env python3

import argparse
import enum
import subprocess
import sys
from typing import List, Tuple, Optional

from semantic_version import Version


class DistroLike(enum.Enum):
    Debian = "debian"
    RedHatFedora = "rhel fedora"


def detect_distro_like() -> DistroLike:
    target_prefix = "ID_LIKE="
    with open('/etc/os-release') as f:
        os_release = [line[len(target_prefix):] for line in f.read().split() if line[:len(target_prefix)] == target_prefix]
    if len(os_release) != 1:
        raise ValueError("Unexpected format of /etc/os-release")
    distro_like = os_release.pop()
    try:
        return DistroLike(distro_like)
    except ValueError:
        raise ValueError(f'Unsupported distro: {distro_like}')


def install_system_dependencies(distro_like: DistroLike) -> None:
    if distro_like == DistroLike.Debian:
        safe_run_process("apt update")
        safe_run_process("apt build-dep -y python3")
        safe_run_process("apt install -y build-essential gdb lcov libbz2-dev libffi-dev libgdbm-dev liblzma-dev "
                         "libncurses5-dev libreadline6-dev libsqlite3-dev libssl-dev lzma lzma-dev tk-dev uuid-dev zlib1g-dev")
    elif distro_like == DistroLike.RedHatFedora:
        # TODO: test this on a centos box
        safe_run_process("yum install -y yum-utils")
        safe_run_process("yum-builddep -y python3")
    else:
        raise ValueError(f"Unsupported distro: {distro_like}")


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


def get_latest_minor_versions(versions: List[str]):
    # Drop the leading 'v' and parse where possible:
    versions = [normalize_version(ver) for ver in versions]
    versions = [(version_str, version) for version_str, version in versions if version is not None]

    # Group by minor version:
    versions_by_minor_version = {f'{version.major}.{version.minor}': [] for version_tag, version in versions}
    for version_tag, version in versions:
        versions_by_minor_version[f'{version.major}.{version.minor}'].append((version_tag, version))

    # Get maximum:
    latest_minor_versions = [max(versions, key=lambda x: x[1]) for _, versions in versions_by_minor_version.items()]

    return latest_minor_versions


def safe_run_process(cmd: str, cwd: Optional[str] = None):
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
    parser.add_argument('--minimum_python_version', '--min', type=str, default='3.0.0')
    parser.add_argument('--maximum_python_version', '--max', type=str, default=None, required=False)
    parser.add_argument('--pull', action='store_true')
    args = parser.parse_args()

    versions = get_versions(cpython_repo_dir=args.cpython_repo_dir)
    versions = get_latest_minor_versions(versions)
    if args.minimum_python_version is not None:
        versions = [(version_tag, version) for version_tag, version in versions if version >= Version(args.minimum_python_version)]
    if args.maximum_python_version is not None:
        versions = [(version_tag, version) for version_tag, version in versions if version <= Version(args.maximum_python_version)]
    version_tags = [version_tag for version_tag, version in versions]

    initial_ref = subprocess.check_output('git rev-parse HEAD'.split(), cwd=args.cpython_repo_dir).decode().strip()
    print(f">>> Initial ref: {initial_ref}")

    # Detect distro and install system dependencies:
    print(">>> Installing system dependencies")
    distro_like = detect_distro_like()
    install_system_dependencies(distro_like)

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
            safe_run_process(cmd=f'./configure --enable-optimizations', cwd=args.cpython_repo_dir)

            print(f">>> Cleaning {version_tag}")
            safe_run_process(cmd=f'make clean', cwd=args.cpython_repo_dir)

            print(f">>> Making {version_tag}")
            safe_run_process(cmd=f'make -j', cwd=args.cpython_repo_dir)

            print(f">>> Installing {version_tag}")
            safe_run_process(cmd=f'make altinstall', cwd=args.cpython_repo_dir)
        except OSError:
            continue

    print(f">>> Restoring head to {initial_ref}")
    subprocess.check_output(f'git checkout {initial_ref}'.split(), cwd=args.cpython_repo_dir)
