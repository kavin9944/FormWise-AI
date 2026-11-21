"""
Unit and Integration tests for Gemini API error handling, HTTP status propagation,
and secret sanitization in FormWise AI.

Verifies:
1. F-01: No raw configuration or credential errors leaked to the frontend.
2. F-02: Propagation of original status_code (502, 503, 504) through helper
   functions and endpoint callers (/api/analyse, /api/checklist, /api/readiness, /api/validate).
3. F-03: Explicit timeout (TimeoutError, httpx.TimeoutException) and APIError DEADLINE_EXCEEDED mapping.
4. F-04: Full Flask test-client HTTP-level assertions and model fallback tests.
5. F-05 & F-06: Robust sanitization of Bearer tokens (including padding), headers, and keys.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import httpx
from google.genai.errors import ClientError, ServerError, APIError

import gemini as gemini_module
import app as app_module

TEST_UID = "test_user_error_suite"
AUTH_HEADER = {"Authorization": "Bearer mock_valid_token"}
DOC_ID = "mock_doc_error_test"


class TestGeminiErrorHandling(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app_module.app.config["TESTING"] = True
        cls.client = app_module.app.test_client()

    def setUp(self):
        # Clear analysis cache for clean test isolation
        app_module._analysis_cache.pop(DOC_ID, None)

    # -----------------------------------------------------------------------
    # Sanitization Tests (F-05, F-06)
    # -----------------------------------------------------------------------
    def test_01_sanitize_log_message_comprehensive(self):
        """Ensure _sanitize_log_message strips sensitive credentials across realistic formats."""
        test_strings = [
            ("key=AQ.Ab8RN6JsecretKey123", "key=[REDACTED]"),
            ("x-goog-api-key: secret_custom_header_key", "x-goog-api-key: [REDACTED]"),
            ("api_key='quoted_secret_val'", "api_key='[REDACTED]'"),
            ('api-key="quoted_secret_val2"', 'api-key="[REDACTED]"'),
            ("Bearer eyJhbGciOiJIUzI1NiJ9.testToken==", "Bearer [REDACTED]"),
            ("Bearer eyJhbGciOiJIUzI1NiJ9.singlePad=", "Bearer [REDACTED]"),
            ("AIzaSyD9876543210Key", "AIza[REDACTED]"),
            ("AQ.Ab8RN6Jabc12345", "AQ.[REDACTED]"),
        ]
        for raw, expected in test_strings:
            sanitized = gemini_module._sanitize_log_message(raw)
            self.assertIn(expected, sanitized)
            # Ensure raw secret string does not appear in sanitized output
            for secret in ["secretKey123", "secret_custom_header_key", "quoted_secret_val", "quoted_secret_val2", "testToken", "singlePad"]:
                if secret in raw:
                    self.assertNotIn(secret, sanitized)

    # -----------------------------------------------------------------------
    # Configuration & Leakage Tests (F-01)
    # -----------------------------------------------------------------------
    def test_02_missing_gemini_api_key_returns_503(self):
        """When GEMINI_API_KEY is not set, analyse_form returns 503 with standard message."""
        with patch.object(gemini_module, "GEMINI_API_KEY", None):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 503)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_03_client_initialization_error_returns_503_and_sanitized_msg(self):
        """When _get_client() raises RuntimeError, analyse_form never leaks the raw error string."""
        with patch.object(gemini_module, "_get_client", side_effect=RuntimeError("GEMINI_API_KEY is not configured. Add it to .env")):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 503)
            # Must NOT leak .env or variable names
            self.assertNotIn(".env", res["error"])
            self.assertNotIn("GEMINI_API_KEY", res["error"])
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    # -----------------------------------------------------------------------
    # Error Handling & Status Code Tests (F-03)
    # -----------------------------------------------------------------------
    def test_04_auth_or_permission_denied_returns_503(self):
        """When Gemini returns 403 PERMISSION_DENIED, analyse_form returns 503."""
        mock_client = MagicMock()
        ce = ClientError(403, {"error": {"code": 403, "message": "PERMISSION_DENIED: Free tier unavailable", "status": "PERMISSION_DENIED"}})
        mock_client.models.generate_content.side_effect = ce

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 503)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_05_quota_exhausted_across_all_models_returns_503(self):
        """When quota is exhausted on all models, analyse_form walks fallback chain and returns 503."""
        mock_client = MagicMock()
        ce = ClientError(429, {"error": {"code": 429, "message": "RESOURCE_EXHAUSTED: Quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
        mock_client.models.generate_content.side_effect = ce

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 503)
            # Verify all fallback models were attempted
            expected_attempts = len(gemini_module.FALLBACK_MODELS)
            self.assertEqual(mock_client.models.generate_content.call_count, expected_attempts)

    def test_06_model_fallback_quota_recovers_on_second_model(self):
        """When model 1 fails with quota error, model 2 succeeds and returns valid response."""
        mock_client = MagicMock()
        ce = ClientError(429, {"error": {"code": 429, "message": "RESOURCE_EXHAUSTED: Quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
        mock_success_resp = MagicMock()
        mock_success_resp.text = json.dumps({"form_title": "Recovered Form", "fields": []})
        mock_client.models.generate_content.side_effect = [ce, mock_success_resp]

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertTrue(res["success"])
            self.assertEqual(res["analysis"]["form_title"], "Recovered Form")
            self.assertEqual(mock_client.models.generate_content.call_count, 2)

    def test_07_upstream_server_error_returns_502(self):
        """When upstream Gemini returns 5xx ServerError, analyse_form returns 502 Bad Gateway."""
        mock_client = MagicMock()
        se = ServerError(500, {"error": {"code": 500, "message": "Internal server error"}})
        mock_client.models.generate_content.side_effect = se

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 502)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_08_upstream_server_error_504_returns_504(self):
        """When upstream Gemini ServerError has code 504 or DEADLINE_EXCEEDED, analyse_form returns 504."""
        mock_client = MagicMock()
        se = ServerError(504, {"error": {"code": 504, "message": "DEADLINE_EXCEEDED: Gateway Timeout", "status": "DEADLINE_EXCEEDED"}})
        mock_client.models.generate_content.side_effect = se

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 504)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_08b_server_error_deadline_exceeded_with_non_504_code_returns_504(self):
        """When ServerError has code 500 (or None) but message has DEADLINE_EXCEEDED, analyse_form returns 504."""
        mock_client = MagicMock()
        se = ServerError(500, {"error": {"code": 500, "message": "DEADLINE_EXCEEDED: upstream timeout", "status": "DEADLINE_EXCEEDED"}})
        mock_client.models.generate_content.side_effect = se

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 504)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_09_httpx_timeout_returns_504(self):
        """When httpx transport raises TimeoutException, analyse_form returns 504 Gateway Timeout."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = httpx.ReadTimeout("Read timed out on socket")

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 504)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_10_provider_deadline_error_returns_504(self):
        """When APIError contains DEADLINE_EXCEEDED, analyse_form returns 504."""
        mock_client = MagicMock()
        ae = APIError(504, {"error": {"code": 504, "message": "DEADLINE_EXCEEDED: upstream timeout", "status": "DEADLINE_EXCEEDED"}})
        mock_client.models.generate_content.side_effect = ae

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 504)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    def test_11_unreadable_json_response_returns_502(self):
        """When upstream returns non-JSON or unreadable content, analyse_form returns 502."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "<<<not valid json>>>"
        mock_client.models.generate_content.return_value = mock_resp

        with patch.object(gemini_module, "_get_client", return_value=mock_client):
            res = gemini_module.analyse_form("Form Text", language="both")
            self.assertFalse(res["success"])
            self.assertEqual(res["status_code"], 502)
            self.assertEqual(res["error"], "AI service is temporarily unavailable. Please try again shortly.")

    # -----------------------------------------------------------------------
    # Helper Function Status Code Propagation Tests (F-02)
    # -----------------------------------------------------------------------
    def test_12_helper_functions_propagate_status_codes(self):
        """Verify _get_document_analysis and _get_document_fields propagate exact status codes."""
        dummy_file = "dummy_path.pdf"

        for expected_code in [502, 503, 504]:
            mock_fail = {
                "success": False,
                "analysis": None,
                "error": "AI service is temporarily unavailable. Please try again shortly.",
                "status_code": expected_code
            }
            with patch.object(app_module, "extract_document_text", return_value={"success": True, "full_text": "Sample text", "file_type": "pdf"}):
                with patch.object(app_module, "analyse_form", return_value=mock_fail):
                    # 1. _get_document_analysis
                    data, err, status = app_module._get_document_analysis(TEST_UID, DOC_ID, dummy_file)
                    self.assertIsNone(data)
                    self.assertEqual(err, "AI service is temporarily unavailable. Please try again shortly.")
                    self.assertEqual(status, expected_code)

                    # 2. _get_document_fields
                    fields, f_err, f_status = app_module._get_document_fields(TEST_UID, DOC_ID, dummy_file)
                    self.assertIsNone(fields)
                    self.assertEqual(f_err, "AI service is temporarily unavailable. Please try again shortly.")
                    self.assertEqual(f_status, expected_code)

    # -----------------------------------------------------------------------
    # HTTP Endpoint Integration Tests (F-02, F-04)
    # -----------------------------------------------------------------------
    @patch.object(app_module, "_check_analyse_rate_limit", return_value=False)
    @patch.object(app_module, "_authenticate_request", return_value=(TEST_UID, None))
    @patch.object(app_module, "_get_user_document_path", return_value="dummy_path.pdf")
    @patch.object(app_module, "extract_document_text", return_value={"success": True, "full_text": "Sample form text", "file_type": "pdf"})
    def test_13_endpoint_api_analyse_propagates_status_codes(self, mock_ext, mock_path, mock_auth, mock_rate):
        """Verify /api/analyse returns exact 502, 503, 504 status codes over HTTP."""
        for expected_code in [502, 503, 504]:
            mock_result = {
                "success": False,
                "analysis": None,
                "error": "AI service is temporarily unavailable. Please try again shortly.",
                "status_code": expected_code
            }
            with patch.object(app_module, "analyse_form", return_value=mock_result):
                resp = self.client.post(
                    "/api/analyse",
                    headers=AUTH_HEADER,
                    json={"document_id": DOC_ID, "language": "both"}
                )
                self.assertEqual(resp.status_code, expected_code)
                body = resp.get_json()
                self.assertFalse(body["success"])
                self.assertEqual(body["error"], "AI service is temporarily unavailable. Please try again shortly.")

    @patch.object(app_module, "_authenticate_request", return_value=(TEST_UID, None))
    @patch.object(app_module, "_get_user_document_path", return_value="dummy_path.pdf")
    @patch.object(app_module, "extract_document_text", return_value={"success": True, "full_text": "Sample form text", "file_type": "pdf"})
    def test_14_endpoint_api_checklist_propagates_status_codes(self, mock_ext, mock_path, mock_auth):
        """Verify /api/checklist returns exact 502, 503, 504 status codes over HTTP."""
        for expected_code in [502, 503, 504]:
            mock_result = {
                "success": False,
                "analysis": None,
                "error": "AI service is temporarily unavailable. Please try again shortly.",
                "status_code": expected_code
            }
            with patch.object(app_module, "analyse_form", return_value=mock_result):
                resp = self.client.post(
                    "/api/checklist",
                    headers=AUTH_HEADER,
                    json={"document_id": DOC_ID}
                )
                self.assertEqual(resp.status_code, expected_code)
                body = resp.get_json()
                self.assertFalse(body["success"])
                self.assertEqual(body["error"], "AI service is temporarily unavailable. Please try again shortly.")

    @patch.object(app_module, "_authenticate_request", return_value=(TEST_UID, None))
    @patch.object(app_module, "_get_user_document_path", return_value="dummy_path.pdf")
    @patch.object(app_module, "extract_document_text", return_value={"success": True, "full_text": "Sample form text", "file_type": "pdf"})
    def test_15_endpoint_api_readiness_propagates_status_codes(self, mock_ext, mock_path, mock_auth):
        """Verify /api/readiness returns exact 502, 503, 504 status codes over HTTP."""
        for expected_code in [502, 503, 504]:
            mock_result = {
                "success": False,
                "analysis": None,
                "error": "AI service is temporarily unavailable. Please try again shortly.",
                "status_code": expected_code
            }
            with patch.object(app_module, "analyse_form", return_value=mock_result):
                resp = self.client.post(
                    "/api/readiness",
                    headers=AUTH_HEADER,
                    json={"document_id": DOC_ID, "answers": {}}
                )
                self.assertEqual(resp.status_code, expected_code)
                body = resp.get_json()
                self.assertFalse(body["success"])
                self.assertEqual(body["error"], "AI service is temporarily unavailable. Please try again shortly.")

    @patch.object(app_module, "_check_validate_rate_limit", return_value=False)
    @patch.object(app_module, "_authenticate_request", return_value=(TEST_UID, None))
    @patch.object(app_module, "_get_user_document_path", return_value="dummy_path.pdf")
    @patch.object(app_module, "extract_document_text", return_value={"success": True, "full_text": "Sample form text", "file_type": "pdf"})
    def test_16_endpoint_api_validate_propagates_status_codes(self, mock_ext, mock_path, mock_auth, mock_rate):
        """Verify /api/validate returns exact 502, 503, 504 status codes over HTTP."""
        for expected_code in [502, 503, 504]:
            mock_result = {
                "success": False,
                "analysis": None,
                "error": "AI service is temporarily unavailable. Please try again shortly.",
                "status_code": expected_code
            }
            with patch.object(app_module, "analyse_form", return_value=mock_result):
                resp = self.client.post(
                    "/api/validate",
                    headers=AUTH_HEADER,
                    json={"document_id": DOC_ID, "answers": {"field1": "val1"}}
                )
                self.assertEqual(resp.status_code, expected_code)
                body = resp.get_json()
                self.assertFalse(body["success"])
                self.assertEqual(body["error"], "AI service is temporarily unavailable. Please try again shortly.")


if __name__ == "__main__":
    unittest.main()
