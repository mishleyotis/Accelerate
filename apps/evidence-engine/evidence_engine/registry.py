"""Domain -> source type -> tier HINT, from the committed registry.

WHY. The card's `item.tier` is produced from the SOURCE's identity (host,
path shape, the name a scan gives itself), never from what a producer
types; the connector refuses a tier the source cannot carry
(`apps/mcp/dma_mcp/source_rules.py`) and the research ledger refuses T1 on
the entity's own domain. So the registry classifies first, and the card
carries the rule as `tier_basis` (CARD-CONTRACT.md §2 `tier`, §3
`source_type_hint` / `ladder_rung`; DISCOVERY.md §1 "fsi_domains.yaml",
§6 "never T1 on the own domain").

THE RULE, in the order it is applied (first match wins):

  1. entity's own domain (host equals or is a subdomain of an entity domain)
       -> entity_owned, T2 for a disclosure path shape, else T5; NEVER T1;
          ladder_rung entity_site.
  2. filing authority (sec.gov/Archives, efts/data.sec.gov, sedarplus.ca,
     companieshouse.gov.uk)             -> filing, T1, rung filings.
  3. regulator (suffix or explicit host) -> regulator, T1, rung regulator —
     except a press / newsroom path     -> regulator, T2 "regulator press release".
  4. a scan-producer token in the source name or URL
                                        -> other, T1 "machine technographic scan".
  5. a vendor-collateral path shape on any other host
                                        -> vendor, T5 (ceiling L2, corroboration required).
  6. a registered third-party host (trade press, news, academic, job board,
     review site)                       -> that type, T3.
  7. anything else                      -> other, T3 "unregistered third-party domain".

ONE RECORDED TENSION, not resolved silently: the methodology makes the
entity's own press release T2, but `source_rules.tier_violation` applies
the vendor-collateral path shapes (`/press-releases/`, `/newsroom/`) to
every non-regulator host — the own domain included — and refuses anything
above T5 there. A card the connector refuses is useless, so an own-domain
path that matches BOTH a disclosure shape and a collateral shape is hinted
T5 with a `tier_basis` that names the cap and the methodology's T2; the
producer sees the conflict in the card instead of a refusal at submit.

Pure: the YAML is read once, no network, no model.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .types import EntityRef

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "registry" / "fsi_domains.yaml"

#: What the methodology says about a vendor's own page — stated in the
#: basis so a producer does not have to look it up (source_rules.VENDOR_*).
VENDOR_CEILING = "L2"


def registry_path() -> Path:
    override = os.environ.get("EE_REGISTRY")
    return Path(override) if override else _DEFAULT_PATH


@lru_cache(maxsize=4)
def _load(path_str: str) -> dict:
    with open(path_str, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    compiled = {
        "tiers": dict(data.get("tiers") or {}),
        "reg_suffixes": tuple(data.get("regulators", {}).get("suffixes") or ()),
        "reg_hosts": frozenset((data.get("regulators", {}).get("hosts") or [])
                               + (data.get("regulators", {}).get("explicit_hosts") or [])),
        "reg_press": tuple(data.get("regulators", {}).get("press_paths") or ()),
        "filings": tuple((e["host"], e.get("path_prefix") or "")
                         for e in data.get("filings", {}).get("hosts") or ()),
        "disclosure": tuple(data.get("entity_owned", {}).get("disclosure_paths") or ()),
        "wires": frozenset(data.get("press_release_wires") or ()),
        "vendor": tuple((re.compile(e["pattern"], re.I), e["what"])
                        for e in data.get("vendor_collateral_paths") or ()),
        "scan_producers": tuple(data.get("scan_producers") or ()),
        "scan_phrases": tuple(data.get("scan_phrases") or ()),
        "tables": {},
        "host_paths": [],
    }
    for stype in ("trade_press", "news", "academic", "job_board", "review_site"):
        section = data.get(stype) or {}
        for h in section.get("hosts") or ():
            compiled["tables"][h.lower()] = stype
        for hp in section.get("host_paths") or ():
            compiled["host_paths"].append((hp["host"].lower(), hp.get("path_prefix") or "", stype))
    compiled["raw"] = data
    return compiled


def load() -> dict:
    """The compiled registry (cached per path; EE_REGISTRY overrides)."""
    return _load(str(registry_path()))


def raw() -> dict:
    """The YAML as loaded, for the pin test."""
    return load()["raw"]


# ── URL pieces ─────────────────────────────────────────────────────────────

def host_of(url: str | None) -> str:
    """Lower-cased host without `www.`, port, path; '' when not a URL."""
    m = re.match(r"^[a-z][a-z0-9+.-]*://(?:www\.)?([^/:?#]+)", (url or "").strip(), flags=re.I)
    return (m.group(1) if m else "").lower().rstrip(".")


def path_of(url: str | None) -> str:
    try:
        p = re.sub(r"^[a-z][a-z0-9+.-]*://[^/]+", "", (url or "").strip(), flags=re.I)
    except (TypeError, ValueError):
        return "/"
    p = p.split("#", 1)[0].split("?", 1)[0]
    return p or "/"


def _under(host: str, known: str) -> bool:
    """`host` IS `known` or a subdomain of it — a suffix at a label boundary,
    never a substring (ncua.gov.example.test is not ncua.gov)."""
    known = known.lower().lstrip(".")
    return bool(host) and (host == known or host.endswith("." + known))


def _domain_host(d) -> str:
    """An entity domain as given ('example-fcu.test', 'www.example-fcu.test',
    'https://example-fcu.test/') -> bare host."""
    d = str(d or "").strip().lower()
    if "://" in d:
        return host_of(d)
    d = d.split("/", 1)[0]
    return d[4:] if d.startswith("www.") else d


#: Hosts the engine never fetches for a card: not evidence-grade (an
#: encyclopaedia is a pointer to sources, never a source), and measured
#: 2026-10-10 to answer 403 to the browser UA from Cloud origins — a wasted
#: slot every brief. A hit here refunds its fetch slot.
NEVER_FETCH_SUFFIXES = ("wikipedia.org", "wikimedia.org", "wiktionary.org")


def never_fetch(url: str | None) -> bool:
    host = host_of(url)
    return any(host == s or host.endswith("." + s) for s in NEVER_FETCH_SUFFIXES)


def is_own_host(url: str | None, entity: EntityRef | None) -> bool:
    """Host equals, or is a subdomain of, one of the entity's domains."""
    if entity is None:
        return False
    host = host_of(url)
    if not host:
        return False
    return any(_under(host, _domain_host(d)) for d in entity.domains or () if _domain_host(d))


