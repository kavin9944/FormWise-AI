"""
test_step4.py – Unit and Integration Tests for Phase 7 Step 4
Verifies Authenticated Checklist, Readiness APIs, and Security Audits in backend/app.py.
"""

import os
import sys
import json
import shutil
import unittest
from unittest.mock import patch, MagicMock

# Ensure backend directory is in path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app as flask_app
from checklist import build_checklist
from scoring import calculate_readiness

TEST_UID_1 = "user_test_1"
TEST_UID_2 = "user_test_2"
VALID_TOKEN_USER1 = "Bearer valid_token_user1"
VALID_TOKEN_USER2 = "Bearer valid_token_user2"
INVALID_TOKEN = "Bearer invalid_token"

TEST_DOC_ID_FORM = "doc_form_1001"
TEST_DOC_ID_EMPTY_REQS = "doc_form_empty_reqs"
TEST_UPLOAD_MARKSHEET = "upload_10th_marksheet"
TEST_UPLOAD_COMMUNITY = "upload_community_cert"
TEST_USER2_DOC = "doc_user2_private"


def mock_verify_id_token(token):
    if token == "valid_token_user1":
        return {"uid": TEST_UID_1}
    elif token == "valid_token_user2":
        return {"uid": TEST_UID_2}
    else:
        raise Exception("Invalid Firebase ID token.")


