"""Zennify tech-taxonomy classifier — catalogue + deny-lists + fuzzy alias.

Why: the tech-stack audit counted ~224 noise rows shipped verbatim from
technographic CSVs — programming languages, operating systems, prose
fragments, even a person's name — because parsers persisted cells
as-is. This module is the single classification gate: every candidate
technology string resolves to one of

    platform            a Zennify-catalogue vendor/product (canonical form)
    engineering_signal  languages/frameworks/OS — evidence the entity
                        builds software, but NOT a stack row
    noise               generic labels ("Various", "CRM"), prose, dates
    unknown_vendor      a plausible product we don't have in the
                        catalogue yet (kept for review, never dropped)

The curated seed extends the five-family map in
``app/services/parsers/tech_linker.py`` (_TECH) with the full FSI vendor
catalogue (cores, digital banking, clouds, identity, CCaaS, data/BI,
security, RPA, martech). ``layer_hint`` follows tech_linker's layers:
foundation | application | platform | intelligence. Alias/fuzzy matching
uses rapidfuzz ratio ≥90 so "Salesforce.com" / light misspellings still
resolve; :func:`split_cell` breaks multi-vendor cells at parse time.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz, process

# canonical → (vendor, layer_hint). Layers per tech_linker._TECH:
# foundation (cores), application (business apps), platform
# (infra/integration/identity/security), intelligence (data/analytics).
_CATALOGUE: dict[str, tuple[str, str]] = {
    # Salesforce family
    "Salesforce": ("Salesforce", "application"),
    "Sales Cloud": ("Salesforce", "application"),
    "Service Cloud": ("Salesforce", "application"),
    "Marketing Cloud": ("Salesforce", "application"),
    "Financial Services Cloud": ("Salesforce", "application"),
    "Experience Cloud": ("Salesforce", "application"),
    "Data Cloud": ("Salesforce", "intelligence"),
    "Agentforce": ("Salesforce", "application"),
    "Einstein": ("Salesforce", "intelligence"),
    "Pardot": ("Salesforce", "application"),
    "MuleSoft": ("Salesforce", "platform"),
    "Tableau": ("Salesforce", "intelligence"),
    "Slack": ("Salesforce", "application"),
    # Data platforms
    "Databricks": ("Databricks", "intelligence"),
    "Snowflake": ("Snowflake", "intelligence"),
    "dbt": ("dbt Labs", "intelligence"),
    # Twilio family
    "Twilio": ("Twilio", "application"),
    "Segment": ("Twilio", "application"),
    "SendGrid": ("Twilio", "application"),
    # Lending / banking applications
    "nCino": ("nCino", "application"),
    "SimpleNexus": ("nCino", "application"),
    "MeridianLink": ("MeridianLink", "application"),
    "Encompass": ("ICE Mortgage Technology", "application"),
    "Blend": ("Blend", "application"),
    # Cores
    "FIS": ("FIS", "foundation"),
    "Fiserv": ("Fiserv", "foundation"),
    "Jack Henry": ("Jack Henry", "foundation"),
    "Temenos": ("Temenos", "foundation"),
    "Finastra": ("Finastra", "foundation"),
    "Corelation KeyStone": ("Corelation", "foundation"),
    "Symitar": ("Jack Henry", "foundation"),
    "Episys": ("Jack Henry", "foundation"),
    "Fiserv DNA": ("Fiserv", "foundation"),
    "Fiserv Premier": ("Fiserv", "foundation"),
    "FIS Horizon": ("FIS", "foundation"),
    # Digital banking
    "Q2": ("Q2", "application"),
    "Alkami": ("Alkami", "application"),
    "Backbase": ("Backbase", "application"),
    "Lumin Digital": ("Lumin Digital", "application"),
    "Banno": ("Jack Henry", "application"),
    # Microsoft
    "Microsoft Azure": ("Microsoft", "platform"),
    "Power BI": ("Microsoft", "intelligence"),
    "Dynamics 365": ("Microsoft", "application"),
    "Microsoft 365": ("Microsoft", "application"),
    "Microsoft Teams": ("Microsoft", "application"),
    "Microsoft Entra ID": ("Microsoft", "platform"),
    # Clouds
    "AWS": ("Amazon", "platform"),
    "Google Cloud": ("Google", "platform"),
    # Identity
    "Okta": ("Okta", "platform"),
    "Ping Identity": ("Ping Identity", "platform"),
    # Enterprise apps
    "ServiceNow": ("ServiceNow", "application"),
    "Workday": ("Workday", "application"),
    "DocuSign": ("DocuSign", "application"),
    # Adobe
    "Adobe": ("Adobe", "application"),
    "Adobe Experience Manager": ("Adobe", "application"),
    "Adobe Analytics": ("Adobe", "intelligence"),
    "Marketo": ("Adobe", "application"),
    # Martech
    "HubSpot": ("HubSpot", "application"),
    "Braze": ("Braze", "application"),
    "Iterable": ("Iterable", "application"),
    # RPA
    "UiPath": ("UiPath", "application"),
    "Blue Prism": ("Blue Prism", "application"),
    "Automation Anywhere": ("Automation Anywhere", "application"),
    # Payments / fincrime / fintech rails
    "Plaid": ("Plaid", "platform"),
    "Zelle": ("Early Warning Services", "application"),
    "Alloy": ("Alloy", "application"),
    "Verafin": ("Nasdaq", "application"),
    "Actimize": ("NICE", "application"),
    # CCaaS / conversational
    "Glia": ("Glia", "application"),
    "LivePerson": ("LivePerson", "application"),
    "Genesys": ("Genesys", "application"),
    "NICE": ("NICE", "application"),
    "Five9": ("Five9", "application"),
    # Data / BI
    "Looker": ("Google", "intelligence"),
    "Qlik": ("Qlik", "intelligence"),
    "Alteryx": ("Alteryx", "intelligence"),
    "Informatica": ("Informatica", "intelligence"),
    # Integration / automation
    "Boomi": ("Boomi", "platform"),
    "Workato": ("Workato", "platform"),
    # Security / observability
    "SailPoint": ("SailPoint", "platform"),
    "CrowdStrike": ("CrowdStrike", "platform"),
    "Zscaler": ("Zscaler", "platform"),
    "Palo Alto Networks": ("Palo Alto Networks", "platform"),
    "Splunk": ("Splunk", "intelligence"),
    "Datadog": ("Datadog", "platform"),
}

# alias (lowercase) → canonical. Canonical names themselves are added below.
_EXTRA_ALIASES: dict[str, str] = {
    "sfdc": "Salesforce", "salesforce.com": "Salesforce", "force.com": "Salesforce",
    "salesforce crm": "Salesforce",
    "salesforce sales cloud": "Sales Cloud",
    "salesforce service cloud": "Service Cloud",
    "salesforce marketing cloud": "Marketing Cloud", "sfmc": "Marketing Cloud",
    "exacttarget": "Marketing Cloud",
    "fsc": "Financial Services Cloud",
    "salesforce fsc": "Financial Services Cloud",
    "salesforce financial services cloud": "Financial Services Cloud",
    "salesforce data cloud": "Data Cloud",
    "salesforce experience cloud": "Experience Cloud",
    "community cloud": "Experience Cloud",
    "salesforce einstein": "Einstein",
    "marketing cloud account engagement": "Pardot",
    "mulesoft anypoint": "MuleSoft", "anypoint": "MuleSoft",
    "encino": "nCino",  # recurring typo in source CSVs (see tech_linker)
    "jack henry & associates": "Jack Henry", "jha": "Jack Henry",
    "corelation": "Corelation KeyStone", "keystone": "Corelation KeyStone",
    "dna": "Fiserv DNA", "premier": "Fiserv Premier", "horizon": "FIS Horizon",
    "lumin": "Lumin Digital",
    "azure": "Microsoft Azure",
    "powerbi": "Power BI",
    "microsoft dynamics": "Dynamics 365", "dynamics": "Dynamics 365",
    "m365": "Microsoft 365", "office 365": "Microsoft 365", "o365": "Microsoft 365",
    "teams": "Microsoft Teams", "ms teams": "Microsoft Teams",
    "entra id": "Microsoft Entra ID", "entra": "Microsoft Entra ID",
    "azure ad": "Microsoft Entra ID", "azure active directory": "Microsoft Entra ID",
    "amazon web services": "AWS",
    "gcp": "Google Cloud", "google cloud platform": "Google Cloud",
    "ping": "Ping Identity",
    "aem": "Adobe Experience Manager",
    "adobe marketo": "Marketo",
    "nice actimize": "Actimize",
    "palo alto": "Palo Alto Networks",
    "q2ebanking": "Q2",
}

_ALIASES: dict[str, str] = {canonical.lower(): canonical for canonical in _CATALOGUE}
_ALIASES.update(_EXTRA_ALIASES)

# Languages / frameworks / web libs / OS — real engineering signals, never
# stack rows. Matched exact-lowercase; "windows*" matches by prefix.
_ENGINEERING_SIGNALS = frozenset({
    "javascript", "typescript", "python", "java", "c#", "c++", "c", "html", "html5",
    "css", "css3", "php", "ruby", "go", "golang", "kotlin", "swift", "objective-c",
    "perl", "scala", "r", "sql", "json", "xml",
    "react", "reactjs", "react.js", "angular", "angularjs", "vue", "vuejs", "vue.js",
    "jquery", "jquery ui", "bootstrap", "webpack", "next.js", "nextjs",
    "node.js", "nodejs", "node", "asp.net", "vb.net", ".net", "dotnet",
    "recaptcha", "polyfill", "polyfill.io", "cdnjs",
    "django", "flask", "rails", "laravel", "spring", "express", "redux", "graphql",
    "sass", "less", "tailwind",
    "linux", "unix", "macos", "mac os", "ubuntu", "centos", "debian",
    "android", "ios",
})

# Generic category labels / placeholders — carry zero vendor information.
_NOISE_LABELS = frozenset({
    "various", "security", "infrastructure", "crm", "core banking", "lending",
    "collaboration", "analytics/bi", "analytics / bi", "analytics", "bi",
    "unspecified vendor", "wire", "payments", "marketing", "devops", "networking",
    "api", "apis", "mobile app", "mobile apps", "internal",
    "other", "unknown", "n/a", "na", "none", "tbd", "misc", "miscellaneous",
    "software", "technology", "tools", "general",
})

_PERSON_TITLE_RE = re.compile(
    r"[A-Z][a-z]+\s+[A-Z][a-z]+\s*[,–—-]?\s*"  # noqa: RUF001
    r"(?:CEO|CTO|CIO|CFO|COO|CISO|Chief|VP|President|Director|EVP|SVP)\b"
)
_DATE_OR_NUMBER_RE = re.compile(
    r"[\d\s.,/%$+-]+"
    r"|(?:19|20)\d{2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}"
    r"|Q[1-4]\s*\d{2,4}",
    re.IGNORECASE,
)


def _result(kind: str, *, canonical: str | None = None, vendor: str | None = None,
            layer_hint: str | None = None, confidence: float) -> dict:
    return {"kind": kind, "canonical": canonical, "vendor": vendor,
            "layer_hint": layer_hint, "confidence": confidence}


def _platform_hit(canonical: str, confidence: float) -> dict:
    vendor, layer = _CATALOGUE[canonical]
    return _result("platform", canonical=canonical, vendor=vendor,
                   layer_hint=layer, confidence=confidence)


def _is_prose(name: str) -> bool:
    if len(name) > 60:
        return True
    if ": " in name and len(name.split()) > 4:
        return True
    if _PERSON_TITLE_RE.search(name):
        return True
    return bool(_DATE_OR_NUMBER_RE.fullmatch(name))


def classify(name: str) -> dict:
    """Classify one technology string against the Zennify taxonomy.

    Returns ``{kind, canonical, vendor, layer_hint, confidence}`` with
    ``kind`` ∈ platform | engineering_signal | noise | unknown_vendor.
    Order of gates: prose guard → deny-lists → exact alias → rapidfuzz
    ratio ≥90 → unknown_vendor (kept, low confidence — reviewable, not
    silently dropped).
    """
    # Strip separators + TRAILING dots only — a leading dot is load-bearing
    # (".NET" must stay ".NET", not become "NET").
    raw = re.sub(r"\s+", " ", (name or "")).strip(" \t,;").rstrip(".")
    if not raw:
        return _result("noise", confidence=1.0)
    if _is_prose(raw):
        return _result("noise", confidence=0.9)
    low = raw.lower()
    if low in _ENGINEERING_SIGNALS or low.startswith("windows"):
        return _result("engineering_signal", confidence=0.95)
    if low in _NOISE_LABELS:
        return _result("noise", confidence=0.95)
    canonical = _ALIASES.get(low)
    if canonical:
        return _platform_hit(canonical, 1.0)
    if len(raw) >= 4:
        match = process.extractOne(low, _ALIASES.keys(), scorer=fuzz.ratio, score_cutoff=90)
        if match:
            return _platform_hit(_ALIASES[match[0]], round(match[1] / 100.0, 4))
    # Qualified platform names carry a real Zennify vendor in the leading
    # token(s) plus a product/category qualifier — "Splunk SIEM",
    # "MuleSoft Anypoint Platform", "Palo Alto NGFW", "FIS IBS",
    # "Salesforce Shield". Exact + whole-string fuzzy match miss these (the
    # qualifier drags the ratio below 90), which silently HID recognizable
    # platforms from the AE (audit 2026-07-02: Alma served 14/34 items,
    # MuleSoft/Splunk/Palo Alto absent). Match the leading token prefixes,
    # longest first, so "palo alto ngfw" resolves via "palo alto".
    tokens = [t for t in re.split(r"[\s/]+", low) if t]
    if len(tokens) > 1:
        for k in range(min(3, len(tokens) - 1), 0, -1):
            canonical = _ALIASES.get(" ".join(tokens[:k]))
            if canonical:
                return _platform_hit(canonical, 0.8)
    return _result("unknown_vendor", vendor=raw, confidence=0.3)


def split_cell(cell: str) -> list[str]:
    """Split a multi-vendor cell into candidate names (parse-time helper).

    Splits on commas, semicolons and spaced " + "; parenthetical asides
    are stripped ("Salesforce (FSC since 2021)" → "Salesforce"). Empty
    fragments are dropped; whitespace collapsed. Callers feed each part
    through :func:`classify`.
    """
    if not cell or not cell.strip():
        return []
    no_parens = re.sub(r"\([^)]*\)", " ", cell)
    parts = re.split(r"[,;]|\s\+\s", no_parens)
    out: list[str] = []
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" \t-–—/")  # noqa: RUF001
        if cleaned:
            out.append(cleaned)
    return out
