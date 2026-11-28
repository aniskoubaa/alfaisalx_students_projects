"""Short texts and timing shown to the user: route words, update notice, reconnect delays and
the redaction of secrets in diagnostics.
"""


from .config import *  # bundle: skip
from .helpers import *  # bundle: skip
from .network_parse import *  # bundle: skip


ROUTE_WORDS = {'cable': 'Ethernet cable', 'wifi': 'Wi-Fi', 'hotspot': 'robot hotspot', 'custom': 'typed address'}


def route_words(via):
    """How the robot is reached, in words for people (the internal names are cable, wifi, hotspot, custom)."""
    return ROUTE_WORDS.get(via, via) if via else via


# ---- v1.3: update notice, reconnect timing, diagnostics redaction ----
def version_tuple(v):
    """'1.3' -> (1, 3); None when it is not a plain dotted number."""
    v = str(v or '').strip()
    return tuple(int(x) for x in v.split('.')) if VERSION_RE.match(v) else None


def version_newer(latest, current):
    """Numeric compare (1.10 > 1.9, 1.3 == 1.3.0). False when either side is not understood."""
    a, b = version_tuple(latest), version_tuple(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def parse_update_info(raw):
    """version.json text/bytes -> {'version','page','notes'} or None. The page must be on the lab's GitHub repo,
    else the default page is used; notes are cut to 300 plain characters."""
    try:
        d = json.loads(raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw)
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get('version'), str) or not VERSION_RE.match(d['version'].strip()):
        return None
    page = d.get('page')
    if not (isinstance(page, str) and page.startswith(UPDATE_PAGE_PREFIX) and page.isprintable() and ' ' not in page):
        page = DEFAULT_UPDATE_PAGE
    notes = d.get('notes')
    notes = ''.join(c if c.isprintable() else ' ' for c in notes).strip()[:300] if isinstance(notes, str) else ''
    return {'version': d['version'].strip(), 'page': page, 'notes': notes}


def reconnect_delay(attempt, delays=RECONNECT_DELAYS):
    """Seconds to wait before attempt number `attempt` (1, 2, 3, ...): 2, 4, 8, 15, 30, 30, ..."""
    return delays[min(max(attempt, 1) - 1, len(delays) - 1)]


def gave_up_text(seconds):
    if seconds >= 60 and seconds % 60 == 0:
        return 'gave up reconnecting after %d minutes' % (seconds // 60)
    return 'gave up reconnecting after %g seconds' % seconds


REDACTED = '[redacted]'
_SECRET_WORDS = r'(?:psk|passwords?|passwd|passphrase|wifi[_ -]?pass(?:word)?|secret)'
_RE_PEM = re.compile(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)', re.S)
_RE_JSON_SECRET = re.compile(r'("?' + _SECRET_WORDS + r'"?\s*[:=]\s*)"(?:[^"\x5c]|\x5c.)*"', re.I)
_RE_SECRET = re.compile(r'(\b' + _SECRET_WORDS + r'\b"?\s*[:=])(?!\s*"?\[redacted)(\s*)[^\r\n]+', re.I)
_RE_TOKEN = re.compile(r'(\btoken\b"?\s*[:=]\s*)"?[^\s"&,;]+"?', re.I)


def redact(text, secrets=()):
    """Remove what must never leave this computer in a diagnostics text: the session token (also as token=...),
    psk/password/passphrase values and PEM private key blocks. `secrets` are exact strings to blank out too."""
    t = text or ''
    for s in secrets:
        if s and len(s) >= 4:
            t = t.replace(s, REDACTED)
    t = _RE_PEM.sub('[redacted private key]', t)
    t = _RE_JSON_SECRET.sub(lambda m: m.group(1) + '"' + REDACTED + '"', t)
    t = _RE_SECRET.sub(lambda m: m.group(1) + m.group(2) + REDACTED, t)
    t = _RE_TOKEN.sub(lambda m: m.group(1) + REDACTED, t)
    return t
