#!/usr/bin/env python3

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def skill_directories(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def skill_names(root: Path) -> set[str]:
    return {path.name for path in skill_directories(root)}


def zip_name(skill: str) -> str:
    return f"{skill}.zip"


def normalize_archive_path(path: PurePosixPath, directory: bool = False) -> str:
    archive_path = path.as_posix()
    if directory and not archive_path.endswith("/"):
        return f"{archive_path}/"
    return archive_path


def write_directory_entry(archive: zipfile.ZipFile, archive_path: PurePosixPath, mode: int) -> None:
    info = zipfile.ZipInfo(normalize_archive_path(archive_path, directory=True))
    info.date_time = FIXED_TIMESTAMP
    info.create_system = 3
    info.external_attr = ((stat.S_IFDIR | mode) << 16) | 0x10
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, b"")


def write_file_entry(archive: zipfile.ZipFile, source: Path, archive_path: PurePosixPath, mode: int) -> None:
    info = zipfile.ZipInfo(normalize_archive_path(archive_path))
    info.date_time = FIXED_TIMESTAMP
    info.create_system = 3
    info.external_attr = ((stat.S_IFREG | mode) << 16)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, source.read_bytes())


def write_symlink_entry(archive: zipfile.ZipFile, source: Path, archive_path: PurePosixPath, mode: int) -> None:
    info = zipfile.ZipInfo(normalize_archive_path(archive_path))
    info.date_time = FIXED_TIMESTAMP
    info.create_system = 3
    info.external_attr = ((stat.S_IFLNK | mode) << 16)
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, os.readlink(source).encode())


def build_archive(source_root: Path, skill: str, output_path: Path) -> None:
    skill_root = source_root / skill
    skill_zip = skill_root / zip_name(skill)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        stack = [skill_root]
        while stack:
            current = stack.pop()
            relative = current.relative_to(skill_root)
            archive_path = PurePosixPath(skill, *relative.parts)
            metadata = current.lstat()
            mode = stat.S_IMODE(metadata.st_mode) or 0o755

            if current.is_symlink():
                write_symlink_entry(archive, current, archive_path, mode)
                continue

            if current.is_dir():
                write_directory_entry(archive, archive_path, mode)
                children = sorted(
                    child for child in current.iterdir() if child != skill_zip
                )
                stack.extend(reversed(children))
                continue

            write_file_entry(archive, current, archive_path, mode)


def staged_skill_names(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD", "--"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    available = skill_names(root)
    changed: set[str] = set()
    for path in result.stdout.splitlines():
        if not path or path.startswith("."):
            continue
        top_level = path.split("/", 1)[0]
        if top_level in available:
            changed.add(top_level)
    return sorted(changed)


def indexed_paths(root: Path, skills: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--full-name", "--", *skills],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [path for path in result.stdout.splitlines() if path]


def checkout_index(root: Path, skills: list[str]) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="skill-index-"))
    paths = indexed_paths(root, skills)
    if not paths:
        return temp_root
    try:
        subprocess.run(
            ["git", "checkout-index", "--force", f"--prefix={temp_root}/", "--", *paths],
            cwd=root,
            check=True,
        )
    except Exception:
        shutil.rmtree(temp_root)
        raise
    return temp_root


def files_match(path_a: Path, path_b: Path) -> bool:
    return path_a.exists() and filecmp.cmp(path_a, path_b, shallow=False)


def replace_if_changed(source_root: Path, root: Path, skill: str) -> bool:
    skill_root = root / skill
    if not skill_root.is_dir():
        return False

    target = skill_root / zip_name(skill)
    with tempfile.NamedTemporaryFile(prefix=f"{skill}-", suffix=".zip", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        build_archive(source_root, skill, temp_path)
        if files_match(target, temp_path):
            return False
        os.replace(temp_path, target)
        return True
    finally:
        if temp_path.exists():
            temp_path.unlink()


def sync(root: Path, skills: list[str]) -> int:
    updated = [skill for skill in skills if replace_if_changed(root, root, skill)]
    if updated:
        print("Updated skill archives:")
        for skill in updated:
            print(f"  - {skill}/{zip_name(skill)}")
    else:
        print("Skill archives are current.")
    return 0


def verify(root: Path, skills: list[str]) -> int:
    stale: list[str] = []
    for skill in skills:
        skill_root = root / skill
        if not skill_root.is_dir():
            continue

        expected = skill_root / zip_name(skill)
        with tempfile.NamedTemporaryFile(prefix=f"{skill}-", suffix=".zip", delete=False) as temp_file:
            temp_path = Path(temp_file.name)

        try:
            build_archive(root, skill, temp_path)
            if not files_match(expected, temp_path):
                stale.append(f"{skill}/{zip_name(skill)}")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    if not stale:
        print("Skill archives verified.")
        return 0

    print("Stale or missing skill archives:")
    for path in stale:
        print(f"  - {path}")
    return 1


def run_pre_commit(root: Path) -> int:
    skills = staged_skill_names(root)
    if not skills:
        return 0

    snapshot = checkout_index(root, skills)
    try:
        updated = [skill for skill in skills if replace_if_changed(snapshot, root, skill)]
    finally:
        shutil.rmtree(snapshot)

    if updated:
        subprocess.run(
            ["git", "add", "--", *(f"{skill}/{zip_name(skill)}" for skill in updated)],
            cwd=root,
            check=True,
        )
        print("Updated staged skill archives:")
        for skill in updated:
            print(f"  - {skill}/{zip_name(skill)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("sync", "verify", "pre-commit"),
        default="sync",
    )
    parser.add_argument(
        "--skill",
        action="append",
        dest="skills",
        help="Limit the operation to one or more top-level skill directories.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    available = skill_names(root)

    skills = sorted(set(args.skills or available))
    unknown = [skill for skill in skills if skill not in available]
    if unknown:
        for skill in unknown:
            print(f"Unknown skill: {skill}", file=sys.stderr)
        return 2

    if args.mode == "sync":
        return sync(root, skills)
    if args.mode == "verify":
        return verify(root, skills)
    return run_pre_commit(root)


if __name__ == "__main__":
    raise SystemExit(main())
