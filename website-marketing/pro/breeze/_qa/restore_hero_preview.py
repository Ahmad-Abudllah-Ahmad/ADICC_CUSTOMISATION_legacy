"""‌⁠‍Restore the hero-preview section that the v3 dataflow replacement
accidentally clobbered. Reinsert it right before the dataflow block.
"""
from pathlib import Path

INDEX = Path(r"c:\Users\Artem Boiko\Desktop\CodeProjects\ERP_26030500\website-marketing\pro\breeze\index.html")
HERO  = Path(r"c:\Users\Artem Boiko\Desktop\CodeProjects\ERP_26030500\website-marketing\pro\breeze\_qa\hero_preview_block.html")

text = INDEX.read_text(encoding="utf-8")

# Strip the orphan "SECTION 1.2" comment that the buggy script left
# wedged inside the SECTION 9.5 separator group.
ORPHAN = (
    "  <!-- ================================================================ -->\n"
    "  <!-- SECTION 1.2 — HERO PREVIEW (module carousel — cycles 5 modules)   -->\n"
    "  <!-- SECTION 9.5 — DATA FLOW (project file → priced BOQ → tender pack) -->\n"
    "  <!-- ================================================================ -->\n"
)
REPLACEMENT = (
    "  <!-- ================================================================ -->\n"
    "  <!-- SECTION 9.5 — DATA FLOW (project file → priced BOQ → tender pack) -->\n"
    "  <!-- ================================================================ -->\n"
)
if ORPHAN not in text:
    raise SystemExit("orphan comment header not found — file may already be repaired")
text = text.replace(ORPHAN, REPLACEMENT, 1)

# Reinsert the hero-preview block right before the SECTION 9.5 marker.
hero_block = HERO.read_text(encoding="utf-8")
SECTION_95_MARK = (
    "  <!-- ================================================================ -->\n"
    "  <!-- SECTION 9.5 — DATA FLOW (project file → priced BOQ → tender pack) -->\n"
)
i = text.find(SECTION_95_MARK)
if i == -1:
    raise SystemExit("SECTION 9.5 marker not found")

# Hero block already starts with its own SEP+comment+SEP triplet, so
# we drop two trailing newlines from before the dataflow's own SEP and
# put hero-preview + a blank line + dataflow's SEP back.
new_text = text[:i] + hero_block + "\n\n" + text[i:]
INDEX.write_text(new_text, encoding="utf-8")
print(f"OK — reinserted {len(hero_block)} bytes of hero-preview")
