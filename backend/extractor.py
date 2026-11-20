"""
FormWise AI - Document Extraction Service
Extracts text and structured field content from PDFs and Images using
PyMuPDF (fitz) and Tesseract OCR (pytesseract + Pillow).
"""

import os
import io
import shutil
from typing import Dict, Any, Optional
from PIL import Image
import pymupdf  # PyMuPDF
import pytesseract

# 1. Configuration Limits
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PDF_PAGES = 20

# 2. Configurable Tesseract OCR binary path and default language
TESSERACT_CANDIDATES = [
    os.environ.get("TESSERACT_PATH", "").strip(),
    os.environ.get("TESSERACT_CMD", "").strip(),
    shutil.which("tesseract") or "",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]

TESSERACT_EXE_PATH = None
TESSERACT_AVAILABLE = False

for candidate in TESSERACT_CANDIDATES:
    if candidate and os.path.isfile(candidate):
        TESSERACT_EXE_PATH = candidate
        TESSERACT_AVAILABLE = True
        pytesseract.pytesseract.tesseract_cmd = candidate
        break

if not TESSERACT_AVAILABLE and shutil.which("tesseract"):
    TESSERACT_AVAILABLE = True
    pytesseract.pytesseract.tesseract_cmd = "tesseract"

DEFAULT_OCR_LANGUAGE = os.environ.get("OCR_LANGUAGE", "eng")

# 3. Magic Byte Signatures for validation
MAGIC_SIGNATURES = {
    "pdf": b"%PDF-",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
}


def validate_file_signature(file_path: str, expected_ext: str) -> bool:
    """
    Validates actual file header against expected magic bytes signature.
    """
    expected_magic = MAGIC_SIGNATURES.get(expected_ext.lower())
    if not expected_magic:
        return False

    try:
        with open(file_path, "rb") as f:
            header = f.read(len(expected_magic))
            return header == expected_magic
    except Exception:
        return False


