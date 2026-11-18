"""Download full Goodbooks and enriched metadata without replacing existing data.

Run from the repository root: python -m ml.download_goodbooks
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen


SOURCES = {
    "ratings.csv": "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master/ratings.csv",
    "books.csv": "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master/books.csv",
    "books_enriched.csv": "https://raw.githubusercontent.com/malcolmosh/goodbooks-10k-extended/master/books_enriched.csv",
    "LICENSE.goodbooks.txt": "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master/LICENSE",
    "LICENSE.extended.txt": "https://raw.githubusercontent.com/malcolmosh/goodbooks-10k-extended/master/LICENSE",
}


def download(destination: Path) -> None:
    expected = json.loads(Path(__file__).with_name("goodbooks_sources.json").read_text(encoding="utf-8"))["files"]
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "sources.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files": {}}
    for name, url in SOURCES.items():
        target = destination / name
        if target.exists():
            entry = manifest["files"].get(name)
            with target.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if not entry or digest != entry["sha256"] or digest != expected[name]["sha256"]:
                raise ValueError(f"Existing file has no matching manifest: {target}; choose another directory")
            print(f"Verified cached {name}", flush=True)
            continue
        print(f"Downloading {name}", flush=True)
        request = Request(url, headers={"User-Agent": "BookShelf-lab3-dataset-loader"})
        digest = hashlib.sha256()
        temporary = None
        try:
            with urlopen(request, timeout=60) as response, tempfile.NamedTemporaryFile(dir=destination, suffix=".part", delete=False) as output:
                temporary = Path(output.name)
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
            if target.exists():
                raise FileExistsError(target)
            if digest.hexdigest() != expected[name]["sha256"]:
                raise ValueError(f"Upstream contents changed for {name}; review the source manifest before updating")
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        manifest["files"][name] = {"url": url, "sha256": digest.hexdigest(), "bytes": target.stat().st_size,
                                    "downloaded_at": datetime.now(timezone.utc).isoformat()}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {name}: {target.stat().st_size:,} bytes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("data/GoodBooksFull"))
    args = parser.parse_args()
    download(args.destination)


if __name__ == "__main__":
    main()
