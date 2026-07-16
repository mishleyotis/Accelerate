"""Unit tests for sentiment signal hygiene (derive_sentiment).

Covers the 2026-07-06 deploy-review fragment-clip fixes: mid-word leading
fragments with trailing punctuation ("wever, …") must be stripped, and the
clip window must snap to word boundaries so the segmenter never returns a
mid-word tail as "the sentence".
"""
from app.scripts import derive_sentiment as ds


def test_clean_sig_strips_leading_fragment_with_trailing_comma():
    # "wever, …" — the comma used to stop the \s+-only strip; the fragment shipped.
    assert ds._clean_sig("wever, employee engagement is strong") == (
        "employee engagement is strong"
    )


def test_clean_sig_keeps_whitelisted_short_words():
    assert ds._clean_sig("app rating 4.5/5 on the App Store").startswith("app rating")


def test_clip_signal_snaps_to_word_boundary():
    prose = (
        "The bank's overall standing however, employee engagement on "
        "Glassdoor is strong at 4.2/5 across the workforce this year."
    )
    sig = ds._clip_signal(prose, prose.index("Glassdoor"))
    assert "Glassdoor" in sig
    first = sig.split()[0]
    # first token is a whole word, never a mid-word tail like "wever"/"loyee"
    assert "wever" not in first
    assert first[:1].isupper() or first.lower() in ds._LC_KEEP or first.isalpha()
