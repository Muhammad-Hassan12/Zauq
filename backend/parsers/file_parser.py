import io
import os
import csv
import base64
from typing import Dict, Any, List, Optional
from pypdf import PdfReader
from docx import Document
import openpyxl

TEXT_EXTENSIONS = {
    ".txt", ".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml",
    ".md", ".log", ".sh", ".sql", ".c", ".cpp", ".h", ".java", ".go", ".rs",
    ".php", ".xml", ".ini", ".env", ".toml", ".bat", ".ps1"
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

def parse_pdf(content_bytes: bytes) -> str:
    """Extracts text page-by-page from PDF bytes."""
    try:
        reader = PdfReader(io.BytesIO(content_bytes))
        pages_text = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(f"--- Page {idx + 1} ---\n{text.strip()}")
        return "\n\n".join(pages_text) if pages_text else "[PDF file contains no extractable text]"
    except Exception as e:
        return f"[PDF Parsing Error: {str(e)}]"

def parse_docx(content_bytes: bytes) -> str:
    """Extracts text and tables from Word (.docx) bytes."""
    try:
        doc = Document(io.BytesIO(content_bytes))
        output = []
        for p in doc.paragraphs:
            if p.text.strip():
                output.append(p.text.strip())

        for table_idx, table in enumerate(doc.tables):
            output.append(f"\n--- Table {table_idx + 1} ---")
            for row in table.rows:
                row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                output.append("| " + " | ".join(row_cells) + " |")

        return "\n".join(output) if output else "[Docx file contains no text]"
    except Exception as e:
        return f"[Docx Parsing Error: {str(e)}]"

def parse_excel(content_bytes: bytes, filename: str) -> str:
    """Extracts sheet data from Excel (.xlsx) or CSV bytes into Markdown tables."""
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".csv":
        try:
            text = content_bytes.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if not rows:
                return "[CSV file is empty]"
            markdown_rows = []
            markdown_rows.append("| " + " | ".join(rows[0]) + " |")
            markdown_rows.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
            for r in rows[1:100]:  # Limit to first 100 rows
                markdown_rows.append("| " + " | ".join(r) + " |")
            return "\n".join(markdown_rows)
        except Exception as e:
            return f"[CSV Parsing Error: {str(e)}]"

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
        sheets_output = []
        for sheet_name in wb.sheetnames[:3]:  # Max 3 sheets
            sheet = wb[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            sheets_output.append(f"--- Sheet: {sheet_name} ---")
            header = [str(c or "") for c in rows[0]]
            sheets_output.append("| " + " | ".join(header) + " |")
            sheets_output.append("| " + " | ".join(["---"] * len(header)) + " |")
            for r in rows[1:50]:  # Limit to 50 rows per sheet
                row_str = [str(c or "") for c in r]
                sheets_output.append("| " + " | ".join(row_str) + " |")
        return "\n\n".join(sheets_output) if sheets_output else "[Excel workbook is empty]"
    except Exception as e:
        return f"[Excel Parsing Error: {str(e)}]"

def parse_text(content_bytes: bytes) -> str:
    """Decodes plain text, code, JSON, and log files."""
    try:
        return content_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        return f"[Text Decoding Error: {str(e)}]"

def parse_attachment(content_bytes: bytes, filename: str, content_type: str = "") -> Dict[str, Any]:
    """
    Main file parsing dispatcher. Detects file type and returns parsed content payload.
    """
    ext = os.path.splitext(filename.lower())[1]

    if ext in IMAGE_EXTENSIONS or content_type.startswith("image/"):
        mime = content_type or f"image/{ext.replace('.', '')}"
        b64_str = base64.b64encode(content_bytes).decode("utf-8")
        return {
            "type": "image",
            "filename": filename,
            "mime_type": mime,
            "bytes_b64": b64_str,
            "content": f"[Attached Image: {filename}]"
        }

    if ext == ".pdf":
        extracted = parse_pdf(content_bytes)
    elif ext == ".docx":
        extracted = parse_docx(content_bytes)
    elif ext in [".xlsx", ".xls", ".csv"]:
        extracted = parse_excel(content_bytes, filename)
    elif ext in TEXT_EXTENSIONS or content_type.startswith("text/") or "json" in content_type:
        extracted = parse_text(content_bytes)
    else:
        # Fallback attempt to read as text
        extracted = parse_text(content_bytes)

    # Truncate extremely long document extractions to 12,000 chars to avoid exceeding model prompt windows
    if len(extracted) > 12000:
        extracted = extracted[:11900] + "\n... [Document Content Truncated for Prompt Length]"

    return {
        "type": "text",
        "filename": filename,
        "content": f"```\n{extracted}\n```"
    }
