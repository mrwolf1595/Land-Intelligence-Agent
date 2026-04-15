"""
Generates the PDF proposal through WeasyPrint and Jinja2.
Handles Arabic Left-To-Right text joining.

WeasyPrint requires GTK native libraries (available on Linux/Kali).
On Windows, PDF generation is skipped gracefully — scraping and analysis
still work without it.
"""
import os
import uuid
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    from weasyprint import HTML
    _PDF_AVAILABLE = True
except Exception:
    _PDF_AVAILABLE = False

def shape_arabic(text: str) -> str:
    """Format Arabic connecting letters correctly for Weasyprint."""
    if not text:
        return ""
    if not _PDF_AVAILABLE:
        return str(text)
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def generate_proposal(analysis: dict, financial: dict, mockup: dict = None) -> str:
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("proposal_template.html")
    
    img_path = mockup.get("image_path", "") if mockup else ""
    if img_path and os.path.exists(img_path):
        img_path = Path(img_path).resolve().as_uri()

    context = {
        "title": shape_arabic(f"دراسة فرصة عقارية - {analysis.get('location', 'موقع غير محدد')}"),
        "dev_type_label": shape_arabic(analysis.get("recommended_development", "عمارة")),
        "area": f"{analysis.get('land_area_sqm', 0):,} m2",
        "asking_price": f"{int(analysis.get('asking_price_sar', 0)):,} SAR",
        "roi_pct": f"{financial.get('roi_pct', 0)} %",
        "mockup_image_uri": img_path,
        "dev_reasoning": shape_arabic(analysis.get("development_reasoning", "")),
        "total_investment": f"{int(financial.get('total_investment_sar', 0)):,} SAR",
        "projected_revenue": f"{int(financial.get('total_revenue_sar', 0)):,} SAR",
        "gross_profit": f"{int(financial.get('gross_profit_sar', 0)):,} SAR",
        "timeline_months": str(financial.get("timeline_months", "?")),
        "flags": [shape_arabic(f) for f in analysis.get("flags", [])],
        "risks": [shape_arabic(r) for r in analysis.get("risks", [])],
        "map_location": shape_arabic(analysis.get("location", ""))
    }
    
    html_str = template.render(context)
    
    output_filename = f"output/reports/Proposal_{uuid.uuid4().hex[:6]}.pdf"
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    
    if not _PDF_AVAILABLE:
        print("[proposal] WeasyPrint unavailable (requires GTK — run on Linux). Skipping PDF.")
        return None

    try:
        HTML(string=html_str).write_pdf(output_filename)
        return output_filename
    except Exception as e:
        print(f"[proposal] Failed to generate PDF: {e}")
        return None
