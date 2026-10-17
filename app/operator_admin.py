"""Explicit local administrative takeover after the controller lease is lost."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def recover(base="http://localhost:8010"):
    url=urlsplit(base)
    if url.scheme not in {"http","https"} or url.hostname not in {"localhost","127.0.0.1","::1"} or url.path:
        raise ValueError("Only a local FastAPI origin is allowed")
    def call(path,data=None,token=None):
        headers={"Origin":base}
        if token:headers["X-Operator-Token"]=token
        body=None if data is None else json.dumps(data).encode()
        if body is not None:headers["Content-Type"]="application/json"
        with urlopen(Request(base+path,data=body,headers=headers),timeout=5) as response:return json.load(response)
    boot=call("/api/operator/bootstrap");token=boot["control_token"]
    status=call("/api/operator/status",token=token)
    path=Path(__file__).resolve().parents[1]/".runtime"/f"operator-{int(boot['server_pid'])}.json"
    # Locate the process-specific file; only the UI performs an explicit takeover.
    print("Enter the recovery code from this local file in Operator's recovery field:")
    print(path)
    print("Session:",status["session_id"],"owner age:",status["reliability"]["owner_age_seconds"])
    return path  # Never print credential contents or perform a hidden takeover.


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--url",default="http://localhost:8010")
    recover(parser.parse_args().url)
