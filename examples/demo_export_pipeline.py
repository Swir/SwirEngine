from __future__ import annotations

import json
import tempfile
from pathlib import Path

from swirengine import ExportTarget, PackagingProfile, ProjectExporter


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="swirengine-export-demo-") as temp:
        root = Path(temp)
        project = root / "project"
        project.mkdir()
        (project / "assets").mkdir()
        (project / "assets" / "hello.txt").write_text("hello export\n", encoding="utf-8")
        (project / "main.py").write_text("print('hello from packaged game')\n", encoding="utf-8")

        profile = PackagingProfile(
            name="export-demo",
            target=ExportTarget.LINUX,
            onefile=True,
        )
        result = ProjectExporter(project).export(profile, root / "staged")
        manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

        print("staged:", result.output_dir)
        print("native spec:", result.native_spec)
        print("files:", manifest["files"])
        print("sha256:", manifest["sha256"])
        print("build command:", " ".join(result.native_build_command or ()))
        print("Use build_native() on a host matching the profile target to create the executable.")


if __name__ == "__main__":
    main()
