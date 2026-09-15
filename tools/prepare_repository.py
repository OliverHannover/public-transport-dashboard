"""Set real publication metadata once a GitHub repository has been chosen."""

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="GitHub OWNER/REPOSITORY")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Expected OWNER/REPOSITORY")
    owner = args.repository.split("/")[0]
    url = "https://github.com/" + args.repository
    path = Path(__file__).resolve().parents[1] / "custom_components/public_transport_dashboard/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(documentation=url + "#readme", issue_tracker=url + "/issues", codeowners=["@" + owner])
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Publication metadata set to " + url + ". No upload performed.")


if __name__ == "__main__":
    main()
