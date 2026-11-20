# FormWise AI – Academic Presentation & Viva Deck

**Project Title**: FormWise AI – Smart AI Form Filling Assistant  
**Domain**: Full-Stack AI Engineering, Natural Language Processing & Educational Technology  
**Date**: November 2026  

---

## Slide 1: Title Slide
- **Project**: FormWise AI – Smart AI Form Filling Assistant
- **Tagline**: Empowering students with bilingual AI form guidance, validation, and readiness scoring
- **Presenter**: Engineering Project Team
- **Platform**: Python (Flask) + Google Gemini API + Firebase + ReportLab

---

## Slide 2: Problem Statement
- **The Challenge**: Indian college admissions, scholarships, and government certificates require completing complex forms with strict documentation.
- **The Pain Point**: First-generation and rural students face language barriers, confusing instructions, and obscure conditional requirements.
- **The Consequence**: Minor formatting mistakes and missed documents result in rejected applications and lost opportunities.

---

## Slide 3: Proposed Solution
- **AI-Powered Bilingual Assistant**: Plain English and clear Tamil explanations for every field.
- **Hybrid Ingestion Engine**: Native PDF text extraction + Tesseract OCR for scanned documents.
- **Intelligent Field Detection**: Automatic classification of field types, requirements, and examples.
- **Smart Validation**: Immediate format error checking and missing-field alerts.
- **Document Checklist & Readiness Score**: Category matching for certificates + 0–100 submission readiness score.
- **Summary PDF Generation**: Clean, watermarked preview and downloadable PDF summary.

---

## Slide 4: System Architecture
```
[ Frontend: HTML5 / CSS3 / ES6 Modules ]
                   │
         Bearer JWT Auth (Firebase)
                   ▼
[ Backend: Flask REST API Server ]
       ├─ PyMuPDF & Tesseract OCR Pipeline
       ├─ Google Gemini API (gemini-3.5-flash-lite)
       ├─ Deterministic Field Validator
       ├─ Document Checklist & Matcher
       ├─ Readiness Scoring Engine (0-100)
       └─ ReportLab PDF Summary Generator
                   │
[ Storage: Google Cloud Firestore + Isolated Local Storage ]
```

---

## Slide 5: Core Workflow (End-to-End)
1. **Authenticate**: Student signs up/logs in with Firebase Authentication.
2. **Setup Profile**: Student saves details (Name, DOB, Mobile, Community, etc.).
3. **Upload Form**: Ingests PDF or image with magic-byte validation.
4. **AI Analysis**: Gemini analyzes fields and supporting document mandates.
5. **Autofill & Guidance**: Student fills answers or uses one-click profile autofill.
6. **Validation**: Deterministic server validation checks formats and required fields.
7. **Checklist & Confirmation**: Student matches and confirms certificates.
8. **Readiness Score**: Transparent 0–100 score with bilingual remediation steps.
9. **Preview & Download**: Student previews tabular answers and downloads the PDF summary.

---

## Slide 6: Module 1 – Document Ingestion & OCR
- **Input Types**: Native digital PDFs, mobile photos, scanned forms (up to 10 MB).
- **Security Check**: Header magic bytes validated (`%PDF-`, `\x89PNG`, `\xFF\xD8\xFF`).
- **Two-Stage Extractor**:
  - *Stage 1*: PyMuPDF text parser (instant native text).
  - *Stage 2*: If page character count < 30, renders page at 150 DPI and invokes Tesseract OCR.
- **Tenant Isolation**: Uploads stored in `uploads/<uid>/<doc_id>.<ext>`.

---

## Slide 7: Module 2 – Gemini AI Form Analysis
- **Model**: `gemini-3.5-flash-lite` (low latency, high free-tier reliability).
- **Prompt Safety**: Uploaded form text is encapsulated inside strict delimiters to prevent prompt injection.
- **Structured Schema**: Model outputs strictly valid JSON:
  - Form title and bilingual summaries
  - Array of fields with `field_name`, `question`, `is_required`, `field_type`, `what_to_fill`, `example`, `explanation_english`, `explanation_tamil`
  - Array of `required_documents` with conditional logic preserved
  - Practical tips in English and Tamil

---

