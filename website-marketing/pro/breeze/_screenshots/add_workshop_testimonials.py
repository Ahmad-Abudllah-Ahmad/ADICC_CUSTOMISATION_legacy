"""Add 3 workshop attendee testimonials to the DDC section of the breeze
index.html, alongside the existing Chris Andrew + Michael Buehler quotes.

Quotes are real, sent by attendees of the DataDrivenConstruction workshop:
  1. Kai Schmitt — Softwareingenieur fuer BIM Automatisierung, Dimexcon (DE)
  2. Philip Becker — Teamleiter Vorfertigung, Herbert Gruppe (DE)
  3. Lukas Fuchs — BIM Manager, D&S (EN)

Avatars are LinkedIn-style JPEGs from the user's Downloads folder, encoded
inline as base64 data URIs so the photos render with zero extra requests
and survive any static-site deploy without a separate asset pipeline.

Idempotent: re-running this script after the cards are already present
does not duplicate them (we early-return when Kai's name is found).
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "index.html"
DOWNLOADS = Path(r"C:\Users\Artem Boiko\Downloads")

PHOTOS = {
    "kai": DOWNLOADS / "1774382396659.jpg",
    "philip": DOWNLOADS / "1623401415768.jpg",
    "lukas": DOWNLOADS / "1660726787833 (1).jpg",
}


def to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def main() -> int:
    src = INDEX.read_text(encoding="utf-8")
    if "Kai Schmitt" in src:
        print("workshop testimonials already present; nothing to do")
        return 0

    for key, path in PHOTOS.items():
        if not path.exists():
            print(f"missing photo for {key}: {path}", file=sys.stderr)
            return 2

    kai_uri = to_data_uri(PHOTOS["kai"])
    philip_uri = to_data_uri(PHOTOS["philip"])
    lukas_uri = to_data_uri(PHOTOS["lukas"])

    # ── 1. Bump the grid from 2 columns to a responsive 3-column layout
    #     so 5 cards land as 3+2 on desktop, 2+2+1 on tablet, 1-up on
    #     phones. Keep the same max-width to stay aligned with the rest
    #     of the page.
    old_grid = (
        "    .ddc-testimonials {\n"
        "      max-width: 1440px;\n"
        "      margin: 0 auto clamp(20px, 2vw, 28px);\n"
        "      padding: 0 clamp(16px, 3vw, 40px);\n"
        "      display: grid;\n"
        "      grid-template-columns: 1fr 1fr;\n"
        "      gap: 16px;\n"
        "    }\n"
        "    @media (max-width: 720px) {\n"
        "      .ddc-testimonials { grid-template-columns: 1fr; }\n"
        "    }"
    )
    new_grid = (
        "    .ddc-testimonials {\n"
        "      max-width: 1440px;\n"
        "      margin: 0 auto clamp(20px, 2vw, 28px);\n"
        "      padding: 0 clamp(16px, 3vw, 40px);\n"
        "      display: grid;\n"
        "      grid-template-columns: repeat(3, 1fr);\n"
        "      gap: 16px;\n"
        "    }\n"
        "    @media (max-width: 1080px) {\n"
        "      .ddc-testimonials { grid-template-columns: repeat(2, 1fr); }\n"
        "    }\n"
        "    @media (max-width: 720px) {\n"
        "      .ddc-testimonials { grid-template-columns: 1fr; }\n"
        "    }"
    )
    if old_grid not in src:
        print("css grid anchor not found — layout may have shifted; aborting", file=sys.stderr)
        return 3
    src = src.replace(old_grid, new_grid, 1)

    # ── 2. Build the three <article> blocks. Quotes preserved verbatim
    #     from the workshop attendees; German umlauts written as HTML
    #     entities so the file stays ASCII-safe for any downstream tool
    #     that doesn't honour the BOM/UTF-8 declaration.
    cards = (
        # Kai Schmitt — DE
        '      <article class="ddc-tst">\n'
        '        <p class="ddc-tst-quote">'
        'Ich fande DataDrivenConstruction Workshop sehr interessant. '
        'Meiner Meinung nach konnten alle folgen. Man merkt auch anhand '
        'deiner Folien wieviel Zeit, Ausdauer und M&uuml;he du hineingesteckt '
        'hast. Auch die Live Pr&auml;sentationen waren super. Das einzige was '
        'ich bem&auml;ngeln w&uuml;rde, w&auml;re die Anzahl der Folien, dadurch '
        'kamen zu viele slides zustande. Aber das ist meckern auf dem '
        'h&ouml;chsten Niveau. Rundum war es der beste Workshop bei dem ich war. '
        'Au&szlig;erdem bist du auch eine sehr angenehme Person.'
        '</p>\n'
        '        <button type="button" class="ddc-tst-toggle" data-gnf-toggle aria-expanded="false"><span class="more-label">Read more</span><span class="less-label">Show less</span></button>\n'
        '        <div class="ddc-tst-author">\n'
        f'          <div class="ddc-tst-avatar"><img src="{kai_uri}" alt="Kai Schmitt" loading="lazy" decoding="async"></div>\n'
        '          <div class="ddc-tst-meta">\n'
        '            <div class="ddc-tst-name">Kai Schmitt</div>\n'
        '            <div class="ddc-tst-role">Dimexcon &middot; Softwareingenieur f&uuml;r BIM Automatisierung</div>\n'
        '          </div>\n'
        '        </div>\n'
        '      </article>\n'
        # Philip Becker — DE
        '      <article class="ddc-tst">\n'
        '        <p class="ddc-tst-quote">'
        'Die DataDrivenConstruction Schulung fand ich insgesamt wirklich '
        'spannend und sehr bereichernd. Besonders gut gefallen haben mir: '
        'der &bdquo;historische&ldquo; Hintergrund zu den verschiedenen '
        'CAD-Softwares (das war spannend zu h&ouml;ren und hatte etwas von '
        'Investigativjournalismus); der interessante Ansatz zur Automatisierung '
        '&uuml;ber DataFrames; deine eigenen praxisnahen Beispiele zur '
        'Prozessautomatisierung im Bauwesen; und der Einblick in aktuelle Trends '
        'wie Claude Code und OpenClaw &mdash; du hast das Thema mit Leben gef&uuml;llt. '
        'Einziger Nachteil: Es war wirklich viel Input in nur zwei Tagen. '
        'Gleichzeitig hast du sehr gut aufgezeigt, wie wir uns selbst weiter '
        'orientieren k&ouml;nnen &mdash; zum Beispiel &uuml;ber das strukturierte '
        'Aufzeichnen unserer Prozesse im Miro-Board. Vielen Dank nochmal f&uuml;r '
        'die Schulung und den Austausch.'
        '</p>\n'
        '        <button type="button" class="ddc-tst-toggle" data-gnf-toggle aria-expanded="false"><span class="more-label">Read more</span><span class="less-label">Show less</span></button>\n'
        '        <div class="ddc-tst-author">\n'
        f'          <div class="ddc-tst-avatar"><img src="{philip_uri}" alt="Philip Becker" loading="lazy" decoding="async"></div>\n'
        '          <div class="ddc-tst-meta">\n'
        '            <div class="ddc-tst-name">Philip Becker</div>\n'
        '            <div class="ddc-tst-role">Herbert Gruppe &middot; Teamleiter Vorfertigung</div>\n'
        '          </div>\n'
        '        </div>\n'
        '      </article>\n'
        # Lukas Fuchs — EN
        '      <article class="ddc-tst">\n'
        '        <p class="ddc-tst-quote">'
        'It was a fantastic workshop with exciting content that we, and I '
        'personally, learned a lot from. Thank you for taking so much time '
        'for us. We look forward to trying out what we learned as soon as '
        'possible and incorporating it into our projects! #bleedingedge'
        '</p>\n'
        '        <button type="button" class="ddc-tst-toggle" data-gnf-toggle aria-expanded="false"><span class="more-label">Read more</span><span class="less-label">Show less</span></button>\n'
        '        <div class="ddc-tst-author">\n'
        f'          <div class="ddc-tst-avatar"><img src="{lukas_uri}" alt="Lukas Fuchs" loading="lazy" decoding="async"></div>\n'
        '          <div class="ddc-tst-meta">\n'
        '            <div class="ddc-tst-name">Lukas Fuchs</div>\n'
        '            <div class="ddc-tst-role">D&amp;S &middot; BIM Manager</div>\n'
        '          </div>\n'
        '        </div>\n'
        '      </article>\n'
    )

    # ── 3. Append the new cards inside the same <div class="ddc-testimonials">
    #     wrapper, right before its closing </div>. We anchor on the second
    #     existing testimonial's closing </article> + the wrapper's </div>
    #     to be unambiguous about which closing tag we mean.
    closing_anchor = '      </article>\n    </div>\n\n  </section>'
    if closing_anchor not in src:
        print("html closing anchor not found; aborting", file=sys.stderr)
        return 4
    src = src.replace(
        closing_anchor,
        f'      </article>\n{cards}    </div>\n\n  </section>',
        1,
    )

    INDEX.write_text(src, encoding="utf-8")
    print("inserted 3 workshop testimonials + bumped grid to 3 cols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
