"""A header or markup detection has a verbatim span to cite.

AAA WCNY (2026-10-14): Drupal (x-generator), Cloudflare (server header) and
UKG (the careers link to recruiting.ultipro.com) were real detections no
register row could cite, because `html_text` drops headers, <meta> and hrefs.
"""
from engine import fetch as F

from fixtures import new_run

MARKUP = ('<html><head><meta name="Generator" content="Drupal 11 (https://www.drupal.org)" />'
          '<script src="https://js.hsforms.net/forms/v2.js"></script></head><body>'
          '<p>Welcome to the club.</p><a href="https://recruiting.ultipro.com/AAA1002AWCN">Jobs</a>'
          '<a href="https://www.example-club.com/about">About</a></body></html>')


def test_markers_name_headers_meta_and_third_party_hosts():
    m = F.tech_markers(MARKUP, {"server": "cloudflare", "x-generator": "Drupal 11"},
                       "https://www.example-club.com/")
    assert "server: cloudflare." in m
    assert "x-generator: Drupal 11." in m
    assert "meta generator: Drupal 11 (https://www.drupal.org)." in m
    assert "js.hsforms.net" in m and "recruiting.ultipro.com" in m
    assert "example-club.com" not in m.split("hosts linked or loaded:")[1]


def test_no_markers_no_block():
    assert F.tech_markers("<p>plain</p>", {}, "https://a.example.com/") == ""


def test_a_superset_replaces_the_held_text_and_anything_else_stays_alt(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False, folder=False)
    url = "https://www.example-club.com/"
    prose = "Welcome to the club. " * 20
    F.store_text(run, url, prose)
    F.store_text(run, url, prose + "\n\nTechnology markers in this response (machine read): server: cloudflare.")
    assert "server: cloudflare" in F.cached_text(run, url)
    meta = F.store_text(run, url, "A different page entirely. " * 20)
    assert meta.get("kept_existing")
    assert "server: cloudflare" in F.cached_text(run, url)


def test_a_protocol_relative_script_host_is_named():
    """AAA WCNY TS-007: HubSpot loads from //js.hsforms.net (no scheme)."""
    m = F.tech_markers('<script src="//js.hsforms.net/forms/embed/v2.js"></script>', {},
                       "https://www.example-club.com/")
    assert "js.hsforms.net" in m
