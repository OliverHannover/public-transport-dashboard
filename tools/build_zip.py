"""Package integration, card, documentation and tests; exclude local QA data."""

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
version = json.loads(
    (root / "custom_components/public_transport_dashboard/manifest.json").read_text(encoding="utf-8")
)["version"]
target = root / f"dist/public-transport-dashboard-{version}.zip"
target.parent.mkdir(exist_ok=True)
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for name in (
        "custom_components",
        "lovelace",
        "tests",
        "tools",
        ".github",
        "README.md",
        "CHANGELOG.md",
        "DOC",
        "reports",
        "LICENSE",
        "hacs.json",
        "pyproject.toml",
        ".gitignore",
    ):
        source = root / name
        files = source.rglob("*") if source.is_dir() else [source]
        for path in files:
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                archive.write(path, path.relative_to(root))
print(target)
