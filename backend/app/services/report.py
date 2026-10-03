from __future__ import annotations
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from .assessment import inr


def build_pdf(rec: dict, client_text: str) -> bytes:
    a = rec["result"]
    p = a["product"]
    ss = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="StructuraAI client summary")
    el = [Paragraph("StructuraAI - Client Summary", ss["Title"]),
          Paragraph(f"Product: {p['product_type']} on {p['underlying']}, {p['tenor_months']} months, notional {inr(p['notional'])}", ss["Normal"]),
          Paragraph(f"Assessment #{rec['id']} | Decision: <b>{a['decision']}</b> | Model: {rec['model_version']}", ss["Normal"]),
          Spacer(1, 10)]
    if a["data_source"] == "synthetic_fallback":
        el.append(Paragraph("<font color='red'>Demo data: synthetic fallback prices were used.</font>", ss["Normal"]))
    el += [Paragraph("What this means for you", ss["Heading2"]), Paragraph(client_text.replace("\n", "<br/>"), ss["Normal"]), Spacer(1, 8),
           Paragraph("If the market moves...", ss["Heading2"])]
    rows = [["Market move", "Final value", "Profit / loss", "Barrier breached"]] + \
           [[f"{s['move_pct']:+g}%", inr(s["final_value"]), f"{s['pnl_pct']:+g}%", {True: "Yes", False: "No", None: "-"}[s["barrier_breached"]]] for s in a["scenarios"]]
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    el += [t, Spacer(1, 10), Paragraph("Past results do not guarantee future results. This is decision support, not an approval to sell.", ss["Italic"])]
    doc.build(el)
    return buf.getvalue()
