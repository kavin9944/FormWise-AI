"""
scoring.py – FormWise AI Phase 7 Step 2
Deterministic Application Readiness Scoring Engine.

Calculates:
  • Form field completion & validity score (60 points maximum)
    - Required fields: 50 points proportional: (valid_completed_required / total_required) * 50
    - Optional fields: 10 bonus points proportional: (valid_completed_optional / total_optional) * 10
    - Safe normalization for forms with zero required or zero optional fields:
        * If total_optional == 0 and total_required > 0: required fields scale to full 60 points:
            (valid_completed_required / total_required) * 60
        * If total_required == 0 and total_optional > 0: optional fields scale to full 60 points:
            (valid_completed_optional / total_optional) * 60
        * If total_required == 0 and total_optional == 0: awards full 60 points (no fields required).
  • Supporting documents score (40 points maximum)
    - Confirmed mandatory documents: (confirmed_matched_mandatory / total_mandatory_documents) * 40
    - Forms with no mandatory documents automatically earn the full 40 points.
    - Only status == 'matched' earns points; 'suggested_match' and 'missing' earn 0 points.
    - AI-suggested documents are NEVER counted as mandatory.
  • Total readiness score (0–100, rounded to 2 decimal places)
  • Qualitative readiness status:
    - 'ready_to_submit': score == 100.0 with zero missing required fields, zero validation errors,
                         and zero missing mandatory documents.
    - 'almost_ready': score >= 75.0 (and not meeting all ready_to_submit criteria).
    - 'in_progress': 25.0 <= score < 75.0.
    - 'not_started': score < 25.0.
  • Deterministic action items in English and Tamil for missing or invalid items.

Security & Safety:
  • Does not mutate input dictionaries.
  • Never uses Gemini fictional examples.
  • Never awards points for suggested but unconfirmed documents.
  • Safe against division by zero and malformed inputs.
  • No external dependencies.
"""

from typing import Any, Dict, List, Optional


