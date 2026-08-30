#!/usr/bin/env python3
"""Extract the DMA Insights design docs (self-contained HTML) to greppable
plain text in docs/text/.

Rules (per build kickoff §2):
- Strip tags; produce readable text with heading markers (#, ##, ###).
- Keep `<div class="code">` blocks intact verbatim — they contain DDL, SQL
  and API examples that are implemented verbatim. They are fenced with ```
  so they are easy to locate.
- The HTML sources in docs/ are read-only source material; re-run this
  script if they are ever re-delivered.

Usage: python3 scripts/extract_docs.py [docs_dir] [out_dir]
"""
import html.parser
import re
import sys
from pathlib import Path

BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "nav",
    "ul", "ol", "table", "thead", "tbody", "tr", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "li", "dt", "dd",
}
HEADING_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ",
                  "h5": "##### ", "h6": "###### "}
SKIP_CONTENT = {"script", "style"}


class DocExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.code_depth = 0      # >0 while inside a <div class="code"> subtree
        self.div_depth_in_code = []
        self.skip_depth = 0
        self.heading = None
        self.cell_pending = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag in SKIP_CONTENT:
            self.skip_depth += 1
            return
        if self.code_depth:
            if tag == "div":
                self.div_depth_in_code[-1] += 1
            if tag == "br":
                self.out.append("\n")
            return
        if tag == "div" and re.search(r"\bcode\b", cls):
            self.code_depth += 1
            self.div_depth_in_code.append(1)
            self.out.append("\n```\n")
            return
        if tag in HEADING_PREFIX:
            self.out.append("\n\n" + HEADING_PREFIX[tag])
            self.heading = tag
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("td", "th"):
            if self.cell_pending:
                self.out.append(" | ")
            self.cell_pending = True
        elif tag in BLOCK_TAGS:
            self.out.append("\n")
            if tag == "tr":
                self.cell_pending = False

    def handle_endtag(self, tag):
        if tag in SKIP_CONTENT:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.code_depth:
            if tag == "div":
                self.div_depth_in_code[-1] -= 1
                if self.div_depth_in_code[-1] == 0:
                    self.div_depth_in_code.pop()
                    self.code_depth -= 1
                    self.out.append("\n```\n")
            return
        if tag in HEADING_PREFIX:
            self.out.append("\n")
            self.heading = None
        elif tag == "tr":
            self.out.append("\n")
            self.cell_pending = False
        elif tag in ("table", "ul", "ol", "p"):
            self.out.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.code_depth:
            self.out.append(data)          # verbatim inside code blocks
        else:
            text = re.sub(r"\s+", " ", data)
            if text.strip() or (self.out and not self.out[-1].endswith("\n")):
                self.out.append(text)

    def text(self):
        raw = "".join(self.out)
        lines = []
        in_code = False
        for line in raw.split("\n"):
            if line.strip() == "```":
                in_code = not in_code
                lines.append("```")
                continue
            lines.append(line if in_code else line.rstrip())
        txt = "\n".join(lines)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        return txt.strip() + "\n"


def main():
    """Extract docs/*.html to greppable text.

    usage: extract_docs.py [DOCS_DIR] [OUT_DIR]

    The source directory is validated BEFORE anything is created. Until
    2026-08-20 the first argument went straight into a mkdir, so
    `extract_docs.py --help` created a directory called "--help" in the
    repository root, and a typo created a junk tree beside it.
    """
    args = [a for a in sys.argv[1:]]
    if args and args[0] in ("-h", "--help"):
        print(main.__doc__.strip())
        return 0
    docs_dir = Path(args[0]) if args else Path("docs")
    if not docs_dir.is_dir():
        print(f"not a directory: {docs_dir}\n\n{main.__doc__.strip()}",
              file=sys.stderr)
        return 2
    out_dir = Path(args[1]) if len(args) > 1 else docs_dir / "text"
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(docs_dir.glob("*.html")):
        parser = DocExtractor()
        parser.feed(src.read_text(encoding="utf-8"))
        dest = out_dir / (src.stem + ".txt")
        dest.write_text(parser.text(), encoding="utf-8")
        print(f"{src.name} -> {dest} ({dest.stat().st_size:,} bytes)")


if __name__ == "__main__":
    sys.exit(main() or 0)
