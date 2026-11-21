import os
import sys
import uuid
import re
import json
import time
import datetime
import threading
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, auth
from extractor import extract_document_text
from gemini import analyse_form, GEMINI_API_KEY
from validator import validate_form
from checklist import build_checklist, confirm_document_match
from scoring import calculate_readiness
from pdf_generator import generate_filled_pdf

# Path to Firebase Admin service account credentials
# Priority:
# 1. Environment variable FIREBASE_SERVICE_ACCOUNT_PATH (if set and exists)
# 2. Local backend/serviceAccountKey.json (project-relative, recommended for teammates)
# 3. Project root serviceAccountKey.json or external secrets folder
SERVICE_ACCOUNT_ENV_PATH = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
LOCAL_SERVICE_ACCOUNT = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
ROOT_SERVICE_ACCOUNT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "serviceAccountKey.json"))
LEGACY_SECRETS_PATH = r"D:\ASTRON\secrets\formwise-service-account.json"

target_path = None
if SERVICE_ACCOUNT_ENV_PATH and os.path.exists(SERVICE_ACCOUNT_ENV_PATH):
    target_path = SERVICE_ACCOUNT_ENV_PATH
elif os.path.exists(LOCAL_SERVICE_ACCOUNT):
    target_path = LOCAL_SERVICE_ACCOUNT
elif os.path.exists(ROOT_SERVICE_ACCOUNT):
    target_path = ROOT_SERVICE_ACCOUNT
elif os.path.exists(LEGACY_SECRETS_PATH):
    target_path = LEGACY_SECRETS_PATH

# Initialize Firebase Admin SDK safely (preventing duplicate initialization)
firebase_cred_obj = None
firestore_client = None

if not firebase_admin._apps:
    if target_path:
        try:
            firebase_cred_obj = credentials.Certificate(target_path)
            firebase_admin.initialize_app(firebase_cred_obj)
            print("Firebase Admin SDK initialized successfully.")
        except Exception as e:
            print("Error initializing Firebase Admin SDK:", str(e))
    else:
        print("Warning: Firebase service account credentials file not found.")
else:
    app_instance = firebase_admin.get_app()
    if hasattr(app_instance, "credential"):
        firebase_cred_obj = app_instance.credential

# 1. Attempt to initialize official firestore client; fallback to REST client if gRPC is blocked
try:
    from firebase_admin import firestore as admin_firestore
    firestore_client = admin_firestore.client()
    print("Firestore native client initialized successfully.")
except Exception as fs_init_err:
    print(f"Native Firestore client unavailable ({fs_init_err}). Initializing REST Firestore client.")

    class FirestoreRestClient:
        """
        Lightweight, secure Firestore client using Google Cloud REST API v1.
        Uses the authenticated service account credentials from Firebase Admin SDK.
        Ensures 100% compatibility when native gRPC libraries are restricted by OS policies.
        """
        def __init__(self, cred_obj):
            self.cred_obj = cred_obj
            self._google_cred = None
            if cred_obj:
                try:
                    self._google_cred = cred_obj.get_credential()
                except Exception as cred_err:
                    print(f"Error obtaining Google credential: {cred_err}")

        def _get_auth_headers(self):
            import requests
            from google.auth.transport.requests import Request
            if not self._google_cred:
                raise RuntimeError("No Google credentials available for Firestore client.")
            if not self._google_cred.valid:
                self._google_cred.refresh(Request())
            return {
                "Authorization": f"Bearer {self._google_cred.token}",
                "Content-Type": "application/json"
            }

        def _get_project_id(self):
            if self.cred_obj and hasattr(self.cred_obj, "project_id") and self.cred_obj.project_id:
                return self.cred_obj.project_id
            return os.environ.get("GOOGLE_CLOUD_PROJECT", "formwise-ai-7caa9")

        def set_document(self, collection_path: str, doc_id: str, data: dict):
            import requests
            project_id = self._get_project_id()
            url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection_path}/{doc_id}"

            fields = {}
            for k, v in data.items():
                if isinstance(v, str):
                    fields[k] = {"stringValue": v}
                elif isinstance(v, int):
                    fields[k] = {"integerValue": str(v)}
                elif isinstance(v, float):
                    fields[k] = {"doubleValue": v}
                elif isinstance(v, bool):
                    fields[k] = {"booleanValue": v}
                elif isinstance(v, datetime.datetime):
                    iso_val = v.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
                    fields[k] = {"timestampValue": iso_val}
                elif isinstance(v, dict):
                    fields[k] = {"stringValue": json.dumps(v)}
                else:
                    fields[k] = {"stringValue": str(v)}

            resp = requests.patch(url, headers=self._get_auth_headers(), json={"fields": fields}, timeout=10)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Firestore REST set error: {resp.status_code} - {resp.text}")
            return resp.json()

        def update_document(self, collection_path: str, doc_id: str, fields_to_update: dict):
            import requests
            project_id = self._get_project_id()
            update_mask = "&".join([f"updateMask.fieldPaths={k}" for k in fields_to_update.keys()])
            url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection_path}/{doc_id}?{update_mask}"

            fields = {}
            for k, v in fields_to_update.items():
                if isinstance(v, str):
                    fields[k] = {"stringValue": v}
                elif isinstance(v, int):
                    fields[k] = {"integerValue": str(v)}
                elif isinstance(v, float):
                    fields[k] = {"doubleValue": v}
                elif isinstance(v, bool):
                    fields[k] = {"booleanValue": v}
                elif isinstance(v, datetime.datetime):
                    iso_val = v.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
                    fields[k] = {"timestampValue": iso_val}
                elif isinstance(v, dict):
                    fields[k] = {"stringValue": json.dumps(v)}
                else:
                    fields[k] = {"stringValue": str(v)}

            resp = requests.patch(url, headers=self._get_auth_headers(), json={"fields": fields}, timeout=10)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Firestore REST update error: {resp.status_code} - {resp.text}")
            return resp.json()

        def get_document(self, collection_path: str, doc_id: str):
            import requests
            project_id = self._get_project_id()
            url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection_path}/{doc_id}"
            resp = requests.get(url, headers=self._get_auth_headers(), timeout=10)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise RuntimeError(f"Firestore REST get error: {resp.status_code} - {resp.text}")
            doc_data = resp.json()
            fields = doc_data.get("fields", {})
            out = {}
            for k, val_dict in fields.items():
                for _, val in val_dict.items():
                    out[k] = val
                    break
            return out

        def list_documents(self, collection_path: str):
            import requests
            project_id = self._get_project_id()
            url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{collection_path}"
            resp = requests.get(url, headers=self._get_auth_headers(), timeout=10)
            if resp.status_code != 200:
                return []
            res_json = resp.json()
            documents = []
            for doc_item in res_json.get("documents", []):
                fields = doc_item.get("fields", {})
                doc_dict = {}
                for k, val_dict in fields.items():
                    for _, val in val_dict.items():
                        doc_dict[k] = val
                        break
                name = doc_item.get("name", "")
                if "/" in name:
                    doc_dict["document_id"] = name.split("/")[-1]
                documents.append(doc_dict)
            return documents

    firestore_client = FirestoreRestClient(firebase_cred_obj)


