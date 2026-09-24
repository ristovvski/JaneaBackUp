"""Auditor's own raw-API helper. READ-ONLY: GET only, hard-fails on non-GET."""
import os, json, time, urllib.parse, urllib.request, ssl, sys

SL = os.environ["SMARTLEAD_API_KEY"]
PD = os.environ["PIPEDRIVE_API_TOKEN"]
N8N = os.environ["N8N_BASE_URL"].rstrip("/")
N8NK = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
# 2026-09-24: the pinned bundle (win_ca_bundle.pem, generated 2026-08-07) stopped verifying ANY of
# the three hosts - n8n, Pipedrive and Smartlead all raised CERTIFICATE_VERIFY_FAILED with it while
# all three verify cleanly against the system trust store. A stale pinned bundle is not a safer
# choice than the OS store, it is simply a broken one, so fall back rather than skip verification.
# Verification is never disabled here; the fallback context still validates the chain.
CTX = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else ssl.create_default_context()
_CTX_SYSTEM = ssl.create_default_context()
_ca_warned = [False]
_use_system = [False]


def _ctx():
    return _CTX_SYSTEM if _use_system[0] else CTX

UA = {"User-Agent": "janea-auditor/1.0", "Accept": "application/json"}

def _red(s):
    s = str(s)
    for sec in (SL, PD, N8NK):
        if sec:
            s = s.replace(sec, "<REDACTED>")
    return s

class HttpErr(Exception):
    def __init__(self, code, body, url):
        self.code, self.body, self.url = code, _red(body), _red(url)
        super().__init__(f"HTTP {code} {self.url[:140]} :: {self.body[:300]}")

def _get(url, headers=None, tries=4):
    last = None
    for i in range(tries):
        h = dict(UA); h.update(headers or {})
        req = urllib.request.Request(url, method="GET", headers=h)
        try:
            with urllib.request.urlopen(req, context=_ctx(), timeout=90) as r:
                return json.loads(r.read().decode("utf-8", "replace") or "null")
        except urllib.error.URLError as e:
            # urllib WRAPS ssl.SSLCertVerificationError in URLError, so catching the ssl class
            # directly never fires - the first version of this fallback was dead code.
            reason = getattr(e, "reason", None)
            is_cert = isinstance(reason, ssl.SSLCertVerificationError) or \
                "CERTIFICATE_VERIFY_FAILED" in str(reason)
            if is_cert and not _use_system[0]:
                _use_system[0] = True
                if not _ca_warned[0]:
                    _ca_warned[0] = True
                    sys.stderr.write("[aud] pinned CA bundle failed verification; falling back to "
                                     "the system trust store (chain still verified)\n")
                continue
            last = e
            time.sleep(2 + 3 * i)
            continue
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504):
                last = HttpErr(e.code, body, url); time.sleep(2 + 3 * i); continue
            raise HttpErr(e.code, body, url)
        except Exception as e:
            last = e; time.sleep(2 + 3 * i)
    raise last

def sl(path, **q):
    q["api_key"] = SL
    return _get(f"https://server.smartlead.ai/api/v1{path}?{urllib.parse.urlencode(q)}")

def pd(path, **q):
    # v1 or v2 depending on path prefix
    base = "https://api.pipedrive.com"
    return _get(f"{base}{path}?{urllib.parse.urlencode(q)}",
                headers={"x-api-token": PD, "Accept": "application/json"})

def n8n(path, **q):
    u = f"{N8N}/api/v1{path}"
    if q: u += "?" + urllib.parse.urlencode(q)
    return _get(u, headers={"X-N8N-API-KEY": N8NK, "Accept": "application/json"})

def jdump(o, f):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1, default=str)
    print(f"[wrote] {f} ({os.path.getsize(p)}B)")

def jload(f):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)
