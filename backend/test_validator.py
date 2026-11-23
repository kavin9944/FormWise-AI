"""
test_validator.py - Unit tests for FormWise AI form validation engine.
Covers strict date validation, strict number validation, bilingual suggestions,
empty/placeholder handling, and boundary conditions.
"""

import unittest
from validator import (
    validate_date,
    validate_number,
    validate_email,
    validate_indian_mobile,
    validate_field,
    validate_form,
    is_placeholder,
    _SUGGESTIONS
)


class TestDateValidation(unittest.TestCase):
    """Test suite for strict date validation."""

    def test_valid_indian_slash_format(self):
        ok, errs = validate_date("15/08/2005")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_valid_indian_hyphen_format(self):
        ok, errs = validate_date("15-08-2005")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_valid_indian_dot_format(self):
        ok, errs = validate_date("15.08.2005")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_valid_iso_format(self):
        ok, errs = validate_date("2005-08-15")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_valid_single_digit_day_month(self):
        ok, errs = validate_date("5/4/2005")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_valid_leap_year_feb_29(self):
        # 2024 is a leap year
        ok, errs = validate_date("29/02/2024")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

        # 2000 is a century leap year
        ok, errs = validate_date("29-02-2000")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_valid_textual_month_formats(self):
        for val in ["15 Aug 2005", "15 August 2005", "15-May-2005", "May 15, 2005", "August 15, 2005"]:
            ok, errs = validate_date(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_2_digit_year(self):
        ok, errs = validate_date("15/08/05")
        self.assertTrue(ok)
        self.assertEqual(errs, [])

    def test_invalid_impossible_feb_31(self):
        # February never has 31 days
        ok, errs = validate_date("31/02/2026")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_invalid_non_leap_year_feb_29(self):
        # 2025 is not a leap year
        ok, errs = validate_date("29/02/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_invalid_30_day_month_with_31(self):
        # April has 30 days
        ok, errs = validate_date("31/04/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

        # June has 30 days
        ok, errs = validate_date("31/06/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_invalid_day_32(self):
        ok, errs = validate_date("32/01/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_invalid_day_zero(self):
        ok, errs = validate_date("00/05/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_invalid_month_13(self):
        ok, errs = validate_date("15/13/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_invalid_month_zero(self):
        ok, errs = validate_date("15/00/2025")
        self.assertFalse(ok)
        self.assertIn("date_invalid", errs)

    def test_year_boundary_out_of_range(self):
        # Year < 1900
        ok, errs = validate_date("15/08/1899")
        self.assertFalse(ok)
        self.assertIn("date_year_out_of_range", errs)

        # Year > 2100
        ok, errs = validate_date("15/08/2101")
        self.assertFalse(ok)
        self.assertIn("date_year_out_of_range", errs)

    def test_year_boundary_acceptable(self):
        # Year 1900
        ok, errs = validate_date("01/01/1900")
        self.assertTrue(ok)
        # Year 2100
        ok, errs = validate_date("31/12/2100")
        self.assertTrue(ok)

    def test_invalid_format_text(self):
        for val in ["abc", "random date", "12345", "31/02/abcd", ""]:
            ok, errs = validate_date(val)
            self.assertFalse(ok)


class TestNumberValidation(unittest.TestCase):
    """Test suite for strict numeric validation."""

    def test_valid_integers(self):
        for val in ["0", "85", "100", "2024", "4500"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_signed_numbers(self):
        ok, errs = validate_number("-5")
        self.assertTrue(ok)
        ok, errs = validate_number("+10")
        self.assertTrue(ok)
        ok, errs = validate_number("-2.5")
        self.assertTrue(ok)

    def test_valid_decimals(self):
        for val in ["85.5", "9.2", "450.75", ".75", "12.00"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_percentages(self):
        for val in ["85%", "92.5%", "85.5 %"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_comma_formatted_numbers(self):
        # Indian numbering system (lakhs/crores) and standard thousands
        for val in ["1,50,000", "15,00,000", "150,000", "1,50,000.50"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_postal_code_and_digit_groupings(self):
        # Indian 6-digit PIN codes
        for val in ["600001", "600 001", "110001"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_phone_number_in_numeric_field(self):
        for val in ["9876543210", "+91 9876543210", "+91-98765-43210", "09876543210"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_valid_grouped_digits(self):
        for val in ["1234 5678", "1234-5678-9012"]:
            ok, errs = validate_number(val)
            self.assertTrue(ok, f"Failed for {val}")
            self.assertEqual(errs, [])

    def test_rejects_alphabetic_text(self):
        for val in ["abc", "eighty five", "N/A", "none", "12abc", "marks: 95", "100 marks", "98x"]:
            ok, errs = validate_number(val)
            self.assertFalse(ok, f"Should reject {val}")
            self.assertIn("number_non_numeric", errs)

    def test_rejects_malformed_formats(self):
        for val in ["12.34.56", "..5", "++5", "--5", "$100", "@123", "#45", ""]:
            ok, errs = validate_number(val)
            self.assertFalse(ok, f"Should reject {val}")
            self.assertIn("number_invalid_format", errs)


class TestFieldValidationIntegration(unittest.TestCase):
    """Test suite for validate_field with dates, numbers, and existing types."""

    def test_required_date_field_valid(self):
        field_def = {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True}
        res = validate_field(field_def, "15/08/2005")
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["errors"], [])

    def test_required_date_field_impossible_date(self):
        field_def = {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True}
        res = validate_field(field_def, "31/02/2026")
        self.assertEqual(res["status"], "error")
        self.assertIn("date_invalid", res["errors"])
        self.assertTrue(len(res["suggestions_en"]) > 0)
        self.assertTrue(len(res["suggestions_ta"]) > 0)

    def test_required_date_field_empty(self):
        field_def = {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True}
        res = validate_field(field_def, "")
        self.assertEqual(res["status"], "error")
        self.assertIn("required_empty", res["errors"])

    def test_optional_date_field_empty(self):
        field_def = {"field_name": "admission_date", "question": "Admission Date", "field_type": "date", "is_required": False}
        res = validate_field(field_def, "")
        self.assertEqual(res["status"], "warning")
        self.assertIn("optional_empty", res["errors"])

    def test_optional_date_field_invalid(self):
        field_def = {"field_name": "admission_date", "question": "Admission Date", "field_type": "date", "is_required": False}
        res = validate_field(field_def, "31/02/2026")
        self.assertEqual(res["status"], "error")
        self.assertIn("date_invalid", res["errors"])

    def test_required_number_field_valid(self):
        field_def = {"field_name": "marks", "question": "HSC Total Marks", "field_type": "number", "is_required": True}
        res = validate_field(field_def, "485.5")
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["errors"], [])

    def test_required_number_field_non_numeric(self):
        field_def = {"field_name": "marks", "question": "HSC Total Marks", "field_type": "number", "is_required": True}
        res = validate_field(field_def, "four hundred")
        self.assertEqual(res["status"], "error")
        self.assertIn("number_non_numeric", res["errors"])
        self.assertTrue(len(res["suggestions_en"]) > 0)
        self.assertTrue(len(res["suggestions_ta"]) > 0)

    def test_number_zero_not_treated_as_placeholder(self):
        field_def = {"field_name": "arrears", "question": "Number of Arrears", "field_type": "number", "is_required": True}
        res = validate_field(field_def, 0)
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["errors"], [])

    def test_language_preference_english_only(self):
        field_def = {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True}
        res = validate_field(field_def, "31/02/2026", language="english")
        self.assertTrue(len(res["suggestions_en"]) > 0)
        self.assertEqual(res["suggestions_ta"], "")

    def test_language_preference_tamil_only(self):
        field_def = {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True}
        res = validate_field(field_def, "31/02/2026", language="tamil")
        self.assertEqual(res["suggestions_en"], "")
        self.assertTrue(len(res["suggestions_ta"]) > 0)


class TestFullFormValidation(unittest.TestCase):
    """Test suite for validate_form with diverse fields."""

    def test_complete_valid_form(self):
        fields = [
            {"field_name": "full_name", "question": "Full Name", "field_type": "text", "is_required": True},
            {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True},
            {"field_name": "email", "question": "Email", "field_type": "email", "is_required": True},
            {"field_name": "phone", "question": "Mobile Number", "field_type": "phone", "is_required": True},
            {"field_name": "percentage", "question": "12th Percentage", "field_type": "number", "is_required": True},
            {"field_name": "pincode", "question": "Pincode", "field_type": "number", "is_required": True},
            {"field_name": "notes", "question": "Additional Notes", "field_type": "text", "is_required": False},
        ]
        answers = {
            "full_name": "Ananya Sharma",
            "dob": "15/08/2005",
            "email": "ananya@example.edu.in",
            "phone": "+91 9876543210",
            "percentage": "92.5%",
            "pincode": "600 001",
            "notes": ""
        }
        res = validate_form(fields, answers)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["error_count"], 0)
        self.assertEqual(res["completed_fields"], 6)

    def test_form_with_date_and_number_errors(self):
        fields = [
            {"field_name": "dob", "question": "Date of Birth", "field_type": "date", "is_required": True},
            {"field_name": "marks", "question": "Marks", "field_type": "number", "is_required": True},
        ]
        answers = {
            "dob": "31/02/2026",
            "marks": "eighty five"
        }
        res = validate_form(fields, answers)
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["error_count"], 2)


if __name__ == "__main__":
    unittest.main()
