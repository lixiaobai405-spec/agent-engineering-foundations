from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_foundations.domain.errors import PathPolicyViolationError
from agent_foundations.tools.filesystem.path_policy import PathPolicy

FIXTURE = Path("tests/fixtures/sample_project").resolve()


def test_authorizes_file_inside_root() -> None:
    policy = PathPolicy(FIXTURE)
    assert policy.authorize("src/auth.py") == FIXTURE / "src/auth.py"


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        ".env",
        ".env.local",
        "credentials.json",
        "secrets.pem",
        ".git/config",
        "C:drive-relative.txt",
        "README.md:alternate-stream",
    ],
)
def test_rejects_escape_and_sensitive_paths(path: str) -> None:
    policy = PathPolicy(FIXTURE)
    with pytest.raises(PathPolicyViolationError):
        policy.authorize(path, must_exist=False)


def test_rejects_absolute_path_even_when_inside_root() -> None:
    policy = PathPolicy(FIXTURE)
    with pytest.raises(PathPolicyViolationError, match="relative"):
        policy.authorize(str(FIXTURE / "README.md"))


def test_rejects_symlink_that_resolves_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this Windows host")
    with pytest.raises(PathPolicyViolationError, match="escapes"):
        PathPolicy(root).authorize("link.txt")


@pytest.mark.parametrize(
    "path",
    [
        ".env/child.txt",
        ".ENV.local/child.txt",
        "credentials.json/child.txt",
        "secrets.pem/child.txt",
        "private.key/child.txt",
        "cookies.json/child.txt",
        "id_rsa/child.txt",
    ],
)
def test_rejects_sensitive_name_in_any_path_component(
    tmp_path: Path,
    path: str,
) -> None:
    root = tmp_path / "root"
    target = root / path
    target.parent.mkdir(parents=True)
    target.write_text("sensitive", encoding="utf-8")

    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy(root).authorize(path)


@pytest.mark.parametrize(
    "name",
    [".npmrc", ".pypirc", ".netrc", ".git-credentials"],
)
def test_rejects_common_credential_files(tmp_path: Path, name: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / name).write_text("token=secret", encoding="utf-8")

    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy(root).authorize(name)


@pytest.mark.parametrize(
    "name",
    [
        "NUL",
        "CON.txt",
        "AUX.json",
        "PRN",
        "COM1.log",
        "LPT9.txt",
        "CLOCK$",
        "CONIN$",
        "CONOUT$",
    ],
)
def test_rejects_windows_reserved_device_names(name: str) -> None:
    with pytest.raises(PathPolicyViolationError, match="reserved"):
        PathPolicy(FIXTURE).authorize(name, must_exist=False)


@pytest.mark.parametrize(
    "path",
    ["bad\x00name", "bad?name", "bad*name", "bad|name"],
)
def test_maps_invalid_windows_path_syntax_to_policy_error(path: str) -> None:
    with pytest.raises(PathPolicyViolationError, match="invalid"):
        PathPolicy(FIXTURE).authorize(path, must_exist=False)


def test_display_path_rejects_sensitive_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    sensitive = root / ".npmrc"
    sensitive.write_text("token=secret", encoding="utf-8")

    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy(root).display_path(sensitive)


def test_resolve_external_read_target_accepts_file_and_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "external"
    directory.mkdir()
    file_path = directory / "notes.txt"
    file_path.write_text("notes", encoding="utf-8")

    assert PathPolicy.resolve_external_read_target(str(directory)) == (
        directory.resolve(strict=True)
    )
    assert PathPolicy.resolve_external_read_target(str(file_path)) == (
        file_path.resolve(strict=True)
    )


def test_external_resolution_does_not_grant_project_authorization(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside", encoding="utf-8")

    assert PathPolicy.resolve_external_read_target(str(external)) == external.resolve()
    with pytest.raises(PathPolicyViolationError, match="relative"):
        PathPolicy(project).authorize(str(external))


@pytest.mark.parametrize(
    "value_factory",
    [
        pytest.param(lambda root: "relative.txt", id="relative"),
        pytest.param(lambda root: str(root / "missing.txt"), id="missing"),
        pytest.param(lambda root: str(root / ".env"), id="env"),
        pytest.param(lambda root: str(root / "credentials.json"), id="credentials"),
        pytest.param(lambda root: str(root / "secrets" / "notes.txt"), id="secrets"),
        pytest.param(lambda root: str(root / "private.pem"), id="private-key"),
        pytest.param(lambda root: str(root / "NUL.txt"), id="reserved-device"),
        pytest.param(lambda root: str(root / "notes.txt") + ":secret", id="ads"),
        pytest.param(lambda root: str(root / "bad\x01name.txt"), id="control"),
        pytest.param(lambda root: r"\\server\share\notes.txt", id="unc"),
        pytest.param(lambda root: r"\\?\C:\notes.txt", id="device-namespace"),
        pytest.param(lambda root: r"\\.\C:\notes.txt", id="device-dot-namespace"),
    ],
)
def test_resolve_external_read_target_hard_rejects_unsafe_values(
    tmp_path: Path,
    value_factory: Callable[[Path], str],
) -> None:
    value = value_factory(tmp_path)
    with pytest.raises(PathPolicyViolationError):
        PathPolicy.resolve_external_read_target(value)


def test_resolve_external_read_target_rejects_non_file_or_directory(
    tmp_path: Path,
) -> None:
    target = tmp_path / "other-target"
    target.mkdir()
    canonical = target.resolve(strict=True)
    original_is_file = Path.is_file
    original_is_dir = Path.is_dir

    def is_file(path: Path) -> bool:
        return False if path == canonical else original_is_file(path)

    def is_dir(path: Path) -> bool:
        return False if path == canonical else original_is_dir(path)

    with (
        patch.object(Path, "is_file", is_file),
        patch.object(Path, "is_dir", is_dir),
        pytest.raises(PathPolicyViolationError, match="file or directory"),
    ):
        PathPolicy.resolve_external_read_target(str(target))


def test_resolve_external_read_target_rechecks_sensitive_symlink_target(
    tmp_path: Path,
) -> None:
    sensitive = tmp_path / "secrets" / "notes.txt"
    sensitive.parent.mkdir()
    sensitive.write_text("sensitive", encoding="utf-8")
    link = tmp_path / "safe-link.txt"
    try:
        link.symlink_to(sensitive)
    except OSError:
        pytest.skip("creating symlinks is not permitted on this Windows host")

    with pytest.raises(PathPolicyViolationError, match="sensitive"):
        PathPolicy.resolve_external_read_target(str(link))
