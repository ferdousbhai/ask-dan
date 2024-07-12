from markdown_v2_formatter import convert_to_markdown_v2


def test_special_characters():
    input_text = "Hello! This is a test."
    expected_output = "Hello\\! This is a test\\."
    assert convert_to_markdown_v2(input_text) == expected_output


def test_bold_and_italic():
    input_text = "This is **bold** and *italic* text."
    expected_output = "This is *bold* and _italic_ text\\."
    assert convert_to_markdown_v2(input_text) == expected_output


def test_links():
    input_text = "Check out [this link](https://example.com)!"
    expected_output = "Check out [this link](https://example\\.com)\\!"
    assert convert_to_markdown_v2(input_text) == expected_output


def test_code_blocks():
    input_text = "```code```"
    expected_output = "```code```"
    assert convert_to_markdown_v2(input_text) == expected_output


def test_inline_code():
    input_text = "`code`"
    expected_output = "`code`"
    assert convert_to_markdown_v2(input_text) == expected_output


def test_complex_text():
    input_text = "**Bold** and `code`"
    expected_output = "*Bold* and `code`"
    assert convert_to_markdown_v2(input_text) == expected_output
