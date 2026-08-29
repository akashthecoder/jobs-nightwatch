"""Render SUBMISSION.md to a print-ready HTML page.

Open the output in a browser and use Cmd+P -> Save as PDF. Browser print
output is better than any CLI converter here (proper page breaks, live
hyperlinks, real font rendering) and needs nothing installed.
"""
import html as H
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def inline(t: str) -> str:
    t = H.escape(t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return t


def is_list(l: str) -> bool:
    return bool(re.match(r"^\s*([-*+]|\d+\.)\s+", l))


def to_html(md: str) -> str:
    lines = md.split("\n")
    out, i, n = [], 0, len(lines)

    while i < n:
        start = i                      # guard: i MUST advance each iteration
        l = lines[i]
        stripped = l.strip()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)", l)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        # table
        if l.startswith("|") and i + 1 < n and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            hdr = [c.strip() for c in l.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in hdr) + "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue

        # blockquote
        if stripped.startswith(">"):
            blk = []
            while i < n and lines[i].strip().startswith(">"):
                blk.append(inline(lines[i].strip().lstrip("> ")))
                i += 1
            out.append("<blockquote>" + "<br>".join(blk) + "</blockquote>")
            continue

        # list
        if is_list(l):
            ordered = bool(re.match(r"^\s*\d+\.\s", l))
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>")
            while i < n:
                cur = lines[i]
                if is_list(cur):
                    out.append("<li>" + inline(re.sub(r"^\s*([-*+]|\d+\.)\s+", "", cur)) + "</li>")
                    i += 1
                elif cur.startswith("  ") and cur.strip() and out and out[-1].endswith("</li>"):
                    out[-1] = out[-1][:-5] + " " + inline(cur.strip()) + "</li>"
                    i += 1
                else:
                    break
            out.append(f"</{tag}>")
            continue

        # paragraph -- consume until a blank line or a block-level construct
        para = []
        while i < n:
            cur = lines[i]
            if not cur.strip() or cur.strip() == "---" or cur.startswith(("#", "|", ">")) or is_list(cur):
                break
            para.append(cur.strip())
            i += 1
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")

        if i == start:                 # nothing consumed -> force progress
            i += 1

    return "\n".join(out)


CSS = """
@page { size: A4; margin: 16mm 14mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
       color:#1a1d24; max-width:190mm; margin:0 auto; padding:0 4mm; }
h1 { font-size:23pt; margin:0 0 2mm; letter-spacing:-.5pt; }
h2 { font-size:14pt; margin:9mm 0 3mm; padding-bottom:1.5mm;
     border-bottom:2px solid #4285F4; color:#12305e; page-break-after:avoid; }
h3 { font-size:11.5pt; margin:6mm 0 2mm; color:#1f3b66; page-break-after:avoid; }
h4 { font-size:10.5pt; margin:4mm 0 1.5mm; }
p { margin:0 0 3mm; }
ul,ol { margin:0 0 3mm; padding-left:6mm; }
li { margin-bottom:1.2mm; }
table { width:100%; border-collapse:collapse; margin:0 0 4mm; font-size:9.5pt;
        page-break-inside:avoid; }
th { background:#eef3fb; text-align:left; padding:2mm 2.5mm; border:1px solid #cbd6e6;
     font-weight:600; }
td { padding:2mm 2.5mm; border:1px solid #dde3ec; vertical-align:top; }
code { background:#f2f4f8; padding:.4mm 1.2mm; border-radius:2px;
       font:9pt ui-monospace,SFMono-Regular,Menlo,monospace; }
blockquote { margin:0 0 4mm; padding:3mm 4mm; background:#f7f9fc;
             border-left:3px solid #4285F4; page-break-inside:avoid; }
a { color:#1a56c4; text-decoration:none; word-break:break-word; }
hr { border:none; border-top:1px solid #dde3ec; margin:7mm 0; }
strong { color:#0d1117; }
.cover { border:1px solid #cbd6e6; border-radius:3mm; padding:5mm 6mm;
         background:#f7f9fc; margin:0 0 6mm; page-break-inside:avoid; }
.cover .t { font-size:9pt; text-transform:uppercase; letter-spacing:.8pt;
            color:#5a6478; margin-bottom:2mm; }
.cover .row { display:flex; gap:4mm; margin-bottom:1.5mm; font-size:10pt; }
.cover .k { width:34mm; color:#5a6478; flex:none; }
.lead { font-size:12pt; color:#4a5468; margin-bottom:5mm; }
"""


def main():
    md = (ROOT / "SUBMISSION.md").read_text()
    # drop the internal header and the field-mapping block above the first rule
    parts = md.split("\n---\n", 1)
    body_md = parts[1] if len(parts) > 1 else md
    body = to_html(body_md)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Jobs NightWatch — Devpost Submission</title><style>{CSS}</style></head><body>
<h1>Jobs NightWatch</h1>
<p class="lead">Job boards show you what exists. This shows you what <em>changed</em>.</p>
<div class="cover">
  <div class="t">Submission summary</div>
  <div class="row"><div class="k">Category</div><div><strong>Taskmaster</strong></div></div>
  <div class="row"><div class="k">Hosted project</div><div><a href="https://nightwatch-dashboard-745162634071.us-central1.run.app">nightwatch-dashboard-745162634071.us-central1.run.app</a></div></div>
  <div class="row"><div class="k">Repository</div><div><a href="https://github.com/akashthecoder/jobs-nightwatch">github.com/akashthecoder/jobs-nightwatch</a> &mdash; private, judge access granted</div></div>
  <div class="row"><div class="k">Demo video</div><div>[ YouTube link ]</div></div>
  <div class="row"><div class="k">Google Cloud</div><div>ADK 2.8.0 &middot; Gemini 3.7 Flash on Vertex AI &middot; Cloud Run &times;3 &middot; Pub/Sub &middot; Firestore &middot; Cloud Scheduler</div></div>
</div>
{body}
</body></html>"""

    out = ROOT / "submission.html"
    out.write_text(html)
    print(f"wrote {out}  ({len(html):,} bytes)")
    print("\nOpen it and press Cmd+P -> Save as PDF.")


if __name__ == "__main__":
    main()
