"""Conservative HTML reconstruction for public rich text (no active content)."""
from html import escape
from html.parser import HTMLParser

from django.core.exceptions import ValidationError

from .models import validate_link

ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "blockquote", "h2", "h3", "h4", "a", "img", "pre", "code", "hr", "table", "thead", "tbody", "tr", "th", "td"}
VOID_TAGS = {"br", "img", "hr"}
DROP_CONTENT = {"script", "style", "iframe", "object", "template", "svg", "math"}


class SafeHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.suppressed = []

    def handle_starttag(self, tag, attrs):
        if self.suppressed:
            if tag in DROP_CONTENT:
                self.suppressed.append(tag)
            return
        if tag in DROP_CONTENT:
            self.suppressed.append(tag)
            return
        if tag not in ALLOWED_TAGS:
            return
        permitted = []
        for name, value in attrs:
            if value is None:
                continue
            if (tag == "a" and name == "href") or (tag == "img" and name == "src"):
                try:
                    validate_link(value)
                except (ValidationError, ValueError):
                    continue
                permitted.append((name, value))
            elif name == "title" or (tag == "img" and name == "alt"):
                permitted.append((name, value))
        if tag == "a":
            permitted.append(("rel", "noopener noreferrer"))
        attributes = "".join(f' {name}="{escape(value, quote=True)}"' for name, value in permitted)
        self.output.append(f"<{tag}{attributes}>")

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.suppressed:
            self.output.append(escape(data))


def safe_html(value):
    parser = SafeHTMLParser()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.output)
