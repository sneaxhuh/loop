"""Plain comparison artifacts, including a PNG snapshot; no product frontend."""

import csv
import html
import json
import struct
import textwrap
import unicodedata
import zlib
from pathlib import Path

from .metrics import ranks
from .storage import write_json

# A tiny bitmap font keeps PNG export runnable on stock Python, without a browser.
_GLYPHS = {
    "A": "01110/10001/10001/11111/10001/10001/10001", "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01111/10000/10000/10000/10000/10000/01111", "D": "11110/10001/10001/10001/10001/10001/11110",
    "E": "11111/10000/10000/11110/10000/10000/11111", "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01111/10000/10000/10111/10001/10001/01111", "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "11111/00100/00100/00100/00100/00100/11111", "J": "00111/00010/00010/00010/10010/10010/01100",
    "K": "10001/10010/10100/11000/10100/10010/10001", "L": "10000/10000/10000/10000/10000/10000/11111",
    "M": "10001/11011/10101/10101/10001/10001/10001", "N": "10001/11001/10101/10011/10001/10001/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110", "P": "11110/10001/10001/11110/10000/10000/10000",
    "Q": "01110/10001/10001/10001/10101/10010/01101", "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110", "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110", "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/10101/01010", "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100", "Z": "11111/00001/00010/00100/01000/10000/11111",
    "0": "01110/10001/10011/10101/11001/10001/01110", "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111", "3": "11110/00001/00001/01110/00001/00001/11110",
    "4": "00010/00110/01010/10010/11111/00010/00010", "5": "11111/10000/10000/11110/00001/00001/11110",
    "6": "01110/10000/10000/11110/10001/10001/01110", "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110", "9": "01110/10001/10001/01111/00001/00001/01110",
    "-": "00000/00000/00000/11111/00000/00000/00000", "_": "00000/00000/00000/00000/00000/00000/11111",
    ".": "00000/00000/00000/00000/00000/00110/00110", ":": "00000/00110/00110/00000/00110/00110/00000",
    "/": "00001/00001/00010/00100/01000/10000/10000", ">": "10000/01000/00100/00010/00100/01000/10000",
    "+": "00000/00100/00100/11111/00100/00100/00000", "=": "00000/00000/11111/00000/11111/00000/00000",
    "?": "01110/10001/00001/00010/00100/00000/00100", "%": "11001/11010/00100/01000/10110/00110/00000",
    "(": "00010/00100/01000/01000/01000/00100/00010", ")": "01000/00100/00010/00010/00010/00100/01000",
    ",": "00000/00000/00000/00000/00110/00100/01000", ";": "00000/00110/00110/00000/00110/00100/01000",
    "'": "00100/00100/00000/00000/00000/00000/00000",
    " ": "00000/00000/00000/00000/00000/00000/00000",
}