def extract_text_from_image(image_path: str, lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts text from an image file (PNG, JPG, JPEG) using Tesseract OCR.
    Returns structured result with success status and text or error details.
    """
    if not TESSERACT_AVAILABLE:
        return {
            "success": False,
            "text": "",
            "error": (
                "Tesseract OCR is not installed or configured on this machine. "
                "To extract text from image files (PNG/JPG), please install Tesseract OCR "
                "from https://github.com/UB-Mannheim/tesseract/wiki and specify TESSERACT_PATH in .env."
            )
        }

    ocr_lang = lang or DEFAULT_OCR_LANGUAGE

    try:
        with Image.open(image_path) as img:
            # Convert to RGB if needed (e.g. RGBA or palette)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Run OCR
            text = pytesseract.image_to_string(img, lang=ocr_lang)
            return {
                "success": True,
                "text": text.strip(),
                "error": None
            }
    except Exception as e:
        return {
            "success": False,
            "text": "",
            "error": f"Image OCR failed: {str(e)}"
        }


def extract_text_from_pdf(pdf_path: str, lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts text from a PDF document page-by-page using PyMuPDF.
    If a page has little/no direct text (< 30 chars), it renders the page to
    an image and runs Tesseract OCR fallback.

    Enforces maximum page limits (20 pages) and sequential memory-efficient processing.

    Returns:
        dict: {
            "success": bool,
            "full_text": str,
            "page_count": int,
            "pages": list of dicts [{"page": int, "text": str, "method": "native"|"ocr"|"failed", "error": Optional[str]}],
            "error": Optional[str]
        }
    """
    ocr_lang = lang or DEFAULT_OCR_LANGUAGE
    doc = None
    pages_data = []
    full_text_parts = []

    try:
        doc = pymupdf.open(pdf_path)
        page_count = len(doc)

        if page_count == 0:
            return {
                "success": False,
                "error": "PDF document contains 0 pages.",
                "page_count": 0,
                "full_text": "",
                "pages": []
            }

        if page_count > MAX_PDF_PAGES:
            return {
                "success": False,
                "error": f"PDF exceeds maximum page limit of {MAX_PDF_PAGES} pages (document has {page_count} pages).",
                "page_count": page_count,
                "full_text": "",
                "pages": []
            }

        for page_idx in range(page_count):
            page_num = page_idx + 1
            page_error = None
            text = ""
            method = "native"

            try:
                page = doc.load_page(page_idx)

                # 1. Try native PDF text extraction first
                text = page.get_text("text").strip()

                # 2. If page has minimal text (< 30 chars), fallback to OCR
                if len(text) < 30:
                    if not TESSERACT_AVAILABLE:
                        page_error = "OCR fallback skipped: Tesseract OCR is not installed or configured."
                    else:
                        try:
                            # Render page at 150 DPI for OCR
                            pix = page.get_pixmap(dpi=150)
                            img_bytes = pix.tobytes("png")
                            del pix  # Free pixmap buffer memory immediately

                            with Image.open(io.BytesIO(img_bytes)) as pil_img:
                                ocr_text = pytesseract.image_to_string(pil_img, lang=ocr_lang).strip()
                                if len(ocr_text) > len(text):
                                    text = ocr_text
                                    method = "ocr"
                        except Exception as ocr_err:
                            page_error = f"OCR fallback error: {str(ocr_err)}"
                            if not text:
                                method = "failed"

            except Exception as page_load_err:
                page_error = f"Page load error: {str(page_load_err)}"
                method = "failed"
                text = ""

            page_dict = {
                "page": page_num,
                "text": text,
                "method": method
            }
            if page_error:
                page_dict["error"] = page_error

            pages_data.append(page_dict)
            if text:
                full_text_parts.append(text)

        return {
            "success": True,
            "full_text": "\n\n".join(full_text_parts),
            "page_count": page_count,
            "pages": pages_data,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read or parse PDF: {str(e)}",
            "page_count": 0,
            "full_text": "",
            "pages": []
        }
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


def extract_document_text(file_path: str, lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Unified extraction entry point for any supported document (PDF, PNG, JPG, JPEG).

    Validates:
    - File existence
    - 10 MB maximum file size limit
    - File extension and magic byte signature
    - Maximum PDF page limit (<= 20 pages)
    """
    # 1. Existence check
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": "File does not exist on server.",
            "file_type": None,
            "page_count": 0,
            "word_count": 0,
            "full_text": "",
            "pages": []
        }

    # 2. File size limit (10 MB)
    try:
        file_size = os.path.getsize(file_path)
    except Exception as size_err:
        return {
            "success": False,
            "error": f"Unable to determine file size: {str(size_err)}",
            "file_type": None,
            "page_count": 0,
            "word_count": 0,
            "full_text": "",
            "pages": []
        }

    if file_size > MAX_FILE_SIZE_BYTES:
        return {
            "success": False,
            "error": f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of 10 MB.",
            "file_type": None,
            "page_count": 0,
            "word_count": 0,
            "full_text": "",
            "pages": []
        }

    # 3. File extension check
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext not in MAGIC_SIGNATURES:
        return {
            "success": False,
            "error": f"Unsupported file extension: .{ext}. Allowed formats: PDF, PNG, JPG, JPEG.",
            "file_type": ext.upper() if ext else None,
            "page_count": 0,
            "word_count": 0,
            "full_text": "",
            "pages": []
        }

    # 4. File magic bytes signature check
    if not validate_file_signature(file_path, ext):
        return {
            "success": False,
            "error": f"File signature mismatch: file content does not match expected .{ext} format.",
            "file_type": ext.upper(),
            "page_count": 0,
            "word_count": 0,
            "full_text": "",
            "pages": []
        }

    # 5. Extraction by format
    if ext == "pdf":
        result = extract_text_from_pdf(pdf_path=file_path, lang=lang)
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Failed to extract text from PDF."),
                "file_type": "PDF",
                "page_count": result.get("page_count", 0),
                "word_count": 0,
                "full_text": "",
                "pages": result.get("pages", [])
            }

        full_text = result.get("full_text", "")
        return {
            "success": True,
            "file_type": "PDF",
            "page_count": result.get("page_count", 1),
            "full_text": full_text,
            "pages": result.get("pages", []),
            "word_count": len(full_text.split()),
            "error": None
        }

    elif ext in ("jpg", "jpeg", "png"):
        img_result = extract_text_from_image(image_path=file_path, lang=lang)
        if not img_result.get("success"):
            return {
                "success": False,
                "error": img_result.get("error", "Failed to extract text from image."),
                "file_type": ext.upper(),
                "page_count": 1,
                "word_count": 0,
                "full_text": "",
                "pages": []
            }

        text = img_result.get("text", "")
        return {
            "success": True,
            "file_type": ext.upper(),
            "page_count": 1,
            "full_text": text,
            "pages": [{"page": 1, "text": text, "method": "ocr"}],
            "word_count": len(text.split()),
            "error": None
        }

    return {
        "success": False,
        "error": f"Unsupported file format: .{ext}",
        "file_type": ext.upper() if ext else None,
        "page_count": 0,
        "word_count": 0,
        "full_text": "",
        "pages": []
    }
