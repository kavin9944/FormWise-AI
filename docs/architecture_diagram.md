# FormWise AI – System Architecture & Data Flow

This document details the complete architectural topology, component interactions, and data flow pipelines of **FormWise AI**.

---

## 1. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph ClientLayer["Frontend Client Tier (Browser)"]
        A1["login.html / register.html\n(Firebase Auth SDK)"]
        A2["dashboard.html\n(Document History)"]
        A3["upload.html\n(Drag & Drop File Upload)"]
        A4["assistant.html\n(Bilingual Explanations & Validation)"]
        A5["preview.html\n(Form Preview & PDF Download)"]
        A6["profile.html\n(Student Profile Management)"]
    end

    subgraph SecurityGateway["Security & Authentication Boundary"]
        G1["Bearer Token Authorization Header\n(Firebase ID Token)"]
        G2["Path Traversal & UID Isolation Check\n(os.path.commonpath)"]
        G3["Magic Byte File Signature Validator"]
    end

    subgraph BackendLayer["Backend Server Tier (Flask REST API)"]
        B1["app.py\n(Route Controller & Dispatcher)"]
        B2["extractor.py\n(PyMuPDF + Tesseract OCR)"]
        B3["gemini.py\n(Google Gemini 3.5 Flash-Lite)"]
        B4["validator.py\n(Deterministic Regex & Semantic Validator)"]
        B5["checklist.py\n(Supporting Document Matcher & Classifier)"]
        B6["scoring.py\n(0-100 Application Readiness Engine)"]
        B7["autofill.py\n(Profile-to-Field Mapper)"]
        B8["pdf_generator.py\n(ReportLab Summary PDF Builder)"]
    end

    subgraph StorageLayer["Data & Persistence Tier"]
        S1["Firebase Firestore\n• users/{uid} (Profile)\n• users/{uid}/documents/{doc_id}"]
        S2["Local Storage\nuploads/{uid}/{doc_id}.pdf"]
    end

    subgraph ExternalServices["External Cloud APIs"]
        E1["Google Gemini Developer API\n(generativelanguage.googleapis.com)"]
        E2["Firebase Authentication Service"]
    end

    %% Interactions
    A1 <--> E2
    A6 <--> S1
    A2 <--> B1
    A3 --> G3 --> B1
    A4 --> G1 --> B1
    A5 --> G1 --> B1

    B1 --> G2 --> S2
    B1 --> S1
    B1 --> B2
    B1 --> B3 --> E1
    B1 --> B4
    B1 --> B5
    B1 --> B6
    B1 --> B7
    B1 --> B8
```

---

## 2. Detailed Data Flow Pipelines

### Pipeline A: Form Upload and Extraction
```mermaid
sequenceDiagram
    autonumber
    actor Student
    participant Browser as Frontend (upload.html)
    participant Flask as Flask Server (/api/upload)
    participant Extractor as extractor.py
    participant Storage as User Storage (uploads/uid/)
    participant Firestore as Cloud Firestore

    Student->>Browser: Selects PDF or Image form
    Browser->>Browser: Validates client-side file extension & size (<10MB)
    Browser->>Flask: POST /api/upload (Multipart form + Bearer Token)
    Flask->>Flask: Verify Firebase token & extract safe UID
    Flask->>Flask: Validate magic bytes header (%PDF-, PNG, JPEG)
    Flask->>Storage: Save file to uploads/{safe_uid}/{safe_doc_id}.pdf
    Flask->>Firestore: Record metadata (status: 'uploaded')
    Flask->>Extractor: extract_document_text(filepath)
    Extractor->>Extractor: Try PyMuPDF native extraction
    opt Text length < 30 chars (Scanned page)
        Extractor->>Extractor: Render page to image at 150 DPI
        Extractor->>Extractor: Tesseract OCR fallback
    end
    Extractor-->>Flask: Full extracted text
    Flask-->>Browser: HTTP 200 {success: true, document_id, word_count}
    Browser->>Student: Redirects to assistant.html?doc_id=...
```

---

### Pipeline B: AI Analysis, Validation, Readiness & PDF Export
```mermaid
sequenceDiagram
    autonumber
    actor Student
    participant Assistant as assistant.html / js
    participant Flask as Flask Server (app.py)
    participant Gemini as Google Gemini API
    participant Validator as validator.py
    participant Scoring as scoring.py
    participant PDFGen as pdf_generator.py

    Student->>Assistant: Clicks "Analyse Form"
    Assistant->>Flask: POST /api/analyse {document_id, language}
    Flask->>Gemini: Prompt with delimited form text
    Gemini-->>Flask: Structured JSON (fields, required_docs, tips)
    Flask-->>Assistant: Analysis data (English + Tamil)
    Assistant->>Student: Renders interactive field cards & examples

    opt Student Clicks "Autofill from Profile"
        Assistant->>Assistant: Safely injects matching profile attributes
    end

    Student->>Assistant: Reviews/Edits answers & Clicks "Validate"
    Assistant->>Flask: POST /api/validate {document_id, answers}
    Flask->>Validator: Deterministic format & required field checking
    Validator-->>Flask: Field results (valid, error, warning)
    Flask-->>Assistant: Returns validation summary

    Assistant->>Flask: POST /api/readiness {document_id, answers}
    Flask->>Scoring: calculate_readiness(validation, checklist)
    Scoring-->>Flask: Score (0-100), status, breakdown, action items
    Flask-->>Assistant: Displays readiness score & next steps

    Student->>Assistant: Clicks "Preview & Download PDF"
    Assistant->>Flask: POST /api/download-pdf {document_id, answers}
    Flask->>PDFGen: generate_filled_pdf(form_title, fields, answers)
    PDFGen-->>Flask: Binary PDF byte stream
    Flask-->>Assistant: HTTP 200 (application/pdf attachment)
    Assistant->>Student: Downloads completed PDF summary
```

---

## 3. Security Boundary Controls

1. **UID Isolation**: All uploaded documents are strictly scoped to the authenticated student's unique Firebase user identifier (`uploads/<uid>/`).
2. **Path Traversal Shield**: All file resolution is validated using `os.path.commonpath([target, user_dir]) == user_dir`.
3. **Magic Byte Verification**: Uploaded content headers are checked against standard binary signatures to prevent malicious payload disguised as PDF or images.
4. **Delimited Prompts**: Form text is encapsulated between `=== BEGIN FORM TEXT ===` and `=== END FORM TEXT ===`, preventing injected user text from escaping into instruction space.
5. **DOM Injection Immunity**: All dynamic elements on the frontend are rendered via `createEl()` and `.textContent`. Zero `innerHTML` interpolation of untrusted input.