def calculate_readiness(
    validation_result: Any,
    checklist_result: Any,
    field_definitions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Calculates the application readiness score and returns a transparent breakdown.

    Parameters:
      validation_result: Dict output from validate_form() or containing 'field_results',
                         or a raw list of field result dictionaries.
      checklist_result: Dict output from build_checklist() or containing 'items',
                        or a raw list of checklist item dictionaries.
      field_definitions: Optional list of raw field definitions to resolve is_required.

    Returns:
      {
        "readiness_score": float (0-100, rounded to 2 decimals),
        "status": str ("ready_to_submit" | "almost_ready" | "in_progress" | "not_started"),
        "score_breakdown": {
          "fields_score": float,
          "fields_max": float (60.0),
          "documents_score": float,
          "documents_max": float (40.0),
          "completed_required_fields": int,
          "total_required_fields": int,
          "completed_optional_fields": int,
          "total_optional_fields": int,
          "validation_errors_count": int,
          "matched_documents_count": int,
          "total_mandatory_documents": int,
          "missing_mandatory_documents_count": int,
        },
        "action_items": list[dict],
      }
    """
    # -------------------------------------------------------------------------
    # 1. Parse and sanitize validation_result safely (No mutation of inputs)
    # -------------------------------------------------------------------------
    field_results: List[Dict[str, Any]] = []
    field_defs_from_val: List[Dict[str, Any]] = []

    if isinstance(validation_result, list):
        field_results = [f for f in validation_result if isinstance(f, dict)]
    elif isinstance(validation_result, dict):
        raw_fr = validation_result.get("field_results")
        if isinstance(raw_fr, list):
            field_results = [f for f in raw_fr if isinstance(f, dict)]

        raw_fd = validation_result.get("field_definitions") or validation_result.get("fields")
        if isinstance(raw_fd, list):
            field_defs_from_val = [f for f in raw_fd if isinstance(f, dict)]

    # Build field_defs lookup map for requirement resolution
    field_defs_map: Dict[str, Dict[str, Any]] = {}
    defs_source = field_definitions if isinstance(field_definitions, list) else field_defs_from_val
    for fdef in defs_source:
        if isinstance(fdef, dict):
            fid = str(fdef.get("field_id") or fdef.get("field_name") or "").strip()
            if fid:
                field_defs_map[fid] = fdef

    # -------------------------------------------------------------------------
    # 2. Part A: Form Fields Evaluation (60 points maximum)
    # -------------------------------------------------------------------------
    total_required = 0
    completed_required = 0
    total_optional = 0
    completed_optional = 0
    validation_errors_count = 0

    action_items: List[Dict[str, Any]] = []

    for f in field_results:
        fid = str(f.get("field_id") or f.get("field_name") or "")
        flabel = str(f.get("field_label") or f.get("question") or f.get("label") or fid).strip()
        fstatus = str(f.get("status", "error")).strip().lower()

        raw_errors = f.get("errors", [])
        ferrors: List[str] = raw_errors if isinstance(raw_errors, list) else []

        suggestions_en = str(f.get("suggestions_en") or f.get("suggestion_en") or "").strip()
        suggestions_ta = str(f.get("suggestions_ta") or f.get("suggestion_ta") or "").strip()

        # Determine if field is required
        is_req = f.get("is_required")
        if is_req is None:
            is_req = f.get("required")

        if is_req is None:
            if fid in field_defs_map:
                def_entry = field_defs_map[fid]
                is_req = bool(def_entry.get("is_required", def_entry.get("required", False)))
            elif "required_empty" in ferrors or "placeholder_required" in ferrors:
                is_req = True
            elif fstatus == "warning" or "optional_empty" in ferrors or "placeholder_optional" in ferrors:
                is_req = False
            elif "*" in flabel:
                is_req = True
            else:
                is_req = True  # Safe default: treat unspecified input fields as required
        else:
            is_req = bool(is_req)

        # Evaluate validity & completion
        if is_req:
            total_required += 1
            if fstatus == "valid":
                completed_required += 1
            else:
                validation_errors_count += 1
                if "required_empty" in ferrors or "placeholder_required" in ferrors or not ferrors:
                    msg_en = suggestions_en or f"Please complete the required field: {flabel}"
                    msg_ta = suggestions_ta or f"தயவுசெய்து கட்டாய புலத்தை நிரப்பவும்: {flabel}"
                    action_items.append({
                        "type": "missing_required_field",
                        "item_id": fid,
                        "field_id": fid,
                        "title": flabel,
                        "label": flabel,
                        "message_en": msg_en,
                        "message_ta": msg_ta,
                        "suggestion_en": suggestions_en,
                        "suggestion_ta": suggestions_ta,
                    })
                else:
                    msg_en = suggestions_en or f"Correct the format error in: {flabel}"
                    msg_ta = suggestions_ta or f"சரியான வடிவத்தில் உள்ளிடவும்: {flabel}"
                    action_items.append({
                        "type": "invalid_field",
                        "item_id": fid,
                        "field_id": fid,
                        "title": flabel,
                        "label": flabel,
                        "message_en": msg_en,
                        "message_ta": msg_ta,
                        "suggestion_en": suggestions_en,
                        "suggestion_ta": suggestions_ta,
                    })
        else:
            total_optional += 1
            if fstatus == "valid":
                completed_optional += 1
            elif fstatus == "error":
                validation_errors_count += 1
                msg_en = suggestions_en or f"Correct the format error in: {flabel}"
                msg_ta = suggestions_ta or f"சரியான வடிவத்தில் உள்ளிடவும்: {flabel}"
                action_items.append({
                    "type": "invalid_field",
                    "item_id": fid,
                    "field_id": fid,
                    "title": flabel,
                    "label": flabel,
                    "message_en": msg_en,
                    "message_ta": msg_ta,
                    "suggestion_en": suggestions_en,
                    "suggestion_ta": suggestions_ta,
                })
            # fstatus == "warning" is optional blank: 0 bonus points, but NO validation failure or error

    # Compute fields score with zero-field normalization
    fields_max = 60.0

    if total_required > 0 and total_optional > 0:
        req_pts = (completed_required / total_required) * 50.0
        opt_pts = (completed_optional / total_optional) * 10.0
        fields_score = req_pts + opt_pts
    elif total_required > 0 and total_optional == 0:
        # Form has only required fields: required fields scale to full 60 points
        req_pts = (completed_required / total_required) * 60.0
        opt_pts = 0.0
        fields_score = req_pts
    elif total_required == 0 and total_optional > 0:
        # Form has only optional fields: optional fields scale to full 60 points
        req_pts = 0.0
        opt_pts = (completed_optional / total_optional) * 60.0
        fields_score = opt_pts
    else:
        # Zero fields on form: award full 60 points (no field obligations pending)
        req_pts = 0.0
        opt_pts = 0.0
        fields_score = 60.0

    # -------------------------------------------------------------------------
    # 3. Part B: Supporting Documents Evaluation (40 points maximum)
    # -------------------------------------------------------------------------
    chk_items: List[Dict[str, Any]] = []

    if isinstance(checklist_result, list):
        chk_items = [item for item in checklist_result if isinstance(item, dict)]
    elif isinstance(checklist_result, dict):
        raw_ci = checklist_result.get("items")
        if isinstance(raw_ci, list):
            chk_items = [item for item in raw_ci if isinstance(item, dict)]

    total_mandatory_docs = 0
    confirmed_matched_mandatory = 0
    missing_mandatory_docs_count = 0

    documents_max = 40.0

    if chk_items:
        for item in chk_items:
            doc_id = str(item.get("doc_id") or item.get("id") or "").strip()
            title_en = str(item.get("title_en") or item.get("title") or doc_id).strip()
            title_ta = str(item.get("title_ta") or item.get("tamil_title") or title_en).strip()
            is_ai_suggested = bool(item.get("is_ai_suggested", False))

            # AI-suggested documents can NEVER be counted as mandatory
            is_mandatory = bool(item.get("is_mandatory", False)) and not is_ai_suggested
            status = str(item.get("status", "missing")).strip().lower()

            if is_mandatory:
                total_mandatory_docs += 1
                if status == "matched":
                    confirmed_matched_mandatory += 1
                else:
                    missing_mandatory_docs_count += 1
                    if status == "suggested_match":
                        action_items.append({
                            "type": "unconfirmed_document",
                            "item_id": doc_id,
                            "doc_id": doc_id,
                            "title": title_en,
                            "title_ta": title_ta,
                            "message_en": f"Review and confirm the suggested match for: {title_en}",
                            "message_ta": f"பரிந்துரைக்கப்பட்ட ஆவணத்தை மதிப்பாய்வு செய்து உறுதிப்படுத்தவும்: {title_ta}",
                        })
                    else:
                        action_items.append({
                            "type": "missing_mandatory_document",
                            "item_id": doc_id,
                            "doc_id": doc_id,
                            "title": title_en,
                            "title_ta": title_ta,
                            "message_en": f"Please upload and confirm the required document: {title_en}",
                            "message_ta": f"தேவையான ஆவணத்தைப் பதிவேற்றி உறுதிப்படுத்தவும்: {title_ta}",
                        })
    elif isinstance(checklist_result, dict):
        # Fallback to direct summary counts if provided without items list
        total_mandatory_docs = int(
            checklist_result.get("total_mandatory_documents")
            or checklist_result.get("mandatory_count")
            or 0
        )
        missing_mandatory_docs_count = int(
            checklist_result.get("missing_mandatory_documents_count")
            or checklist_result.get("missing_mandatory_count")
            or 0
        )
        raw_matched = checklist_result.get("matched_documents_count")
        if raw_matched is not None:
            confirmed_matched_mandatory = int(raw_matched)
        else:
            confirmed_matched_mandatory = max(0, total_mandatory_docs - missing_mandatory_docs_count)

    # Documents score formula
    if total_mandatory_docs > 0:
        documents_score = (confirmed_matched_mandatory / total_mandatory_docs) * documents_max
    else:
        # If no mandatory supporting documents exist, award full 40 points
        documents_score = documents_max

    # -------------------------------------------------------------------------
    # 4. Total Score & Qualitative Status Determination
    # -------------------------------------------------------------------------
    total_raw_score = fields_score + documents_score
    readiness_score = round(max(0.0, min(100.0, total_raw_score)), 2)

    # Status rules:
    # 'ready_to_submit' ONLY when score is 100 AND zero missing mandatory fields,
    # zero validation errors, and zero missing mandatory documents.
    is_perfect_score = (readiness_score >= 100.0)
    no_missing_required = (completed_required == total_required)
    no_validation_errors = (validation_errors_count == 0)
    no_missing_mandatory_docs = (missing_mandatory_docs_count == 0)

    if is_perfect_score and no_missing_required and no_validation_errors and no_missing_mandatory_docs:
        status = "ready_to_submit"
    elif readiness_score >= 75.0:
        status = "almost_ready"
    elif readiness_score >= 25.0:
        status = "in_progress"
    else:
        status = "not_started"

    return {
        "readiness_score": readiness_score,
        "status": status,
        "score_breakdown": {
            "fields_score": round(fields_score, 2),
            "fields_max": fields_max,
            "documents_score": round(documents_score, 2),
            "documents_max": documents_max,
            "completed_required_fields": completed_required,
            "total_required_fields": total_required,
            "completed_optional_fields": completed_optional,
            "total_optional_fields": total_optional,
            "required_points": round(req_pts, 2),
            "optional_points": round(opt_pts, 2),
            "validation_errors_count": validation_errors_count,
            "matched_documents_count": confirmed_matched_mandatory,
            "total_mandatory_documents": total_mandatory_docs,
            "missing_mandatory_documents_count": missing_mandatory_docs_count,
        },
        "action_items": action_items,
    }


# =============================================================================
# Unit Tests Runner (Comprehensive 15-case verification)
# =============================================================================

def run_unit_tests() -> Dict[str, Any]:
    """
    Executes the 15 required unit test cases using synthetic data only.
    Returns:
        {"passed": int, "failed": int, "total": int, "results": List[dict]}
    """
    test_results: List[Dict[str, Any]] = []

    def assert_test(name: str, condition: bool, details: str = ""):
        test_results.append({
            "name": name,
            "passed": bool(condition),
            "details": details
        })

    # 1. No fields completed
    val_1 = {
        "field_results": [
            {"field_id": "name", "is_required": True, "status": "error", "errors": ["required_empty"]},
            {"field_id": "email", "is_required": True, "status": "error", "errors": ["required_empty"]},
            {"field_id": "notes", "is_required": False, "status": "warning", "errors": ["optional_empty"]},
        ]
    }
    chk_1 = {
        "items": [
            {"doc_id": "aadhaar", "is_mandatory": True, "is_ai_suggested": False, "status": "missing"}
        ]
    }
    res_1 = calculate_readiness(val_1, chk_1)
    assert_test(
        "1. No fields completed",
        res_1["readiness_score"] == 0.0 and res_1["status"] == "not_started" and len(res_1["action_items"]) == 3,
        f"Score: {res_1['readiness_score']}, Status: {res_1['status']}, Actions: {len(res_1['action_items'])}"
    )

    # 2. All required fields valid (optional empty, no docs)
    val_2 = {
        "field_results": [
            {"field_id": "name", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "email", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "notes", "is_required": False, "status": "warning", "errors": ["optional_empty"]},
        ]
    }
    chk_2 = {"items": []}
    res_2 = calculate_readiness(val_2, chk_2)
    # Required = 50, Optional = 0, Docs = 40 (none mandatory) -> Total = 90.0, status: almost_ready
    assert_test(
        "2. All required fields valid",
        res_2["readiness_score"] == 90.0 and res_2["status"] == "almost_ready",
        f"Score: {res_2['readiness_score']}, Status: {res_2['status']}"
    )

    # 3. Invalid required field
    val_3 = {
        "field_results": [
            {"field_id": "name", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "email", "is_required": True, "status": "error", "errors": ["email_invalid"], "suggestions_en": "Provide valid email"},
        ]
    }
    chk_3 = {"items": []}
    res_3 = calculate_readiness(val_3, chk_3)
    # total_required=2, valid=1 -> (1/2)*60 = 30; Docs = 40 -> Total = 70.0, status: in_progress
    assert_test(
        "3. Invalid required field",
        res_3["readiness_score"] == 70.0 and res_3["status"] == "in_progress" and res_3["score_breakdown"]["validation_errors_count"] == 1,
        f"Score: {res_3['readiness_score']}, Status: {res_3['status']}, Errors: {res_3['score_breakdown']['validation_errors_count']}"
    )

    # 4. Missing required field
    val_4 = {
        "field_results": [
            {"field_id": "name", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "phone", "is_required": True, "status": "error", "errors": ["required_empty"]},
        ]
    }
    chk_4 = {"items": []}
    res_4 = calculate_readiness(val_4, chk_4)
    assert_test(
        "4. Missing required field",
        res_4["readiness_score"] == 70.0 and any(a["type"] == "missing_required_field" for a in res_4["action_items"]),
        f"Score: {res_4['readiness_score']}, Action types: {[a['type'] for a in res_4['action_items']]}"
    )

    # 5. Optional blank field does not cause validation failure
    val_5 = {
        "field_results": [
            {"field_id": "name", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "alt_phone", "is_required": False, "status": "warning", "errors": ["optional_empty"]},
        ]
    }
    chk_5 = {"items": []}
    res_5 = calculate_readiness(val_5, chk_5)
    # Required: 50.0, Optional: 0.0, Docs: 40.0 -> 90.0
    assert_test(
        "5. Optional blank field",
        res_5["readiness_score"] == 90.0 and res_5["score_breakdown"]["validation_errors_count"] == 0,
        f"Score: {res_5['readiness_score']}, Validation errors: {res_5['score_breakdown']['validation_errors_count']}"
    )

    # 6. All mandatory documents confirmed
    val_6 = {"field_results": []}
    chk_6 = {
        "items": [
            {"doc_id": "10th_marksheet", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
            {"doc_id": "aadhaar", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
        ]
    }
    res_6 = calculate_readiness(val_6, chk_6)
    # Fields: 60.0 (no fields), Docs: 40.0 -> 100.0, ready_to_submit
    assert_test(
        "6. All mandatory documents confirmed",
        res_6["readiness_score"] == 100.0 and res_6["status"] == "ready_to_submit" and res_6["score_breakdown"]["missing_mandatory_documents_count"] == 0,
        f"Score: {res_6['readiness_score']}, Status: {res_6['status']}"
    )

    # 7. Missing mandatory document
    val_7 = {"field_results": []}
    chk_7 = {
        "items": [
            {"doc_id": "marksheet", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
            {"doc_id": "tc", "is_mandatory": True, "is_ai_suggested": False, "status": "missing"},
        ]
    }
    res_7 = calculate_readiness(val_7, chk_7)
    # Fields: 60.0, Docs: (1/2)*40 = 20.0 -> Total: 80.0, status: almost_ready
    assert_test(
        "7. Missing mandatory document",
        res_7["readiness_score"] == 80.0 and res_7["status"] == "almost_ready" and res_7["score_breakdown"]["missing_mandatory_documents_count"] == 1,
        f"Score: {res_7['readiness_score']}, Missing mandatory: {res_7['score_breakdown']['missing_mandatory_documents_count']}"
    )

    # 8. Suggested match earns zero document points
    val_8 = {"field_results": []}
    chk_8 = {
        "items": [
            {"doc_id": "income_cert", "is_mandatory": True, "is_ai_suggested": False, "status": "suggested_match"},
        ]
    }
    res_8 = calculate_readiness(val_8, chk_8)
    # Fields: 60.0, Docs: (0/1)*40 = 0.0 -> Total: 60.0, status: in_progress
    assert_test(
        "8. Suggested match earns zero document points",
        res_8["score_breakdown"]["documents_score"] == 0.0 and res_8["readiness_score"] == 60.0 and res_8["score_breakdown"]["matched_documents_count"] == 0,
        f"Docs score: {res_8['score_breakdown']['documents_score']}, Matched: {res_8['score_breakdown']['matched_documents_count']}"
    )

    # 9. AI-suggested document excluded from mandatory count
    val_9 = {"field_results": []}
    chk_9 = {
        "items": [
            {"doc_id": "marksheet", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
            {"doc_id": "bonus_cert", "is_mandatory": True, "is_ai_suggested": True, "status": "missing"},
        ]
    }
    res_9 = calculate_readiness(val_9, chk_9)
    # total_mandatory should be 1 (bonus_cert excluded because is_ai_suggested=True)
    assert_test(
        "9. AI-suggested document excluded from mandatory count",
        res_9["score_breakdown"]["total_mandatory_documents"] == 1 and res_9["score_breakdown"]["documents_score"] == 40.0 and res_9["readiness_score"] == 100.0,
        f"Total mandatory: {res_9['score_breakdown']['total_mandatory_documents']}, Docs score: {res_9['score_breakdown']['documents_score']}"
    )

    # 10. No mandatory documents awards full 40 points
    val_10 = {"field_results": []}
    chk_10 = {"items": []}
    res_10 = calculate_readiness(val_10, chk_10)
    assert_test(
        "10. No mandatory documents",
        res_10["score_breakdown"]["documents_score"] == 40.0 and res_10["score_breakdown"]["total_mandatory_documents"] == 0,
        f"Docs score: {res_10['score_breakdown']['documents_score']}"
    )

    # 11. Zero optional fields scales required fields to full 60 points
    val_11 = {
        "field_results": [
            {"field_id": "f1", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "f2", "is_required": True, "status": "valid", "errors": []},
        ]
    }
    chk_11 = {
        "items": [
            {"doc_id": "d1", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"}
        ]
    }
    res_11 = calculate_readiness(val_11, chk_11)
    # Required: (2/2)*60 = 60.0, Docs: (1/1)*40 = 40.0 -> 100.0
    assert_test(
        "11. Zero optional fields",
        res_11["score_breakdown"]["fields_score"] == 60.0 and res_11["readiness_score"] == 100.0 and res_11["status"] == "ready_to_submit",
        f"Fields score: {res_11['score_breakdown']['fields_score']}, Total: {res_11['readiness_score']}"
    )

    # 12. Zero required fields scales optional fields to full 60 points
    val_12 = {
        "field_results": [
            {"field_id": "o1", "is_required": False, "status": "valid", "errors": []},
            {"field_id": "o2", "is_required": False, "status": "valid", "errors": []},
        ]
    }
    chk_12 = {"items": []}
    res_12 = calculate_readiness(val_12, chk_12)
    # Optional: (2/2)*60 = 60.0, Docs: 40.0 -> 100.0
    assert_test(
        "12. Zero required fields",
        res_12["score_breakdown"]["fields_score"] == 60.0 and res_12["readiness_score"] == 100.0 and res_12["status"] == "ready_to_submit",
        f"Fields score: {res_12['score_breakdown']['fields_score']}, Total: {res_12['readiness_score']}"
    )

    # 13. Fully complete application gives 100%
    val_13 = {
        "field_results": [
            {"field_id": "name", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "email", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "bio", "is_required": False, "status": "valid", "errors": []},
        ]
    }
    chk_13 = {
        "items": [
            {"doc_id": "marksheet", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
            {"doc_id": "id_card", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
        ]
    }
    res_13 = calculate_readiness(val_13, chk_13)
    # Req: 50.0, Opt: 10.0, Docs: 40.0 -> Total: 100.0, status: ready_to_submit, 0 actions
    assert_test(
        "13. Fully complete application gives 100%",
        res_13["readiness_score"] == 100.0 and res_13["status"] == "ready_to_submit" and len(res_13["action_items"]) == 0,
        f"Score: {res_13['readiness_score']}, Status: {res_13['status']}, Actions: {len(res_13['action_items'])}"
    )

    # 14. Malformed input handling (does not crash or mutate)
    val_14_mut = {"field_results": [{"field_id": "x", "is_required": True, "status": "valid"}]}
    chk_14_mut = {"items": [{"doc_id": "d", "is_mandatory": True, "status": "matched"}]}
    import copy
    val_14_copy = copy.deepcopy(val_14_mut)
    chk_14_copy = copy.deepcopy(chk_14_mut)

    res_14a = calculate_readiness(None, None)
    res_14b = calculate_readiness("invalid_str", 12345)
    res_14c = calculate_readiness({"field_results": [None, 42, "bad", {}]}, {"items": [None, 99, {}]})
    calculate_readiness(val_14_mut, chk_14_mut)

    no_mutation = (val_14_mut == val_14_copy and chk_14_mut == chk_14_copy)
    assert_test(
        "14. Malformed input handling",
        isinstance(res_14a, dict) and isinstance(res_14b, dict) and isinstance(res_14c, dict) and no_mutation,
        f"res_14a keys: {list(res_14a.keys())}, No mutation: {no_mutation}"
    )

    # 15. Exact score calculations and rounding
    val_15 = {
        "field_results": [
            {"field_id": "r1", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "r2", "is_required": True, "status": "valid", "errors": []},
            {"field_id": "r3", "is_required": True, "status": "error", "errors": ["required_empty"]},
            {"field_id": "o1", "is_required": False, "status": "valid", "errors": []},
            {"field_id": "o2", "is_required": False, "status": "warning", "errors": ["optional_empty"]},
            {"field_id": "o3", "is_required": False, "status": "warning", "errors": ["optional_empty"]},
        ]
    }
    chk_15 = {
        "items": [
            {"doc_id": "d1", "is_mandatory": True, "is_ai_suggested": False, "status": "matched"},
            {"doc_id": "d2", "is_mandatory": True, "is_ai_suggested": False, "status": "missing"},
            {"doc_id": "d3", "is_mandatory": True, "is_ai_suggested": False, "status": "missing"},
        ]
    }
    res_15 = calculate_readiness(val_15, chk_15)
    # req_pts = (2/3) * 50 = 33.333333...
    # opt_pts = (1/3) * 10 = 3.333333...
    # fields_score = 36.67
    # doc_pts = (1/3) * 40 = 13.333333... -> 13.33
    # total = 36.666666... + 13.333333... = 50.00
    assert_test(
        "15. Exact score calculations and rounding",
        res_15["score_breakdown"]["fields_score"] == 36.67
        and res_15["score_breakdown"]["documents_score"] == 13.33
        and res_15["readiness_score"] == 50.0
        and res_15["status"] == "in_progress",
        f"Fields: {res_15['score_breakdown']['fields_score']}, Docs: {res_15['score_breakdown']['documents_score']}, Total: {res_15['readiness_score']}"
    )

    passed_count = sum(1 for t in test_results if t["passed"])
    failed_count = sum(1 for t in test_results if not t["passed"])

    return {
        "passed": passed_count,
        "failed": failed_count,
        "total": len(test_results),
        "results": test_results
    }


if __name__ == "__main__":
    report = run_unit_tests()
    print("=" * 60)
    print(f"FormWise AI Scoring Engine Unit Tests: {report['passed']}/{report['total']} Passed ({report['failed']} Failed)")
    print("=" * 60)
    for test in report["results"]:
        status_symbol = "✔ PASS" if test["passed"] else "✖ FAIL"
        print(f"[{status_symbol}] {test['name']}")
        if test["details"]:
            print(f"       Details: {test['details']}")
    print("=" * 60)
