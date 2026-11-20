"""
validator.py – FormWise AI Phase 6 Step 1
Deterministic (non-AI) smart form validation engine.

Validates:
  • Required fields (empty / whitespace / placeholder values)
  • Email address syntax
  • Indian mobile / phone numbers

Provides bilingual (English + Tamil) correction suggestions.
Completely independent of Gemini.
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLACEHOLDER_VALUES: set[str] = {
    "", "---", "--", "-", "n/a", "na", "nil", "none", "null",
    "not applicable", "not available", "tbd", "todo", "unknown",
}

# Indian mobile: starting digits 6-9 are valid prefixes for mobile numbers.
_VALID_MOBILE_STARTS = frozenset("6789")

# Obvious dummy patterns to reject (all same digits: 0000000000, 9999999999, etc.)
_DUMMY_PATTERNS = re.compile(r"^(\d)\1{9}$")

# ---------------------------------------------------------------------------
# Bilingual suggestion strings
# ---------------------------------------------------------------------------

# Each entry: (english_text, tamil_text)
_SUGGESTIONS: dict[str, tuple[str, str]] = {
    "required_empty": (
        "This field is required. Please fill in the information before submitting.",
        "இந்தத் தகவல் கட்டாயம் தேவை. தயவுசெய்து தகவலை நிரப்பவும்.",
    ),
    "optional_empty": (
        "This field is optional, but filling it in may be helpful.",
        "இந்தத் தகவல் விரும்பினால் நிரப்பலாம்; தேவையில்லை என்றால் வெறுமனே விட்டுவிடலாம்.",
    ),
    "placeholder_required": (
        "Please replace the placeholder text with your actual information.",
        "சொரகடி உரையை உங்கள் உண்மையான தகவலால் மாற்றவும்.",
    ),
    "placeholder_optional": (
        "The placeholder text has been left as-is. You may replace it with your actual information.",
        "சொரகடி உரை அப்படியே உள்ளது. உண்மையான தகவலை நிரப்ப விரும்பினால் மாற்றலாம்.",
    ),
    "email_missing_at": (
        "The email address is missing the '@' symbol. Example: student@college.edu.in",
        "மின்னஞ்சல் முகவரியில் '@' குறியீடு இல்லை. எடுத்துக்காட்டு: student@college.edu.in",
    ),
    "email_empty_local": (
        "The email address has nothing before the '@'. Example: yourname@example.com",
        "'@' குறியீட்டிற்கு முன்பு பெயர் இல்லை. எடுத்துக்காட்டு: yourname@example.com",
    ),
    "email_empty_domain": (
        "The email address is missing a domain after '@'. Example: name@gmail.com",
        "'@' குறியீட்டிற்கு பின் டொமைன் இல்லை. எடுத்துக்காட்டு: name@gmail.com",
    ),
    "email_missing_dot_in_domain": (
        "The domain part of the email must contain at least one dot. Example: name@domain.com",
        "மின்னஞ்சல் டொமைனில் குறைந்தது ஒரு புள்ளி (.) இருக்க வேண்டும். எடுத்துக்காட்டு: name@domain.com",
    ),
    "email_consecutive_dots": (
        "The email address contains consecutive dots ('..') which is not allowed.",
        "மின்னஞ்சல் முகவரியில் தொடர்ந்து இரு புள்ளிகள் ('..') இருக்கக் கூடாது.",
    ),
    "email_leading_trailing_dot": (
        "The email address starts or ends with a dot, which is not allowed.",
        "மின்னஞ்சல் முகவரி புள்ளியுடன் தொடங்கவோ முடியவோ கூடாது.",
    ),
    "email_domain_leading_trailing_dot": (
        "The domain part of the email cannot start or end with a dot.",
        "மின்னஞ்சல் டொமைன் புள்ளியுடன் தொடங்கவோ முடியவோ கூடாது.",
    ),
    "email_invalid_tld": (
        "The email address has an invalid top-level domain (the last part after the final dot).",
        "மின்னஞ்சலின் கடைசி பகுதி (TLD) சரியாக இல்லை.",
    ),
    "email_invalid_chars": (
        "The email address contains invalid characters. Use only letters, numbers, dots, hyphens and underscores.",
        "மின்னஞ்சல் முகவரியில் அனுமதிக்கப்படாத எழுத்துகள் உள்ளன.",
    ),
    "phone_non_digits": (
        "The phone number contains non-numeric characters. Please enter digits only (and optional +91 prefix).",
        "தொலைபேசி எண்ணில் தவறான எழுத்துகள் உள்ளன. இலக்கங்களை மட்டும் உள்ளிடவும்.",
    ),
    "phone_too_short": (
        "The mobile number is too short. Indian mobile numbers have 10 digits (e.g. 9876543210).",
        "மொபைல் எண் மிகவும் குறுகியது. இந்திய மொபைல் எண்களில் 10 இலக்கங்கள் இருக்க வேண்டும்.",
    ),
    "phone_too_long": (
        "The mobile number is too long. Indian mobile numbers have exactly 10 digits after the country code.",
        "மொபைல் எண் மிகவும் நீண்டது. தேய்ந்த குறியீட்டிற்கு பிறகு சரியாக 10 இலக்கங்கள் இருக்க வேண்டும்.",
    ),
    "phone_invalid_start": (
        "Indian mobile numbers must start with 6, 7, 8, or 9. Please check the number.",
        "இந்திய மொபைல் எண் 6, 7, 8 அல்லது 9 இல் தொடங்க வேண்டும். எண்ணை சரிபார்க்கவும்.",
    ),
    "phone_dummy": (
        "This looks like a placeholder or test number. Please enter your real mobile number.",
        "இது ஒரு தவறான அல்லது போலி எண்ணாக தெரிகிறது. உண்மையான மொபைல் எண்ணை உள்ளிடவும்.",
    ),
    "generic_invalid": (
        "The value entered does not appear to be valid. Please check and correct it.",
        "உள்ளிட்ட மதிப்பு சரியாக தெரியவில்லை. சரிபார்த்து திருத்தவும்.",
    ),
}


# ---------------------------------------------------------------------------
# Helper: placeholder detection
# ---------------------------------------------------------------------------

def is_placeholder(value: Any) -> bool:
    """Return True if *value* is empty, whitespace-only, or a known placeholder."""
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in PLACEHOLDER_VALUES


# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------

def validate_email(email: str) -> tuple[bool, list[str]]:
    """
    Validate an email address syntactically.
    Returns (is_valid, list_of_error_codes).
    Does NOT verify whether an inbox actually exists.
    """
    errors: list[str] = []

    if not isinstance(email, str):
        email = str(email)

    email = email.strip()

    # 1. Must contain exactly one '@'
    if "@" not in email:
        errors.append("email_missing_at")
        return False, errors

    at_count = email.count("@")
    if at_count > 1:
        errors.append("email_missing_at")
        return False, errors

    local, domain = email.split("@", 1)

    # 2. Local part must not be empty
    if not local:
        errors.append("email_empty_local")

    # 3. Domain must not be empty
    if not domain:
        errors.append("email_empty_domain")
        return False, errors

    # 4. No consecutive dots anywhere
    if ".." in email:
        errors.append("email_consecutive_dots")

    # 5. Local part must not start or end with a dot
    if local.startswith(".") or local.endswith("."):
        errors.append("email_leading_trailing_dot")

    # 6. Domain must not start or end with a dot
    if domain.startswith(".") or domain.endswith("."):
        errors.append("email_domain_leading_trailing_dot")

    # 7. Domain must contain at least one dot (for TLD)
    if "." not in domain:
        errors.append("email_missing_dot_in_domain")
        return False, errors

    # 8. TLD (last segment after final dot) must be 2-18 alphabetic characters
    tld = domain.rsplit(".", 1)[-1]
    if not tld or not re.match(r"^[A-Za-z]{2,18}$", tld):
        errors.append("email_invalid_tld")

    # 9. Local part: allow letters, digits, dots, hyphens, underscores, plus signs
    if not re.match(r"^[A-Za-z0-9._%+\-]+$", local):
        errors.append("email_invalid_chars")

    # 10. Domain labels must be letters, digits, or hyphens
    domain_labels = domain.split(".")
    for label in domain_labels:
        if not re.match(r"^[A-Za-z0-9\-]+$", label):
            if "email_invalid_chars" not in errors:
                errors.append("email_invalid_chars")
            break

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Indian mobile number validation
# ---------------------------------------------------------------------------

def validate_indian_mobile(phone: str) -> tuple[bool, list[str]]:
    """
    Validate an Indian mobile number.
    Accepts:
      * 10-digit bare number: 9876543210
      * With +91 prefix:     +91 9876543210
      * With 0 prefix:       0 9876543210
      * With spaces/hyphens: +91-98765-43210
    Returns (is_valid, list_of_error_codes).
    """
    errors: list[str] = []

    if not isinstance(phone, str):
        phone = str(phone)

    raw = phone.strip()

    # Remove allowed formatting characters: spaces, hyphens, parentheses
    cleaned = re.sub(r"[\s\-().]+", "", raw)

    # Check for non-digit, non-plus characters (after removing formatting)
    if not re.match(r"^\+?\d+$", cleaned):
        errors.append("phone_non_digits")
        return False, errors

    # Strip country code prefix
    digits = cleaned
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]

    # Must be exactly 10 digits now
    if not digits.isdigit():
        errors.append("phone_non_digits")
        return False, errors

    if len(digits) < 10:
        errors.append("phone_too_short")
        return False, errors

    if len(digits) > 10:
        errors.append("phone_too_long")
        return False, errors

    # Starting digit must be 6, 7, 8, or 9
    if digits[0] not in _VALID_MOBILE_STARTS:
        errors.append("phone_invalid_start")

    # Reject obvious dummy / repeated patterns (e.g. 0000000000, 9999999999)
    if _DUMMY_PATTERNS.match(digits):
        errors.append("phone_dummy")

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Suggestion builder
# ---------------------------------------------------------------------------

def _build_suggestions(
    error_codes: list[str],
    language: str,
) -> tuple[str, str]:
    """
    Map error codes to English and Tamil suggestion strings.
    Returns (suggestions_en, suggestions_ta).
    language: "english" | "tamil" | "both"
    """
    want_en = language in ("english", "both")
    want_ta = language in ("tamil", "both")

    en_parts: list[str] = []
    ta_parts: list[str] = []

    for code in error_codes:
        if code in _SUGGESTIONS:
            en_text, ta_text = _SUGGESTIONS[code]
        else:
            en_text, ta_text = _SUGGESTIONS["generic_invalid"]

        if want_en and en_text not in en_parts:
            en_parts.append(en_text)
        if want_ta and ta_text not in ta_parts:
            ta_parts.append(ta_text)

    suggestions_en = " ".join(en_parts) if want_en else ""
    suggestions_ta = " ".join(ta_parts) if want_ta else ""
    return suggestions_en, suggestions_ta


# ---------------------------------------------------------------------------
# Single-field validation
# ---------------------------------------------------------------------------

def validate_field(
    field_def: dict,
    student_answer: Any,
    language: str = "both",
) -> dict:
    """
    Validate one form field.

    field_def keys used:
      field_name   - machine key (string)
      question     - human-readable label (string)
      is_required  - bool (default False)
      field_type   - "email" | "phone" | "text" | "number" | "date" (default "text")

    Returns:
      {
        field_id:       str,
        field_label:    str,
        status:         "valid" | "warning" | "error",
        errors:         [str, ...],
        suggestions_en: str,
        suggestions_ta: str,
      }
    """
    field_id: str = str(field_def.get("field_name", ""))
    field_label: str = str(field_def.get("question", field_id))
    is_required: bool = bool(field_def.get("is_required", False))
    field_type: str = str(field_def.get("field_type", "text")).lower()

    # Normalize the student answer
    answer_str = str(student_answer).strip() if student_answer is not None else ""

    errors: list[str] = []

    # --- Step 1: Empty / placeholder check ---
    if is_placeholder(answer_str):
        if is_required:
            # Distinguish true empty from placeholder text
            if not answer_str:
                errors.append("required_empty")
            else:
                errors.append("placeholder_required")
        else:
            # Optional and empty/placeholder - warning, not error
            if not answer_str:
                code = "optional_empty"
            else:
                code = "placeholder_optional"
            suggestions_en, suggestions_ta = _build_suggestions([code], language)
            return {
                "field_id": field_id,
                "field_label": field_label,
                "status": "warning",
                "errors": [code],
                "suggestions_en": suggestions_en,
                "suggestions_ta": suggestions_ta,
            }

        # Required field is empty/placeholder - error
        suggestions_en, suggestions_ta = _build_suggestions(errors, language)
        return {
            "field_id": field_id,
            "field_label": field_label,
            "status": "error",
            "errors": errors,
            "suggestions_en": suggestions_en,
            "suggestions_ta": suggestions_ta,
        }

    # --- Step 2: Format validation for non-empty values ---
    if field_type == "email":
        ok, fmt_errors = validate_email(answer_str)
        if not ok:
            errors.extend(fmt_errors)

    elif field_type in ("phone", "mobile"):
        ok, fmt_errors = validate_indian_mobile(answer_str)
        if not ok:
            errors.extend(fmt_errors)

    # Other types (text, number, date) - no deterministic format check here.
    # Number/date validation can be added in future steps.

    if errors:
        suggestions_en, suggestions_ta = _build_suggestions(errors, language)
        return {
            "field_id": field_id,
            "field_label": field_label,
            "status": "error",
            "errors": errors,
            "suggestions_en": suggestions_en,
            "suggestions_ta": suggestions_ta,
        }

    return {
        "field_id": field_id,
        "field_label": field_label,
        "status": "valid",
        "errors": [],
        "suggestions_en": "",
        "suggestions_ta": "",
    }


# ---------------------------------------------------------------------------
# Full-form validation
# ---------------------------------------------------------------------------

def validate_form(
    field_definitions: list[dict],
    student_answers: dict[str, Any],
    language: str = "both",
) -> dict:
    """
    Validate all fields in a form.

    field_definitions: list of field_def dicts (see validate_field)
    student_answers:   dict mapping field_name -> student's raw answer
    language:          "english" | "tamil" | "both"

    Returns:
      {
        is_valid:               bool,
        total_fields:           int,
        completed_fields:       int,
        missing_required_count: int,
        error_count:            int,
        field_results:          [validate_field result, ...],
      }
    """
    field_results = []
    missing_required_count = 0
    error_count = 0
    completed_fields = 0

    for field_def in field_definitions:
        field_name = str(field_def.get("field_name", ""))
        # Look up the student's answer; default to empty string if not provided.
        raw_answer = student_answers.get(field_name, "")

        result = validate_field(field_def, raw_answer, language)
        field_results.append(result)

        if result["status"] == "valid":
            completed_fields += 1
        elif result["status"] == "error":
            error_count += 1
            if "required_empty" in result["errors"] or "placeholder_required" in result["errors"]:
                missing_required_count += 1
        # "warning" fields (optional + empty) are neither complete nor errors

    is_valid = error_count == 0

    return {
        "is_valid": is_valid,
        "total_fields": len(field_definitions),
        "completed_fields": completed_fields,
        "missing_required_count": missing_required_count,
        "error_count": error_count,
        "field_results": field_results,
    }
