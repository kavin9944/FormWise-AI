"""
checklist.py – FormWise AI Phase 7 Step 1
Document Checklist Logic & Matching Engine.

Functions:
  • normalize_requirement: Validates and formats a single document requirement.
  • normalize_requirements: Normalizes a list of raw document requirements.
  • find_suggested_match: Deterministic filename keyword matching against uploaded documents.
  • build_checklist: Combines requirements, uploaded documents, and student confirmations.
  • confirm_document_match: Validates and records a student-confirmed document match.

Rules:
  • Explicitly requested documents may be mandatory.
  • AI-suggested documents are NEVER automatically mandatory.
  • Uncertain matches are tagged 'suggested_match', never 'matched'.
  • Only student-confirmed matches receive status 'matched'.
  • Functions operate purely on provided metadata dicts; no filesystem or network access.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Keywords dictionary for heuristic document suggestions
# ---------------------------------------------------------------------------
_KEYWORD_MAP: Dict[str, List[str]] = {
    "marksheet": [
        "marksheet", "mark_sheet", "mark sheet", "grade", "10th", "12th",
        "sslc", "hsc", "cbse", "icse", "scorecard", "transcript",
    ],
    "transfer_certificate": [
        "transfer_certificate", "transfer certificate", "tc", "school_leaving",
        "transfer", "migration", "leaving_certificate",
    ],
    "photograph": [
        "photo", "photograph", "passport_photo", "passport photo",
        "pic", "image", "avatar", "profile_pic",
    ],
    "identity_proof": [
        "aadhaar", "aadhar", "identity", "id_card", "id card", "voter",
        "pan_card", "pan card", "pancard", "passport", "driving", "national_id",
    ],
    "community_certificate": [
        "community", "caste", "reservation", "category", "bc", "mbc",
        "sc", "st", "obc", "ews",
    ],
    "income_certificate": [
        "income", "salary", "pay_slip", "payslip", "income_cert",
    ],
    "signature": [
        "signature", "sign", "specimen_signature",
    ],
}

# Recognized standard document types
VALID_DOC_TYPES: Set[str] = {
    "marksheet",
    "transfer_certificate",
    "photograph",
    "identity_proof",
    "community_certificate",
    "income_certificate",
    "signature",
    "other",
}


# ---------------------------------------------------------------------------
# 1. Document Requirement Normalization
# ---------------------------------------------------------------------------

def normalize_requirement(raw: Any) -> Optional[Dict[str, Any]]:
    """
    Normalizes a single raw requirement entry into standard schema:
      - doc_id: str (snake_case identifier)
      - doc_type: str (standardized type string)
      - title_en: str
      - title_ta: str
      - is_mandatory: bool
      - is_ai_suggested: bool

    Returns None if the entry is malformed or missing essential titles.
    """
    if not isinstance(raw, dict):
        return None

    # Title extraction
    title_en = str(raw.get("title_en") or raw.get("title") or raw.get("document_name") or "").strip()
    if not title_en:
        return None

    title_ta = str(raw.get("title_ta") or raw.get("tamil_title") or "").strip()

    # doc_id generation / sanitization
    raw_id = str(raw.get("doc_id") or raw.get("id") or title_en).strip().lower()
    doc_id = re.sub(r"[^a-z0-9_]+", "_", raw_id).strip("_")
    if not doc_id:
        doc_id = "document_" + str(abs(hash(title_en)))[:8]

    # doc_type determination
    raw_type = str(raw.get("doc_type") or raw.get("type") or "").strip().lower()
    if raw_type in VALID_DOC_TYPES:
        doc_type = raw_type
    else:
        # Heuristic doc_type inference from title
        doc_type = "other"
        title_lower = title_en.lower()
        for candidate_type, keywords in _KEYWORD_MAP.items():
            if any(kw in title_lower for kw in keywords):
                doc_type = candidate_type
                break

    # Flags
    is_ai_suggested = bool(raw.get("is_ai_suggested", False))

    # STRICT RULE: AI-suggested documents can NEVER be mandatory automatically
    if is_ai_suggested:
        is_mandatory = False
    else:
        is_mandatory = bool(raw.get("is_mandatory", False))

    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "title_en": title_en,
        "title_ta": title_ta,
        "is_mandatory": is_mandatory,
        "is_ai_suggested": is_ai_suggested,
    }


def normalize_requirements(raw_list: Any) -> List[Dict[str, Any]]:
    """
    Normalizes a list of requirement entries.
    Safely rejects malformed entries and prevents duplicate doc_ids.
    """
    if not isinstance(raw_list, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for item in raw_list:
        norm = normalize_requirement(item)
        if not norm:
            continue

        base_id = norm["doc_id"]
        unique_id = base_id
        counter = 2
        while unique_id in seen_ids:
            unique_id = f"{base_id}_{counter}"
            counter += 1

        norm["doc_id"] = unique_id
        seen_ids.add(unique_id)
        normalized.append(norm)

    return normalized


# ---------------------------------------------------------------------------
# 2. Document Matching Heuristics
# ---------------------------------------------------------------------------

def find_suggested_match(
    requirement: Dict[str, Any],
    uploaded_documents: List[Dict[str, Any]],
    already_matched_doc_ids: Set[str],
) -> Optional[Dict[str, Any]]:
    """
    Deterministically suggests a possible matching document from uploaded_documents
    based on original_filename keyword matching.

    Rules:
      • Case-insensitive.
      • Excludes documents that are already confirmed/matched to another requirement.
      • Does NOT declare confirmed status — this is only a candidate suggestion.
      • Returns None if no clear keyword match is found.
    """
    doc_type = requirement.get("doc_type", "other")
    title_en = requirement.get("title_en", "").lower()

    # Build search tokens
    keywords: List[str] = []
    if doc_type in _KEYWORD_MAP:
        keywords.extend(_KEYWORD_MAP[doc_type])

    # Add significant tokens from title_en (length > 3)
    title_tokens = [t for t in re.split(r"[^a-z0-9]+", title_en) if len(t) > 3]
    for token in title_tokens:
        if token not in keywords:
            keywords.append(token)

    for doc in uploaded_documents:
        doc_id = str(doc.get("document_id") or doc.get("id") or "")
        if not doc_id or doc_id in already_matched_doc_ids:
            continue

        filename = str(doc.get("original_filename") or "").lower()
        if not filename:
            continue

        # Clean filename for token matching
        clean_name = re.sub(r"[^a-z0-9]+", " ", filename)

        for kw in keywords:
            # Check for substring or token match
            if kw in filename or kw in clean_name:
                return doc

    return None


# ---------------------------------------------------------------------------
# 3. Checklist Construction
# ---------------------------------------------------------------------------

def build_checklist(
    requirements: List[Dict[str, Any]],
    uploaded_documents: List[Dict[str, Any]],
    confirmed_matches: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Builds the complete document checklist result.

    Parameters:
      requirements: Normalized list of document requirements.
      uploaded_documents: List of document metadata objects owned by authenticated user.
      confirmed_matches: Optional dict mapping { requirement_doc_id: uploaded_document_id }
                         representing student-confirmed assignments.

    Returns dict with summary counts and per-requirement checklist items:
      - total_required: int
      - mandatory_count: int
      - optional_count: int
      - matched_count: int
      - missing_mandatory_count: int
      - items: list of checklist item dicts
    """
    if confirmed_matches is None:
        confirmed_matches = {}

    # Map uploaded documents by document_id for rapid O(1) lookup
    uploads_by_id: Dict[str, Dict[str, Any]] = {}
    for doc in uploaded_documents:
        did = str(doc.get("document_id") or doc.get("id") or "").strip()
        if did:
            uploads_by_id[did] = doc

    # Track which uploads are claimed to prevent duplicate suggestions
    used_upload_ids: Set[str] = set()
    for req_id, up_id in confirmed_matches.items():
        if up_id in uploads_by_id:
            used_upload_ids.add(up_id)

    items: List[Dict[str, Any]] = []
    matched_count = 0
    missing_mandatory_count = 0
    mandatory_count = 0

    for req in requirements:
        req_id = req["doc_id"]
        is_mandatory = req["is_mandatory"]
        if is_mandatory:
            mandatory_count += 1

        confirmed_doc_id = confirmed_matches.get(req_id)
        if confirmed_doc_id and confirmed_doc_id in uploads_by_id:
            matched_doc = uploads_by_id[confirmed_doc_id]
            matched_count += 1
            items.append({
                "doc_id": req_id,
                "doc_type": req["doc_type"],
                "title_en": req["title_en"],
                "title_ta": req["title_ta"],
                "is_mandatory": is_mandatory,
                "is_ai_suggested": req["is_ai_suggested"],
                "status": "matched",
                "matched_document_id": confirmed_doc_id,
                "matched_filename": matched_doc.get("original_filename", ""),
                "suggested_document_id": None,
                "suggested_filename": None,
            })
            continue

        # Not confirmed: check for suggested match
        suggested = find_suggested_match(req, uploaded_documents, used_upload_ids)
        if suggested:
            sugg_id = str(suggested.get("document_id") or suggested.get("id"))
            used_upload_ids.add(sugg_id)
            if is_mandatory:
                missing_mandatory_count += 1

            items.append({
                "doc_id": req_id,
                "doc_type": req["doc_type"],
                "title_en": req["title_en"],
                "title_ta": req["title_ta"],
                "is_mandatory": is_mandatory,
                "is_ai_suggested": req["is_ai_suggested"],
                "status": "suggested_match",
                "matched_document_id": None,
                "matched_filename": None,
                "suggested_document_id": sugg_id,
                "suggested_filename": suggested.get("original_filename", ""),
            })
        else:
            if is_mandatory:
                missing_mandatory_count += 1

            items.append({
                "doc_id": req_id,
                "doc_type": req["doc_type"],
                "title_en": req["title_en"],
                "title_ta": req["title_ta"],
                "is_mandatory": is_mandatory,
                "is_ai_suggested": req["is_ai_suggested"],
                "status": "missing",
                "matched_document_id": None,
                "matched_filename": None,
                "suggested_document_id": None,
                "suggested_filename": None,
            })

    return {
        "total_required": len(requirements),
        "mandatory_count": mandatory_count,
        "optional_count": len(requirements) - mandatory_count,
        "matched_count": matched_count,
        "missing_mandatory_count": missing_mandatory_count,
        "is_complete": missing_mandatory_count == 0,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 4. Student Confirmation Helper
# ---------------------------------------------------------------------------

def confirm_document_match(
    requirements: List[Dict[str, Any]],
    uploaded_documents: List[Dict[str, Any]],
    current_confirmed_matches: Dict[str, str],
    target_req_id: str,
    selected_document_id: Optional[str],
) -> Tuple[bool, Dict[str, str], Optional[str]]:
    """
    Validates and updates a student's confirmed match.

    Parameters:
      requirements: Normalized list of checklist requirements.
      uploaded_documents: Authenticated user's uploaded documents list.
      current_confirmed_matches: Current dict { req_id: document_id }.
      target_req_id: The checklist requirement identifier.
      selected_document_id: The uploaded document_id chosen by the student (or None/empty to unconfirm).

    Returns:
      (success: bool, updated_confirmed_matches: dict, error_message: Optional[str])

    Security:
      - Validates that target_req_id exists in requirements.
      - Validates that selected_document_id strictly belongs to the supplied uploaded_documents list.
      - Disallows mapping a document that doesn't exist in the user's storage.
    """
    # 1. Validate requirement exists
    req_ids = {r["doc_id"] for r in requirements}
    if target_req_id not in req_ids:
        return False, current_confirmed_matches, f"Checklist requirement '{target_req_id}' does not exist."

    updated = dict(current_confirmed_matches)

    # If unconfirming / removing match
    if not selected_document_id:
        updated.pop(target_req_id, None)
        return True, updated, None

    # 2. Validate selected document exists in user's uploaded documents list
    valid_upload_ids = {str(d.get("document_id") or d.get("id")) for d in uploaded_documents}
    if selected_document_id not in valid_upload_ids:
        return False, current_confirmed_matches, "Selected document not found in your uploaded documents."

    # 3. Record confirmed match
    updated[target_req_id] = selected_document_id
    return True, updated, None
