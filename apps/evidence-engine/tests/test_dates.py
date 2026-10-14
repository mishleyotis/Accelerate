import datetime as dt

from evidence_engine import dates

TODAY = dt.date(2026, 10, 10)


def test_metadata_wins():
    html = '<html><head><meta property="article:published_time" content="2026-03-03T10:00:00Z"></head><body>x</body></html>'
    assert dates.published_date(html, "https://x.test/2024/01/post", today=TODAY) == ("2026-03-03", "meta")


def test_json_ld_and_time_element():
    assert dates.from_metadata('<script type="application/ld+json">{"datePublished":"2025-12-05"}</script>') == ("2025-12-05", "json-ld datePublished")
    assert dates.from_metadata('<time itemprop="datePublished" datetime="2025-11-30">x</time>') == ("2025-11-30", "time element")
    # an events page <time> without the publication marker is NOT a date
    assert dates.from_metadata('<time datetime="2025-11-30">x</time>') == (None, None)


def test_url_path():
    assert dates.from_url("https://x.test/news/2025/08/30/story") == ("2025-08-30", "url path")
    assert dates.from_url("https://x.test/20230406/story") == ("2023-04-06", "url path")
    assert dates.from_url("https://x.test/uploads/2024/07/file.pdf") == ("2024-07-01", "url path (month)")
    assert dates.from_url("https://x.test/no-date") == (None, None)


def test_dateline():
    assert dates.from_dateline("ANYTOWN, ST, March 3, 2026 – Example Federal Credit Union today announced") == ("2026-03-03", "dateline")
    assert dates.from_dateline("Published 5 December 2025 by the newsroom") == ("2025-12-05", "dateline")
    assert dates.from_dateline("No date in this text at all.") == (None, None)


def test_modified_and_copyright_are_never_read():
    html = ('<html><head><meta property="article:modified_time" content="2026-09-01"></head>'
            '<body>© 2026 Example FCU. All rights reserved.</body></html>')
    assert dates.published_date(html, "https://x.test/about", "Copyright 2026 Example", today=TODAY) == (None, None)


def test_future_dates_are_dropped():
    html = '<meta property="article:published_time" content="2027-01-01">'
    assert dates.published_date(html, "", today=TODAY) == (None, None)


def test_retrieval_date_is_never_assumed():
    assert dates.published_date("<p>hello</p>", "https://x.test/p", "hello", today=TODAY) == (None, None)
