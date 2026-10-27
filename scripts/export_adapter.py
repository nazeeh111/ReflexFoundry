"""Package only the trained head and required reproducibility metadata for release."""

import json
import shutil
import tarfile
from pathlib import Path

from reflexfoundry.model import file_hash

root = Path(__file__).resolve().parents[1]
trained = root / "models/adapted-v1"
package = root / "models/adapter-v1"
for name in ("manifest.json", "rl_agent_config.json", "train_report.json"):
    shutil.copy2(trained / name, package / name)
manifest = json.loads((package / "manifest.json").read_text())
if file_hash(trained / "head.safetensors") != manifest["head_sha256"]:
    raise RuntimeError("head digest mismatch")
output = root / "dist/reflexfoundry-laya-head-v0.1.0.tar.gz"
output.parent.mkdir(exist_ok=True)
with tarfile.open(output, "w:gz") as archive:
    for name in ("manifest.json", "rl_agent_config.json", "train_report.json", "README.md"):
        archive.add(package / name, arcname=name)
    archive.add(trained / "head.safetensors", arcname="head.safetensors")
    for name in ("encoder", "tokenizer"):
        archive.add(trained / name, arcname=name)
    archive.add(root / "LICENSE", arcname="LICENSE")
    archive.add(root / "THIRD_PARTY_NOTICES.md", arcname="THIRD_PARTY_NOTICES.md")
print(output)
