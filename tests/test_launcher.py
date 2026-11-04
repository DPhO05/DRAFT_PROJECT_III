"""Mo-tro-ly.command: the tutor double-clicks it; uv and curl are fakes, nothing real is installed or fetched."""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "Mo-tro-ly.command"
UV_URL = "https://astral.sh/uv/install.sh"


def fake(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def launch(tmp_path: Path, with_uv: bool, uv_exit: int = 0) -> tuple[Path, str]:
    """Run a copy of the launcher from a folder with a space and an accent, under a fake HOME and PATH.

    Returns the fake calls file and the launcher's output; `uv_exit` is what the fake `tutor app` exits with."""
    app, home, bin_ = tmp_path / "Gia sư Toán", tmp_path / "home", tmp_path / "bin"
    for d in (app, home / ".local" / "bin", bin_):
        d.mkdir(parents=True)
    shutil.copy(LAUNCHER, app / LAUNCHER.name)
    calls, uv = tmp_path / "calls.txt", f'echo "$PWD|$TUTOR_DATA|$*" >> "{tmp_path / "calls.txt"}"\nexit {uv_exit}\n'
    fake(tmp_path / "uv-installed", uv)
    # the installer puts uv in ~/.local/bin, where the launcher looks next
    fake(bin_ / "curl", f'echo "curl $*" >> "{calls}"\ncp "{tmp_path / "uv-installed"}" "$HOME/.local/bin/uv"\n')
    if with_uv:
        fake(bin_ / "uv", uv)
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(home)}
    run = subprocess.run(  # stdin at EOF ends the error path's `read -r` at once
        ["bash", str(app / LAUNCHER.name)],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return calls, run.stdout


def test_runs_uv_in_app_folder_with_data_in_home(tmp_path):
    calls, _ = launch(tmp_path, with_uv=True)
    assert calls.read_text("utf-8").splitlines() == [  # no curl line: uv was found
        f"{tmp_path / 'Gia sư Toán'}|{tmp_path / 'home' / 'GiaSuToan'}|run --frozen --no-dev tutor app"
    ]


def test_installs_uv_when_missing(tmp_path):
    calls, _ = launch(tmp_path, with_uv=False)
    first, second = calls.read_text("utf-8").splitlines()
    assert first == f"curl -LsSf {UV_URL}"
    assert second.endswith("|run --frozen --no-dev tutor app")  # the freshly installed uv ran


def test_normal_exit_does_not_say_app_stopped(tmp_path):
    _, out = launch(tmp_path, with_uv=True, uv_exit=0)  # a second double-click opens the browser and exits 0
    assert "App đã dừng" not in out


def test_app_error_says_app_stopped(tmp_path):
    _, out = launch(tmp_path, with_uv=True, uv_exit=1)
    assert "App đã dừng vì lỗi ở trên." in out


def test_launcher_is_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", LAUNCHER.name], cwd=REPO, capture_output=True, text=True, check=True)
    assert out.stdout.startswith("100755")
