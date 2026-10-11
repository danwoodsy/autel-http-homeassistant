"""Build a deterministic manual-install ZIP with the /config directory layout."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    component = root / "custom_components" / "autel_http"
    manifest = json.loads((component / "manifest.json").read_text())
    if manifest["domain"] != "autel_http":
        raise ValueError("Unexpected integration domain")
    files = sorted(
        path for path in component.rglob("*") if path.suffix in {".py", ".json"}
    )
    destination = root / "dist" / "autel_http.zip"
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            name = path.relative_to(root).as_posix()
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        license_info = ZipInfo(
            "custom_components/autel_http/LICENSE.txt",
            date_time=(2026, 1, 1, 0, 0, 0),
        )
        license_info.compress_type = ZIP_DEFLATED
        license_info.external_attr = 0o100644 << 16
        archive.writestr(license_info, (root / "LICENSE").read_bytes())
    print(f"Built {destination} ({manifest['version']}, {len(files) + 1} files)")


if __name__ == "__main__":
    main()
