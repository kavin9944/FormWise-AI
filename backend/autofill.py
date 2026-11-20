"""
autofill.py – FormWise AI Profile-Based Autofill Helper
Provides deterministic mapping between student profile attributes
and extracted form field definitions.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


# Normalized mappings between standard profile keys and common form field patterns
PROFILE_FIELD_PATTERNS = {
    "full_name": [
        r"\b(?:full\s*name|student\s*name|applicant\s*name|candidate\s*name|name\s*of\s*the\s*student|name\s*of\s*the\s*applicant)\b",
        r"\bname\b(?!.*(?:parent|father|mother|guardian|emergency|institution|college|school|referee))",
    ],
    "first_name": [r"\b(?:first\s*name|given\s*name)\b"],
    "last_name": [r"\b(?:last\s*name|surname|family\s*name)\b"],
    "dob": [
        r"\b(?:date\s*of\s*birth|dob|birth\s*date|d\.o\.b)\b",
    ],
    "gender": [r"\b(?:gender|sex)\b"],
    "email": [r"\b(?:email|e-mail|email\s*address|e-mail\s*id)\b"],
    "phone": [
        r"\b(?:phone|mobile|cell|contact\s*number|mobile\s*number|phone\s*number|telephone)\b(?!.*(?:parent|guardian|emergency))",
    ],
    "address": [
        r"\b(?:permanent\s*address|residential\s*address|communication\s*address|present\s*address|postal\s*address|address\s*for\s*communication|address)\b",
    ],
    "city": [r"\b(?:city|town|district)\b"],
    "state": [r"\b(?:state|province)\b"],
    "pincode": [r"\b(?:pincode|pin\s*code|postal\s*code|zip\s*code|zip)\b"],
    "community": [
        r"\b(?:community|caste|category|social\s*category)\b",
    ],
    "father_name": [
        r"\b(?:father(?:'?s)?\s*name|name\s*of\s*father)\b",
    ],
    "mother_name": [
        r"\b(?:mother(?:'?s)?\s*name|name\s*of\s*mother)\b",
    ],
    "guardian_name": [
        r"\b(?:guardian(?:'?s)?\s*name|name\s*of\s*guardian)\b",
    ],
    "parent_phone": [
        r"\b(?:parent(?:'?s)?\s*phone|parent(?:'?s)?\s*mobile|guardian(?:'?s)?\s*phone|emergency\s*contact)\b",
    ],
    "aadhaar_number": [
        r"\b(?:aadhaar|aadhar|uidai|aadhaar\s*number|aadhar\s*no)\b",
    ],
    "nationality": [r"\b(?:nationality|citizenship)\b"],
    "blood_group": [r"\b(?:blood\s*group|blood\s*type)\b"],
}


def match_profile_field(field_name: str, question: str) -> Optional[str]:
    """
    Given a field name and question text from the form, returns the matching
    profile attribute key if a high-confidence match exists, else None.
    """
    text = f"{field_name} {question}".lower().strip()

    for profile_key, patterns in PROFILE_FIELD_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return profile_key

    return None


def generate_autofill_answers(
    fields: List[Dict[str, Any]],
    student_profile: Dict[str, Any],
    existing_answers: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Generates autofill answers from student profile for matching form fields.
    SAFETY: Never overwrites answers already supplied by the student in existing_answers.

    Returns:
      (autofill_dict, list_of_autofilled_field_names)
    """
    if existing_answers is None:
        existing_answers = {}

    autofill_answers: Dict[str, str] = {}
    autofilled_keys: List[str] = []

    for field in fields:
        fid = str(field.get("field_id") or field.get("field_name") or "")
        fname = str(field.get("field_name") or fid)
        q = str(field.get("question") or field.get("label") or fname)

        # Do not overwrite student-entered answers
        if existing_answers.get(fid) or existing_answers.get(fname):
            continue

        matched_profile_key = match_profile_field(fname, q)
        if matched_profile_key and matched_profile_key in student_profile:
            val = str(student_profile[matched_profile_key] or "").strip()
            if val:
                autofill_answers[fid] = val
                autofilled_keys.append(fname)

    return autofill_answers, autofilled_keys