class TestPhase7Step4APIs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = flask_app.app.test_client()
        flask_app.app.config["TESTING"] = True

        # Setup test upload directories
        cls.user1_dir = os.path.join(flask_app.BASE_UPLOAD_DIR, TEST_UID_1)
        cls.user2_dir = os.path.join(flask_app.BASE_UPLOAD_DIR, TEST_UID_2)
        os.makedirs(cls.user1_dir, exist_ok=True)
        os.makedirs(cls.user2_dir, exist_ok=True)

        # Create dummy PDF files with valid PDF headers
        pdf_header = b"%PDF-1.4 sample pdf content for testing formwise"
        with open(os.path.join(cls.user1_dir, f"{TEST_DOC_ID_FORM}.pdf"), "wb") as f:
            f.write(pdf_header)

        with open(os.path.join(cls.user1_dir, f"{TEST_DOC_ID_EMPTY_REQS}.pdf"), "wb") as f:
            f.write(pdf_header)

        with open(os.path.join(cls.user1_dir, f"{TEST_UPLOAD_MARKSHEET}.pdf"), "wb") as f:
            f.write(pdf_header)

        with open(os.path.join(cls.user1_dir, f"{TEST_UPLOAD_COMMUNITY}.pdf"), "wb") as f:
            f.write(pdf_header)

        with open(os.path.join(cls.user2_dir, f"{TEST_USER2_DOC}.pdf"), "wb") as f:
            f.write(pdf_header)

        # Populate in-memory analysis cache
        cls.form_analysis = {
            "form_title": "Scholarship Application",
            "summary_english": "Test application form",
            "summary_tamil": "விண்ணப்ப படிவம்",
            "fields": [
                {
                    "field_name": "full_name",
                    "field_id": "full_name",
                    "question": "Full Name",
                    "is_required": True,
                    "field_type": "text",
                    "example": "John Doe Fictional"
                },
                {
                    "field_name": "dob",
                    "field_id": "dob",
                    "question": "Date of Birth",
                    "is_required": True,
                    "field_type": "date",
                    "example": "2000-01-01"
                },
                {
                    "field_name": "email",
                    "field_id": "email",
                    "question": "Email Address",
                    "is_required": True,
                    "field_type": "email",
                    "example": "john@example.com"
                },
                {
                    "field_name": "optional_notes",
                    "field_id": "optional_notes",
                    "question": "Additional Notes",
                    "is_required": False,
                    "field_type": "text",
                    "example": "None"
                }
            ],
            "required_documents": [
                {
                    "doc_id": "10th_marksheet",
                    "doc_type": "marksheet",
                    "title_en": "10th Standard Mark Sheet",
                    "title_ta": "10-ஆம் வகுப்பு மதிப்பெண் சான்றிதழ்",
                    "is_mandatory": True,
                    "is_ai_suggested": False,
                    "evidence": "Section 4: Mandatory enclosure"
                },
                {
                    "doc_id": "community_certificate",
                    "doc_type": "community_certificate",
                    "title_en": "Community Certificate",
                    "title_ta": "சாதிச் சான்றிதழ்",
                    "is_mandatory": True,
                    "is_ai_suggested": False,
                    "evidence": "Required for reserved category"
                },
                {
                    "doc_id": "income_certificate",
                    "doc_type": "income_certificate",
                    "title_en": "Income Certificate",
                    "title_ta": "வருமானச் சான்றிதழ்",
                    "is_mandatory": False,
                    "is_ai_suggested": False,
                    "evidence": "Income certificate may be enclosed"
                }
            ]
        }

        flask_app._analysis_cache[TEST_DOC_ID_FORM] = cls.form_analysis

        flask_app._analysis_cache[TEST_DOC_ID_EMPTY_REQS] = {
            "form_title": "Simple Survey Form",
            "fields": [
                {
                    "field_name": "applicant_name",
                    "field_id": "applicant_name",
                    "question": "Applicant Name",
                    "is_required": True,
                    "field_type": "text"
                }
            ],
            "required_documents": []
        }

    @classmethod
    def tearDownClass(cls):
        # Clean up test directories and caches
        shutil.rmtree(cls.user1_dir, ignore_errors=True)
        shutil.rmtree(cls.user2_dir, ignore_errors=True)
        flask_app._analysis_cache.pop(TEST_DOC_ID_FORM, None)
        flask_app._analysis_cache.pop(TEST_DOC_ID_EMPTY_REQS, None)
        flask_app._confirmed_matches_cache.clear()

    def setUp(self):
        # Reset confirmed matches in both cache and Firestore for clean test isolation
        flask_app._save_persisted_confirmed_matches(TEST_UID_1, TEST_DOC_ID_FORM, {})
        flask_app._analysis_cache[TEST_DOC_ID_FORM] = self.form_analysis

    # 1. Missing authentication
    def test_01_missing_authentication(self):
        for endpoint in ["/api/checklist", "/api/checklist/confirm", "/api/readiness"]:
            res = self.client.post(endpoint, json={"document_id": TEST_DOC_ID_FORM})
            self.assertEqual(res.status_code, 401)
            data = res.get_json()
            self.assertFalse(data.get("success"))
            self.assertIn("Authorization header", data.get("error", ""))

    # 2. Invalid authentication
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_02_invalid_authentication(self, mock_auth):
        for endpoint in ["/api/checklist", "/api/checklist/confirm", "/api/readiness"]:
            res = self.client.post(
                endpoint,
                headers={"Authorization": INVALID_TOKEN},
                json={"document_id": TEST_DOC_ID_FORM}
            )
            self.assertEqual(res.status_code, 401)
            data = res.get_json()
            self.assertFalse(data.get("success"))
            self.assertIn("Unauthorized", data.get("error", ""))

    # 3. Cross-user document access
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_03_cross_user_document_access(self, mock_auth):
        res = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_USER2_DOC}
        )
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("not found in user storage", data.get("error", "").lower())

    # 4. Valid checklist request
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_04_valid_checklist_request(self, mock_auth):
        res = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_FORM}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("total_required"), 3)
        self.assertEqual(data.get("mandatory_count"), 2)
        self.assertEqual(data.get("optional_count"), 1)
        self.assertIsInstance(data.get("items"), list)
        self.assertEqual(len(data["items"]), 3)

    # 5. Empty supporting-document requirements
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_05_empty_supporting_document_requirements(self, mock_auth):
        res = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_EMPTY_REQS}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("total_required"), 0)
        self.assertEqual(data.get("mandatory_count"), 0)
        self.assertTrue(data.get("is_complete"))
        self.assertEqual(data.get("items"), [])

    # 6. Suggested match remains unconfirmed
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_06_suggested_match_remains_unconfirmed(self, mock_auth):
        res = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_FORM}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        items = data.get("items", [])
        marksheet_item = next((i for i in items if i["doc_id"] == "10th_marksheet"), None)
        self.assertIsNotNone(marksheet_item)
        # Must be suggested_match, NOT matched!
        self.assertEqual(marksheet_item["status"], "suggested_match")
        self.assertIsNone(marksheet_item["matched_document_id"])
        self.assertEqual(marksheet_item["suggested_document_id"], TEST_UPLOAD_MARKSHEET)
        # matched_count must be 0
        self.assertEqual(data.get("matched_count"), 0)

    # 7. Successful document confirmation
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_07_successful_document_confirmation(self, mock_auth):
        res = self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("confirmed_matches", {}).get("10th_marksheet"), TEST_UPLOAD_MARKSHEET)

        # Verify checklist reflects status == "matched"
        check_res = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_FORM}
        )
        check_data = check_res.get_json()
        marksheet_item = next((i for i in check_data["items"] if i["doc_id"] == "10th_marksheet"), None)
        self.assertEqual(marksheet_item["status"], "matched")
        self.assertEqual(marksheet_item["matched_document_id"], TEST_UPLOAD_MARKSHEET)
        self.assertEqual(check_data["matched_count"], 1)

    # 8. Invalid document confirmation
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_08_invalid_document_confirmation(self, mock_auth):
        # Case A: Requirement ID does not exist
        res1 = self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "non_existent_req_xyz",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )
        self.assertEqual(res1.status_code, 400)
        self.assertFalse(res1.get_json().get("success"))

        # Case B: Selected document does not belong to user
        res2 = self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "community_certificate",
                "selected_doc_id": TEST_USER2_DOC
            }
        )
        self.assertEqual(res2.status_code, 400)
        self.assertFalse(res2.get_json().get("success"))
        self.assertIn("not found in your uploaded documents", res2.get_json().get("error", "").lower())

    # 9. Confirmation persistence
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_09_confirmation_persistence(self, mock_auth):
        self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )

        self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "community_certificate",
                "selected_doc_id": TEST_UPLOAD_COMMUNITY
            }
        )

        persisted = flask_app._get_persisted_confirmed_matches(TEST_UID_1, TEST_DOC_ID_FORM)
        self.assertEqual(persisted.get("10th_marksheet"), TEST_UPLOAD_MARKSHEET)
        self.assertEqual(persisted.get("community_certificate"), TEST_UPLOAD_COMMUNITY)

        # Unconfirm community certificate safely
        res_unconfirm = self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "community_certificate",
                "selected_doc_id": None
            }
        )
        self.assertEqual(res_unconfirm.status_code, 200)
        persisted_after = flask_app._get_persisted_confirmed_matches(TEST_UID_1, TEST_DOC_ID_FORM)
        self.assertNotIn("community_certificate", persisted_after)
        self.assertEqual(persisted_after.get("10th_marksheet"), TEST_UPLOAD_MARKSHEET)

    # 10. Readiness score with empty answers
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_10_readiness_score_with_empty_answers(self, mock_auth):
        res = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "answers": {}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        breakdown = data.get("score_breakdown", {})
        self.assertEqual(breakdown.get("fields_score"), 0.0)
        self.assertEqual(breakdown.get("completed_required_fields"), 0)
        self.assertEqual(data.get("validation_summary", {}).get("completed_fields"), 0)
        self.assertFalse(data.get("validation_summary", {}).get("is_valid"))

    # 11. Readiness score with valid answers and confirmed documents
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_11_readiness_score_with_valid_answers(self, mock_auth):
        self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )
        self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "community_certificate",
                "selected_doc_id": TEST_UPLOAD_COMMUNITY
            }
        )

        valid_answers = {
            "full_name": "Ravi Kumar",
            "dob": "2002-05-15",
            "email": "ravi.kumar@example.com",
            "optional_notes": "First class honours graduate"
        }
        res = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "answers": valid_answers
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        breakdown = data.get("score_breakdown", {})
        self.assertEqual(breakdown.get("fields_score"), 60.0)
        self.assertEqual(breakdown.get("documents_score"), 40.0)
        self.assertEqual(data.get("readiness_score"), 100.0)
        self.assertEqual(data.get("status"), "ready_to_submit")
        self.assertTrue(data.get("validation_summary", {}).get("is_valid"))

    # 12. Missing mandatory document affects score
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_12_missing_mandatory_document_affects_score(self, mock_auth):
        self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )

        valid_answers = {
            "full_name": "Ravi Kumar",
            "dob": "2002-05-15",
            "email": "ravi.kumar@example.com",
            "optional_notes": "First class graduate"
        }
        res = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "answers": valid_answers
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        breakdown = data.get("score_breakdown", {})
        # Only 1 of 2 mandatory docs is matched: documents_score = (1/2)*40 = 20.0
        self.assertEqual(breakdown.get("documents_score"), 20.0)
        self.assertEqual(data.get("readiness_score"), 80.0)
        self.assertNotEqual(data.get("status"), "ready_to_submit")
        self.assertEqual(data.get("checklist_summary", {}).get("missing_mandatory_count"), 1)

    # 13. Suggested document does not earn mandatory-document points
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_13_suggested_document_does_not_earn_mandatory_points(self, mock_auth):
        valid_answers = {
            "full_name": "Ravi Kumar",
            "dob": "2002-05-15",
            "email": "ravi.kumar@example.com"
        }
        res = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "answers": valid_answers
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        breakdown = data.get("score_breakdown", {})
        self.assertEqual(breakdown.get("documents_score"), 0.0)
        self.assertEqual(breakdown.get("matched_documents_count"), 0)

    # 14. Invalid request payload
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_14_invalid_request_payload(self, mock_auth):
        res1 = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"answers": {}}
        )
        self.assertEqual(res1.status_code, 400)

        res2 = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_FORM, "answers": "not_a_dict"}
        )
        self.assertEqual(res2.status_code, 400)

        too_many_answers = {f"field_{i}": f"val_{i}" for i in range(205)}
        res3 = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_FORM, "answers": too_many_answers}
        )
        self.assertEqual(res3.status_code, 400)
        self.assertIn("exceeds maximum allowed limit", res3.get_json().get("error", "").lower())

    # 15. Existing endpoint regression tests
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_15_existing_endpoint_regression(self, mock_auth):
        res_val = self.client.post(
            "/api/validate",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "answers": {"full_name": "Alice Wonderland", "dob": "2001-01-01", "email": "alice@wonder.com"}
            }
        )
        self.assertEqual(res_val.status_code, 200)
        self.assertTrue(res_val.get_json().get("success"))

        res_ext = self.client.post(
            "/api/extract",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": "non_existent_doc"}
        )
        self.assertEqual(res_ext.status_code, 404)

    # 16. Health endpoint
    def test_16_health_endpoint(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertIn("Backend is healthy", data.get("message", ""))

    # 17. No Gemini fictional examples used as student answers
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_17_no_fictional_examples_used_as_answers(self, mock_auth):
        partial_answers = {
            "full_name": "Real Student Name"
        }
        res = self.client.post(
            "/api/readiness",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "answers": partial_answers
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        validation = data.get("validation_summary", {})
        self.assertEqual(validation.get("completed_fields"), 1)
        self.assertEqual(validation.get("missing_required_count"), 2)
        breakdown = data.get("score_breakdown", {})
        self.assertEqual(breakdown.get("completed_required_fields"), 1)

    # -------------------------------------------------------------------
    # Security Audit Tests (Requirement 1-7 & Additional Audits)
    # -------------------------------------------------------------------

    # 18. Security: Frontend cannot fake confirmed_matches in /api/checklist
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_18_security_frontend_cannot_fake_checklist_matches(self, mock_auth):
        # Student attempts to pass a fake confirmed_matches mapping in the request body
        faked_matches = {
            "10th_marksheet": TEST_UPLOAD_MARKSHEET,
            "community_certificate": TEST_UPLOAD_COMMUNITY
        }
        res = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "confirmed_matches": faked_matches
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # Matched count MUST BE 0! Faked matches in body must be ignored.
        self.assertEqual(data.get("matched_count"), 0)
        for item in data.get("items", []):
            self.assertNotEqual(item.get("status"), "matched", "Unverified frontend match must never become 'matched'")

    # 19. Security: Deleted or missing uploaded file cannot remain confirmed
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_19_security_deleted_uploaded_file_cannot_remain_confirmed(self, mock_auth):
        # 1. Confirm marksheet
        self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )
        # Verify it was matched
        res1 = self.client.post(
            "/api/checklist",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={"document_id": TEST_DOC_ID_FORM}
        )
        self.assertEqual(res1.get_json().get("matched_count"), 1)

        # 2. Simulate deletion of the uploaded file on disk
        marksheet_path = os.path.join(self.user1_dir, f"{TEST_UPLOAD_MARKSHEET}.pdf")
        backup_path = marksheet_path + ".bak"
        os.rename(marksheet_path, backup_path)

        try:
            # 3. Call checklist again: the deleted file must NOT be matched!
            res2 = self.client.post(
                "/api/checklist",
                headers={"Authorization": VALID_TOKEN_USER1},
                json={"document_id": TEST_DOC_ID_FORM}
            )
            data2 = res2.get_json()
            self.assertEqual(data2.get("matched_count"), 0, "Deleted file must not remain matched in checklist")

            # 4. Call readiness: deleted file must earn 0 document points!
            res_readiness = self.client.post(
                "/api/readiness",
                headers={"Authorization": VALID_TOKEN_USER1},
                json={
                    "document_id": TEST_DOC_ID_FORM,
                    "answers": {"full_name": "Ravi", "dob": "2000-01-01", "email": "ravi@ex.com"}
                }
            )
            breakdown = res_readiness.get_json().get("score_breakdown", {})
            self.assertEqual(breakdown.get("documents_score"), 0.0, "Deleted file must not earn readiness points")
        finally:
            # Restore file for clean teardown
            if os.path.exists(backup_path):
                os.rename(backup_path, marksheet_path)

    # 20. Security: Firestore failure does not silently claim confirmation saved
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    @patch.object(flask_app, "_save_persisted_confirmed_matches", return_value=False)
    def test_20_security_firestore_failure_returns_500(self, mock_save, mock_auth):
        res = self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_UPLOAD_MARKSHEET
            }
        )
        self.assertEqual(res.status_code, 500)
        data = res.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("Failed to persist", data.get("error", ""))

    # 21. Security: Form document cannot be confirmed as its own supporting document
    @patch.object(flask_app.auth, "verify_id_token", side_effect=mock_verify_id_token)
    def test_21_security_cannot_match_form_document_as_own_supporting_doc(self, mock_auth):
        res = self.client.post(
            "/api/checklist/confirm",
            headers={"Authorization": VALID_TOKEN_USER1},
            json={
                "document_id": TEST_DOC_ID_FORM,
                "requirement_id": "10th_marksheet",
                "selected_doc_id": TEST_DOC_ID_FORM
            }
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("cannot be matched as its own supporting document", data.get("error", "").lower())


if __name__ == "__main__":
    print("=" * 60)
    print("Running FormWise AI Phase 7 Step 4 Test Suite (with Security Audit)...")
    print("=" * 60)
    unittest.main(verbosity=2)
