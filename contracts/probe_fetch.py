# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import hashlib
import json


class RainHedgeProbe(gl.Contract):
    """One-shot diagnostic: store exactly what gl.nondet.web.get returns
    for the pinned URL — status, byte length, sha256, head/tail text —
    so a digest mismatch can be attributed (transfer encoding, UA-specific
    body, rate-limit page, or canonicalization)."""
    probe: str

    def __init__(self):
        self.probe = "{}"

    @gl.public.view
    def get_probe(self) -> str:
        return self.probe

    @gl.public.write
    def fetch(self, url: str) -> None:
        out = {"url": url}
        try:
            response = gl.nondet.web.get(url)
            status = getattr(response, "status", None)
            body = getattr(response, "body", None)
            out["status"] = str(status)
            if isinstance(body, str):
                out["type"] = "str"
                raw = body.encode("utf-8", "surrogatepass")
            else:
                out["type"] = "bytes"
                raw = bytes(body)
            out["len"] = len(raw)
            out["sha256"] = hashlib.sha256(raw).hexdigest()
            out["head"] = raw[:220].decode("utf-8", "replace")
            out["tail"] = raw[-120:].decode("utf-8", "replace")
        except Exception as err:
            out["error"] = str(err)[:300]
        self.probe = json.dumps(out, sort_keys=True)
