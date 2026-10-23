"""Clone the verified repair; leave LIVE and all historical revisions untouched."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path("C:/live-captions")
BASE = ROOT / "logs/trad_lab/m5c2repair_20261022T020037Z/environment_repaired_ready/plan.json"
BASE_SHA = "21e9f77888844103adb7f9ecfbc962db4cd9ee173e488ee9140da4df770dc03c"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    copy = Path(data["copy"]).resolve()
    if not copy.is_relative_to(ROOT / "logs/trad_lab") or copy.name != "copy" or path.parent != copy.parent:
        raise ValueError("Isolated M5-D copy required")
    if data["phase"] != "M5-D" or data["backend_port"] != 18000 or data["trad_port"] != 18010 or data["lan_port"] != 3000:
        raise ValueError("M5-D policy changed")
    if data.get("default_mode") != "replay" or data.get("deepl_enabled") is not False or data.get("network_authorized") is not False:
        raise ValueError("Preparation must not inherit an earlier physical/provider authorization")
    if digest(BASE) != BASE_SHA:
        raise ValueError("Historical plan changed")
    old = json.loads(BASE.read_text(encoding="utf-8"))
    for name, sha in data["manifest"].items():
        target = (copy / name).resolve()
        if not target.is_relative_to(copy) or digest(target) != sha:
            raise ValueError("Frozen source changed: " + name)
    actual = {p.relative_to(copy).as_posix() for p in copy.rglob("*") if p.is_file()
              and not {"__pycache__", ".runtime"}.intersection(p.parts)}
    if actual != set(data["manifest"]):
        raise ValueError("Unmanifested source")
    # Three integration hooks/labels only. All other historical files stay exact.
    changed = {n for n in old["manifest"] if data["manifest"].get(n) != old["manifest"][n]}
    if changed != {"app/main.py", "app/templates/overlay.html", "app/templates/operator.html"}:
        raise ValueError("Unexpected changes to M5-C2")
    if data["profile"] != old["profile"]:
        raise ValueError("ASR profile changed")
    return data


def prepare(out):
    from trad_lab.m5c2r.prepare import verify as verify_base
    if digest(BASE) != BASE_SHA:
        raise ValueError("Unexpected base plan")
    old = verify_base(BASE)
    out = Path(out).resolve()
    if not out.is_relative_to(ROOT / "logs/trad_lab"):
        raise ValueError("Lab destination required")
    out.mkdir(parents=True, exist_ok=False)
    copy = out / "copy"
    for name, sha in old["manifest"].items():
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(old["copy"]) / name, target)
        if digest(target) != sha:
            raise ValueError("Copy mismatch")
    for source in (ROOT / "trad_lab/m5d").glob("*"):
        if source.is_file():
            target = copy / "trad_lab/m5d" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    target = copy / "app/main.py"
    text = target.read_text(encoding="utf-8")
    text = text.replace("from trad_lab.m5c2r.runtime import ", "from trad_lab.m5d.runtime import ")
    text = text.replace("from trad_lab.m5c2b.runtime import provider_from_config", "from trad_lab.m5d.runtime import provider_from_config")
    target.write_text(text, encoding="utf-8")
    target = copy / "app/templates/overlay.html"
    text = target.read_text(encoding="utf-8").replace("M5-C2 B · ASR REAL · DEEPL REAL EN→ES · ENSAYO", "M5-D · OVERLAY LAN · ENSAYO")
    target.write_text(text, encoding="utf-8")
    target = copy / "app/templates/operator.html"
    target.write_text(target.read_text(encoding="utf-8").replace("</body>", '<script src="/static/m5d_replay.js"></script></body>'), encoding="utf-8")
    shutil.copyfile(ROOT / "trad_lab/m5d/replay.js", copy / "app/static/m5d_replay.js")
    manifest = {p.relative_to(copy).as_posix(): digest(p) for p in copy.rglob("*") if p.is_file()}
    data = {**old, "phase": "M5-D", "copy": str(copy), "manifest": manifest,
            "base_plan": str(BASE), "base_plan_sha256": BASE_SHA, "lan_port": 3000,
            "services_started": False, "default_mode": "replay", "network_authorized": False,
            "deepl_enabled": False, "physical_enabled": False, "B_authorized": False,
            "credential_storage": "Replay never reads .env; live mode requires separate explicit authorization and uses the original local factory",
            "human_authorization": "Preparation and offline tests only; TCP, firewall and physical LAN test require new approval"}
    (out / "plan.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    verify(out / "plan.json")
    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    print(json.dumps({"files": len(prepare(args.out)["manifest"])}))
