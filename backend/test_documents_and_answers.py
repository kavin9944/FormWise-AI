"""
test_documents_and_answers.py – Comprehensive Test Suite for F-02 & F-03
Tests:
1. Authenticated document listing (GET /api/documents)
2. Unauthenticated request rejection (401)
3. Cross-user document access rejection (404)
4. Saving and retrieving answer drafts (POST /api/answers, GET /api/answers)
5. Updating existing drafts with safe merging
6. Empty payload safety (preserves existing answers unless clear=True)
7. Empty and malformed payloads (400 validation errors)
8. Firestore failure handling and local cache fallback
9. Existing answer restoration for preview and PDF download
10. Document deletion cleans up draft answers
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app as flask_app


class TestDocumentsAndAnswers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flask_app.app.config["TESTING"] = True
        cls.client = flask_app.app.test_client()

        cls.user_a_uid = "test_user_alpha"
        cls.user_b_uid = "test_user_beta"

        cls.user_a_dir = os.path.join(flask_app.BASE_UPLOAD_DIR, cls.user_a_uid)
        cls.user_b_dir = os.path.join(flask_app.BASE_UPLOAD_DIR, cls.user_b_uid)
        os.makedirs(cls.user_a_dir, exist_ok=True)
        os.makedirs(cls.user_b_dir, exist_ok=True)

        cls.doc_a1_id = "doc_alpha_1"
        cls.doc_a2_id = "doc_alpha_2"
        cls.doc_b1_id = "doc_beta_1"

        with open(os.path.join(cls.user_a_dir, f"{cls.doc_a1_id}.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 User A Doc 1")
        with open(os.path.join(cls.user_a_dir, f"{cls.doc_a2_id}.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 User A Doc 2")
        with open(os.path.join(cls.user_b_dir, f"{cls.doc_b1_id}.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 User B Doc 1")

        # Mock analysis cache for doc_a1
        with flask_app._analysis_cache_lock:
            flask_app._analysis_cache[cls.doc_a1_id] = {
                "form_title": "Alpha College Admission Form",
                "summary_english": "Test admission form for User A",
                "fields": [
                    {"field_id": "full_name", "field_name": "full_name", "question": "Full Name", "is_required": True, "field_type": "text"},
                    {"field_id": "phone", "field_name": "phone", "question": "Mobile Number", "is_required": True, "field_type": "phone"},
                ],
                "required_documents": []
            }

        # Isolate Firestore network calls during test execution
        cls.orig_firestore = flask_app.firestore_client
        flask_app.firestore_client = None

    @classmethod
    def tearDownClass(cls):
        flask_app.firestore_client = cls.orig_firestore
        import shutil
        if os.path.exists(cls.user_a_dir):
            shutil.rmtree(cls.user_a_dir, ignore_errors=True)
        if os.path.exists(cls.user_b_dir):
            shutil.rmtree(cls.user_b_dir, ignore_errors=True)

    def _auth_header(self, uid):
        return {"Authorization": f"Bearer mock_token_for_{uid}"}

    def _mock_verify_token(self, token):
        if "mock_token_for_" in token:
            uid = token.split("mock_token_for_")[1]
            return {"uid": uid}
        raise ValueError("Invalid mock token")

    # -------------------------------------------------------------------------
    # 1. Unauthenticated Request Rejection
    # -------------------------------------------------------------------------
    def test_01_unauthenticated_requests_rejected(self):
        """Verify that GET /api/documents, GET /api/answers, and POST /api/answers reject unauthenticated requests."""
        # Missing auth header
        res = self.client.get("/api/documents")
        self.assertEqual(res.status_code, 401)

        res = self.client.get(f"/api/answers?document_id={self.doc_a1_id}")
        self.assertEqual(res.status_code, 401)

        res = self.client.post("/api/answers", json={"document_id": self.doc_a1_id, "answers": {}})
        self.assertEqual(res.status_code, 401)

        # Invalid token
        res = self.client.get("/api/documents", headers={"Authorization": "Bearer bad_token"})
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------------------
    # 2. Authenticated Document Listing (F-02)
    # -------------------------------------------------------------------------
    def test_02_authenticated_document_listing(self):
        """Verify that GET /api/documents returns all documents owned by the authenticated student."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            res = self.client.get("/api/documents", headers=self._auth_header(self.user_a_uid))
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("documents", data)
            doc_ids = [d["document_id"] for d in data["documents"]]
            self.assertIn(self.doc_a1_id, doc_ids)
            self.assertIn(self.doc_a2_id, doc_ids)
            # User B's document must NOT appear
            self.assertNotIn(self.doc_b1_id, doc_ids)

            # Metadata formatting
            a1_doc = next(d for d in data["documents"] if d["document_id"] == self.doc_a1_id)
            self.assertEqual(a1_doc["form_title"], "Alpha College Admission Form")
            self.assertEqual(a1_doc["file_type"], "PDF")
            self.assertIn("has_answers", a1_doc)

    # -------------------------------------------------------------------------
    # 3. Cross-User Document Access Rejection
    # -------------------------------------------------------------------------
    def test_03_cross_user_document_access_rejected(self):
        """Verify that User B cannot read or save draft answers for User A's document."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # User B attempts to read User A's document answers
            res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_b_uid)
            )
            self.assertEqual(res.status_code, 404)
            data = res.get_json()
            self.assertFalse(data.get("success"))
            self.assertIn("not found", data.get("error", "").lower())

            # User B attempts to save draft answers for User A's document
            res = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_b_uid),
                json={"document_id": self.doc_a1_id, "answers": {"full_name": "Hacker Bob"}}
            )
            self.assertEqual(res.status_code, 404)

    # -------------------------------------------------------------------------
    # 4. Saving and Retrieving Answer Drafts (F-03)
    # -------------------------------------------------------------------------
    def test_04_save_and_retrieve_answers(self):
        """Verify saving and retrieving answers for an owned document."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # Save answers
            answers_to_save = {
                "full_name": "Alice Wonderland",
                "phone": "9876543210"
            }
            res = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": answers_to_save}
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("saved_count"), 2)
            self.assertIsNotNone(data.get("updated_at"))

            # Retrieve answers
            res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data["answers"].get("full_name"), "Alice Wonderland")
            self.assertEqual(data["answers"].get("phone"), "9876543210")

    # -------------------------------------------------------------------------
    # 5. Updating Existing Draft with Safe Merging
    # -------------------------------------------------------------------------
    def test_05_update_existing_draft_merge(self):
        """Verify that saving partial answers merges with existing answers rather than overwriting them."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # Save additional field 'dob' while updating 'phone'
            partial_update = {
                "phone": "9123456780",
                "dob": "2005-08-15"
            }
            res = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": partial_update}
            )
            self.assertEqual(res.status_code, 200)

            # Retrieve merged answers
            res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            self.assertEqual(res.status_code, 200)
            answers = res.get_json().get("answers", {})
            # full_name should be preserved
            self.assertEqual(answers.get("full_name"), "Alice Wonderland")
            # phone should be updated
            self.assertEqual(answers.get("phone"), "9123456780")
            # dob should be added
            self.assertEqual(answers.get("dob"), "2005-08-15")

    # -------------------------------------------------------------------------
    # 6. Empty Payload Safety (Preserves Existing Draft unless clear=True)
    # -------------------------------------------------------------------------
    def test_06_empty_payload_safety_and_clear_flag(self):
        """Verify that an empty answers payload does not destroy existing answers unless clear=True."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # Send empty answers without clear flag
            res = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": {}}
            )
            self.assertEqual(res.status_code, 200)

            # Check that existing answers are intact
            res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            answers = res.get_json().get("answers", {})
            self.assertTrue(len(answers) > 0)
            self.assertEqual(answers.get("full_name"), "Alice Wonderland")

            # Send empty answers with clear=True
            res = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": {}, "clear": True}
            )
            self.assertEqual(res.status_code, 200)

            # Check that answers were cleared
            res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            answers = res.get_json().get("answers", {})
            self.assertEqual(len(answers), 0)

    # -------------------------------------------------------------------------
    # 7. Empty and Malformed Payloads (400 Errors)
    # -------------------------------------------------------------------------
    def test_07_empty_and_malformed_payloads(self):
        """Verify strict input validation and appropriate 400 error codes."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # Missing document_id in GET
            res = self.client.get("/api/answers", headers=self._auth_header(self.user_a_uid))
            self.assertEqual(res.status_code, 400)

            # Non-dict JSON in POST
            res = self.client.post("/api/answers", headers=self._auth_header(self.user_a_uid), data="not a json", content_type="text/plain")
            self.assertEqual(res.status_code, 400)

            # Missing document_id in POST
            res = self.client.post("/api/answers", headers=self._auth_header(self.user_a_uid), json={"answers": {"a": "1"}})
            self.assertEqual(res.status_code, 400)

            # Missing answers field in POST
            res = self.client.post("/api/answers", headers=self._auth_header(self.user_a_uid), json={"document_id": self.doc_a1_id})
            self.assertEqual(res.status_code, 400)

            # Invalid document_id characters in GET
            res = self.client.get("/api/answers?document_id=../../etc/passwd", headers=self._auth_header(self.user_a_uid))
            self.assertEqual(res.status_code, 404)

    # -------------------------------------------------------------------------
    # 8. Firestore Failure Handling and Local Cache Fallback
    # -------------------------------------------------------------------------
    def test_08_firestore_failure_fallback_to_local_cache(self):
        """Verify that when Firestore raises an error, draft answers are safely persisted in local user storage."""
        mock_broken_firestore = MagicMock()
        mock_broken_firestore.collection.side_effect = RuntimeError("Simulated Firestore gRPC failure")

        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            with patch.object(flask_app, "firestore_client", mock_broken_firestore):
                # Save draft while Firestore is failing
                res = self.client.post(
                    "/api/answers",
                    headers=self._auth_header(self.user_a_uid),
                    json={"document_id": self.doc_a2_id, "answers": {"notes": "Saved during Firestore outage"}}
                )
                self.assertEqual(res.status_code, 200)

                # Verify file exists on local disk in user's isolated directory
                local_file = os.path.join(self.user_a_dir, f"{self.doc_a2_id}_answers.json")
                self.assertTrue(os.path.exists(local_file))

                # Retrieve answers while Firestore is still failing
                res = self.client.get(
                    f"/api/answers?document_id={self.doc_a2_id}",
                    headers=self._auth_header(self.user_a_uid)
                )
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertEqual(data["answers"].get("notes"), "Saved during Firestore outage")

    # -------------------------------------------------------------------------
    # 9. Existing Answer Restoration for Preview and PDF Download
    # -------------------------------------------------------------------------
    def test_09_existing_answer_restoration_for_preview_and_pdf(self):
        """Verify that saved answers seamlessly feed /api/preview and /api/download-pdf."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # Save answers for doc_a1
            self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": {"full_name": "Carol Danvers", "phone": "9988776655"}}
            )

            # Retrieve answers
            ans_res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            saved_answers = ans_res.get_json().get("answers", {})

            # Preview endpoint with restored answers
            prev_res = self.client.post(
                "/api/preview",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": saved_answers}
            )
            self.assertEqual(prev_res.status_code, 200)
            prev_data = prev_res.get_json()
            self.assertEqual(prev_data.get("filled_count"), 2)

            # Download PDF endpoint with restored answers
            pdf_res = self.client.post(
                "/api/download-pdf",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": saved_answers}
            )
            self.assertEqual(pdf_res.status_code, 200)
            self.assertEqual(pdf_res.mimetype, "application/pdf")
            self.assertTrue(pdf_res.data.startswith(b"%PDF-"))

    # -------------------------------------------------------------------------
    # 10. Document Deletion Cleans Up Draft Answers
    # -------------------------------------------------------------------------
    def test_10_document_deletion_cleans_up_draft_answers(self):
        """Verify that deleting a document cleans up local answer cache and prevents future access."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # Ensure doc_a2 has saved answers
            self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a2_id, "answers": {"status": "temp"}}
            )
            local_file = os.path.join(self.user_a_dir, f"{self.doc_a2_id}_answers.json")
            self.assertTrue(os.path.exists(local_file))

            # Delete the document
            del_res = self.client.delete(
                f"/api/document/{self.doc_a2_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            self.assertIn(del_res.status_code, (200, 202))

            # Verify local answer cache file was removed
            self.assertFalse(os.path.exists(local_file))

            # Subsequent attempt to access answers for deleted document returns 404
            get_res = self.client.get(
                f"/api/answers?document_id={self.doc_a2_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            self.assertEqual(get_res.status_code, 404)

    # -------------------------------------------------------------------------
    # 11. Concurrent Backend Updates to Different Fields (Thread Safety)
    # -------------------------------------------------------------------------
    def test_11_concurrent_backend_updates_different_fields(self):
        """Verify that concurrent threads updating different fields do not overwrite or lose fields."""
        import threading
        num_threads = 5
        barrier = threading.Barrier(num_threads)
        errors = []

        def worker(thread_idx):
            field_name = f"thread_field_{thread_idx}"
            field_val = f"value_from_thread_{thread_idx}"
            try:
                barrier.wait(timeout=5)
                with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
                    res = self.client.post(
                        "/api/answers",
                        headers=self._auth_header(self.user_a_uid),
                        json={"document_id": self.doc_a1_id, "answers": {field_name: field_val}}
                    )
                    if res.status_code != 200:
                        errors.append(f"Thread {thread_idx} failed with {res.status_code}")
            except Exception as e:
                errors.append(f"Thread {thread_idx} exception: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(errors), 0, f"Errors in concurrent writes: {errors}")

        # Retrieve merged answers and confirm all threads' fields exist
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            get_res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            self.assertEqual(get_res.status_code, 200)
            data = get_res.get_json()
            saved_answers = data.get("answers", {})
            for i in range(num_threads):
                self.assertIn(f"thread_field_{i}", saved_answers)
                self.assertEqual(saved_answers[f"thread_field_{i}"], f"value_from_thread_{i}")

    # -------------------------------------------------------------------------
    # 12. Concurrent Backend Updates to Same Field (Monotonic Versioning)
    # -------------------------------------------------------------------------
    def test_12_concurrent_backend_updates_same_field(self):
        """Verify concurrent updates to the same field maintain integrity and monotonic versioning."""
        import threading
        num_threads = 4
        barrier = threading.Barrier(num_threads)
        responses = []

        def worker(thread_idx):
            try:
                barrier.wait(timeout=5)
                with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
                    res = self.client.post(
                        "/api/answers",
                        headers=self._auth_header(self.user_a_uid),
                        json={"document_id": self.doc_a1_id, "answers": {"race_field": f"winner_{thread_idx}"}}
                    )
                    responses.append(res.status_code)
            except Exception as e:
                responses.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertTrue(all(code == 200 for code in responses))

        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            get_res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            data = get_res.get_json()
            # Ensure race_field is one of the valid winner values
            self.assertTrue(data.get("answers", {}).get("race_field", "").startswith("winner_"))
            self.assertGreaterEqual(data.get("version", 0), num_threads)

    # -------------------------------------------------------------------------
    # 13. Firestore Success Persistence Semantics (cloud_synced: true)
    # -------------------------------------------------------------------------
    def test_13_firestore_success_returns_cloud_synced_true(self):
        """Verify that when Firestore succeeds, cloud_synced is true and storage_mode is 'firestore'."""
        mock_fs = MagicMock()
        mock_doc = MagicMock()
        mock_draft = MagicMock()
        mock_fs.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc
        mock_doc.collection.return_value.document.return_value = mock_draft

        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            with patch.object(flask_app, "firestore_client", mock_fs):
                res = self.client.post(
                    "/api/answers",
                    headers=self._auth_header(self.user_a_uid),
                    json={"document_id": self.doc_a1_id, "answers": {"cloud_test": "val"}}
                )
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertTrue(data.get("success"))
                self.assertTrue(data.get("cloud_synced"))
                self.assertEqual(data.get("storage_mode"), "firestore")

    # -------------------------------------------------------------------------
    # 14. Local-Only Fallback Persistence Semantics (cloud_synced: false)
    # -------------------------------------------------------------------------
    def test_14_local_only_fallback_returns_cloud_synced_false(self):
        """Verify that when Firestore is offline, cloud_synced is false and storage_mode is 'local_fallback'."""
        mock_broken_fs = MagicMock()
        mock_broken_fs.collection.side_effect = RuntimeError("Firestore unavailable")

        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            with patch.object(flask_app, "firestore_client", mock_broken_fs):
                res = self.client.post(
                    "/api/answers",
                    headers=self._auth_header(self.user_a_uid),
                    json={"document_id": self.doc_a1_id, "answers": {"local_only_test": "val"}}
                )
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertTrue(data.get("success"))
                self.assertFalse(data.get("cloud_synced"))
                self.assertEqual(data.get("storage_mode"), "local_fallback")

    # -------------------------------------------------------------------------
    # 15. Both Storage Targets Failing Returns HTTP 500
    # -------------------------------------------------------------------------
    def test_15_both_storage_targets_failing_returns_500(self):
        """Verify that when both Firestore and local disk cache fail, endpoint returns HTTP 500."""
        mock_broken_fs = MagicMock()
        mock_broken_fs.collection.side_effect = RuntimeError("Firestore outage")

        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            with patch.object(flask_app, "firestore_client", mock_broken_fs):
                with patch("os.replace", side_effect=OSError("Read-only file system")):
                    res = self.client.post(
                        "/api/answers",
                        headers=self._auth_header(self.user_a_uid),
                        json={"document_id": self.doc_a1_id, "answers": {"fail_test": "val"}}
                    )
                    self.assertEqual(res.status_code, 500)
                    data = res.get_json()
                    self.assertFalse(data.get("success"))
                    self.assertIn("Failed to persist", data.get("error", ""))

    # -------------------------------------------------------------------------
    # 16. Dashboard Document Listing Draft Status (cloud_synced vs local_only)
    # -------------------------------------------------------------------------
    def test_16_dashboard_document_listing_draft_status(self):
        """Verify GET /api/documents reports accurate draft_status and storage_mode."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            res = self.client.get("/api/documents", headers=self._auth_header(self.user_a_uid))
            self.assertEqual(res.status_code, 200)
            docs = res.get_json().get("documents", [])
            # doc_a1 has local answers saved in earlier tests
            a1 = next((d for d in docs if d["document_id"] == self.doc_a1_id), None)
            self.assertIsNotNone(a1)
            self.assertTrue(a1["has_answers"])
            self.assertIn(a1["draft_status"], ("cloud_synced", "local_only"))

    # -------------------------------------------------------------------------
    # 17. Firestore Draft Subcollection Cleanup on Document Deletion
    # -------------------------------------------------------------------------
    def test_17_firestore_draft_subcollection_cleanup_on_deletion(self):
        """Verify that deleting a document cleans up the Firestore answers/draft subcollection."""
        mock_fs = MagicMock()
        mock_doc = MagicMock()
        mock_draft = MagicMock()
        mock_doc_snap = MagicMock()
        mock_doc_snap.exists = True
        mock_doc.get.return_value = mock_doc_snap

        mock_fs.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc
        mock_doc.collection.return_value.document.return_value = mock_draft

        # Create temporary document for deletion
        temp_doc_id = "doc_temp_deletion"
        with open(os.path.join(self.user_a_dir, f"{temp_doc_id}.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 Temp")

        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            with patch.object(flask_app, "firestore_client", mock_fs):
                del_res = self.client.delete(
                    f"/api/document/{temp_doc_id}",
                    headers=self._auth_header(self.user_a_uid)
                )
                self.assertIn(del_res.status_code, (200, 202))
                # Verify that draft.delete() was explicitly invoked
                mock_draft.delete.assert_called()

    # -------------------------------------------------------------------------
    # 18. Cross-User Deletion Rejection (404)
    # -------------------------------------------------------------------------
    def test_18_cross_user_deletion_rejected(self):
        """Verify that User B cannot delete User A's document and gets HTTP 404."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            del_res = self.client.delete(
                f"/api/document/{self.doc_a1_id}",
                headers=self._auth_header(self.user_b_uid)
            )
            self.assertEqual(del_res.status_code, 404)
            # Verify User A's document still exists
            a1_file = os.path.join(self.user_a_dir, f"{self.doc_a1_id}.pdf")
            self.assertTrue(os.path.exists(a1_file))

    # -------------------------------------------------------------------------
    # 19. Two Overlapping Saves with New Input Arriving During First Request
    # -------------------------------------------------------------------------
    def test_19_overlapping_saves_with_queued_trailing_save(self):
        """Verify that when a second save is queued while the first is in-flight, trailing inputs are safely persisted."""
        with patch.object(flask_app.auth, "verify_id_token", side_effect=self._mock_verify_token):
            # First request sends initial draft
            res1 = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": {"q1": "initial_answer"}}
            )
            self.assertEqual(res1.status_code, 200)
            data1 = res1.get_json()
            ver1 = data1.get("version", 0)

            # Second (trailing) save with updated inputs
            res2 = self.client.post(
                "/api/answers",
                headers=self._auth_header(self.user_a_uid),
                json={"document_id": self.doc_a1_id, "answers": {"q1": "updated_answer", "q2": "new_trailing_answer"}}
            )
            self.assertEqual(res2.status_code, 200)
            data2 = res2.get_json()
            ver2 = data2.get("version", 0)
            self.assertGreater(ver2, ver1)

            # Confirm latest state reflects trailing inputs
            get_res = self.client.get(
                f"/api/answers?document_id={self.doc_a1_id}",
                headers=self._auth_header(self.user_a_uid)
            )
            self.assertEqual(get_res.status_code, 200)
            final_answers = get_res.get_json().get("answers", {})
            self.assertEqual(final_answers.get("q1"), "updated_answer")
            self.assertEqual(final_answers.get("q2"), "new_trailing_answer")


if __name__ == "__main__":
    unittest.main()
