import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aight_api.main import app

target = Path(__file__).resolve().parents[1] / "docs/openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print("Exported docs/openapi.json from implemented models.")
