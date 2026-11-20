"""Step 2: fetch the small datasets the forest module needs and verify them.

Downloads (only these, as approved in the plan):
  * geoBoundaries PAK ADM1 + ADM2 GeoJSON (public domain)
  * DISFOR samples/labels/pixel_data parquet + classes.json (EUPL-1.2)
  * LoDIA reforestation parquet: ONLY the `iso3` column via HTTP range reads

Run:  .venv\\Scripts\\python scripts\\download_data.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import PROCESSED_DIR, RAW_DIR  # noqa: E402

UA = {"User-Agent": "kp-geoshield-research/0.1"}

GEOBOUNDARIES = {
    "ADM1": "https://www.geoboundaries.org/api/current/gbOpen/PAK/ADM1/",
    "ADM2": "https://www.geoboundaries.org/api/current/gbOpen/PAK/ADM2/",
}
DISFOR_BASE = "https://huggingface.co/datasets/JR-DIGITAL/DISFOR/resolve/main/"
DISFOR_FILES = ["classes.json", "samples.parquet", "labels.parquet", "pixel_data.parquet"]
LODIA_URL = "https://dataverse.harvard.edu/api/access/datafile/12556067"


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached  {dest.name} ({dest.stat().st_size:,} B)")
        return dest
    with requests.get(url, headers=UA, stream=True, timeout=120, allow_redirects=True) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.replace(dest)
    print(f"  fetched {dest.name} ({dest.stat().st_size:,} B)")
    return dest


def get_boundaries() -> None:
    print("[geoBoundaries]")
    for level, api in GEOBOUNDARIES.items():
        meta = requests.get(api, headers=UA, timeout=60).json()
        fetch(meta["gjDownloadURL"], RAW_DIR / f"geoBoundaries-PAK-{level}.geojson")


def get_disfor() -> None:
    print("[DISFOR]")
    d = RAW_DIR / "disfor"
    d.mkdir(exist_ok=True)
    for name in DISFOR_FILES:
        fetch(DISFOR_BASE + name + "?download=true", d / name)


class HTTPRangeFile(io.RawIOBase):
    """Minimal seekable file over HTTP range requests (for reading parquet footers/columns)."""

    def __init__(self, url: str):
        r = requests.get(url, headers={**UA, "Range": "bytes=0-0"}, timeout=60, allow_redirects=True)
        r.raise_for_status()
        self.url = r.url  # resolved (signed S3) URL
        self.size = int(r.headers["Content-Range"].split("/")[-1])
        self.pos = 0
        self.bytes_read = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        r = requests.get(self.url, headers={**UA, "Range": f"bytes={self.pos}-{end}"}, timeout=120)
        r.raise_for_status()
        data = r.content
        self.pos += len(data)
        self.bytes_read += len(data)
        return data

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def check_lodia_pakistan() -> None:
    print("[LoDIA iso3 check]")
    import pyarrow.parquet as pq

    f = HTTPRangeFile(LODIA_URL)
    pf = pq.ParquetFile(f)
    cols = pf.schema_arrow.names
    print(f"  file size {f.size:,} B, rows {pf.metadata.num_rows:,}, columns {len(cols)}")
    print(f"  columns: {cols}")
    key = "iso3" if "iso3" in cols else next((c for c in cols if c.lower() in {"iso3", "country"}), None)
    if key is None:
        print("  !! no iso3/country column found — cannot check Pakistan")
        return
    iso = pf.read(columns=[key]).column(key).to_pandas()
    counts = iso.value_counts()
    pak = int(counts.get("PAK", 0) + counts.get("Pakistan", 0))
    print(f"  read {f.bytes_read:,} B of {f.size:,} B (column '{key}' only)")
    print(f"  PAK rows: {pak:,}   (countries present: {counts.size})")
    print("  top 10:", counts.head(10).to_dict())
    (PROCESSED_DIR / "lodia_country_counts.json").write_text(json.dumps(counts.to_dict(), indent=1))


if __name__ == "__main__":
    get_boundaries()
    get_disfor()
    check_lodia_pakistan()