def save_document_metadata_to_firestore(uid: str, doc_id: str, original_filename: str, file_type: str) -> bool:
    """
    Saves document metadata under users/{authenticated_uid}/documents/{document_id}.
    Safe error handling to prevent leaking internal server details.
    """
    if not firestore_client:
        print("Warning: Firestore client not initialized. Skipping metadata storage.")
        return False

    collection_path = f"users/{uid}/documents"
    doc_data = {
        "document_id": doc_id,
        "original_filename": original_filename,
        "file_type": file_type,
        "upload_timestamp": datetime.datetime.now(datetime.timezone.utc),
        "status": "uploaded"
    }

    try:
        if hasattr(firestore_client, "collection"):
            doc_ref = firestore_client.collection("users").document(uid).collection("documents").document(doc_id)
            doc_ref.set(doc_data)
        elif hasattr(firestore_client, "set_document"):
            firestore_client.set_document(collection_path, doc_id, doc_data)
        return True
    except Exception as e:
        print(f"Error saving document metadata to Firestore for user {uid}, doc {doc_id}: {e}")
        return False


def update_document_status_in_firestore(uid: str, doc_id: str, new_status: str) -> bool:
    """
    Updates the document status under users/{authenticated_uid}/documents/{document_id}.
    """
    if not firestore_client:
        print("Warning: Firestore client not initialized. Skipping status update.")
        return False

    collection_path = f"users/{uid}/documents"
    update_data = {
        "status": new_status,
        "updated_at": datetime.datetime.now(datetime.timezone.utc)
    }

    try:
        if hasattr(firestore_client, "collection"):
            doc_ref = firestore_client.collection("users").document(uid).collection("documents").document(doc_id)
            doc_ref.update(update_data)
        elif hasattr(firestore_client, "update_document"):
            firestore_client.update_document(collection_path, doc_id, update_data)
        return True
    except Exception as e:
        print(f"Error updating document status in Firestore for user {uid}, doc {doc_id}: {e}")
        return False


# In-memory confirmed matches cache: { (safe_uid, safe_doc_id): { requirement_id: selected_doc_id } }
_matches_cache_lock = threading.Lock()
_confirmed_matches_cache: Dict[Tuple[str, str], Dict[str, str]] = {}


def _get_persisted_confirmed_matches(safe_uid: str, safe_doc_id: str) -> Dict[str, str]:
    """
    Retrieves confirmed document matches strictly from authoritative Firestore metadata.
    Guarantees in-memory cache never overrides newer persisted Firestore data.
    """
    cache_key = (safe_uid, safe_doc_id)

    # 1. Query authoritative Firestore first
    if firestore_client:
        try:
            if hasattr(firestore_client, "collection"):
                doc_snap = firestore_client.collection("users").document(safe_uid).collection("documents").document(safe_doc_id).get()
                if doc_snap.exists:
                    data = doc_snap.to_dict() or {}
                    matches = data.get("confirmed_matches")
                    if isinstance(matches, dict):
                        with _matches_cache_lock:
                            _confirmed_matches_cache[cache_key] = dict(matches)
                        return dict(matches)
                    elif matches is None:
                        # Explicitly empty in Firestore
                        with _matches_cache_lock:
                            _confirmed_matches_cache[cache_key] = {}
                        return {}
            elif hasattr(firestore_client, "get_document"):
                doc_data = firestore_client.get_document(f"users/{safe_uid}/documents", safe_doc_id)
                if doc_data:
                    matches = doc_data.get("confirmed_matches")
                    if isinstance(matches, str):
                        try:
                            matches = json.loads(matches)
                        except Exception:
                            matches = {}
                    if isinstance(matches, dict):
                        with _matches_cache_lock:
                            _confirmed_matches_cache[cache_key] = dict(matches)
                        return dict(matches)
        except Exception as e:
            print(f"Note: Error reading confirmed matches from Firestore (using cache fallback): {e}")

    # 2. Fallback to in-memory cache if Firestore is offline
    with _matches_cache_lock:
        if cache_key in _confirmed_matches_cache:
            return dict(_confirmed_matches_cache[cache_key])

    return {}


def _save_persisted_confirmed_matches(safe_uid: str, safe_doc_id: str, matches: Dict[str, str]) -> bool:
    """
    Persists student confirmed matches to Firestore and updates in-memory cache.
    Returns True if successfully saved; False on database error.
    Ensures Firestore failures are never silently masked as successes.
    """
    cache_key = (safe_uid, safe_doc_id)

    if firestore_client:
        try:
            if hasattr(firestore_client, "collection"):
                doc_ref = firestore_client.collection("users").document(safe_uid).collection("documents").document(safe_doc_id)
                try:
                    doc_ref.update({
                        "confirmed_matches": matches,
                        "updated_at": datetime.datetime.now(datetime.timezone.utc)
                    })
                except Exception:
                    doc_ref.set({
                        "confirmed_matches": matches,
                        "updated_at": datetime.datetime.now(datetime.timezone.utc)
                    })
                with _matches_cache_lock:
                    _confirmed_matches_cache[cache_key] = dict(matches)
                return True
            elif hasattr(firestore_client, "update_document"):
                firestore_client.update_document(
                    f"users/{safe_uid}/documents",
                    safe_doc_id,
                    {"confirmed_matches": matches}
                )
                with _matches_cache_lock:
                    _confirmed_matches_cache[cache_key] = dict(matches)
                return True
        except Exception as e:
            print(f"Error saving confirmed matches to Firestore: {e}")
            return False

    # Standalone mock/testing fallback when no Firestore client configured
    with _matches_cache_lock:
        _confirmed_matches_cache[cache_key] = dict(matches)
    return True


