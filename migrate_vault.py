#!/usr/bin/env python3
"""
Sphene 1-Click Vault Migration Engine
Seamlessly imports standard desktop Markdown vaults (folders or .zip archives) into Sphene.
Preserves folder structures, frontmatter, tags, [[Wikilinks]], task checklists, and attachments.
"""

import os
import sys
import re
import shutil
import zipfile
import tempfile
import argparse
from datetime import datetime

IGNORE_DIRS = {".obsidian", ".trash", ".git", ".idea", ".vscode", "node_modules", ".cache"}
MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".mp3", ".mp4", ".mov"}

def slugify(text: str) -> str:
    """Convert arbitrary title or folder name to a clean URL slug."""
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", text)
    return slug or "untitled"

def parse_frontmatter_and_body(content: str):
    """Separate YAML frontmatter and Markdown body."""
    m = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n([\s\S]*)$", content)
    if m:
        return m.group(1).strip(), m.group(2)
    return None, content

def extract_title_from_body(body: str, fallback: str) -> str:
    """Attempt to extract first H1 heading, or fall back to filename."""
    m = re.search(r"^#\s+(.*?)\s*$", body, flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fallback

def migrate_vault(source_path: str, dest_knowledge_dir: str, clean_dest: bool = False) -> dict:
    """Migrate an external vault directory or zip archive into Sphene's knowledge directory."""
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source vault '{source_path}' does not exist.")

    temp_extract_dir = None
    work_dir = source_path

    # If source is a zip archive, extract to temp directory
    if os.path.isfile(source_path) and (source_path.endswith(".zip") or zipfile.is_zipfile(source_path)):
        temp_extract_dir = tempfile.mkdtemp(prefix="sphene_mig_")
        with zipfile.ZipFile(source_path, "r") as zf:
            zf.extractall(temp_extract_dir)
        work_dir = temp_extract_dir
        children = [os.path.join(work_dir, c) for c in os.listdir(work_dir) if not c.startswith(".")]
        if len(children) == 1 and os.path.isdir(children[0]):
            work_dir = children[0]

    os.makedirs(dest_knowledge_dir, exist_ok=True)
    if clean_dest:
        for item in os.listdir(dest_knowledge_dir):
            p = os.path.join(dest_knowledge_dir, item)
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.isfile(p) and item != "default.md":
                os.remove(p)

    dest_attachments_dir = os.path.join(dest_knowledge_dir, "attachments")
    os.makedirs(dest_attachments_dir, exist_ok=True)

    stats = {
        "notes_imported": 0,
        "attachments_imported": 0,
        "canvases_converted": 0,
        "folders_mapped": 0
    }

    # Pass 1: Copy and index all media attachments
    attachment_map = {}
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in MEDIA_EXTENSIONS:
                src_file = os.path.join(root, f)
                target_media = os.path.join(dest_attachments_dir, f)
                shutil.copy2(src_file, target_media)
                attachment_map[f] = f"attachments/{f}"
                stats["attachments_imported"] += 1

    # Pass 2: Process all Markdown & Canvas documents
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel_path = os.path.relpath(root, work_dir)
        
        if rel_path == ".":
            current_dest_base = dest_knowledge_dir
        else:
            path_parts = [p for p in rel_path.split(os.sep) if p and p not in IGNORE_DIRS]
            current_dest_base = os.path.join(dest_knowledge_dir, *path_parts)
            stats["folders_mapped"] += 1

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            src_file = os.path.join(root, f)
            raw_basename = os.path.splitext(f)[0]

            if ext == ".md":
                with open(src_file, "r", encoding="utf-8", errors="replace") as fh:
                    raw_text = fh.read()

                frontmatter, body = parse_frontmatter_and_body(raw_text)
                title = raw_basename
                if frontmatter:
                    tm = re.search(r"^title:\s*[\"']?(.*?)[\"']?\s*$", frontmatter, flags=re.MULTILINE)
                    if tm and tm.group(1).strip():
                        title = tm.group(1).strip()
                    else:
                        title = extract_title_from_body(body, raw_basename)
                else:
                    title = extract_title_from_body(body, raw_basename)

                def replace_media_transclusion(match):
                    parts = match.group(1).split("|")
                    media_name = parts[0].strip()
                    alt = parts[1].strip() if len(parts) > 1 else media_name
                    if media_name in attachment_map:
                        return f"![{alt}]({attachment_map[media_name]})"
                    return f"![{alt}](attachments/{media_name})"

                body = re.sub(r"!\[\[(.*?)\]\]", replace_media_transclusion, body)

                file_mtime = datetime.fromtimestamp(os.path.getmtime(src_file)).strftime("%Y-%m-%d")
                if frontmatter:
                    if not re.search(r"^title:", frontmatter, flags=re.MULTILINE):
                        frontmatter = f"title: \"{title}\"\n" + frontmatter
                    if not re.search(r"^date:", frontmatter, flags=re.MULTILINE):
                        frontmatter += f"\ndate: {file_mtime}"
                else:
                    frontmatter = f"title: \"{title}\"\ndate: {file_mtime}\ntaxonomy:\n  tag: [imported]"

                os.makedirs(current_dest_base, exist_ok=True)
                dest_file = os.path.join(current_dest_base, f)

                with open(dest_file, "w", encoding="utf-8") as out:
                    out.write(f"---\n{frontmatter.strip()}\n---\n\n{body.lstrip()}")

                stats["notes_imported"] += 1

            elif ext == ".canvas":
                file_mtime = datetime.fromtimestamp(os.path.getmtime(src_file)).strftime("%Y-%m-%d")
                frontmatter = f"title: \"{raw_basename} (Canvas Map)\"\ndate: {file_mtime}\ntaxonomy:\n  tag: [canvas, visual-map]"
                body = f"# {raw_basename} (Visual Canvas Map)\n\nConverted from visual canvas layout.\n\n```json\n"
                with open(src_file, "r", encoding="utf-8", errors="replace") as fh:
                    body += fh.read()
                body += "\n```\n"

                os.makedirs(current_dest_base, exist_ok=True)
                dest_file = os.path.join(current_dest_base, f"{raw_basename}-canvas.md")

                with open(dest_file, "w", encoding="utf-8") as out:
                    out.write(f"---\n{frontmatter}\n---\n\n{body}")

                stats["canvases_converted"] += 1

    if temp_extract_dir and os.path.isdir(temp_extract_dir):
        shutil.rmtree(temp_extract_dir, ignore_errors=True)

    return stats

def main():
    parser = argparse.ArgumentParser(description="Sphene 1-Click Vault Migration Engine")
    parser.add_argument("source", help="Path to existing vault directory or .zip archive")
    parser.add_argument("--dest", default=os.environ.get("SPHENE_VAULT_DIR", "/DATA/AppData/sphene/vault"),
                        help="Destination knowledge directory")
    parser.add_argument("--clean", action="store_true", help="Clean destination directory prior to migration")
    args = parser.parse_args()

    print(f"=== Sphene Vault Migration Engine ===")
    print(f"Source:      {args.source}")
    print(f"Destination: {args.dest}")

    start_time = datetime.now()
    stats = migrate_vault(args.source, args.dest, clean_dest=args.clean)
    elapsed = (datetime.now() - start_time).total_seconds()

    print("\n✓ Migration completed successfully!")
    print(f"  • Notes imported:       {stats['notes_imported']}")
    print(f"  • Folders mapped:       {stats['folders_mapped']}")
    print(f"  • Attachments copied:   {stats['attachments_imported']}")
    print(f"  • Canvases converted:   {stats['canvases_converted']}")
    print(f"  • Elapsed time:         {elapsed:.2f}s")

if __name__ == "__main__":
    main()
