"""Build the opt-in resume backend from a pinned, verified upstream archive."""

import argparse
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

URL = "https://codeload.github.com/qjfoidnh/BaiduPCS-Go/tar.gz/refs/tags/v4.0.2"
SHA256 = "12904ec8daee445b357f59d604103108a324f5b1c60cb0d8324f5df216683553"
COMMIT = "225bdd3b6cb298601c4d5ef7104c3e08cd1d692d"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    args = parser.parse_args()
    if not shutil.which("go") or not shutil.which("patch"):
        parser.error("Go 1.23+ and patch are required")
    base = args.build_dir.expanduser().resolve()
    source = base / "BaiduPCS-Go-4.0.2"
    if source.exists():
        parser.error("Build source already exists; choose a new build directory to avoid overwriting changes")
    base.mkdir(parents=True, exist_ok=True)
    archive = base / "upstream-v4.0.2.tar.gz"
    data = archive.read_bytes() if archive.exists() else urllib.request.urlopen(URL, timeout=60).read(8 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit("Upstream archive integrity check failed")
    if not archive.exists():
        archive.write_bytes(data)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as bundle:
        for entry in bundle.getmembers():
            target = (base / entry.name).resolve()
            if base not in target.parents or entry.issym() or entry.islnk() or not (entry.isfile() or entry.isdir()):
                raise SystemExit("Unexpected archive member")
        bundle.extractall(base)
    patch = Path(__file__).resolve().parents[1] / "patches/baidupcs-go-v4.0.2-resume.patch"
    subprocess.run(["patch", "-p1", "--batch", "-i", str(patch)], cwd=source, check=True)
    subprocess.run(["go", "test", "./requester/uploader", "-run", "TestAigoodbaiduyun", "-count=1"], cwd=source, check=True)
    binary = base / "BaiduPCS-Go-resume"
    subprocess.run(["go", "build", "-trimpath", "-ldflags", "-s -w -X main.Version=v4.0.2-aigoodbaiduyun-resume1", "-o", str(binary), "."], cwd=source, check=True)
    print(f"Verified upstream commit: {COMMIT}")
    print(f"AIGOODBAIDUYUN_RESUME_BIN={binary}")
    print(f"Binary SHA-256: {hashlib.sha256(binary.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
