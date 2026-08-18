# Document Formatting Specification

Read this file during Batch 3 when generating the .docx report. Use the docx skill
for implementation — read the `docx` skill first (invoke it by name; do not hardcode a path to it).

---

## Branding Colors

| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Zennify Teal | #27BBAF | (39, 187, 175) | Headings, accent elements, table headers |
| Zennify Teal Dark | #1A8A80 | (26, 138, 128) | H2 headings, borders |
| Zennify Teal Light | #E0F5F3 | (224, 245, 243) | Table alt rows, insight card backgrounds |
| Text Dark | #1E1E1E | — | Body text |
| Text Medium | #4A4A4A | — | Captions, secondary text |
| White | #FFFFFF | — | Table header text, backgrounds |
| Border Gray | #CCCCCC | — | Table borders |

---

## Typography (DM Sans)

| Style | Font | Size | Weight | Color |
|-------|------|------|--------|-------|
| Title | DM Sans | 28pt | Bold | #27BBAF |
| Heading 1 | DM Sans | 18pt | Bold | #27BBAF |
| Heading 2 | DM Sans | 14pt | Bold | #1A8A80 |
| Heading 3 | DM Sans | 12pt | Bold | #1E1E1E |
| Body | DM Sans | 11pt | Regular | #1E1E1E |
| Caption | DM Sans | 9pt | Italic | #4A4A4A |
| Table Header | DM Sans | 10pt | Bold | #FFFFFF (on #27BBAF bg) |
| Table Body | DM Sans | 10pt | Regular | #1E1E1E |
| Footer | DM Sans | 8pt | Regular | #4A4A4A |

**Note**: DM Sans is a Google Font. Document will render correctly only if the font is
installed on the machine opening it. Add a note in the cover page.

---

## Page Setup

- Size: US Letter (8.5" × 11")
- Margins: 1" all sides
- Orientation: Portrait
- Line spacing: 1.15 for body text

---

## Cover Page

1. Zennify Teal horizontal rule at top
2. Title: "Digital Maturity Assessment — Public Evidence Research" (DM Sans 28pt Bold, Teal)
3. Subtitle: [Entity Name] (DM Sans 18pt Bold, Dark)
4. Date of assessment
5. Classification: [Subvertical]
6. Disclaimer: "This document contains ceiling estimates based on public evidence only.
   No maturity scores are assigned. Actual maturity may be lower."
7. "CONFIDENTIAL — Prepared by Zennify"

## Header/Footer

- **Header**: "Zennify — Digital Maturity Assessment | [Entity Name]" (DM Sans 8pt, Teal)
- **Footer**: "CONFIDENTIAL | Page [number] | Ceiling estimates only — not maturity scores" (DM Sans 8pt, Medium)
- Page break between each D-section

## Table Formatting

- Header row: #27BBAF background, white bold text
- Alternating rows: white / #E0F5F3
- Borders: thin #CCCCCC
- Cell padding: 0.05"
- **Zennify-priority highlight**: In tech tables, rows for Zennify-priority platforms get
  a 3pt left border in #27BBAF

## Insight Card Formatting

- Left border: 3pt #27BBAF
- Background: #E0F5F3
- Padding: 0.1" all sides
- Field labels: DM Sans 10pt Bold
- Field values: DM Sans 10pt Regular

## Ceiling Estimate Formatting

- Estimate value: Bold #27BBAF
- Uncertainty band: Regular #4A4A4A in parentheses
- Example: **L3.5** (±0.5)

---

## python-docx Implementation Notes

```python
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# Set default font
style = doc.styles['Normal']
style.font.name = 'DM Sans'
style.font.size = Pt(11)

# Heading colors
doc.styles['Heading 1'].font.color.rgb = RGBColor(0x27, 0xBB, 0xAF)
doc.styles['Heading 2'].font.color.rgb = RGBColor(0x1A, 0x8A, 0x80)

# Table cell shading
shading = OxmlElement('w:shd')
shading.set(qn('w:fill'), '27BBAF')
```

Save to `/mnt/user-data/outputs/DMA_Report_[Entity]_[Date].docx`
