"""
test_pdf.py - Unit tests for PDF generation and download routes
"""
import os
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app as flask_app
from pdf_generator import generate_filled_pdf


class TestPDFGeneration(unittest.TestCase):
    def setUp(self):
        self.fields = [
            {"field_id": "full_name", "field_name": "full_name", "question": "Full Name", "field_type": "text", "is_required": True},
            {"field_id": "email", "field_name": "email", "question": "Email Address", "field_type": "email", "is_required": True},
            {"field_id": "notes", "field_name": "notes", "question": "Optional Notes", "field_type": "text", "is_required": False},
        ]
        self.answers = {
            "full_name": "Alice Johnson",
            "email": "alice@example.com",
            "notes": "Testing notes"
        }
        self.checklist = [
            {"doc_id": "id_proof", "title_en": "ID Proof", "is_mandatory": True, "matched_document_id": "doc123"}
        ]

    def test_01_generate_filled_pdf_bytes(self):
        pdf_bytes = generate_filled_pdf(
            form_title="Test Application Form",
            fields=self.fields,
            student_answers=self.answers,
            analysis_data={"summary_english": "A sample summary"},
            checklist_items=self.checklist,
            readiness_score=85.5,
            readiness_status="almost_ready"
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 500)
        # PDF magic bytes
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_02_generate_pdf_empty_answers(self):
        pdf_bytes = generate_filled_pdf(
            form_title="Empty Application",
            fields=self.fields,
            student_answers={},
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))


class TestPDFRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = flask_app.app.test_client()
        flask_app.app.config["TESTING"] = True
        cls.test_uid = "user_test_pdf"
        cls.user_dir = os.path.join(flask_app.BASE_UPLOAD_DIR, cls.test_uid)
        os.makedirs(cls.user_dir, exist_ok=True)
        cls.doc_id = "test_form_pdf_1"
        with open(os.path.join(cls.user_dir, f"{cls.doc_id}.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 sample content")

        with flask_app._analysis_cache_lock:
            flask_app._analysis_cache[cls.doc_id] = {
                "form_title": "Student Admission Form",
                "summary_english": "Test admission form",
                "fields": [
                    {"field_name": "student_name", "field_id": "student_name", "question": "Student Name", "is_required": True, "field_type": "text"},
                    {"field_name": "phone", "field_id": "phone", "question": "Phone Number", "is_required": True, "field_type": "phone"},
                ],
                "required_documents": []
            }

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.user_dir):
            import shutil
            shutil.rmtree(cls.user_dir, ignore_errors=True)

    def mock_auth(self, token):
        return {"uid": self.test_uid}

    def test_03_preview_endpoint(self):
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self.mock_auth):
            res = self.client.post(
                "/api/preview",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "document_id": self.doc_id,
                    "answers": {"student_name": "Jane Smith"}
                }
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("form_title"), "Student Admission Form")
            self.assertEqual(data.get("total_fields"), 2)
            self.assertEqual(data.get("filled_count"), 1)

    def test_04_download_pdf_endpoint(self):
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self.mock_auth):
            res = self.client.post(
                "/api/download-pdf",
                headers={"Authorization": "Bearer test_token"},
                json={
                    "document_id": self.doc_id,
                    "answers": {"student_name": "Jane Smith", "phone": "9876543210"}
                }
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.mimetype, "application/pdf")
            self.assertTrue(res.data.startswith(b"%PDF-"))
            self.assertIn("attachment", res.headers.get("Content-Disposition", ""))


if __name__ == "__main__":
    unittest.main()