## Slide 8: Module 3 – Smart Validation & Autofill
- **Profile Autofill**:
  - Matches saved profile attributes (Full Name, Phone, DOB, Community, Address).
  - **Golden Safety Rule**: Never overwrites answers already entered by the student.
- **Deterministic Validation**:
  - Phone: `^[6-9]\d{9}$` (Indian 10-digit mobile standards).
  - Email: Standard RFC syntax checking.
  - Date: ISO and standard date formats with boundary validation.
  - Required Fields: Immediate flagging of uncompleted mandatory items.

---

## Slide 9: Module 4 – Document Checklist & Confirmation
- **Heuristic Categorization**: Identifies mark sheets, transfer certificates, community certificates, and income certificates.
- **Negative-Wording Safeguards**: Distinguishes "Required" from "Optional", "May enclose", or "Not required for general category".
- **Student Confirmation**:
  - Matches student's uploaded proofs to form requirements.
  - Allows confirming or clearing matches via `POST /api/checklist/confirm`.
  - Confirmed matches are persisted securely in Google Cloud Firestore.

---

## Slide 10: Module 5 – Application Readiness Scoring
- **Total Score Range**: 0 to 100 points.
- **Field Component (60 Pts)**:
  - Required fields: Up to 50 points proportional to valid completed fields.
  - Optional fields: Up to 10 bonus points.
  - Safe zero-field normalization if form has zero optional or required fields.
- **Document Component (40 Pts)**:
  - Confirmed mandatory documents: Up to 40 points proportional to confirmed matches.
  - Forms with no mandatory documents automatically earn 40 points.
- **Action Items**: Outputs clear, prioritized tasks in English and Tamil.

---

## Slide 11: Module 6 – Preview & PDF Generation
- **Form Preview (`preview.html`)**:
  - Interactive tabular review of all questions and student answers.
  - Displays total fields count and filled fields count.
  - Back link to assistant with retained inputs.
- **PDF Generator (`pdf_generator.py`)**:
  - Built with ReportLab 5.1.0.
  - Form metadata, field answers, requirement badges, and checklist status table.
  - Clear submission disclaimer preventing unauthorized portal submissions.

---

## Slide 12: Security & Privacy Architecture
1. **Firebase Bearer JWT**: Every API endpoint verifies cryptographic token and extracts `uid`.
2. **User Isolation**: Strictly prevents cross-user document access via directory sandboxing.
3. **No innerHTML**: Client-side rendering exclusively uses `textContent` and `createEl()`.
4. **Secret Protection**: API keys and service accounts are excluded from client code and Git.
5. **No Auto-Submission**: Generates review summaries only; never submits to official portals.

---

## Slide 13: Testing & Experimental Results
- **Automated Backend Test Suite**:
  - `test_step4.py`: **21 / 21 Tests Passed** (Auth, security, checklist, readiness).
  - `test_pdf.py`: **4 / 4 Tests Passed** (PDF bytes, preview endpoint, download attachment).
- **Syntax Validation**:
  - Python: 8 / 8 modules cleanly compiled via `py_compile`.
  - JavaScript: 6 / 6 files validated with zero syntax errors via Node.js AST check.
- **Total Automated Tests**: **25 / 25 Passing (100% Success Rate)**.

---

## Slide 14: Demonstration Screens
1. **Registration & Login**: Secure Firebase authentication interface.
2. **Student Profile**: Centralized personal details management.
3. **Form Upload**: Drag-and-drop document upload with format validation.
4. **AI Assistant**: Interactive field cards with Tamil/English toggles and fictional examples.
5. **Checklist & Readiness Card**: Document status and 0–100 readiness meter.
6. **Form Preview & PDF Download**: Tabular review and downloadable ReportLab summary.

---

## Slide 15: Conclusion & Future Scope
- **Conclusion**:
  - FormWise AI successfully simplifies complex administrative forms for first-generation students.
  - Delivers complete, working, bilingual form understanding, deterministic validation, checklist management, and PDF generation.
- **Future Scope**:
  - Expand to Hindi, Telugu, and Kannada language models.
  - Edge OCR with mobile camera capture.
  - Voice-guided form reading for accessibility.

**Thank You! Questions & Discussion.**