def png_snapshot(path, title, banner, sections):
    lines = [(title, 3, (21, 36, 55)), (banner, 2, (170, 55, 25))]
    for heading, values in sections:
        lines.append((heading, 2, (21, 36, 55)))
        lines.extend((value, 2, (54, 65, 80)) for value in values)
    width, height = 1500, 60 + sum(scale * 7 + 19 for _, scale, _ in lines)
    wrapped = []
    for value, scale, color in lines:
        value = unicodedata.normalize("NFKD", value).encode("ascii", errors="replace").decode()
        wrapped.extend((line, scale, color) for line in textwrap.wrap(value, width=(width - 50) // (6 * scale)) or [""])
    lines = wrapped
    height = 60 + sum(scale * 7 + 19 for _, scale, _ in lines)
    pixels = bytearray((248, 250, 252)) * (width * height)
    y = 25
    for text, scale, color in lines:
        x = 25
        for char in text.upper()[:(width - 50) // (6 * scale)]:
            for row, bitmap in enumerate(_GLYPHS.get(char, _GLYPHS["?"]).split("/")):
                for column, bit in enumerate(bitmap):
                    if bit != "1":
                        continue
                    for dy in range(scale):
                        start = ((y + row * scale + dy) * width + x + column * scale) * 3
                        pixels[start:start + scale * 3] = bytes(color) * scale
            x += 6 * scale
        y += scale * 7 + 19
    raw = b"".join(b"\x00" + bytes(pixels[row * width * 3:(row + 1) * width * 3]) for row in range(height))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def selection_text(decision, names):
    proposal = decision["proposal"]
    if "selection" in proposal:
        return " + ".join(names[value] for value in proposal["selection"]) or proposal["status"]
    return "; ".join("%s: %s > %s" % (names[move["candidate_id"]], move["from"], move["to"]) for move in proposal.get("moves", [])) or proposal["status"]


def write_report(fixture, recordings, report, directory):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / "report.json", report)
    names = {candidate["id"]: candidate["name"] for candidate in fixture["candidates"]}
    rows = {(row["source"], row["profile_id"], row["variant"]): row for row in recordings["rows"]}
    with (path / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["profile", "variant", "candidate_id", "candidate_name", "qloo_rank", "gemini_rank", "qloo_raw_affinity", "in_common_pool", "evidence_mode"])
        for profile in fixture["profiles"]:
            for variant in profile["variants"]:
                a = rows.get(("qloo", profile["id"], variant), {})
                b = rows.get(("gemini", profile["id"], variant), {})
                ra, rb = ranks(a.get("groups", [])), ranks(b.get("groups", []))
                for candidate in fixture["candidates"]:
                    cid = candidate["id"]
                    writer.writerow([profile["id"], variant, cid, candidate["name"], ra.get(cid, ""), rb.get(cid, ""),
                                     a.get("raw_scores", {}).get(cid, ""), cid in report["common_pool"], report["mode"]])
    with (path / "decisions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "variant", "utility", "status", "decision", "cost_units", "worst_fit", "regret", "constraint_valid", "proposal_id"])
        for decision in report["decisions"]:
            proposal = decision["proposal"]
            writer.writerow([decision["source"], decision["variant"], decision["utility"], proposal["status"], selection_text(decision, names),
                             proposal.get("cost_units", ""), proposal.get("worst_fit", ""), json.dumps(proposal.get("regret", {})), decision["validation"]["valid"], decision["proposal_id"]])
    if report["mode"] == "synthetic":
        banner = "SYNTHETIC VERIFICATION - NO LIVE GATES PASSED"
    elif report["ranking_failures"] or report["missing_rows"]:
        banner = "LIVE EVIDENCE INCOMPLETE - PRODUCT DECISION: " + report["selection"].upper()
    else:
        banner = "LIVE EXPERIMENT - PRODUCT DECISION: " + report["selection"].upper()
    if report["mode"] == "live" and fixture["provenance"] == "synthetic_test":
        banner += " - SYNTHETIC OPERATIONAL INPUTS"
    baseline_models = sorted({row["model"] for row in recordings["rows"]
                              if row["source"] == "gemini" and row.get("status") == "ok"
                              and isinstance(row.get("model"), str)})
    baseline_label = "Gemini baseline: " + (", ".join(baseline_models) or
                                           ("synthetic test rankings" if report["mode"] == "synthetic" else "not yet recorded"))
    gate_rows = ["%s: %s" % (name.replace("_", " "), value["status"]) for name, value in report["gates"].items()]
    choice_rows = ["%s / %s: %s" % (value["source"], value["variant"], selection_text(value, names))
                   for value in report["decisions"] if value["utility"] == "ordinal"]
    if not choice_rows:
        choice_rows = ["Matched-source rankings incomplete. Decisions remain pending."]
    human_rows = ["%s: Qloo %s / Gemini %s (%s matched pairs)" % (value["participant_id"],
                  "%.1f%%" % (100 * value["qloo"]) if "qloo" in value else "pending",
                  "%.1f%%" % (100 * value["gemini"]) if "gemini" in value else "pending", value.get("compared", 0)) for value in report["human_results"]]
    sections = [("Baseline", [baseline_label]), ("Gates", gate_rows), ("Ordinal decisions", choice_rows)]
    ranking_previews = []
    for profile in fixture["profiles"]:
        for variant in profile["variants"]:
            for source in ("qloo", "gemini"):
                row = rows.get((source, profile["id"], variant), {})
                if row.get("status") == "ok" and row.get("groups"):
                    order = [value for group in row["groups"] for value in group]
                    midranks = ranks(row["groups"])
                    ranking_previews.append({"source": source, "profile": profile["id"], "variant": variant,
                                             "ranked": len(order), "top_three": [names[value] for value in order[:3]],
                                             "top_ranks": [midranks[value] for value in order[:3]]})
    if ranking_previews:
        sections.append(("Captured ranking previews - baseline gates may still be pending",
                         ["%s / %s / %s (%s ranked): %s" % (value["source"], value["profile"], value["variant"],
                          value["ranked"], "; ".join("%s (rank %g)" % pair for pair in
                                                    zip(value["top_three"], value["top_ranks"]))) for value in ranking_previews]))
    if human_rows:
        sections.append(("Human preference pilot", human_rows))
    sections.append(("Interpretation", ["Rank-based fit is a relative index, not a satisfaction probability.",
                                         "Baseline wins, ties, failures, and missing evidence remain visible."]))
    if fixture["provenance"] == "synthetic_test":
        sections[-1][1].append("Ownership, offers, availability, and costs are synthetic test conditions.")
    png_snapshot(path / "comparison.png", fixture["kind"] + " evidence sprint", banner, sections)
    esc = html.escape
    document = ["<!doctype html><meta charset='utf-8'><title>Evidence sprint</title>",
                "<style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px}td,th{border:1px solid #ccc;padding:8px;text-align:left}table{border-collapse:collapse;width:100%}pre{white-space:pre-wrap}.banner{background:#fff0d5;padding:16px}</style>",
                "<h1>" + esc(fixture["kind"]) + " evidence sprint</h1><p class='banner'>" + esc(banner) + "</p>",
                "<p>" + esc(baseline_label) + "</p><p>Fixture: " + esc(fixture["frozen_hash"]) + "</p><h2>Gates</h2><table><tr><th>Gate</th><th>Status</th><th>Evidence</th></tr>"]
    for name, gate in report["gates"].items():
        document.append("<tr><td>%s</td><td>%s</td><td><pre>%s</pre></td></tr>" % (esc(name), esc(gate["status"]), esc(json.dumps(gate["detail"], indent=2, ensure_ascii=False))))
    document.append("</table><h2>Matched decisions and sensitivity</h2><table><tr><th>Source</th><th>Variant</th><th>Utility</th><th>Decision</th><th>Valid</th></tr>")
    for value in report["decisions"]:
        document.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (esc(value["source"]), esc(value["variant"]), esc(value["utility"]), esc(selection_text(value, names)), value["validation"]["valid"]))
    document.append("</table><h2>Captured ranking previews</h2><p>These show each successful request's own pool. They do not establish a matched baseline comparison or participant preference accuracy. Ties use equal midranks in these previews and the full CSV.</p><table><tr><th>Source</th><th>Profile</th><th>Variant</th><th>Ranked</th><th>First three returned (with ranks)</th></tr>")
    for value in ranking_previews:
        preview = "; ".join("%s (rank %g)" % pair for pair in zip(value["top_three"], value["top_ranks"]))
        document.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (esc(value["source"]), esc(value["profile"]), esc(value["variant"]), value["ranked"], esc(preview)))
    document.append("</table><h2>Limits</h2><ul>" + "".join("<li>" + esc(value) + "</li>" for value in report["limitations"]) + "</ul>")
    document.append("<p>Download <a href='comparison.csv'>ranking comparison</a>, <a href='decisions.csv'>decisions</a>, <a href='comparison.png'>PNG snapshot</a>, or <a href='report.json'>full report</a>.</p>")
    (path / "report.html").write_text("\n".join(document) + "\n", encoding="utf-8")
    declared = next((value for value in report["decisions"] if value["source"] == "qloo" and value["variant"] == "declared" and value["utility"] == "ordinal"), None)
    if declared:
        review = {"recorded_at": None, "participants": {participant["id"]: {"accepted": None, "reason": ""} for participant in fixture["participants"]}}
        template_path = path / "acceptance-template.json"
        if not template_path.exists():
            write_json(template_path, {"loop_acceptance": {declared["proposal_id"]: review}})
    return path / "report.html"
