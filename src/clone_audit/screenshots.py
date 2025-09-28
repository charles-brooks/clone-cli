"""Homepage screenshot utilities."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class ScreenshotError(RuntimeError):
    """Raised when an external screenshot attempt fails."""


_CHROME_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)


def capture_homepage(
    url: str,
    timeout: float = 20.0,
    width: int = 1280,
    height: int = 720,
    delay: float = 2.0,
    method: str = "auto",
    user_agent: str | None = None,
) -> bytes:
    """Capture a screenshot of the given URL using available tooling.

    Prefers headless Chrome/Chromium for modern rendering. Falls back to
    wkhtmltoimage if Chrome is unavailable or fails.
    """

    methods = [method] if method != "auto" else ["chrome", "wkhtml"]
    last_error: Optional[Exception] = None

    for tool in methods:
        if tool == "chrome":
            binary = _find_chrome()
            if not binary:
                last_error = ScreenshotError("Headless Chrome/Chromium not found")
                continue
            try:
                return _capture_with_chrome(binary, url, timeout, width, height, delay, user_agent)
            except ScreenshotError as exc:
                last_error = exc
                if method != "auto":
                    break
                continue
        if tool == "wkhtml":
            binary = shutil.which("wkhtmltoimage")
            if not binary:
                last_error = ScreenshotError("wkhtmltoimage binary not found on PATH")
                continue
            try:
                return _capture_with_wkhtml(binary, url, timeout, width, delay, user_agent)
            except ScreenshotError as exc:
                last_error = exc
                if method != "auto":
                    break
                continue

    if last_error:
        raise ScreenshotError(str(last_error))
    raise ScreenshotError("No screenshot tool available")


def _capture_with_chrome(
    binary: str,
    url: str,
    timeout: float,
    width: int,
    height: int,
    delay: float,
    user_agent: str | None,
) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    delay_ms = max(int(delay * 1000), 0)
    ua = user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    cmd = [
        binary,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--disable-dev-shm-usage",
        "--disable-features=AutomationControlled",
        "--run-all-compositor-stages-before-draw",
        f"--user-agent={ua}",
        f"--window-size={width},{height}",
        f"--screenshot={tmp_path}",
    ]
    if delay_ms > 0:
        cmd.append(f"--virtual-time-budget={delay_ms + 5000}")
    cmd.append(url)

    try:
        subprocess.run(cmd, check=True, timeout=timeout)
        data = tmp_path.read_bytes()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ScreenshotError(f"Chrome screenshot failed: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not data:
        raise ScreenshotError("Chrome produced an empty screenshot")
    return data


def _capture_with_wkhtml(
    binary: str,
    url: str,
    timeout: float,
    width: int,
    delay: float,
    user_agent: str | None,
) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    delay_ms = max(int(delay * 1000), 0)
    ua = user_agent or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    cmd = [
        binary,
        "--quiet",
        "--width",
        str(width),
        "--quality",
        "90",
        "--javascript-delay",
        str(delay_ms),
        "--custom-header",
        "User-Agent",
        ua,
        "--load-error-handling",
        "ignore",
        "--load-media-error-handling",
        "ignore",
        "--no-stop-slow-scripts",
        url,
        str(tmp_path),
    ]

    try:
        subprocess.run(cmd, check=True, timeout=timeout)
        data = tmp_path.read_bytes()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ScreenshotError(f"wkhtmltoimage failed: {exc}") from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not data:
        raise ScreenshotError("wkhtmltoimage produced an empty output file")
    return data


def _find_chrome() -> Optional[str]:
    for candidate in _CHROME_BINARIES:
        path = shutil.which(candidate)
        if path:
            return path
    return None


__all__ = ["capture_homepage", "ScreenshotError"]
