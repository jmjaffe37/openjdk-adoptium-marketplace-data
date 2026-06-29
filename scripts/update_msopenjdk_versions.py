"""Update the Microsoft OpenJDK marketplace versions file from release indexes.

Usage:
    update_msopenjdk_versions.py --versions_file=<versions_file> --release_dir=<release_dir>... [--exclude_alpine]

Options:
    --versions_file=<versions_file>  Path to microsoft-openjdk-versions.json.
    --release_dir=<release_dir>      Release directory containing index.json. Repeat for each major.
    --exclude_alpine                 Exclude Alpine package entries (for jdk11 and jdk17) from generated files.
    --help  Show this help message.

Example:
    update_msopenjdk_versions.py --versions_file=../general_info/microsoft-openjdk-versions.json --release_dir=../25 --release_dir=../21 --release_dir=../17
    update_msopenjdk_versions.py --versions_file=../general_info/microsoft-openjdk-versions.json --release_dir=../21 --release_dir=../17 --release_dir=../11 --exclude_alpine
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from docopt import docopt

logging.basicConfig(format="%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

RELEASE_URL = "https://aka.ms/download-jdk"
# Only the major version is required in the version string within the json filename,
# all other versions are optional since not all releases have them.
RELEASE_PATTERN = re.compile(
    r"^jdk_(?P<major>\d+)(?:_(?P<minor>\d+)(?:_(?P<security>\d+)(?:_(?P<patch>\d+))?)?)?\.json$"
)
PACKAGE_LAYOUT = (
    ("darwin", "x64", "macos-x64.tar.gz"),
    ("linux", "x64", "linux-x64.tar.gz"),
    ("win32", "x64", "windows-x64.zip"),
    ("darwin", "aarch64", "macos-aarch64.tar.gz"),
    ("linux", "aarch64", "linux-aarch64.tar.gz"),
    ("win32", "aarch64", "windows-aarch64.zip"),
)

ALPINE_PACKAGE_LAYOUT = (("alpine", "x64", "alpine-x64.tar.gz"),)
EXCLUDE_ALPINE = False


def parse_version_from_release_json_name(release_filename: str) -> str:
    match = RELEASE_PATTERN.fullmatch(release_filename)
    if not match:
        raise ValueError(f"Unsupported release filename format: {release_filename}")

    major = match.group("major")
    minor = match.group("minor") or "0"
    security = match.group("security") or "0"
    patch = match.group("patch")

    if patch is not None:
        return f"{major}.{minor}.{security}.{patch}"

    return f"{major}.{minor}.{security}"


def load_release_json_names(release_dir: Path) -> list[str]:
    index_file = release_dir / "index.json"
    if not index_file.is_file():
        raise FileNotFoundError(f"Missing index.json in {release_dir}")

    with index_file.open("r", encoding="utf-8") as file_handle:
        index_data = json.load(file_handle)

    releases = index_data.get("releases")
    if not isinstance(releases, list):
        raise ValueError(f"Expected a releases list in {index_file}")

    return [release for release in releases if isinstance(release, str)]


def build_files(version: str) -> list[dict[str, str]]:
    files = []
    package_layout = PACKAGE_LAYOUT
    if not EXCLUDE_ALPINE and (version.startswith("11.") or version.startswith("17.")):
        package_layout += ALPINE_PACKAGE_LAYOUT

    for platform, arch, suffix in package_layout:
        filename = f"microsoft-jdk-{version}-{suffix}"
        files.append(
            {
                "filename": filename,
                "arch": arch,
                "platform": platform,
                "download_url": f"{RELEASE_URL}/{filename}",
            }
        )
    return files


def build_version_entry(version: str) -> dict[str, object]:
    return {
        "version": version,
        "stable": True,
        "release_url": RELEASE_URL,
        "files": build_files(version),
    }


def version_sort_key(version: str) -> tuple[int, int, int, float]:
    parts: list[str] = version.split("+")
    parts = parts[0].split(".") + parts[1:]
    if len(parts) == 3:
        major, minor, security = parts
        patch = "0"
    elif len(parts) == 4:
        major, minor, security, patch = parts
    else:
        raise ValueError(f"Unsupported version format: {version}")

    return (int(major), int(minor), int(security), float(patch))


def load_existing_versions(versions_file: Path) -> list[str]:
    if not versions_file.is_file():
        return []

    with versions_file.open("r", encoding="utf-8") as file_handle:
        versions_data = json.load(file_handle)

    if not isinstance(versions_data, list):
        raise ValueError(f"Expected a top-level list in {versions_file}")

    existing_versions: list[str] = []
    for entry in versions_data:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if isinstance(version, str):
            existing_versions.append(version)

    return existing_versions


def collect_versions(release_dirs: list[Path]) -> list[str]:
    versions: list[str] = []
    seen_versions: set[str] = set()

    for release_dir in release_dirs:
        for release_filename in load_release_json_names(release_dir):
            version = parse_version_from_release_json_name(release_filename)
            if version in seen_versions:
                continue
            versions.append(version)
            seen_versions.add(version)

    return versions


def main(versions_file: Path, release_dirs: list[Path]) -> None:
    versions = collect_versions(release_dirs)
    versions.extend(load_existing_versions(versions_file))
    versions = sorted(set(versions), key=version_sort_key, reverse=True)
    version_entries = [build_version_entry(version) for version in versions]

    with versions_file.open("w", encoding="utf-8") as file_handle:
        json.dump(version_entries, file_handle, indent=4)
        file_handle.write("\n")

    logger.info(
        "Updated %s with %d Microsoft OpenJDK version entries",
        versions_file,
        len(version_entries),
    )


if __name__ == "__main__":
    args = docopt(__doc__)
    EXCLUDE_ALPINE = bool(args["--exclude_alpine"])
    versions_file = Path(str(args["--versions_file"])).resolve()
    release_dirs = [
        Path(release_dir).resolve() for release_dir in args["--release_dir"]
    ]
    main(versions_file=versions_file, release_dirs=release_dirs)