def regulatory_publisher(url: str | None) -> bool:
    """Same rule as source_rules.regulatory_publisher: explicit host or a
    registrable suffix, at a label boundary."""
    host = host_of(url)
    if not host:
        return False
    reg = load()
    if any(_under(host, known) for known in reg["reg_hosts"]):
        return True
    return any(host == s.lstrip(".") or host.endswith(s) for s in reg["reg_suffixes"])


def is_wire(url_or_host: str | None) -> bool:
    host = host_of(url_or_host) if "://" in str(url_or_host or "") else str(url_or_host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(_under(host, w) for w in load()["wires"])


def vendor_collateral(url: str | None) -> str | None:
    """What kind of vendor collateral this path is, or None (regulators
    exempt, as in the connector)."""
    if not url or regulatory_publisher(url):
        return None
    path = path_of(url)
    for pattern, what in load()["vendor"]:
        if pattern.search(path):
            return what
    return None


def scan_source(source_name: str | None, url: str | None = None) -> str | None:
    """The scan this source describes, or None — matched on the name it
    gives itself and the URL together (a scan often has no page)."""
    hay = " ".join(x for x in (source_name, url) if x).lower()
    if not hay:
        return None
    reg = load()
    for phrase in reg["scan_phrases"]:
        if phrase in hay:
            return phrase
    for producer in reg["scan_producers"]:
        if producer in hay:
            return f"a {producer} scan"
    return None


def _filing(host: str, path: str) -> bool:
    for fhost, prefix in load()["filings"]:
        if _under(host, fhost) and (not prefix or path.lower().startswith(prefix.lower())):
            return True
    return False


def _regulator_press(path: str) -> bool:
    p = path.lower()
    return any(marker in p for marker in load()["reg_press"])


def _disclosure(path: str) -> bool:
    p = path.lower()
    return any(p.startswith(d) or ("/" + d.lstrip("/")) in p for d in load()["disclosure"])


def _table_type(host: str, path: str) -> str | None:
    reg = load()
    for thost, prefix, stype in reg["host_paths"]:
        if _under(host, thost) and path.lower().startswith(prefix.lower()):
            return stype
    # longest registered suffix wins (apps.apple.com before apple.com if both)
    best = None
    for thost, stype in reg["tables"].items():
        if _under(host, thost) and (best is None or len(thost) > len(best[0])):
            best = (thost, stype)
    return best[1] if best else None


_RUNG = {"regulator": "regulator", "filing": "filings", "entity_owned": "entity_site",
         "trade_press": "trade_press", "news": "news", "academic": "academic",
         "job_board": "careers", "review_site": "other", "vendor": "other", "other": "other"}


def classify(url: str | None, entity: EntityRef | None = None, *,
             source_name: str | None = None) -> dict:
    """-> {source_type, tier, tier_basis, ladder_rung, is_wire, is_vendor_collateral}
    for one URL, in the order the module docstring states."""
    reg = load()
    tiers = reg["tiers"]
    host = host_of(url)
    path = path_of(url)
    wire = is_wire(host)
    collateral = None if regulatory_publisher(url) else vendor_collateral(url)

    def out(stype, tier, basis, rung=None):
        return {"source_type": stype, "tier": tier, "tier_basis": basis,
                "ladder_rung": rung or _RUNG[stype], "is_wire": wire,
                "is_vendor_collateral": collateral is not None}

    # 1. the entity's own domain — never T1
    if is_own_host(url, entity):
        if _disclosure(path):
            if collateral:
                return out("entity_owned", tiers["vendor"],
                           f"the entity's own {collateral} — official disclosure (T2) in the "
                           f"methodology, capped at {tiers['vendor']} by the connector's "
                           f"vendor-collateral path rule (source_rules.tier_violation); "
                           f"never T1 on the own domain")
            return out("entity_owned", tiers["entity_owned_disclosure"],
                       f"the entity's own disclosure page on {host} (annual report / "
                       f"investor / press / governance): official disclosure, never T1")
        return out("entity_owned", tiers["entity_owned_other"],
                   f"the entity's own site {host} outside a disclosure path (product / "
                   f"about / careers): marketing, never T1")
    # 2. the filing authority's copy
    if host and _filing(host, path):
        return out("filing", tiers["filing"],
                   f"registry: {host} is a filing authority's copy ({tiers['filing']})")
    # 3. a regulator
    if host and regulatory_publisher(url):
        if _regulator_press(path):
            return out("regulator", tiers["regulator_press"],
                       f"regulator press release: {host} newsroom / press path is a "
                       f"disclosure ({tiers['regulator_press']}), not an examination record")
        return out("regulator", tiers["regulator"],
                   f"registry: {host} is a prudential regulator or government body "
                   f"({tiers['regulator']})")
    # 4. a machine technographic scan names itself
    scan = scan_source(source_name, url)
    if scan:
        return out("other", tiers["scan"],
                   f"machine technographic scan (contract.SCAN_TIER): {scan}", rung="other")
    # 5. vendor collateral by path shape, on any other host
    if collateral:
        return out("vendor", tiers["vendor"],
                   f"vendor collateral, ceiling {VENDOR_CEILING}, corroboration required: "
                   f"{collateral} on {host or 'an unknown host'}")
    # 6. a registered third party
    stype = _table_type(host, path) if host else None
    if stype:
        return out(stype, tiers[stype],
                   f"registry: {host} is {stype.replace('_', ' ')} ({tiers[stype]})")
    # 7. unknown
    return out("other", tiers["other"],
               f"unregistered third-party domain {host or '(no host)'} ({tiers['other']})")