def _get_verified_confirmed_matches(
    safe_uid: str,
    safe_doc_id: str,
    required_documents: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Retrieves and strictly verifies confirmed matches for the authenticated student.
    Guarantees:
      1. Sourced from authoritative Firestore document metadata.
      2. Requirement ID must exist in the document's required_documents list.
      3. Confirmed uploaded file must physically exist in user's isolated upload directory.
      4. Deleted or missing uploaded files are automatically stripped and never counted.
      5. Frontend request bodies can never inject or bypass confirmed matches.
    """
    raw_matches = _get_persisted_confirmed_matches(safe_uid, safe_doc_id)
    if not raw_matches or not isinstance(raw_matches, dict):
        return {}

    valid_req_ids = {r.get("doc_id") for r in required_documents if isinstance(r, dict) and r.get("doc_id")}
    verified_matches: Dict[str, str] = {}

    for req_id, selected_doc_id in raw_matches.items():
        if req_id not in valid_req_ids:
            continue

        # Prevent form document from matching itself as supporting document
        if selected_doc_id == safe_doc_id:
            continue

        # Verify uploaded document physically exists in user's isolated storage
        doc_path = _get_user_document_path(safe_uid, selected_doc_id)
        if not doc_path or not os.path.exists(doc_path):
            continue

        verified_matches[req_id] = selected_doc_id

    return verified_matches


# Initialize Flask application with frontend static directory
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# Configure maximum request payload to 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# Base uploads directory (located outside public static webroot)
BASE_UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)

# Allowed extensions and magic byte signatures
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def validate_magic_bytes(file_stream, ext):
    """Verify that file content header matches expected magic bytes signature."""
    header = file_stream.read(16)
    file_stream.seek(0)
    if ext == "pdf":
        return header.startswith(b"%PDF-")
    elif ext in ("jpg", "jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    elif ext == "png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    return False


# Enable CORS with support for frontend origins and Authorization headers
CORS(app, resources={r"/*": {"origins": "*"}}, allow_headers=["Content-Type", "Authorization"])


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle uploads exceeding maximum allowed size."""
    return jsonify({
        "success": False,
        "error": "File size exceeds the 10 MB maximum limit."
    }), 413


@app.route("/", methods=["GET"])
def home():
    """Serve the landing / home page for FormWise AI."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint returning service status in JSON format."""
    return jsonify({
        "status": "success",
        "message": "Backend is healthy",
        "firebase_admin_initialized": bool(firebase_admin._apps),
        "firestore_initialized": bool(firestore_client is not None)
    })


# ---------------------------------------------------------------------------
# Authentication and Path Resolution Helpers
# ---------------------------------------------------------------------------

def _authenticate_request() -> Tuple[Optional[str], Optional[Tuple[Any, int]]]:
    """
    Verifies Firebase Bearer token from the request Authorization header.
    Returns:
        (safe_uid: str, None) on successful verification.
        (None, (error_response, 401/400)) on failure.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, (jsonify({
            "success": False,
            "error": "Missing or malformed Authorization header. Expected 'Bearer <token>'."
        }), 401)

    id_token = auth_header.split("Bearer ", 1)[1].strip()
    if not id_token:
        return None, (jsonify({
            "success": False,
            "error": "Authentication token missing."
        }), 401)

    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token.get("uid")
        if not uid:
            return None, (jsonify({
                "success": False,
                "error": "Invalid token: UID claim missing."
            }), 401)
        safe_uid = re.sub(r"[^a-zA-Z0-9_\-]", "", str(uid))
        if not safe_uid:
            return None, (jsonify({
                "success": False,
                "error": "Invalid user identity format."
            }), 400)
        return safe_uid, None
    except Exception:
        return None, (jsonify({
            "success": False,
            "error": "Unauthorized: Invalid or expired Firebase authentication token."
        }), 401)


def _get_user_document_path(safe_uid: str, document_id: str) -> Optional[str]:
    """
    Locates target document file in user's isolated storage directory:
    uploads/<safe_uid>/<safe_doc_id>.*
    Guarantees path traversal prevention via os.path.commonpath.
    """
    if not safe_uid or not document_id:
        return None
    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(document_id))
    if not safe_doc_id:
        return None

    user_upload_dir = os.path.join(BASE_UPLOAD_DIR, safe_uid)
    if not os.path.exists(user_upload_dir):
        return None

    for fname in os.listdir(user_upload_dir):
        if fname.startswith(safe_doc_id + "."):
            candidate = os.path.join(user_upload_dir, fname)
            if os.path.commonpath([candidate, user_upload_dir]) == user_upload_dir and os.path.exists(candidate):
                return candidate
    return None


def _get_user_uploaded_documents(safe_uid: str) -> List[Dict[str, Any]]:
    """
    Retrieves all uploaded document metadata objects belonging to the authenticated user.
    Sources from Firestore native/REST client and reconciles with local storage files.
    """
    documents: List[Dict[str, Any]] = []
    seen_doc_ids: set = set()

    # 1. Query Firestore if available
    if firestore_client:
        try:
            if hasattr(firestore_client, "collection"):
                docs_ref = firestore_client.collection("users").document(safe_uid).collection("documents").stream()
                for d in docs_ref:
                    doc_data = d.to_dict() or {}
                    did = doc_data.get("document_id") or d.id
                    if did and did not in seen_doc_ids:
                        doc_data["document_id"] = did
                        documents.append(doc_data)
                        seen_doc_ids.add(did)
            elif hasattr(firestore_client, "list_documents"):
                rest_docs = firestore_client.list_documents(f"users/{safe_uid}/documents")
                for d in rest_docs:
                    did = d.get("document_id")
                    if did and did not in seen_doc_ids:
                        documents.append(d)
                        seen_doc_ids.add(did)
        except Exception as e:
            print(f"Note: Error querying Firestore user documents: {e}")

    # 2. Check filesystem user directory to ensure all files in storage are represented
    user_upload_dir = os.path.join(BASE_UPLOAD_DIR, safe_uid)
    if os.path.exists(user_upload_dir):
        try:
            for fname in os.listdir(user_upload_dir):
                if "." in fname:
                    doc_id, ext = fname.rsplit(".", 1)
                    if doc_id and doc_id not in seen_doc_ids:
                        documents.append({
                            "document_id": doc_id,
                            "original_filename": fname,
                            "file_type": ext.upper(),
                            "status": "uploaded"
                        })
                        seen_doc_ids.add(doc_id)
        except Exception as e:
            print(f"Note: Error reading user storage files: {e}")

    return documents


# ---------------------------------------------------------------------------
# Core Analysis & Rate Limiting
# ---------------------------------------------------------------------------
_analyse_rate_lock = threading.Lock()
_analyse_last_call: dict = {}          # { safe_uid: last_call_epoch_seconds }
ANALYSE_COOLDOWN_SECONDS: int = 15     # Min seconds between calls per user

_analysis_cache_lock = threading.Lock()
_analysis_cache: dict = {}              # { safe_doc_id: analysis_dict }

_validate_rate_lock = threading.Lock()
_validate_last_call: dict = {}          # { safe_uid: last_call_epoch_seconds }
VALIDATE_COOLDOWN_SECONDS: float = 1.0  # 1 second cooldown per user to prevent burst spam


def _check_analyse_rate_limit(safe_uid: str) -> bool:
    """Returns True if the user is within the cooldown window (should be blocked)."""
    now = time.monotonic()
    with _analyse_rate_lock:
        last = _analyse_last_call.get(safe_uid, 0.0)
        if now - last < ANALYSE_COOLDOWN_SECONDS:
            return True
        _analyse_last_call[safe_uid] = now
        return False


def _check_validate_rate_limit(safe_uid: str) -> bool:
    """Returns True if the user sends repeated validate requests too quickly."""
    now = time.monotonic()
    with _validate_rate_lock:
        last = _validate_last_call.get(safe_uid, 0.0)
        if now - last < VALIDATE_COOLDOWN_SECONDS:
            return True
        _validate_last_call[safe_uid] = now
        return False


def _map_analysis_error_status(err_msg: Optional[str]) -> int:
    """
    Maps an analysis error message to an appropriate HTTP status code:
    - 504 for timeouts
    - 503 for unavailable AI services (auth / quota / unconfigured / provider outage)
    - 502 for invalid or unreadable upstream provider responses
    - 422 for unprocessable document text / extraction failures
    - 500 for unexpected internal errors
    """
    if not err_msg:
        return 503
    msg = str(err_msg).lower()
    if "timed out" in msg or "timeout" in msg or "deadline" in msg:
        return 504
    if "temporarily unavailable" in msg or "not configured" in msg or "quota" in msg or "authentication" in msg:
        return 503
    if "unreadable" in msg or "invalid data format" in msg or "rejected" in msg:
        return 502
    if "no readable text" in msg or "failed to extract" in msg:
        return 422
    return 503


def _get_document_analysis(safe_uid: str, safe_doc_id: str, target_file: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    """
    Retrieves full form analysis (fields + required_documents) for a document.
    Reuses cached analysis if available; otherwise extracts text and calls analyse_form().
    Returns (analysis_dict, error_message, status_code).
    """
    with _analysis_cache_lock:
        cached = _analysis_cache.get(safe_doc_id)
        if cached and isinstance(cached, dict) and "fields" in cached:
            return cached, None, 200

    try:
        extraction_result = extract_document_text(target_file)
    except Exception:
        return None, "An error occurred while reading the document.", 500

    if not extraction_result.get("success"):
        return None, extraction_result.get("error", "Failed to extract text from the document."), 422

    full_text = extraction_result.get("full_text", "")
    if not full_text.strip():
        return None, "No readable text could be extracted from this document.", 422

    MAX_INPUT_CHARS = 20_000
    if len(full_text) > MAX_INPUT_CHARS:
        full_text = full_text[:MAX_INPUT_CHARS]

    # Run analysis using existing Gemini service
    result = analyse_form(text=full_text, language="both")
    if not result.get("success"):
        status_code = result.get("status_code") or _map_analysis_error_status(result.get("error"))
        return None, result.get("error", "AI service is temporarily unavailable. Please try again shortly."), status_code

    analysis_data = result.get("analysis") or {}

    with _analysis_cache_lock:
        _analysis_cache[safe_doc_id] = analysis_data

    # Update Firestore status
    update_document_status_in_firestore(
        uid=safe_uid,
        doc_id=safe_doc_id,
        new_status="analysed"
    )

    return analysis_data, None, 200


def _get_document_fields(safe_uid: str, safe_doc_id: str, target_file: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str], int]:
    """Retrieves form field definitions for a document."""
    analysis_data, err, status_code = _get_document_analysis(safe_uid, safe_doc_id, target_file)
    if err or not analysis_data:
        return None, err, status_code
    return analysis_data.get("fields", []), None, 200


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_document():
    """
    Secure Document Upload Endpoint:
    1. Authenticates student via Firebase ID Token in Authorization header.
    2. Validates file presence, extension (PDF, JPG, JPEG, PNG), size, and magic bytes.
    3. Saves securely in a student-isolated folder (uploads/<uid>/).
    4. Records document metadata in Firestore under users/{uid}/documents/{document_id}.
    5. Returns sanitized document ID and status without exposing local server paths.
    """
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No file field found in request. Please upload using key 'file'."
        }), 400

    uploaded_file = request.files["file"]
    if not uploaded_file or uploaded_file.filename == "":
        return jsonify({
            "success": False,
            "error": "No file selected for upload."
        }), 400

    original_filename = secure_filename(uploaded_file.filename)
    if not original_filename or "." not in original_filename:
        return jsonify({
            "success": False,
            "error": "Invalid filename or missing file extension."
        }), 400

    ext = original_filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f"Unsupported file type (.{ext}). Allowed formats: PDF, JPG, JPEG, PNG."
        }), 400

    try:
        uploaded_file.seek(0, os.SEEK_END)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)

        if file_size == 0:
            return jsonify({
                "success": False,
                "error": "Uploaded file is empty (0 bytes)."
            }), 400

        if not validate_magic_bytes(uploaded_file.stream, ext):
            return jsonify({
                "success": False,
                "error": "File signature does not match the claimed file extension."
            }), 400
    except Exception:
        return jsonify({
            "success": False,
            "error": "Unable to verify file contents."
        }), 400

    user_upload_dir = os.path.join(BASE_UPLOAD_DIR, safe_uid)
    os.makedirs(user_upload_dir, exist_ok=True)

    document_id = uuid.uuid4().hex
    stored_filename = f"{document_id}.{ext}"
    destination_path = os.path.join(user_upload_dir, stored_filename)

    try:
        uploaded_file.save(destination_path)
    except Exception:
        return jsonify({
            "success": False,
            "error": "Failed to store document securely."
        }), 500

    save_document_metadata_to_firestore(
        uid=safe_uid,
        doc_id=document_id,
        original_filename=original_filename,
        file_type=ext.upper()
    )

    return jsonify({
        "success": True,
        "message": "Document uploaded successfully.",
        "document_id": document_id,
        "filename": original_filename,
        "file_type": ext.upper()
    }), 201


@app.route("/api/extract", methods=["POST"])
def extract_document():
    """
    Authenticated Document Text Extraction Endpoint
    - Verifies Firebase ID token.
    - Locates the student's document by document_id in uploads/<uid>/.
    - Extracts text via PyMuPDF and OCR via extractor.py.
    - Updates document status in Firestore to 'extracted'.
    - Returns structured extracted text and metadata.
    """
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    data = request.get_json(silent=True) or {}
    document_id = data.get("document_id") or request.form.get("document_id")
    if not document_id:
        return jsonify({
            "success": False,
            "error": "Missing required field: 'document_id'."
        }), 400

    target_file = _get_user_document_path(safe_uid, document_id)
    if not target_file:
        return jsonify({
            "success": False,
            "error": "Document not found in user storage."
        }), 404

    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(document_id))

    try:
        extraction_result = extract_document_text(target_file)
        if not extraction_result.get("success"):
            return jsonify({
                "success": False,
                "error": extraction_result.get("error", "Extraction failed.")
            }), 500

        update_document_status_in_firestore(
            uid=safe_uid,
            doc_id=safe_doc_id,
            new_status="extracted"
        )

        return jsonify({
            "success": True,
            "document_id": safe_doc_id,
            "file_type": extraction_result.get("file_type"),
            "page_count": extraction_result.get("page_count", 1),
            "word_count": extraction_result.get("word_count", 0),
            "full_text": extraction_result.get("full_text", ""),
            "pages": extraction_result.get("pages", [])
        }), 200

    except Exception:
        return jsonify({
            "success": False,
            "error": "An error occurred during document extraction."
        }), 500


@app.route("/api/analyse", methods=["POST"])
def analyse_document():
    """
    Authenticated AI Form Analysis Endpoint.
    1. Verify Firebase ID token.
    2. Validate document_id and language (english / tamil / both).
    3. Locate document in user's isolated upload directory.
    4. Extract text using extract_document_text().
    5. Call analyse_form() in gemini.py.
    6. Return structured bilingual JSON analysis.
    """
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    document_id = body.get("document_id", "").strip()
    language = body.get("language", "both").strip().lower()

    if not document_id:
        return jsonify({
            "success": False,
            "error": "Missing required field: 'document_id'."
        }), 400

    if language not in ("english", "tamil", "both"):
        return jsonify({
            "success": False,
            "error": "Invalid language. Allowed values: 'english', 'tamil', 'both'."
        }), 400

    if not GEMINI_API_KEY:
        return jsonify({
            "success": False,
            "error": "AI service is temporarily unavailable. Please try again shortly."
        }), 503

    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id)
    if not safe_doc_id:
        return jsonify({
            "success": False,
            "error": "Invalid document ID format."
        }), 400

    if _check_analyse_rate_limit(safe_uid):
        return jsonify({
            "success": False,
            "error": f"Please wait {ANALYSE_COOLDOWN_SECONDS} seconds before submitting another analysis request."
        }), 429

    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({
            "success": False,
            "error": "Document not found in user storage."
        }), 404

    try:
        extraction_result = extract_document_text(target_file)
    except Exception:
        return jsonify({
            "success": False,
            "error": "An error occurred while reading the document."
        }), 500

    if not extraction_result.get("success"):
        return jsonify({
            "success": False,
            "error": extraction_result.get("error", "Failed to extract text from the document.")
        }), 422

    full_text: str = extraction_result.get("full_text", "")
    if not full_text.strip():
        return jsonify({
            "success": False,
            "error": "No readable text could be extracted from this document."
        }), 422

    MAX_INPUT_CHARS = 20_000
    if len(full_text) > MAX_INPUT_CHARS:
        full_text = full_text[:MAX_INPUT_CHARS]

    result = analyse_form(text=full_text, language=language)
    if not result.get("success"):
        status_code = result.get("status_code") or _map_analysis_error_status(result.get("error"))
        return jsonify({
            "success": False,
            "error": result.get("error", "AI service is temporarily unavailable. Please try again shortly.")
        }), status_code

    analysis_data = result.get("analysis")
    if analysis_data:
        with _analysis_cache_lock:
            _analysis_cache[safe_doc_id] = analysis_data

    update_document_status_in_firestore(
        uid=safe_uid,
        doc_id=safe_doc_id,
        new_status="analysed"
    )

    return jsonify({
        "success": True,
        "document_id": safe_doc_id,
        "language": language,
        "file_type": extraction_result.get("file_type"),
        "page_count": extraction_result.get("page_count", 1),
        "word_count": extraction_result.get("word_count", 0),
        "analysis": result.get("analysis")
    }), 200


@app.route("/api/validate", methods=["POST"])
def validate_student_form():
    """
    Authenticated Form Validation Endpoint.
    1. Verify Firebase ID token from Authorization header.
    2. Parse and validate JSON body (document_id, answers dict, language).
    3. Verify document ownership in user's isolated storage (uploads/<uid>/).
    4. Retrieve field definitions (via cache or existing extraction + analyse_form flow).
    5. Pass fields and student answers to validate_form() in validator.py.
    6. Return structured validation response without leaking server paths or secrets.
    """
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({
            "success": False,
            "error": "Request body must be a valid JSON object."
        }), 400

    document_id = body.get("document_id")
    if not document_id or not isinstance(document_id, str) or not document_id.strip():
        return jsonify({
            "success": False,
            "error": "Missing required field: 'document_id'."
        }), 400

    document_id = document_id.strip()

    answers = body.get("answers")
    if answers is None or not isinstance(answers, dict):
        return jsonify({
            "success": False,
            "error": "Missing or invalid required field: 'answers'. Must be a JSON object."
        }), 400

    if len(answers) > 200:
        return jsonify({
            "success": False,
            "error": "Answers dictionary exceeds maximum allowed limit of 200 fields."
        }), 400

    for k, v in answers.items():
        if not isinstance(k, str) or len(k) > 100:
            return jsonify({
                "success": False,
                "error": "Invalid field identifier in answers."
            }), 400
        if v is not None and len(str(v)) > 5000:
            return jsonify({
                "success": False,
                "error": "Answer length exceeds maximum allowed limit of 5000 characters."
            }), 400

    language = body.get("language", "both")
    if not isinstance(language, str) or language.strip().lower() not in ("english", "tamil", "both"):
        return jsonify({
            "success": False,
            "error": "Invalid language. Allowed values: 'english', 'tamil', 'both'."
        }), 400

    language = language.strip().lower()
    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id)
    if not safe_doc_id:
        return jsonify({
            "success": False,
            "error": "Invalid document ID format."
        }), 400

    if _check_validate_rate_limit(safe_uid):
        return jsonify({
            "success": False,
            "error": "Too many validation requests. Please wait a moment before trying again."
        }), 429

    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({
            "success": False,
            "error": "Document not found in user storage."
        }), 404

    fields, err_msg, status_code = _get_document_fields(safe_uid, safe_doc_id, target_file)
    if err_msg or not isinstance(fields, list):
        return jsonify({
            "success": False,
            "error": err_msg or "AI service is temporarily unavailable. Please try again shortly."
        }), status_code

    normalized_answers = dict(answers)
    for field_def in fields:
        fname = field_def.get("field_name")
        fid = field_def.get("field_id")
        q = field_def.get("question")
        if fname and fname not in normalized_answers:
            if fid and fid in answers:
                normalized_answers[fname] = answers[fid]
            elif q and q in answers:
                normalized_answers[fname] = answers[q]

    try:
        validation_result = validate_form(
            field_definitions=fields,
            student_answers=normalized_answers,
            language=language
        )
    except Exception:
        return jsonify({
            "success": False,
            "error": "An error occurred during form validation."
        }), 500

    return jsonify({
        "success": True,
        "document_id": safe_doc_id,
        "is_valid": validation_result.get("is_valid", False),
        "total_fields": validation_result.get("total_fields", 0),
        "completed_fields": validation_result.get("completed_fields", 0),
        "missing_required_count": validation_result.get("missing_required_count", 0),
        "error_count": validation_result.get("error_count", 0),
        "field_results": validation_result.get("field_results", [])
    }), 200


# ---------------------------------------------------------------------------
# Phase 7 Step 4: Authenticated Checklist & Readiness Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/checklist", methods=["POST"])
def get_document_checklist():
    """
    Authenticated Document Checklist Endpoint:
    1. Authenticates student and validates document ownership.
    2. Retrieves document analysis (cached or via existing analysis flow).
    3. Retrieves student's uploaded documents metadata from Firestore and storage.
    4. Retrieves persisted confirmed matches strictly from authoritative Firestore metadata.
       SECURITY: Ignores and discards any unverified confirmation mappings passed in the request body.
    5. Verifies every confirmed document physically exists in student's upload directory.
    6. Builds checklist using build_checklist().
    7. Suggested matches remain unconfirmed until student explicitly confirms them.
    8. Returns complete checklist summary and individual document items.
    """
    # 1. Authentication
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    # 2. Parse request payload
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({
            "success": False,
            "error": "Request body must be a valid JSON object."
        }), 400

    document_id = body.get("document_id")
    if not document_id or not isinstance(document_id, str) or not document_id.strip():
        return jsonify({
            "success": False,
            "error": "Missing required field: 'document_id'."
        }), 400

    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id.strip())
    if not safe_doc_id:
        return jsonify({
            "success": False,
            "error": "Invalid document ID format."
        }), 400

    # 3. Ownership & existence check (returns 404 if not found in user storage)
    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({
            "success": False,
            "error": "Document not found in user storage."
        }), 404

    # 4. Retrieve form analysis
    analysis_data, err_msg, status_code = _get_document_analysis(safe_uid, safe_doc_id, target_file)
    if err_msg or not isinstance(analysis_data, dict):
        return jsonify({
            "success": False,
            "error": err_msg or "AI service is temporarily unavailable. Please try again shortly."
        }), status_code

    required_documents = analysis_data.get("required_documents", [])
    if not isinstance(required_documents, list):
        required_documents = []

    # 5. Retrieve user's uploaded document metadata
    uploaded_docs = _get_user_uploaded_documents(safe_uid)

    # 6. SECURITY: Confirmed matches are retrieved exclusively from authoritative Firestore
    # metadata and verified against the user's physical storage directory.
    # Frontend-supplied confirmed_matches dictionaries in request bodies are NEVER trusted.
    verified_matches = _get_verified_confirmed_matches(safe_uid, safe_doc_id, required_documents)

    # 7. Build checklist (suggested matches remain unconfirmed)
    try:
        checklist_result = build_checklist(
            requirements=required_documents,
            uploaded_documents=uploaded_docs,
            confirmed_matches=verified_matches
        )
    except Exception:
        return jsonify({
            "success": False,
            "error": "Failed to generate document checklist."
        }), 500

    return jsonify({
        "success": True,
        "document_id": safe_doc_id,
        "total_required": checklist_result.get("total_required", 0),
        "mandatory_count": checklist_result.get("mandatory_count", 0),
        "optional_count": checklist_result.get("optional_count", 0),
        "matched_count": checklist_result.get("matched_count", 0),
        "missing_mandatory_count": checklist_result.get("missing_mandatory_count", 0),
        "is_complete": checklist_result.get("is_complete", False),
        "items": checklist_result.get("items", []),
        "uploaded_documents": uploaded_docs
    }), 200


@app.route("/api/checklist/confirm", methods=["POST"])
def confirm_checklist_match():
    """
    Authenticated Document Match Confirmation Endpoint:
    1. Authenticates student and validates document ownership.
    2. Validates requirement existence against document analysis.
    3. Validates that the selected document physically belongs to the user's upload directory.
    4. Calls confirm_document_match() to validate and update mapping.
    5. Persists confirmed matches under user's Firestore document metadata.
    6. Ensures Firestore failure does not silently claim that a confirmation was saved.
    7. Returns confirmation status and updated matches.
    """
    # 1. Authentication
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    # 2. Parse request payload
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({
            "success": False,
            "error": "Request body must be a valid JSON object."
        }), 400

    document_id = body.get("document_id")
    requirement_id = body.get("requirement_id")
    selected_doc_id = body.get("selected_doc_id")

    if not document_id or not isinstance(document_id, str) or not document_id.strip():
        return jsonify({
            "success": False,
            "error": "Missing required field: 'document_id'."
        }), 400

    if not requirement_id or not isinstance(requirement_id, str) or not requirement_id.strip():
        return jsonify({
            "success": False,
            "error": "Missing required field: 'requirement_id'."
        }), 400

    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id.strip())
    safe_req_id = requirement_id.strip()

    # 3. Ownership & existence check (returns 404 if not found in user storage)
    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({
            "success": False,
            "error": "Document not found in user storage."
        }), 404

    # 4. Retrieve form analysis
    analysis_data, err_msg, status_code = _get_document_analysis(safe_uid, safe_doc_id, target_file)
    if err_msg or not isinstance(analysis_data, dict):
        return jsonify({
            "success": False,
            "error": err_msg or "AI service is temporarily unavailable. Please try again shortly."
        }), status_code

    required_documents = analysis_data.get("required_documents", [])
    if not isinstance(required_documents, list):
        required_documents = []

    # Validate requirement exists in form requirements
    valid_req_ids = {r.get("doc_id") for r in required_documents if isinstance(r, dict) and r.get("doc_id")}
    if safe_req_id not in valid_req_ids:
        return jsonify({
            "success": False,
            "error": f"Checklist requirement '{safe_req_id}' does not exist in this form."
        }), 400

    # 5. Retrieve user's uploaded documents metadata and current confirmed matches
    uploaded_docs = _get_user_uploaded_documents(safe_uid)
    current_matches = _get_persisted_confirmed_matches(safe_uid, safe_doc_id)

    # 6. Validate selected document if confirming
    cleaned_selected_id = str(selected_doc_id).strip() if selected_doc_id else None

    if cleaned_selected_id:
        # Prevent form document from matching itself as supporting document
        if cleaned_selected_id == safe_doc_id:
            return jsonify({
                "success": False,
                "error": "A form document cannot be matched as its own supporting document."
            }), 400

        # Verify selected document physically exists in user's isolated storage
        selected_file = _get_user_document_path(safe_uid, cleaned_selected_id)
        if not selected_file or not os.path.exists(selected_file):
            return jsonify({
                "success": False,
                "error": "Selected document not found in your uploaded documents."
            }), 400

    # 7. Validate and confirm match using existing confirm_document_match helper
    success, updated_matches, error_msg = confirm_document_match(
        requirements=required_documents,
        uploaded_documents=uploaded_docs,
        current_confirmed_matches=current_matches,
        target_req_id=safe_req_id,
        selected_document_id=cleaned_selected_id
    )

    if not success:
        return jsonify({
            "success": False,
            "error": error_msg or "Failed to confirm document match."
        }), 400

    # 8. Persist confirmed matches in Firestore (ensures failure returns HTTP 500)
    saved = _save_persisted_confirmed_matches(safe_uid, safe_doc_id, updated_matches)
    if not saved:
        return jsonify({
            "success": False,
            "error": "Failed to persist document match to database."
        }), 500

    return jsonify({
        "success": True,
        "document_id": safe_doc_id,
        "requirement_id": safe_req_id,
        "selected_doc_id": cleaned_selected_id,
        "confirmed_matches": updated_matches,
        "message": "Document match confirmed successfully." if cleaned_selected_id else "Document match cleared successfully."
    }), 200


@app.route("/api/readiness", methods=["POST"])
def calculate_application_readiness():
    """
    Authenticated Application Readiness Scoring Endpoint:
    1. Authenticates student and validates document ownership.
    2. Retrieves form analysis (fields and requirements).
    3. Validates student answers using validate_form().
    4. Builds checklist using verified confirmed matches (strictly validated against physical storage).
    5. Calculates score using calculate_readiness(validation_res, checklist_res, fields).
    6. Returns total readiness score, status, transparent breakdown, and action items.
    """
    # 1. Authentication
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    # 2. Parse request payload
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({
            "success": False,
            "error": "Request body must be a valid JSON object."
        }), 400

    document_id = body.get("document_id")
    if not document_id or not isinstance(document_id, str) or not document_id.strip():
        return jsonify({
            "success": False,
            "error": "Missing required field: 'document_id'."
        }), 400

    answers = body.get("answers")
    if answers is None or not isinstance(answers, dict):
        return jsonify({
            "success": False,
            "error": "Missing or invalid required field: 'answers'. Must be a JSON object."
        }), 400

    if len(answers) > 200:
        return jsonify({
            "success": False,
            "error": "Answers dictionary exceeds maximum allowed limit of 200 fields."
        }), 400

    for k, v in answers.items():
        if not isinstance(k, str) or len(k) > 100:
            return jsonify({
                "success": False,
                "error": "Invalid field identifier in answers."
            }), 400
        if v is not None and len(str(v)) > 5000:
            return jsonify({
                "success": False,
                "error": "Answer length exceeds maximum allowed limit of 5000 characters."
            }), 400

    language = body.get("language", "both")
    if not isinstance(language, str) or language.strip().lower() not in ("english", "tamil", "both"):
        return jsonify({
            "success": False,
            "error": "Invalid language. Allowed values: 'english', 'tamil', 'both'."
        }), 400

    language = language.strip().lower()
    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id.strip())

    # 3. Ownership & existence check (returns 404 if not found in user storage)
    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({
            "success": False,
            "error": "Document not found in user storage."
        }), 404

    # 4. Retrieve form analysis
    analysis_data, err_msg, status_code = _get_document_analysis(safe_uid, safe_doc_id, target_file)
    if err_msg or not isinstance(analysis_data, dict):
        return jsonify({
            "success": False,
            "error": err_msg or "AI service is temporarily unavailable. Please try again shortly."
        }), status_code

    fields = analysis_data.get("fields", [])
    required_documents = analysis_data.get("required_documents", [])
    if not isinstance(fields, list):
        fields = []
    if not isinstance(required_documents, list):
        required_documents = []

    # 5. Normalize student answers (matching validate_form logic)
    normalized_answers = dict(answers)
    for field_def in fields:
        fname = field_def.get("field_name")
        fid = field_def.get("field_id")
        q = field_def.get("question")
        if fname and fname not in normalized_answers:
            if fid and fid in answers:
                normalized_answers[fname] = answers[fid]
            elif q and q in answers:
                normalized_answers[fname] = answers[q]

    # 6. Deterministic form validation (Actual student answers only; never fictional examples)
    try:
        validation_result = validate_form(
            field_definitions=fields,
            student_answers=normalized_answers,
            language=language
        )
    except Exception:
        return jsonify({
            "success": False,
            "error": "An error occurred during form validation."
        }), 500

    # 7. Build checklist using strictly verified confirmed matches
    uploaded_docs = _get_user_uploaded_documents(safe_uid)
    verified_matches = _get_verified_confirmed_matches(safe_uid, safe_doc_id, required_documents)

    try:
        checklist_result = build_checklist(
            requirements=required_documents,
            uploaded_documents=uploaded_docs,
            confirmed_matches=verified_matches
        )
    except Exception:
        return jsonify({
            "success": False,
            "error": "An error occurred while building the document checklist."
        }), 500

    # 8. Calculate application readiness score
    try:
        readiness_result = calculate_readiness(
            validation_result=validation_result,
            checklist_result=checklist_result,
            field_definitions=fields
        )
    except Exception:
        return jsonify({
            "success": False,
            "error": "An error occurred while calculating readiness score."
        }), 500

    # 9. Return structured response
    return jsonify({
        "success": True,
        "document_id": safe_doc_id,
        "readiness_score": readiness_result.get("readiness_score", 0.0),
        "status": readiness_result.get("status", "not_started"),
        "score_breakdown": readiness_result.get("score_breakdown", {}),
        "action_items": readiness_result.get("action_items", []),
        "validation_summary": {
            "is_valid": validation_result.get("is_valid", False),
            "total_fields": validation_result.get("total_fields", 0),
            "completed_fields": validation_result.get("completed_fields", 0),
            "missing_required_count": validation_result.get("missing_required_count", 0),
            "error_count": validation_result.get("error_count", 0)
        },
        "checklist_summary": {
            "total_required": checklist_result.get("total_required", 0),
            "mandatory_count": checklist_result.get("mandatory_count", 0),
            "optional_count": checklist_result.get("optional_count", 0),
            "matched_count": checklist_result.get("matched_count", 0),
            "missing_mandatory_count": checklist_result.get("missing_mandatory_count", 0),
            "is_complete": checklist_result.get("is_complete", False)
        }
    }), 200


@app.route("/api/preview", methods=["POST"])
def preview_form():
    """
    Authenticated Form Preview Endpoint.
    Returns a JSON summary of fields and answers for client-side preview rendering.
    """
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"success": False, "error": "Request body must be a valid JSON object."}), 400

    document_id = body.get("document_id")
    if not document_id or not isinstance(document_id, str) or not document_id.strip():
        return jsonify({"success": False, "error": "Missing required field: 'document_id'."}), 400

    answers = body.get("answers")
    if answers is None or not isinstance(answers, dict):
        return jsonify({"success": False, "error": "Missing or invalid required field: 'answers'."}), 400

    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id.strip())
    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({"success": False, "error": "Document not found in user storage."}), 404

    analysis_data, err_msg, status_code = _get_document_analysis(safe_uid, safe_doc_id, target_file)
    if err_msg or not isinstance(analysis_data, dict):
        return jsonify({"success": False, "error": err_msg or "AI service is temporarily unavailable. Please try again shortly."}), status_code

    fields = analysis_data.get("fields", [])
    if not isinstance(fields, list):
        fields = []

    # Build preview data
    preview_fields = []
    for idx, field in enumerate(fields, 1):
        field_id = str(field.get("field_id") or field.get("field_name") or f"field_{idx}")
        field_name = str(field.get("field_name") or field_id)
        question = str(field.get("question") or field.get("label") or field_name).strip()
        is_required = bool(field.get("is_required", False))
        field_type = str(field.get("field_type", "text")).strip().lower()

        answer = answers.get(field_id)
        if answer is None:
            answer = answers.get(field_name)

        preview_fields.append({
            "number": idx,
            "field_id": field_id,
            "question": question,
            "field_type": field_type,
            "is_required": is_required,
            "answer": str(answer).strip() if answer else "",
            "has_answer": bool(answer and str(answer).strip()),
        })

    return jsonify({
        "success": True,
        "document_id": safe_doc_id,
        "form_title": analysis_data.get("form_title", "Application Form"),
        "summary_english": analysis_data.get("summary_english", ""),
        "fields": preview_fields,
        "total_fields": len(preview_fields),
        "filled_count": sum(1 for f in preview_fields if f["has_answer"]),
    }), 200


@app.route("/api/download-pdf", methods=["POST"])
def download_pdf():
    """
    Authenticated PDF Download Endpoint.
    Generates and returns a filled-form PDF as an attachment.
    """
    safe_uid, auth_err = _authenticate_request()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"success": False, "error": "Request body must be a valid JSON object."}), 400

    document_id = body.get("document_id")
    if not document_id or not isinstance(document_id, str) or not document_id.strip():
        return jsonify({"success": False, "error": "Missing required field: 'document_id'."}), 400

    answers = body.get("answers")
    if answers is None or not isinstance(answers, dict):
        return jsonify({"success": False, "error": "Missing or invalid required field: 'answers'."}), 400

    safe_doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "", document_id.strip())
    target_file = _get_user_document_path(safe_uid, safe_doc_id)
    if not target_file:
        return jsonify({"success": False, "error": "Document not found in user storage."}), 404

    analysis_data, err_msg, status_code = _get_document_analysis(safe_uid, safe_doc_id, target_file)
    if err_msg or not isinstance(analysis_data, dict):
        return jsonify({"success": False, "error": err_msg or "AI service is temporarily unavailable. Please try again shortly."}), status_code

    fields = analysis_data.get("fields", [])
    if not isinstance(fields, list):
        fields = []

    required_documents = analysis_data.get("required_documents", [])
    if not isinstance(required_documents, list):
        required_documents = []

    # Optionally gather checklist data
    checklist_items = None
    readiness_score_val = None
    readiness_status_val = None

    try:
        uploaded_docs = _get_user_uploaded_documents(safe_uid)
        verified_matches = _get_verified_confirmed_matches(safe_uid, safe_doc_id, required_documents)
        checklist_result = build_checklist(
            requirements=required_documents,
            uploaded_documents=uploaded_docs,
            confirmed_matches=verified_matches
        )
        checklist_items = checklist_result.get("items", [])
    except Exception:
        pass

    try:
        language = body.get("language", "both")
        if not isinstance(language, str):
            language = "both"
        normalized_answers = dict(answers)
        for field_def in fields:
            fname = field_def.get("field_name")
            fid = field_def.get("field_id")
            if fname and fname not in normalized_answers:
                if fid and fid in answers:
                    normalized_answers[fname] = answers[fid]

        validation_result = validate_form(
            field_definitions=fields,
            student_answers=normalized_answers,
            language=language.strip().lower() if isinstance(language, str) else "both"
        )
        checklist_for_score = checklist_result if 'checklist_result' in dir() else {"items": []}
        readiness_result = calculate_readiness(
            validation_result=validation_result,
            checklist_result=checklist_for_score,
            field_definitions=fields
        )
        readiness_score_val = readiness_result.get("readiness_score")
        readiness_status_val = readiness_result.get("status")
    except Exception:
        pass

    form_title = analysis_data.get("form_title", "Application Form")

    try:
        pdf_bytes = generate_filled_pdf(
            form_title=form_title,
            fields=fields,
            student_answers=answers,
            analysis_data=analysis_data,
            checklist_items=checklist_items,
            readiness_score=readiness_score_val,
            readiness_status=readiness_status_val,
        )
    except Exception as e:
        print(f"PDF generation error: {e}")
        return jsonify({"success": False, "error": "An error occurred while generating the PDF."}), 500

    from flask import Response
    safe_title = re.sub(r"[^a-zA-Z0-9_ -]", "", form_title)[:50] or "FormWise_AI"
    filename = f"{safe_title}_{safe_doc_id[:8]}.pdf"

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        }
    )


# ---------------------------------------------------------------------------
# Static Frontend Serving Route (Single-Link Deployment)
# ---------------------------------------------------------------------------

@app.route("/<path:path>", methods=["GET"])
def serve_frontend_file(path: str):
    """
    Serve static frontend assets and HTML pages dynamically.
    Enables single-link deployment (one URL serves both frontend and API).
    """
    # Prevent intercepting unmatched API routes or health check
    if path.startswith("api/") or path == "health":
        return jsonify({"success": False, "error": f"API endpoint '/{path}' not found."}), 404

    target_file = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(target_file):
        return send_from_directory(FRONTEND_DIR, path)

    # Support extensionless routing (e.g., /login -> login.html)
    html_file = os.path.join(FRONTEND_DIR, f"{path}.html")
    if os.path.isfile(html_file):
        return send_from_directory(FRONTEND_DIR, f"{path}.html")

    return jsonify({"success": False, "error": f"Resource '{path}' not found."}), 404


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug, use_reloader=debug)
