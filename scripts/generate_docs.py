#!/usr/bin/env python3

import argparse
from pathlib import Path
import markdown
import re
import shutil

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md(?:#[^)]+)?)\)")
BUILD_NOTE_RE = re.compile(r"<!--\s*build:note\s+(.*?)\s*-->")
BUILD_IGNORE_RE = re.compile(r"<!--\s*build:ignore\s*-->")


def clean_output_dir(dst_root: Path):
    """
    Fully remove and recreate the output directory.
    """
    if not dst_root.is_relative_to(Path.cwd()):
        raise ValueError("The output must be in the current working directory.")
    if dst_root == Path("/"):
        raise ValueError("Invalid path.")

    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)


def rewrite_md_links(text: str) -> str:
    """
    Convert relative .md links to .html while preserving anchors.
    """

    def repl(match):
        label = match.group(1)
        target = match.group(2)

        if "#" in target:
            path, anchor = target.split("#", 1)
            return f"[{label}]({Path(path).with_suffix('.html')}#{anchor})"
        else:
            return f"[{label}]({Path(target).with_suffix('.html')})"

    return MD_LINK_RE.sub(repl, text)


def build_html(md_text: str, stylesheet_name: str | None) -> str:
    md = markdown.Markdown(extensions=["fenced_code", "tables", "toc"])

    body = md.convert(md_text)

    css_link = ""
    if stylesheet_name:
        css_link = f'<link rel="stylesheet" href="{stylesheet_name}">'

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
{css_link}
</head>
<body>

{body}

</body>
</html>
"""


def process_build_comments(md_text: str) -> tuple[str, list[str]]:
    """
    Processes build-only comments in markdowns.
    Returns:
      - cleaned markdown
    """

    # Handle build:note → convert to HTML block
    def note_repl(match):
        content = match.group(1).strip()
        return content

    md_text = BUILD_NOTE_RE.sub(note_repl, md_text)

    # Remove build:ignore comments
    md_text = BUILD_IGNORE_RE.sub("", md_text)

    return md_text


def copy_stylesheet(css_src: Path, dst_root: Path):
    dst_file = dst_root / css_src.name
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    dst_file.write_text(css_src.read_text(encoding="utf-8"), encoding="utf-8")


def convert_file(src_path, src_root, dst_root, stylesheet_name):
    rel_path = src_path.relative_to(src_root)
    out_path = (dst_root / rel_path).with_suffix(".html")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    md_text = src_path.read_text(encoding="utf-8")

    # 1. Process build comments
    md_text = process_build_comments(md_text)

    # 2. Rewrite links
    md_text = rewrite_md_links(md_text)

    # 3. Render HTML
    html = build_html(md_text, stylesheet_name)

    out_path.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Convert Markdown to static HTML")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--css", type=str, default=None)

    args = parser.parse_args()

    src_root = args.input_dir.resolve()
    dst_root = args.output_dir.resolve()

    clean_output_dir(dst_root)

    css_name = None
    if args.css:
        css_path = Path(args.css)
        copy_stylesheet(css_path, dst_root)
        css_name = css_path.name  # referenced in HTML

    for md_file in src_root.rglob("*.md"):
        convert_file(md_file, src_root, dst_root, css_name)


if __name__ == "__main__":
    main()
