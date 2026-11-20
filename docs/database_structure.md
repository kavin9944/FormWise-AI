# FormWise AI – Database Structure & Schema Documentation

FormWise AI utilizes **Google Cloud Firestore** (NoSQL Document Database) in conjunction with **Firebase Authentication**.

This document outlines the complete database topology, collection hierarchies, document schemas, security rules, and data access patterns.

---

## 1. Collection Hierarchy

```
firestore/
├── users/
│   └── {uid}/                               [Document: Student Profile]
│       ├── full_name: string
│       ├── email: string
│       ├── phone: string
│       ├── dob: string (YYYY-MM-DD)
│       ├── gender: string
│       ├── community: string
│       ├── address: string
│       ├── city: string
│       ├── state: string
│       ├── pincode: string
│       ├── father_name: string
│       ├── mother_name: string
│       ├── parent_phone: string
│       ├── aadhaar_number: string
│       ├── created_at: timestamp
│       ├── updated_at: timestamp
│       │
│       └── documents/                       [Subcollection: User Documents]
│           └── {document_id}/               [Document: Form or Supporting File]
│               ├── document_id: string
│               ├── original_filename: string
│               ├── file_type: string ("PDF" | "PNG" | "JPEG")
│               ├── upload_timestamp: timestamp
│               ├── status: string ("uploaded" | "analysed")
│               ├── confirmed_matches: map   [Optional: requirement_id -> upload_doc_id]
│               │   ├── 10th_marksheet: string
│               │   └── community_certificate: string
│               └── updated_at: timestamp
```

---

## 2. Document Schema Specifications

### Collection: `users`
- **Path**: `users/{uid}`
- **Primary Key**: `{uid}` (Firebase Authentication User Unique Identifier)
- **Purpose**: Stores student personal, educational, and contact details used for profile management and form autofill.

| Field Name | Type | Required | Description / Example |
|---|---|---|---|
| `full_name` | String | Yes | Student's full legal name (`"Priya Raman"`) |
| `email` | String | Yes | Verified email address (`"priya@example.com"`) |
| `phone` | String | Yes | 10-digit mobile number (`"9876543210"`) |
| `dob` | String | Yes | Date of birth in ISO format (`"2002-05-14"`) |
| `gender` | String | Yes | Gender (`"Female"` / `"Male"` / `"Other"`) |
| `community` | String | No | Social category (`"OBC"` / `"SC"` / `"ST"` / `"General"`) |
| `address` | String | No | Residential address (`"123 Gandhi Street, Anna Nagar"`) |
| `city` | String | No | City or town name (`"Chennai"`) |
| `state` | String | No | State or union territory (`"Tamil Nadu"`) |
| `pincode` | String | No | 6-digit postal code (`"600040"`) |
| `father_name` | String | No | Father's full name (`"Ramanathan K"`) |
| `mother_name` | String | No | Mother's full name (`"Meenakshi R"`) |
| `parent_phone` | String | No | Parent/Guardian mobile number (`"9876543211"`) |
| `aadhaar_number`| String | No | Masked or 12-digit UIDAI number (`"XXXX-XXXX-1234"`) |
| `created_at` | Timestamp | Yes | Account profile creation date |
| `updated_at` | Timestamp | Yes | Last profile modification date |

---

### Subcollection: `documents`
- **Path**: `users/{uid}/documents/{document_id}`
- **Primary Key**: `{document_id}` (32-character hexadecimal UUID string)
- **Purpose**: Tracks documents uploaded by the student (application forms and supporting proofs), their processing state, and confirmed requirement mappings.

| Field Name | Type | Required | Description / Example |
|---|---|---|---|
| `document_id` | String | Yes | Unique file identifier (`"eca4e2108e5845afb9fcf1ac847812b9"`) |
| `original_filename` | String | Yes | Original client filename (`"College_Admission_Form.pdf"`) |
| `file_type` | String | Yes | Document file extension (`"PDF"`, `"PNG"`, `"JPG"`) |
| `upload_timestamp`| Timestamp | Yes | Server UTC upload timestamp |
| `status` | String | Yes | Lifecycle status (`"uploaded"` -> `"analysed"`) |
| `confirmed_matches`| Map<String, String> | No | Requirement ID mapped to uploaded document ID: `{"10th_marksheet": "677a08f6f..."}` |
| `updated_at` | Timestamp | No | Last modification timestamp of document metadata |

---

## 3. Storage Architecture

While document metadata is indexed in Firestore, the binary files themselves are stored in a dedicated, isolated filesystem directory outside the public webroot:

```
FormWise-AI/uploads/
└── {uid}/
    ├── {document_id}.pdf
    └── {supporting_cert_id}.pdf
```

### Path Traversal Defense
When fetching any file:
```python
candidate = os.path.join(user_upload_dir, fname)
if os.path.commonpath([candidate, user_upload_dir]) == user_upload_dir and os.path.exists(candidate):
    return candidate
```
This guarantees that no user can access documents belonging to another user (`../other_uid/file.pdf`).

---

## 4. Firestore Security Rules (Production Recommendation)

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    
    // Students can only read and write their own profile
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
      
      // Students can only access their own uploaded document metadata
      match /documents/{docId} {
        allow read, write: if request.auth != null && request.auth.uid == userId;
      }
    }
  }
}
```
