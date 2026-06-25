from pdf_concatenator.pdf_build import _text_width, _wrap_text_to_width


def test_wrap_text_to_width_splits_before_limit():
    text = (
        "2005-03-01 Estates & Management Ltd Scannable Document on "
        "May 22, 2020 at 14_08_03.pdf"
    )
    max_width = 300.0
    lines = _wrap_text_to_width(text, "Helvetica", 11, max_width)
    assert len(lines) > 1
    for line in lines:
        assert _text_width("Helvetica", 11, line) <= max_width + 1
