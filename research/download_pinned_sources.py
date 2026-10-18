"""Download public price-only research inputs pinned to specific Git commits.

No bundled market datasets and no broker credentials. The user must review
the data provider's terms before deciding to use a feed in another context.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from leek.price_proxy import git_blob_sha, ProxyBlocked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default="research/pinned_price_sources.json")
    ap.add_argument("--dest", required=True)
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    dest = Path(args.dest)
    if not dest.is_dir():
        ap.error("destination directory must already exist")
    for name, entry in manifest.items():
        repo = entry["repository"]
        if len(repo.split("/")) != 2 or not all(p.replace("-", "").replace("_", "").isalnum() for p in repo.split("/")):
            raise ProxyBlocked("invalid provider name")
        commit = entry["commit"]
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ProxyBlocked("unfrozen source commit")
        path = quote(entry["path"], safe="/")
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
        with urlopen(url, timeout=30) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ProxyBlocked("input too large")
        sha = git_blob_sha(raw)
        if sha != entry["blob_sha"]:
            raise ProxyBlocked(f"{name}: provider SHA mismatch")
        output = dest / f"{name}.csv"
        if output.exists():
            raise ProxyBlocked("refusing existing dataset output")
        output.write_bytes(raw)
        print(f"{name}: git-blob-sha={sha} bytes={len(raw)}")


if __name__ == "__main__":
    main()
