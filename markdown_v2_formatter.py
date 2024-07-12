import re


def convert_to_markdown_v2(text):
    # Characters to be escaped in MarkdownV2
    special_chars = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]

    # Escape special characters
    for char in special_chars:
        text = text.replace(char, "\\" + char)

    # Convert bold (we don't change the syntax for bold)
    text = re.sub(r"\\\*\\\*(.*?)\\\*\\\*", r"*\1*", text)

    # Convert italic (we don't change the syntax for italic)
    text = re.sub(r"\\\*(.*?)\\\*", r"_\1_", text)

    # Convert links (we don't change the syntax for links)
    text = re.sub(r"\\\[(.*?)\\\]\\\((.*?)\\\)", r"[\1](\2)", text)

    # Convert code blocks (we keep the triple backticks)
    text = re.sub(r"\\\`\\\`\\\`(.*?)\\\`\\\`\\\`", r"```\1```", text, flags=re.DOTALL)

    # Convert inline code (we keep the single backticks)
    text = re.sub(r"\\\`(.*?)\\\`", r"`\1`", text)

    return text
