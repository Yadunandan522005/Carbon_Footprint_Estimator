# app.py
import os
import io
import csv
import json
import base64
import re
import uuid

from datetime import datetime
from collections import defaultdict
from urllib.parse import urlencode
from flask import (

    Flask, request, jsonify, send_file, render_template_string,

    redirect, abort
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import pandas as pd
# New platypus imports for improved PDF layout
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm


# Gas ordering used in UI and PDF

GAS_ORDER = ['CO2', 'CH4', 'N2O', 'SO2']



# Optional: Pillow (for PDF chart handling)

PIL_AVAILABLE = False

try:

    from PIL import Image as PILImage

    PIL_AVAILABLE = True

except Exception:

    PIL_AVAILABLE = False



# Bill uploads use local Tesseract OCR; no third-party OCR API key is required.
app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024




# --------------------------------------------------
# VERCEL-SAFE FILE AND DIRECTORY CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Load optional local environment variables. No API key is required by this app.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
except Exception:
    pass


# Detect Vercel reliably
IS_VERCEL = (
    os.environ.get("VERCEL") == "1"
    or bool(os.environ.get("VERCEL_ENV"))
    or BASE_DIR.startswith("/var/task")
)

# All runtime files must be written to /tmp on Vercel
DATA_DIR = (
    "/tmp/carbon_footprint_estimator"
    if IS_VERCEL
    else BASE_DIR
)

os.makedirs(DATA_DIR, exist_ok=True)

# Use bundled files for reading when available.
# If missing, create fallback files in writable storage.
EMISSION_FACTORS_FILE = os.path.join(
    BASE_DIR, "emission_factors.json"
)

if not os.path.isfile(EMISSION_FACTORS_FILE):
    EMISSION_FACTORS_FILE = os.path.join(
        DATA_DIR, "emission_factors.json"
    )

SAMPLE_CSV = os.path.join(BASE_DIR, "sample.csv")

if not os.path.isfile(SAMPLE_CSV):
    SAMPLE_CSV = os.path.join(DATA_DIR, "sample.csv")

STATS_FILE = os.path.join(DATA_DIR, "stats.json")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
RESULTS_DIR = os.path.join(DATA_DIR, "results")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)


# --------------------------------------------------
# DEFAULT FILE DATA
# --------------------------------------------------

DEFAULT_FACTORS = {
    "gwp": {
        "CO2": 1,
        "CH4": 28,
        "N2O": 265,
        "SO2": 0.0
    },
    "activity_factors": {
        "electricity": {
            "unit": "kWh",
            "CO2": 0.5,
            "CH4": 0.0001,
            "N2O": 0.00005
        },
        "diesel": {
            "unit": "liter",
            "CO2": 2.68,
            "CH4": 0.0002,
            "N2O": 0.0001
        },
        "petrol": {
            "unit": "liter",
            "CO2": 2.31,
            "CH4": 0.00015,
            "N2O": 0.00005
        },
        "fertilizer": {
            "unit": "kg",
            "CO2": 0.0,
            "CH4": 0.0,
            "N2O": 0.3
        }
    },
    "last_updated": datetime.utcnow().isoformat()
}

DEFAULT_THRESHOLDS = {
    "low": 500.0,
    "medium": 2000.0
}


def ensure_files():

    if not os.path.exists(EMISSION_FACTORS_FILE):
        with open(EMISSION_FACTORS_FILE, "w") as f:
            json.dump({
                "factors": DEFAULT_FACTORS,
                "thresholds": DEFAULT_THRESHOLDS
            }, f, indent=2)

    if not os.path.exists(SAMPLE_CSV):
        sample = [
            ["source_id", "activity_date", "activity_type",
             "quantity", "unit", "gas"],
            ["A1", "2025-01-10", "electricity", "150", "kWh", "CO2"],
            ["A2", "2025-01-12", "diesel", "50", "liter", "CO2"],
            ["A3", "2025-01-15", "fertilizer", "10", "kg", "N2O"]
        ]

        with open(SAMPLE_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(sample)

    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w") as f:
            json.dump({
                "total_calculations": 0,
                "avg_footprint_kg": 0.0,
                "last_run": None
            }, f)


ensure_files()


# Default emission factors and thresholds (editable file produced)

DEFAULT_FACTORS = {

    "gwp": {"CO2": 1, "CH4": 28, "N2O": 265, "SO2": 0.0},

    "activity_factors": {

        # unit: emission per unit (kg of gas per unit)

        "electricity": {"unit": "kWh", "CO2": 0.5, "CH4": 0.0001, "N2O": 0.00005},

        "diesel": {"unit": "liter", "CO2": 2.68, "CH4": 0.0002, "N2O": 0.0001},

        "petrol": {"unit": "liter", "CO2": 2.31, "CH4": 0.00015, "N2O": 0.00005},

        "fertilizer": {"unit": "kg", "CO2": 0.0, "CH4": 0.0, "N2O": 0.3}

    },

    "last_updated": datetime.utcnow().isoformat()

}

DEFAULT_THRESHOLDS = {"low": 500.0, "medium": 2000.0}



UNIT_CONVERSIONS = {

    "Wh": {"kWh": 1 / 1000},

    "kWh": {"Wh": 1000},

    "liter": {"liter": 1},

    "L": {"liter": 1},

    "kg": {"kg": 1},

    "g": {"kg": 1 / 1000},

    "ton": {"kg": 1000}

}



def ensure_files():

    if not os.path.exists(EMISSION_FACTORS_FILE):

        with open(EMISSION_FACTORS_FILE, "w") as f:

            json.dump({"factors": DEFAULT_FACTORS, "thresholds": DEFAULT_THRESHOLDS}, f, indent=2)

    if not os.path.exists(SAMPLE_CSV):

        sample = [

            ["source_id", "activity_date", "activity_type", "quantity", "unit", "gas"],

            ["A1", "2025-01-10", "electricity", "150", "kWh", "CO2"],

            ["A2", "2025-01-12", "diesel", "50", "liter", "CO2"],

            ["A3", "2025-01-15", "fertilizer", "10", "kg", "N2O"]

        ]

        with open(SAMPLE_CSV, "w", newline="") as f:

            writer = csv.writer(f)

            writer.writerows(sample)

    if not os.path.exists(STATS_FILE):

        with open(STATS_FILE, "w") as f:

            json.dump({"total_calculations": 0, "avg_footprint_kg": 0.0, "last_run": None}, f)



ensure_files()



def load_emission_config():

    with open(EMISSION_FACTORS_FILE, "r") as f:

        data = json.load(f)

    factors = data.get("factors", DEFAULT_FACTORS)

    thresholds = data.get("thresholds", DEFAULT_THRESHOLDS)

    return factors, thresholds



def update_stats(total_co2_kg):

    with open(STATS_FILE, "r") as f:

        s = json.load(f)

    total_runs = s.get("total_calculations", 0) + 1

    avg = s.get("avg_footprint_kg", 0.0)

    new_avg = (avg * s.get("total_calculations", 0) + total_co2_kg) / total_runs

    s.update({"total_calculations": total_runs, "avg_footprint_kg": new_avg, "last_run": datetime.utcnow().isoformat()})

    with open(STATS_FILE, "w") as f:

        json.dump(s, f, indent=2)



def classify(total_kg, thresholds):

    if total_kg < thresholds["low"]:

        return "Low"

    if total_kg <= thresholds["medium"]:

        return "Medium"

    return "High"



def convert_unit(quantity, from_unit, to_unit):

    if not from_unit or not to_unit:

        return None

    if from_unit == to_unit:

        return quantity

    if from_unit in UNIT_CONVERSIONS and to_unit in UNIT_CONVERSIONS[from_unit]:

        return quantity * UNIT_CONVERSIONS[from_unit][to_unit]

    if to_unit in UNIT_CONVERSIONS and from_unit in UNIT_CONVERSIONS[to_unit]:

        return quantity / UNIT_CONVERSIONS[to_unit][from_unit]

    return None



# Electricity bill reading: local OCR (no API key or paid OCR service).
# Windows requires the free Tesseract OCR program to be installed separately.
KWH_RE = re.compile(
    r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:kwh|kw\s*h|k\s*w\s*h)\b",
    re.IGNORECASE,
)
CONSUMPTION_RE = re.compile(
    r"(?:"
    r"consumption\s*(?:units?|detail)\b|"
    r"(?:total\s+)?(?:units?|quantity)\s*(?:consumed|used)\b|"
    r"(?:bill\s+for\s+)?consumed\s+units?\b|"
    r"consumption\b|"
    r"energy\s*consumed\b"
    r")"
    r"[^0-9\r\n]*([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
METER_RE = re.compile(
    r"(?:present|current|closing)[^0-9\r\n]{0,25}([0-9][0-9,]*(?:\.[0-9]+)?)"
    r"|(?:previous|prev\.?|opening)[^0-9\r\n]{0,25}([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)


def _configure_tesseract():
    """Find the standard Windows Tesseract installation when it is not on PATH."""
    try:
        import pytesseract
        if os.name == "nt":
            candidates = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for candidate in candidates:
                if os.path.isfile(candidate):
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    break
        return pytesseract
    except ImportError:
        return None


def _extract_kwh_from_text(text):
    """Return the best positive electricity consumption value found in bill text."""
    clean_text = re.sub(r"[^\x09\x0a\x0d\x20-\x7E]", " ", text or "")
    clean_text = re.sub(r"\bk\s*[. ]*\s*w\s*[. ]*\s*h\b", "kWh", clean_text, flags=re.IGNORECASE)

    def parse_numbers(matches):
        result = []
        for match in matches:
            if isinstance(match, tuple):
                match = next((item for item in match if item), "")
            try:
                value = float(str(match).replace(",", "").strip())
                if value > 0:
                    result.append(value)
            except (TypeError, ValueError):
                pass
        return result

    explicit_kwh = []
    tariff_words = re.compile(
        r"\b(?:first|over|tier|tariff|rate|charge|per\s*kwh|threshold)\b",
        re.IGNORECASE,
    )
    for line in clean_text.splitlines():
        if tariff_words.search(line):
            continue
        explicit_kwh.extend(parse_numbers(KWH_RE.findall(line)))
    if explicit_kwh:
        return explicit_kwh[-1], None

    labeled = []
    label_pattern = re.compile(
        r"(?:consum(?:ption|ed)|energy\s*(?:consumed|units?)|"
        r"(?:total\s+)?(?:electric(?:ity)?\s+)?units?\s*(?:consumed|used)?|"
        r"(?:total\s+)?(?:quantity|load)\s*(?:used|consumed)?)"
        r"[^0-9\r\n]{0,20}([0-9][0-9,]*(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    for line in clean_text.splitlines():
        if re.search(r"\b(?:amount|charge|cost|rate|tax|bill|payable|demand)\b", line, re.I):
            continue
        labeled.extend(parse_numbers(label_pattern.findall(line)))
    if labeled:
        return labeled[-1], None

    consumption_values = parse_numbers(CONSUMPTION_RE.findall(clean_text))
    if consumption_values:
        return consumption_values[-1], None

    meter_pairs = METER_RE.findall(clean_text)
    present_values = []
    previous_values = []
    for present, previous in meter_pairs:
        present_values.extend(parse_numbers([present]))
        previous_values.extend(parse_numbers([previous]))
    if present_values and previous_values:
        difference = max(present_values) - min(previous_values)
        if difference > 0:
            return difference, None

    return None, "Could not identify an electricity consumption value on this bill. Upload the original bill image or PDF containing kWh, units consumed, or consumption; a screenshot of this upload page is not a bill."


def extract_kwh_from_image(image_path):
    """OCR a bill image locally and extract its kWh value."""
    pytesseract = _configure_tesseract()
    if pytesseract is None:
        return None, "Local OCR package is missing. Run: python -m pip install -r requirements.txt"
    try:
        from PIL import Image, ImageOps, ImageEnhance, ImageFilter
        with Image.open(image_path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            texts = []
            rotations = (0,)
            for rotation in rotations:
                rotated = image.rotate(rotation, expand=True)
                if rotated.width < 1800:
                    scale = min(3, 1800 / max(rotated.width, 1))
                    rotated = rotated.resize(
                        (int(rotated.width * scale), int(rotated.height * scale))
                    )
                base = ImageOps.grayscale(rotated)
                variants = (
                    base,
                    base.filter(ImageFilter.SHARPEN),
                    ImageEnhance.Contrast(base).enhance(2.0),
                )
                for processed in variants:
                    for psm in (6, 11, 3):
                        texts.append(
                            pytesseract.image_to_string(
                                processed, config=f"--oem 3 --psm {psm}"
                            )
                        )
        for text in texts:
            quantity, error = _extract_kwh_from_text(text)
            if quantity is not None:
                return quantity, None
        return None, "Could not identify an electricity consumption value on this bill. Upload the original bill image or PDF containing kWh, units consumed, or consumption; a screenshot of this upload page is not a bill."
    except Exception as exc:
        message = str(exc)
        if "tesseract is not installed" in message.lower() or "not found" in message.lower():
            return None, "Tesseract OCR is not installed. Install the free Tesseract program, then restart VS Code. See LOCAL_SETUP_FIX.md."
        return None, f"Could not read this bill image: {exc}"


def extract_kwh_from_pdf(pdf_path):
    """Read selectable PDF text first; use local OCR for scanned PDF pages."""
    text = ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        pass
    quantity, error = _extract_kwh_from_text(text)
    if quantity is not None:
        return quantity, None

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None, "Scanned PDF OCR support is missing. Install project requirements with: python -m pip install -r requirements.txt"
    try:
        doc = fitz.open(pdf_path)
        page_text = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image_bytes = pix.tobytes("png")
            from PIL import Image
            import io as _io
            with Image.open(_io.BytesIO(image_bytes)) as image:
                pytesseract = _configure_tesseract()
                if pytesseract is None:
                    return None, "Local OCR package is missing. Run: python -m pip install -r requirements.txt"
                page_text.append(pytesseract.image_to_string(image, config="--oem 3 --psm 6"))
        return _extract_kwh_from_text("\n".join(page_text))
    except Exception as exc:
        if "tesseract is not installed" in str(exc).lower() or "not found" in str(exc).lower():
            return None, "Tesseract OCR is not installed. Install the free Tesseract program, then restart VS Code. See LOCAL_SETUP_FIX.md."
        return None, f"Could not read this PDF: {exc}"


def normalize_activity_key(act_type):

    if not act_type:

        return None

    k = str(act_type).strip().lower().replace(' ', '_')

    if k in ['gasoline', 'gas']:

        return 'petrol'

    return k



def process_rows_backend(rows, selected_gases):

    """

    Core processing. Returns a dictionary with per_gas_totals_kg, summary_line, suggestions, etc.

    """

    factors, thresholds = load_emission_config()

    gwp = factors.get("gwp", {})

    activity_factors = factors.get("activity_factors", {})



    # Normalize activity factors keys

    af_norm = {}

    for k, v in activity_factors.items():

        af_norm[k.lower()] = v



    per_gas_totals = defaultdict(float)

    rows_skipped = []

    processed_count = 0

    activities_out = []



    for idx, r in enumerate(rows):

        q_raw = r.get('quantity')

        try:

            q = float(str(q_raw).replace(',', ''))

        except Exception:

            rows_skipped.append({"index": idx, "reason": f"invalid quantity ({q_raw})"})

            continue

        act_type = str(r.get('activity_type') or '').strip()

        unit = str(r.get('unit') or '').strip()

        row_gas = (str(r.get('gas') or '')).strip()

        key = normalize_activity_key(act_type) or 'electricity'

        af = af_norm.get(key) or af_norm.get(act_type.lower())

        if not af:

            rows_skipped.append({"index": idx, "reason": f"missing emission factor for activity_type '{act_type}'"})

            continue

        expected_unit = af.get("unit")

        if unit == '' or unit is None:

            unit = expected_unit or ''

        if expected_unit and unit and unit != expected_unit:

            conv = convert_unit(q, unit, expected_unit)

            if conv is None:

                rows_skipped.append({"index": idx, "reason": f"unsupported unit conversion {unit} -> {expected_unit}"})

                continue

            q_converted = conv

        else:

            q_converted = q



        # The user's selected gases are authoritative for every uploaded row.
        def normalize_gas_name(value):
            return str(value or "").strip().replace("₂", "2").replace("₄", "4").upper()

        selected_normalized = {normalize_gas_name(g) for g in (selected_gases or [])}
        if selected_normalized:
            if row_gas:
                gases_to_compute = [row_gas] if normalize_gas_name(row_gas) in selected_normalized else []
            else:
                gases_to_compute = list(selected_gases)
        elif row_gas:
            gases_to_compute = [row_gas]
        else:
            gases_to_compute = [
                g for g in af.keys()
                if g != "unit" and normalize_gas_name(g) in gwp
            ]



        row_emissions = {}

        for gas in gases_to_compute:

            gas_norm = str(gas).replace('₂','2').replace('₄','4').upper()

            # try various keys

            fac_val = af.get(gas_norm) or af.get(gas_norm.capitalize()) or af.get(gas_norm.lower())

            if fac_val is None:

                continue

            emissions_kg = q_converted * float(fac_val)

            per_gas_totals[gas_norm] += emissions_kg

            row_emissions[gas_norm] = emissions_kg



        if not row_emissions:
            rows_skipped.append({
                "index": idx,
                "reason": f"gas '{row_gas}' is not selected or has no matching emission factor"
            })
            continue

        processed_count += 1

        activities_out.append({

            "index": idx,

            "activity_type": act_type,

            "quantity": q,

            "unit": unit,

            "row_emissions": row_emissions

        })



    total_co2_equivalent = 0.0

    for gas, kg in per_gas_totals.items():

        total_co2_equivalent += kg * gwp.get(gas, 0)



    update_stats(total_co2_equivalent)

    classification = classify(total_co2_equivalent, thresholds)

    if classification == "High":

        suggestions = [

            "Consider energy-efficiency upgrades, switch to renewable electricity, and optimize logistics to reduce fuel consumption.",

            "Review top emitting activities for targeted interventions."

        ]

    elif classification == "Medium":

        suggestions = [

            "Good progress — consider targeted interventions like LED upgrades, thermostat optimization, and routing improvements.",

            "Track high-emitting activities monthly."

        ]

    else:

        suggestions = [

            "Great job — keep monitoring and consider offsetting remaining emissions if needed.",

            "Consider continuous improvement measures and set reduction targets."

        ]



    # ensure all GAS_ORDER keys present

    per_gas_out = {g: round(per_gas_totals.get(g, 0.0), 6) for g in GAS_ORDER}

    labels = list(per_gas_out.keys())

    values = [round(per_gas_out[k], 3) for k in labels]



    for a in activities_out:

        total_row_co2e = 0.0

        for g, kg in a["row_emissions"].items():

            total_row_co2e += kg * gwp.get(g, 0)

        a["total_co2e_kg"] = total_row_co2e

        a["total_co2_kg"] = total_row_co2e



    top_activities = sorted(activities_out, key=lambda x: x["total_co2_kg"], reverse=True)[:10]

    summary_line = f"Estimated total CO2: {round(total_co2_equivalent,3)} kg CO2 — {classification}."

    response = {

        "rows_processed": processed_count,

        "rows_skipped": len(rows_skipped),

        "skipped_details": rows_skipped,

        "per_gas_totals_kg": per_gas_out,

        "total_co2_kg": round(total_co2_equivalent, 6),

        "classification": classification,

        "suggestions": suggestions,

        "chart_data": {"labels": labels, "values": values},

        "top_activities": top_activities,

        "summary_line": summary_line,

        # Include the selected gases/mode and the input rows so PDF can show them

        "selected_gases": selected_gases,

        "input_rows": rows

    }

    return response



# ---------- Routes ----------

@app.route("/")

def home():

    with open(STATS_FILE, "r") as f:

        stats = json.load(f)



    html = r"""

<!DOCTYPE html>

<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Carbon Footprint Estimator</title>



    <link href="https://fonts.googleapis.com/css2?family=Inter:wght\@300;400;500;600;700;800&display=swap" rel="stylesheet">



    <style>

        * {

            margin: 0;

            padding: 0;

            box-sizing: border-box;

        }



        html {

            min-height: 100%;

            background: #082b43;

        }



        body {

            font-family: 'Inter', Arial, sans-serif;

            min-height: 100vh;

            color: #ffffff;

            background: linear-gradient(

                135deg,

                #082b43 0%,

                #145276 50%,

                #dceaf1 100%

            );

            background-repeat: no-repeat;

            background-size: cover;

            background-attachment: fixed;

        }



        .container {

            width: 90%;

            max-width: 1000px;

            margin: 0 auto;

            padding: 65px 0;

        }



        .hero {

            width: 100%;

            background: linear-gradient(135deg, #061f35, #164d70);

            padding: 50px 35px;

            border-radius: 20px;

            text-align: center;

            border: 1px solid rgba(255,255,255,0.3);

            box-shadow:

                0 15px 40px rgba(0,0,0,0.30),

                0 0 0 1px rgba(255,255,255,0.05);

            transition: 0.3s ease;

        }



        .hero:hover {

            box-shadow: 0 20px 50px rgba(0,0,0,0.35);

        }



        .project-logo {

            width: 85px;

            height: 85px;

            margin: 0 auto 20px;

            display: flex;

            align-items: center;

            justify-content: center;

            background: rgba(255,255,255,0.12);

            border: 1px solid rgba(255,255,255,0.35);

            border-radius: 22px;

            box-shadow: 0 8px 22px rgba(0,0,0,0.25);

        }



        .project-logo svg {

            width: 60px;

            height: 60px;

        }



        .hero h1 {

            font-size: clamp(30px, 4vw, 44px);

            font-weight: 800;

            color: #ffffff;

            letter-spacing: -1px;

            margin-bottom: 14px;

        }



        .hero p {

            font-size: 17px;

            line-height: 1.7;

            color: #e5f1f8;

        }



        .card {

            width: 100%;

            background: #ffffff;

            color: #102333;

            padding: 40px 30px;

            margin-top: 30px;

            border-radius: 20px;

            border: 1px solid #d5e2eb;

            text-align: center;

            box-shadow:

                0 15px 35px rgba(0,0,0,0.20),

                0 3px 10px rgba(0,0,0,0.08);

            transition: all 0.3s ease;

        }



        .card:hover {

            transform: translateY(-4px);

            box-shadow: 0 22px 45px rgba(0,0,0,0.24);

        }



        .card h2 {

            font-size: 27px;

            font-weight: 700;

            color: #071c2d;

            margin-bottom: 18px;

        }



        .card p {

            font-size: 17px;

            line-height: 1.7;

            color: #263746;

            margin-bottom: 24px;

        }



        .btn {

            display: inline-block;

            background: #1976dc;

            color: #ffffff;

            padding: 13px 23px;

            border-radius: 11px;

            border: 1px solid #1264bd;

            text-decoration: none;

            font-size: 16px;

            font-weight: 600;

            box-shadow: 0 5px 14px rgba(25,118,220,0.25);

            transition: all 0.25s ease;

        }



        .btn:hover {

            background: #095dbb;

            transform: translateY(-3px);

            box-shadow: 0 9px 20px rgba(25,118,220,0.35);

        }



        .upload-link {

            display: inline-block;

            margin-left: 18px;

            color: #102333;

            text-decoration: none;

            font-size: 16px;

            font-weight: 600;

            transition: 0.2s ease;

        }



        .upload-link:hover {

            color: #1976dc;

            text-decoration: underline;

        }



        @media (max-width: 600px) {

            .container {

                width: 92%;

                padding: 35px 0;

            }



            .hero {

                padding: 35px 18px;

            }



            .project-logo {

                width: 70px;

                height: 70px;

            }



            .project-logo svg {

                width: 50px;

                height: 50px;

            }



            .hero h1 {

                font-size: 29px;

            }



            .hero p {

                font-size: 14px;

            }



            .card {

                padding: 30px 18px;

            }



            .card h2 {

                font-size: 22px;

            }



            .card p {

                font-size: 15px;

            }



            .btn {

                padding: 11px 16px;

                font-size: 14px;

            }



            .upload-link {

                margin-left: 10px;

                font-size: 14px;

            }

        }

    
/* Shared Carbon Footprint theme for every application page */
:root {
    --carbon-navy: #082b43;
    --carbon-blue: #145276;
    --carbon-pale: #dceaf1;
    --carbon-accent: #1976dc;
    --carbon-border: rgba(255,255,255,0.38);
    --carbon-shadow: 0 16px 38px rgba(0, 0, 0, 0.20);
}
html {
    min-height: 100%;
    background: var(--carbon-navy);
}
body {
    min-height: 100vh;
    margin: 0;
    font-family: Inter, Arial, sans-serif;
    background: linear-gradient(135deg, #082b43 0%, #145276 55%, #dceaf1 100%);
    background-repeat: no-repeat;
    background-size: cover;
    background-attachment: fixed;
    color: #102333;
}
.wrap, .container {
    width: min(92%, 1100px);
    margin-left: auto !important;
    margin-right: auto !important;
}
.wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 38px 0;
}
.card, .transport-card {
    background: #fff;
    border: 1px solid rgba(8, 43, 67, 0.16);
    border-radius: 18px;
    box-shadow: var(--carbon-shadow);
}
.container {
    padding-top: 38px;
    padding-bottom: 48px;
}
.container > .card {
    padding: 24px;
    margin-bottom: 18px;
}
.brand-mark {
    width: 70px;
    height: 70px;
    flex: 0 0 70px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 14px;
    border-radius: 19px;
    background: linear-gradient(145deg, #174d70, #0b304a);
    border: 1px solid rgba(255,255,255,0.38);
    box-shadow: 0 9px 22px rgba(0,0,0,0.22);
}
.brand-mark svg {
    width: 49px;
    height: 49px;
}
.brand-mark.page-icon {
    background: linear-gradient(145deg, #174d70, #0b304a);
}
.brand-mark.page-icon svg {
    width: 52px;
    height: 52px;
}
.wrap > .card {
    width: 100%;
    max-width: 760px;
    padding: 36px;
    text-align: center;
}
.wrap > .card h1 {
    text-align: center;
    color: #0b3a56;
    margin: 0 0 10px;
}
.wrap > .card .lead {
    text-align: center;
}
.checkbox-list {
    max-width: 540px;
    margin: 22px auto 0;
    text-align: left;
}
.ch {
    background: #f7fafc;
    border: 1px solid #dce7ef !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(8,43,67,0.05);
}
.actions {
    justify-content: center;
}
.btn, .btn-primary, button {
    border-radius: 10px;
}
.btn-primary, .btn {
    background: #1976dc;
    box-shadow: 0 6px 16px rgba(25,118,220,0.22);
}
.container > .card.header-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
}
.container > .card.header-row .brand-mark {
    margin: 0 16px 0 0;
}
.container > .card.header-row h1 {
    color: #0b3a56;
}
.container .card, .container .transport-card {
    border: 1px solid rgba(8,43,67,0.14);
    box-shadow: 0 12px 28px rgba(0,0,0,0.14);
}
.container .drop {
    border-radius: 14px;
    border-color: #a9c4d6;
}
.container .transport-card {
    padding: 18px;
    border-radius: 16px;
}
.container table {
    background: #fff;
}
.container .grid .item {
    border: 1px solid #dce7ef;
    border-radius: 12px;
}
@media (max-width: 700px) {
    .wrap { padding: 22px 0; }
    .wrap > .card { padding: 24px 18px; }
    .container { width: 94%; padding-top: 20px; }
    .container > .card { padding: 17px; }
    .container > .card.header-row .brand-mark { margin: 0 auto 12px; }
}

</style>

</head>



<body>

    <div class="container">



        <div class="hero">

            <div class="project-logo">

                <svg viewBox="0 0 100 100"

                     xmlns="http://www.w3.org/2000/svg"

                     role="img"

                     aria-label="Green carbon leaf logo">



                    <path

                        d="M50 85 C15 75 10 42 22 18

                           C48 15 78 25 82 50

                           C85 70 68 85 50 85Z"

                        fill="#55D68B"/>



                    <path

                        d="M28 65 C40 43 58 34 75 29

                           C65 49 48 65 28 65Z"

                        fill="#B8F5C9"/>



                    <path

                        d="M28 65 C43 52 57 42 75 29"

                        stroke="#075C43"

                        stroke-width="4"

                        fill="none"

                        stroke-linecap="round"/>



                    <path

                        d="M28 65 C35 75 42 81 50 85"

                        stroke="#075C43"

                        stroke-width="4"

                        fill="none"

                        stroke-linecap="round"/>



                    <circle cx="72" cy="75" r="16" fill="#ffffff"/>



                    <text x="72" y="81"

                          font-size="17"

                          font-weight="bold"

                          text-anchor="middle"

                          fill="#08764C">C</text>

                </svg>

            </div>



            <h1>Carbon Footprint Estimator</h1>



            <p>

                Quickly estimate emissions from activity data

                or an electricity bill image.

            </p>

        </div>



        <div class="card">

            <h2>Choose gases &amp; compute</h2>



            <p>

                Select which greenhouse gases you want to include

                and then upload your CSV or bill image.

            </p>



            <a class="btn" href="/choose">Choose gases</a>



            <a class="upload-link" href="/upload">Upload data</a>

        </div>



    </div>

</body>

</html>

"""



    return render_template_string(html, stats=stats)





@app.route("/choose", methods=["GET", "POST"])

def choose():

    if request.method == "POST":

        selected = request.form.getlist('gases')

        if not selected:

            return "Select at least one gas", 400

        return redirect('/upload?' + urlencode({'gases': ','.join(selected)}))

    html = r"""

<!doctype html>

<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">

<title>Choose gases</title>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght\@300;400;600;700&display=swap" rel="stylesheet">

<style>

  :root{--accent:#0b3a66;--muted:#6b7280}

  body{font-family:Inter,Arial,sans-serif;margin:0;background:#f6f8fb}

  .wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:28px}

  .card{width:100%;max-width:720px;background:white;border-radius:12px;padding:32px;box-shadow:0 18px 40px rgba(9,20,30,0.06)}

  h1{margin:0 0 8px;color:var(--accent)}

  .lead{margin:0 0 20px;color:var(--muted)}

  .checkbox-list{display:flex;flex-direction:column;gap:10px}

  .ch{display:flex;align-items:center;gap:12px;padding:12px;border-radius:8px;border:1px solid #eef3f8}

  .ch input{width:18px;height:18px}

  .ch label{font-weight:600}

  .actions{display:flex;gap:12px;justify-content:center;margin-top:18px}

  .btn-primary{background:var(--accent);color:#fff;padding:10px 14px;border-radius:8px;border:none}

  a.cancel{color:var(--muted);align-self:center;text-decoration:none}


/* Shared Carbon Footprint theme for every application page */
:root {
    --carbon-navy: #082b43;
    --carbon-blue: #145276;
    --carbon-pale: #dceaf1;
    --carbon-accent: #1976dc;
    --carbon-border: rgba(255,255,255,0.38);
    --carbon-shadow: 0 16px 38px rgba(0, 0, 0, 0.20);
}
html {
    min-height: 100%;
    background: var(--carbon-navy);
}
body {
    min-height: 100vh;
    margin: 0;
    font-family: Inter, Arial, sans-serif;
    background: linear-gradient(135deg, #082b43 0%, #145276 55%, #dceaf1 100%);
    background-repeat: no-repeat;
    background-size: cover;
    background-attachment: fixed;
    color: #102333;
}
.wrap, .container {
    width: min(92%, 1100px);
    margin-left: auto !important;
    margin-right: auto !important;
}
.wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 38px 0;
}
.card, .transport-card {
    background: #fff;
    border: 1px solid rgba(8, 43, 67, 0.16);
    border-radius: 18px;
    box-shadow: var(--carbon-shadow);
}
.container {
    padding-top: 38px;
    padding-bottom: 48px;
}
.container > .card {
    padding: 24px;
    margin-bottom: 18px;
}
.brand-mark {
    width: 70px;
    height: 70px;
    flex: 0 0 70px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 14px;
    border-radius: 19px;
    background: linear-gradient(145deg, #174d70, #0b304a);
    border: 1px solid rgba(255,255,255,0.38);
    box-shadow: 0 9px 22px rgba(0,0,0,0.22);
}
.brand-mark svg {
    width: 49px;
    height: 49px;
}
.wrap > .card {
    width: 100%;
    max-width: 760px;
    padding: 36px;
    text-align: center;
}
.wrap > .card h1 {
    text-align: center;
    color: #0b3a56;
    margin: 0 0 10px;
}
.wrap > .card .lead {
    text-align: center;
}
.checkbox-list {
    max-width: 540px;
    margin: 22px auto 0;
    text-align: left;
}
.ch {
    background: #f7fafc;
    border: 1px solid #dce7ef !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(8,43,67,0.05);
}
.actions {
    justify-content: center;
}
.btn, .btn-primary, button {
    border-radius: 10px;
}
.btn-primary, .btn {
    background: #1976dc;
    box-shadow: 0 6px 16px rgba(25,118,220,0.22);
}
.container > .card.header-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
}
.container > .card.header-row .brand-mark {
    margin: 0 16px 0 0;
}
.container > .card.header-row h1 {
    color: #0b3a56;
}
.container .card, .container .transport-card {
    border: 1px solid rgba(8,43,67,0.14);
    box-shadow: 0 12px 28px rgba(0,0,0,0.14);
}
.container .drop {
    border-radius: 14px;
    border-color: #a9c4d6;
}
.container .transport-card {
    padding: 18px;
    border-radius: 16px;
}
.container table {
    background: #fff;
}
.container .grid .item {
    border: 1px solid #dce7ef;
    border-radius: 12px;
}
@media (max-width: 700px) {
    .wrap { padding: 22px 0; }
    .wrap > .card { padding: 24px 18px; }
    .container { width: 94%; padding-top: 20px; }
    .container > .card { padding: 17px; }
    .container > .card.header-row .brand-mark { margin: 0 auto 12px; }
}

</style>

</head><body>

<div class="wrap">

  <div class="card">

    
<div class="brand-mark page-icon" role="img" aria-label="Greenhouse gas molecule icon">
  <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <g stroke="#B8E6FF" stroke-width="7" stroke-linecap="round">
      <path d="M50 50 L24 27 M50 50 L77 27 M50 50 L24 75 M50 50 L77 75"/>
    </g>
    <circle cx="50" cy="50" r="17" fill="#54D6A0" stroke="#E8FFF5" stroke-width="4"/>
    <circle cx="22" cy="24" r="11" fill="#65C8FF" stroke="#E8F7FF" stroke-width="3"/>
    <circle cx="79" cy="24" r="11" fill="#65C8FF" stroke="#E8F7FF" stroke-width="3"/>
    <circle cx="22" cy="78" r="11" fill="#65C8FF" stroke="#E8F7FF" stroke-width="3"/>
    <circle cx="79" cy="78" r="11" fill="#65C8FF" stroke="#E8F7FF" stroke-width="3"/>
  </svg>
</div>

    <h1>Choose gases</h1>

    <p class="lead">Select gases to include in the computation.</p>

    <form method="post">

      <div class="checkbox-list">

        <div class="ch"><input id="g_co2" type="checkbox" name="gases" value="CO2" checked><label for="g_co2">Carbon (CO₂)</label></div>

        <div class="ch"><input id="g_ch4" type="checkbox" name="gases" value="CH4" checked><label for="g_ch4">Methane (CH₄)</label></div>

        <div class="ch"><input id="g_n2o" type="checkbox" name="gases" value="N2O" checked><label for="g_n2o">Nitrous Oxide (N₂O)</label></div>

        <div class="ch"><input id="g_so2" type="checkbox" name="gases" value="SO2"><label for="g_so2">Sulphur (SO₂)</label></div>

      </div>

      <div class="actions">

        <button class="btn-primary" type="submit">Next → Upload & Results</button>

        <a class="cancel" href="/">Cancel</a>

      </div>

    </form>

  </div>

</div>

</body></html>

"""

    return render_template_string(html)



@app.route("/upload")

def upload_page():

    gases_param = request.args.get('gases', '')

    selected = [g for g in gases_param.split(',') if g]

    factors, thresholds = load_emission_config()

    with open(STATS_FILE, "r") as f:

        stats = json.load(f)



    # Main upload page — when Calculate is clicked the backend returns a redirect URL and the client navigates to it

    html = r"""

<!doctype html>

<html><head><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Upload & Results</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght\@300;400;600;700&display=swap" rel="stylesheet">

<style>

  body{font-family:Inter,Arial,sans-serif;background:#f6f8fb;padding:20px}

  .container{max-width:1100px;margin:8px auto}

  .card{background:#fff;padding:18px;border-radius:12px;box-shadow:0 12px 30px rgba(11,26,40,0.06);margin-bottom:14px}

  .header-row{display:flex;justify-content:space-between;align-items:center;gap:12px}

  h1{margin:0;font-size:22px}.small{color:#6b7280;font-size:13px}

  .btn{background:#0b3a66;color:#fff;padding:8px 12px;border-radius:8px;border:none;cursor:pointer}

  .drop{min-height:120px;border:2px dashed #e6e9ef;display:flex;align-items:center;justify-content:center;cursor:pointer;background:#fafbfe;border-radius:8px}

  .preview{font-family:monospace;background:#f8fafc;padding:8px;border-radius:6px;color:#0f172a}

  .chart-container{width:360px;height:200px;margin-top:12px}

  .error{color:#b91c1c}

  .controls{display:flex;gap:10px;flex-wrap:wrap}

  .two-cols{display:flex;gap:18px;align-items:flex-start}

  .left-col{flex:1}

  .right-col{width:360px}

  .transport-card{background:#fff;border-radius:10px;padding:14px;border:1px solid #eef3f8}

  .transport-card h4{margin:0 0 8px}

  .transport-card .btn-vehicle{background:#1a73d8;color:#fff;padding:8px 10px;border-radius:8px;border:none;cursor:pointer;margin-right:8px}

  .transport-form{margin-top:10px;padding-top:10px;border-top:1px dashed #eef3f8}

  .tf-row{display:flex;gap:8px;margin-bottom:8px;align-items:center}

  .tf-row input{padding:8px;border-radius:6px;border:1px solid #e6e9ef;flex:1}

  .calc-row{margin-top:12px}

  @media (max-width:900px){

    .two-cols{flex-direction:column}

    .right-col{width:100%}

  }


/* Shared Carbon Footprint theme for every application page */
:root {
    --carbon-navy: #082b43;
    --carbon-blue: #145276;
    --carbon-pale: #dceaf1;
    --carbon-accent: #1976dc;
    --carbon-border: rgba(255,255,255,0.38);
    --carbon-shadow: 0 16px 38px rgba(0, 0, 0, 0.20);
}
html {
    min-height: 100%;
    background: var(--carbon-navy);
}
body {
    min-height: 100vh;
    margin: 0;
    font-family: Inter, Arial, sans-serif;
    background: linear-gradient(135deg, #082b43 0%, #145276 55%, #dceaf1 100%);
    background-repeat: no-repeat;
    background-size: cover;
    background-attachment: fixed;
    color: #102333;
}
.wrap, .container {
    width: min(92%, 1100px);
    margin-left: auto !important;
    margin-right: auto !important;
}
.wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 38px 0;
}
.card, .transport-card {
    background: #fff;
    border: 1px solid rgba(8, 43, 67, 0.16);
    border-radius: 18px;
    box-shadow: var(--carbon-shadow);
}
.container {
    padding-top: 38px;
    padding-bottom: 48px;
}
.container > .card {
    padding: 24px;
    margin-bottom: 18px;
}
.brand-mark {
    width: 70px;
    height: 70px;
    flex: 0 0 70px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 14px;
    border-radius: 19px;
    background: linear-gradient(145deg, #174d70, #0b304a);
    border: 1px solid rgba(255,255,255,0.38);
    box-shadow: 0 9px 22px rgba(0,0,0,0.22);
}
.brand-mark svg {
    width: 49px;
    height: 49px;
}
.wrap > .card {
    width: 100%;
    max-width: 760px;
    padding: 36px;
    text-align: center;
}
.wrap > .card h1 {
    text-align: center;
    color: #0b3a56;
    margin: 0 0 10px;
}
.wrap > .card .lead {
    text-align: center;
}
.checkbox-list {
    max-width: 540px;
    margin: 22px auto 0;
    text-align: left;
}
.ch {
    background: #f7fafc;
    border: 1px solid #dce7ef !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(8,43,67,0.05);
}
.actions {
    justify-content: center;
}
.btn, .btn-primary, button {
    border-radius: 10px;
}
.btn-primary, .btn {
    background: #1976dc;
    box-shadow: 0 6px 16px rgba(25,118,220,0.22);
}
.container > .card.header-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
}
.container > .card.header-row .brand-mark {
    margin: 0 16px 0 0;
}
.container > .card.header-row h1 {
    color: #0b3a56;
}
.container .card, .container .transport-card {
    border: 1px solid rgba(8,43,67,0.14);
    box-shadow: 0 12px 28px rgba(0,0,0,0.14);
}
.container .drop {
    border-radius: 14px;
    border-color: #a9c4d6;
}
.container .transport-card {
    padding: 18px;
    border-radius: 16px;
}
.container table {
    background: #fff;
}
.container .grid .item {
    border: 1px solid #dce7ef;
    border-radius: 12px;
}
@media (max-width: 700px) {
    .wrap { padding: 22px 0; }
    .wrap > .card { padding: 24px 18px; }
    .container { width: 94%; padding-top: 20px; }
    .container > .card { padding: 17px; }
    .container > .card.header-row .brand-mark { margin: 0 auto 12px; }
}

</style>

</head><body>

<div class="container">

  <div class="card header-row">

    <div>

      
<div class="brand-mark page-icon" role="img" aria-label="Upload data icon">
  <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M25 69H75C86 69 91 61 91 51C91 41 83 34 73 34C69 19 57 12 44 16C33 19 27 28 27 39C15 39 9 47 9 56C9 64 15 69 25 69Z" fill="#DDF3FF" stroke="#65C8FF" stroke-width="4"/>
    <path d="M50 82V45 M36 59L50 45L64 59" fill="none" stroke="#39C98A" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M29 88H71" stroke="#B8E6FF" stroke-width="5" stroke-linecap="round"/>
  </svg>
</div>

      <h1>Upload & Results</h1>

      <div class="small">Selected gases: <strong id="selected_gases">{{selected_display}}</strong></div>

    </div>

    <div class="controls">

      <a class="btn" href="/"><strong>Home</strong></a>

      <a class="btn" href="/choose" style="background:#1b5f8a">Change gases</a>

    </div>

  </div>



  <div class="two-cols">

    <div class="left-col">

      <div class="card">

        <h3>Upload (CSV, PDF or electricity bill image)</h3>

        <div id="dropzone" class="drop">Drag & Drop CSV, PDF or bill image here or click to select</div>

        <input id="file_input" type="file" accept=".csv,.pdf,image/png,image/jpeg,image/webp" style="display:none" />

        <div id="file_meta" class="small" style="margin-top:8px"></div>

        <div id="error" class="error" style="display:none;margin-top:8px"></div>

        <div id="bill_image_preview_wrap" style="display:none;margin-top:12px;text-align:left">
          <div class="small">Bill selected. Click Calculate to read the bill automatically and estimate its electricity emissions.</div>
          <img id="bill_image_preview" alt="Electricity bill preview" style="display:none;max-width:100%;max-height:280px;margin-top:12px;border-radius:10px;border:1px solid #d5e2eb">
        </div>

        <div id="calc_box" class="calc-row" style="display:none">

          <button id="calculate_btn" class="btn">Calculate</button>

          <button id="clear_btn" style="margin-left:8px;background:#fff;border:1px solid #e6e9ef;color:#0b3a66;padding:8px 12px;border-radius:8px">Clear</button>

        </div>



        <div id="preview_block" style="display:none;margin-top:12px" class="card">

          <h4>Preview (first rows of CSV)</h4><div id="preview" class="preview"></div>

        </div>



        <div style="margin-top:8px;color:#6b7280;font-size:13px">After calculating you will be redirected to a results page (new sheet) showing the chart and details.</div>



      </div>

    </div>



    <div class="right-col">

      <div class="transport-card">

        <h4>Transportation usage</h4>

        <p class="small">Quick manual input for vehicle fuel (petrol/diesel). Enter liters and press <strong>Calculate</strong> to compute emissions.</p>

        <div>

          <button class="btn-vehicle" onclick="openTransportForm('petrol')">Petrol vehicle</button>

          <button class="btn-vehicle" onclick="openTransportForm('diesel')">Diesel vehicle</button>

        </div>



        <div id="transport_form" class="transport-form" style="display:none">

          <div style="font-size:13px;margin-bottom:8px">Adding entries for: <strong id="transport_type"></strong></div>



          <div class="tf-row">

            <input id="liters_input" placeholder="liters" />

            <button style="margin-left:8px;background:#fff;border:1px solid #e6e9ef;color:#0b3a66;padding:8px 12px;border-radius:8px" onclick="clearTransportForm()">Clear</button>

          </div>



          <div style="margin-top:10px">

            <button id="transport_calc" class="btn" onclick="calculateTransport()">Calculate</button>

          </div>

        </div>

      </div>



      <div style="height:16px"></div>

    </div>

  </div>



</div>



<script>

const selectedGases = {{selected_json|safe}};

document.getElementById('selected_gases').innerText = selectedGases.join(', ') || 'None';



const drop = document.getElementById('dropzone');

const fileInput = document.getElementById('file_input');

const fileMeta = document.getElementById('file_meta');

const errElm = document.getElementById('error');

const calcBox = document.getElementById('calc_box');

const calcBtn = document.getElementById('calculate_btn');

const clearBtn = document.getElementById('clear_btn');

let uploadedFile = null;

let uploadedIsCsv = false;
let uploadedIsPdf = false;



function showError(msg){ errElm.style.display='block'; errElm.innerText = msg; }

function clearError(){ errElm.style.display='none'; errElm.innerText = ''; }



drop.addEventListener('click', ()=> fileInput.click());

drop.addEventListener('dragover', e=> { e.preventDefault(); drop.style.background='#eef'; });

drop.addEventListener('dragleave', ()=> { drop.style.background=''; });

drop.addEventListener('drop', e=> { e.preventDefault(); drop.style.background=''; handleFile(e.dataTransfer.files[0]); });

fileInput.addEventListener('change', e=> handleFile(e.target.files[0]));

clearBtn.addEventListener('click', ()=> {
  uploadedFile=null; uploadedIsCsv=false; uploadedIsPdf=false;
  fileMeta.innerText=''; calcBox.style.display='none';
  document.getElementById('preview_block').style.display='none';
  document.getElementById('bill_image_preview_wrap').style.display='none';
  document.getElementById('bill_image_preview').style.display='none';
  fileInput.value='';
  clearError();
});



function isPdfFile(file){ if (!file) return false; const n=(file.name||'').toLowerCase(); return n.endsWith('.pdf') || file.type==='application/pdf'; }

function isCsvFile(file){ if (!file) return false; const n = (file.name||'').toLowerCase(); return n.endsWith('.csv') || (file.type && file.type.includes('csv')); }

function isImageFile(file){ if (!file) return false; return (file.type && file.type.startsWith('image/')) || (file.name||'').toLowerCase().match(/\.(png|jpe?g|webp|gif)$/); }



function handleFile(file){

  clearError();

  if (!file) return;

  uploadedFile = file;

  fileMeta.innerText = `Selected: ${file.name} (${file.size} bytes)`;
  calcBox.style.display = 'block';
  uploadedIsCsv = false;
  uploadedIsPdf = false;
  document.getElementById('bill_image_preview_wrap').style.display = 'none';
  document.getElementById('bill_image_preview').style.display = 'none';

  if (isCsvFile(file)){

    uploadedIsCsv = true;

    const reader = new FileReader();

    reader.onload = ()=> {

      const txt = reader.result;

      const rows = txt.split(/**\r**?**\n**/).filter(Boolean).slice(0,6);

      document.getElementById('preview').innerText = rows.join('**\\**&#x6E;');

      document.getElementById('preview_block').style.display = 'block';

    };

    reader.readAsText(file);

    return;

  }

  if (isPdfFile(file)){
    uploadedIsPdf = true;
    document.getElementById('preview_block').style.display = 'none';
    document.getElementById('bill_image_preview_wrap').style.display = 'block';
    return;
  }

  if (isImageFile(file)){
    document.getElementById('preview_block').style.display = 'none';
    document.getElementById('bill_image_preview_wrap').style.display = 'block';
    const preview = document.getElementById('bill_image_preview');
    preview.src = URL.createObjectURL(file);
    preview.style.display = 'block';
    return;
  }

  uploadedFile = null;
  calcBox.style.display = 'none';
  showError('Unsupported file type. Upload CSV, PDF, JPG, JPEG or PNG.');

}



calcBtn.addEventListener('click', async ()=> {

  clearError();

  if (!uploadedFile){ showError('Select a file first'); return; }

  if (uploadedIsCsv){

    const fd = new FormData();

    fd.append('file', uploadedFile);

    fd.append('mapping', JSON.stringify({}));

    fd.append('gases', JSON.stringify(selectedGases));

    const res = await fetch('/api/upload', { method:'POST', body: fd });

    const data = await res.json();

    if (!res.ok){ showError(data.error || 'Upload failed'); return; }

    if (data.redirect){

      window.location.href = data.redirect;

    } else {

      showError('Unexpected response from server.');

    }

  } else {

    const fd = new FormData();
    fd.append('file', uploadedFile);
    fd.append('gases', JSON.stringify(selectedGases));

    const res = await fetch('/api/bill_upload', { method:'POST', body: fd });
    const data = await res.json();

    if (!res.ok){ showError(data.error || 'Bill processing failed'); return; }
    if (data.redirect){ window.location.href = data.redirect; }
    else { showError('Unexpected response from server.'); }

  }

});



 // Transport quick form

let currentTransportType = null;

function openTransportForm(type){

  currentTransportType = type;

  document.getElementById('transport_form').style.display = 'block';

  document.getElementById('transport_type').innerText = type.charAt(0).toUpperCase() + type.slice(1);

  document.getElementById('liters_input').value = '';

}

function clearTransportForm(){

  document.getElementById('liters_input').value = '';

}

async function calculateTransport(){

  clearError();

  if (!currentTransportType){ showError('Select Petrol or Diesel first'); return; }

  const v = document.getElementById('liters_input').value.trim();

  if (!v){ showError('Enter liters'); return; }

  const n = Number(v);

  if (isNaN(n) || n <= 0){ showError('Enter a positive number for liters'); return; }

  const rows = [{

    "source_id": "",

    "activity_date": "",

    "activity_type": currentTransportType,

    "quantity": n,

    "unit": "liter",

    "gas": ""

  }];

  const payload = { rows: rows, gases: selectedGases };

  const res = await fetch('/api/process_rows', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });

  const data = await res.json();

  if (!res.ok){ showError(data.error || 'Processing failed'); return; }

  if (data.redirect){

    window.location.href = data.redirect;

  } else {

    showError('Unexpected response from server.');

  }

}

</script>

</body></html>

"""

    selected_display = ', '.join(selected) if selected else 'None'

    return render_template_string(html, selected_display=selected_display,

                                  selected_json=json.dumps(selected), factors=factors, stats=stats)



# API endpoints — they now save the computed result to a file and return a redirect URL



def save_result_and_get_url(result_obj):

    rid = uuid.uuid4().hex

    path = os.path.join(RESULTS_DIR, f"{rid}.json")

    with open(path, "w") as f:

        json.dump(result_obj, f, default=str)

    return f"/results/{rid}"



@app.route("/api/bill_upload", methods=["POST"])
def api_bill_upload():
    """Automatically read an electricity bill PDF/image using local OCR."""
    if "file" not in request.files:
        return jsonify({"error": "No bill file was uploaded."}), 400

    uploaded = request.files["file"]
    filename = os.path.basename(uploaded.filename or "")
    extension = os.path.splitext(filename)[1].lower()
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
    if extension not in allowed:
        return jsonify({"error": "Unsupported file. Upload a PDF, JPG, JPEG, PNG or WEBP file."}), 400

    safe_name = f"{uuid.uuid4().hex}{extension}"
    save_path = os.path.join(UPLOADS_DIR, safe_name)
    uploaded.save(save_path)

    try:
        gases = json.loads(request.form.get("gases") or "[]")
    except (TypeError, ValueError):
        gases = []

    if extension == ".pdf":
        quantity, read_error = extract_kwh_from_pdf(save_path)
    else:
        quantity, read_error = extract_kwh_from_image(save_path)

    if read_error:
        return jsonify({"error": read_error}), 400

    rows = [{
        "source_id": filename,
        "activity_date": datetime.now().strftime("%Y-%m-%d"),
        "activity_type": "electricity",
        "quantity": quantity,
        "unit": "kWh",
        "gas": ""
    }]

    result = process_rows_backend(rows, gases)
    redirect_url = save_result_and_get_url(result)
    return jsonify({"redirect": redirect_url, "message": f"Bill read successfully: {quantity:g} kWh detected."})


@app.route("/api/upload", methods=["POST"])

def api_upload():

    if 'file' not in request.files:

        return jsonify({"error": "no file uploaded"}), 400

    file = request.files['file']

    filename = (file.filename or "").lower()

    if not filename.endswith('.csv'):

        return jsonify({"error": "uploaded file is not a CSV. Upload a PDF or supported bill image using the bill upload option."}), 400

    mapping = request.form.get('mapping') or "{}"

    try:

        mapping = json.loads(mapping)

    except:

        mapping = {}

    gases = request.form.get('gases') or "[]"

    try:

        gases = json.loads(gases)

    except:

        gases = []

    try:

        df = pd.read_csv(file)

    except Exception as e:

        return jsonify({"error": f"failed to parse CSV: {e}"}), 400

    std_df = pd.DataFrame()

    for col in df.columns:

        target = mapping.get(col)

        if target:

            std_df[target] = df[col]

        else:

            low = col.lower()

            if low in ['source_id','id','source']:

                std_df['source_id'] = df[col]

            elif low in ['activity_date','date']:

                std_df['activity_date'] = df[col]

            elif low in ['activity_type','type','activity']:

                std_df['activity_type'] = df[col]

            elif low in ['quantity','qty','amount','consumption','consumption_kwh','kwh','units','units_consumed']:

                std_df['quantity'] = df[col]

            elif low in ['unit','units']:

                std_df['unit'] = df[col]

            elif low in ['gas','ghg','gas_type']:

                std_df['gas'] = df[col]

    for needed in ['activity_date','activity_type','quantity','unit']:

        if needed not in std_df.columns:

            std_df[needed] = None

    rows = []

    for idx, row in std_df.iterrows():

        rows.append({

            "source_id": row.get('source_id', ''),

            "activity_date": row.get('activity_date', ''),

            "activity_type": row.get('activity_type', 'electricity'),

            "quantity": row.get('quantity'),

            "unit": row.get('unit', ''),

            "gas": row.get('gas', '')

        })

    result = process_rows_backend(rows, gases)

    redirect_url = save_result_and_get_url(result)

    return jsonify({"redirect": redirect_url})



@app.route("/api/process_rows", methods=["POST"])

def api_process_rows():

    # Accept JSON body

    data = request.get_json(silent=True)

    if not data:

        return jsonify({"error": "expected JSON body"}), 400

    rows = data.get('rows', [])

    gases = data.get('gases', [])

    result = process_rows_backend(rows, gases)

    redirect_url = save_result_and_get_url(result)

    return jsonify({"redirect": redirect_url})



@app.route("/download_sample")

def download_sample():

    return send_file(SAMPLE_CSV, as_attachment=True)



@app.route("/api/stats")

def api_stats():

    with open(STATS_FILE, "r") as f:

        return jsonify(json.load(f))



# Results page: reads saved JSON and displays chart + details in its own page

@app.route("/results/<rid>")

def results_page(rid):

    path = os.path.join(RESULTS_DIR, f"{rid}.json")

    if not os.path.exists(path):

        return abort(404)

    with open(path, "r") as f:

        result = json.load(f)



    # Render an HTML page with Chart.js using embedded JSON result

    # NOTE: Web view still shows top activities, PDF will include selected mode/gases and inputs

    html = r"""

<!doctype html>

<html>

<head>

  <meta charset="utf-8">

  <title>Results - Carbon Footprint Estimator</title>

  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

  <link href="https://fonts.googleapis.com/css2?family=Inter:wght\@300;400;600;700&display=swap" rel="stylesheet">

  <style>

    body{font-family:Inter,Arial,sans-serif;background:#f6f8fb;padding:20px}

    .container{max-width:1000px;margin:8px auto}

    .card{background:#fff;padding:18px;border-radius:12px;box-shadow:0 12px 30px rgba(11,26,40,0.06);margin-bottom:14px}

    h1{margin:0 0 8px}

    .small{color:#6b7280;font-size:13px}

    .btn{background:#0b3a66;color:#fff;padding:8px 12px;border-radius:8px;border:none;cursor:pointer}

    .row{display:flex;gap:18px;align-items:flex-start}

    .chart-box{width:480px;height:320px}

    .panel{flex:1}

    .muted{color:#6b7280}

    .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}

    .grid .item{background:#f8fafc;padding:10px;border-radius:8px;text-align:center}

    table{width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden}

    thead th{color:#6b7280;padding:12px 10px;background:#fff;text-align:left;font-weight:600}

    tbody td{padding:12px 10px;border-top:1px solid #f1f5f9}

    /* alignment: left for activity, right for numbers */

    .col-activity{width:50%;text-align:left}

    .col-qty{width:15%;text-align:right}

    .col-unit{width:15%;text-align:center}

    .col-co2{width:20%;text-align:right}

    /* responsive */

    @media (max-width:900px){

      .row{flex-direction:column}

      .chart-box{width:100%;height:300px}

    }

  
/* Shared Carbon Footprint theme for every application page */
:root {
    --carbon-navy: #082b43;
    --carbon-blue: #145276;
    --carbon-pale: #dceaf1;
    --carbon-accent: #1976dc;
    --carbon-border: rgba(255,255,255,0.38);
    --carbon-shadow: 0 16px 38px rgba(0, 0, 0, 0.20);
}
html {
    min-height: 100%;
    background: var(--carbon-navy);
}
body {
    min-height: 100vh;
    margin: 0;
    font-family: Inter, Arial, sans-serif;
    background: linear-gradient(135deg, #082b43 0%, #145276 55%, #dceaf1 100%);
    background-repeat: no-repeat;
    background-size: cover;
    background-attachment: fixed;
    color: #102333;
}
.wrap, .container {
    width: min(92%, 1100px);
    margin-left: auto !important;
    margin-right: auto !important;
}
.wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 38px 0;
}
.card, .transport-card {
    background: #fff;
    border: 1px solid rgba(8, 43, 67, 0.16);
    border-radius: 18px;
    box-shadow: var(--carbon-shadow);
}
.container {
    padding-top: 38px;
    padding-bottom: 48px;
}
.container > .card {
    padding: 24px;
    margin-bottom: 18px;
}
.brand-mark {
    width: 70px;
    height: 70px;
    flex: 0 0 70px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 14px;
    border-radius: 19px;
    background: linear-gradient(145deg, #174d70, #0b304a);
    border: 1px solid rgba(255,255,255,0.38);
    box-shadow: 0 9px 22px rgba(0,0,0,0.22);
}
.brand-mark svg {
    width: 49px;
    height: 49px;
}
.wrap > .card {
    width: 100%;
    max-width: 760px;
    padding: 36px;
    text-align: center;
}
.wrap > .card h1 {
    text-align: center;
    color: #0b3a56;
    margin: 0 0 10px;
}
.wrap > .card .lead {
    text-align: center;
}
.checkbox-list {
    max-width: 540px;
    margin: 22px auto 0;
    text-align: left;
}
.ch {
    background: #f7fafc;
    border: 1px solid #dce7ef !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(8,43,67,0.05);
}
.actions {
    justify-content: center;
}
.btn, .btn-primary, button {
    border-radius: 10px;
}
.btn-primary, .btn {
    background: #1976dc;
    box-shadow: 0 6px 16px rgba(25,118,220,0.22);
}
.container > .card.header-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
}
.container > .card.header-row .brand-mark {
    margin: 0 16px 0 0;
}
.container > .card.header-row h1 {
    color: #0b3a56;
}
.container .card, .container .transport-card {
    border: 1px solid rgba(8,43,67,0.14);
    box-shadow: 0 12px 28px rgba(0,0,0,0.14);
}
.container .drop {
    border-radius: 14px;
    border-color: #a9c4d6;
}
.container .transport-card {
    padding: 18px;
    border-radius: 16px;
}
.container table {
    background: #fff;
}
.container .grid .item {
    border: 1px solid #dce7ef;
    border-radius: 12px;
}
@media (max-width: 700px) {
    .wrap { padding: 22px 0; }
    .wrap > .card { padding: 24px 18px; }
    .container { width: 94%; padding-top: 20px; }
    .container > .card { padding: 17px; }
    .container > .card.header-row .brand-mark { margin: 0 auto 12px; }
}

</style>

</head>

<body>

  <div class="container">

    <div class="card">

      <div style="display:flex;justify-content:space-between;align-items:center">

        <div>
<div class="brand-mark page-icon" role="img" aria-label="Emission results chart icon">
  <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M17 15V84H88" fill="none" stroke="#DDF3FF" stroke-width="5" stroke-linecap="round"/>
    <rect x="27" y="55" width="13" height="25" rx="3" fill="#65C8FF"/>
    <rect x="48" y="39" width="13" height="41" rx="3" fill="#54D6A0"/>
    <rect x="69" y="23" width="13" height="57" rx="3" fill="#FFD166"/>
    <path d="M25 43L45 31L59 34L82 12" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M70 12H82V24" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</div>

        <h1>Results</h1></div>

        <div><a class="btn" href="/upload">New calculation</a></div>

      </div>

      <p class="small" id="summary_line">{{summary_line}}</p>



      <div class="row" style="align-items:flex-start">

        <div class="chart-box card" style="padding:12px">

          <canvas id="gasChart" width="480" height="320"></canvas>

        </div>



        <div class="panel card" style="padding:12px">

          <h3 style="margin-top:0">Per-gas totals (kg)</h3>

          <div class="grid" id="per_gas_grid"></div>



          <h3 style="margin-top:6px">Suggestions</h3>

          <div id="suggestions"></div>

          <div style="margin-top:12px">

            <button id="download_pdf" class="btn">Download PDF</button>

          </div>

        </div>

      </div>



      <div class="card" style="margin-top:12px">

        <h4 style="margin-top:0">Top emitting activities</h4>

        <div id="top_activities" class="muted"></div>

      </div>

    </div>

  </div>



<script>

const result = {{result_json|safe}};

document.getElementById('summary_line').innerText = result.summary_line || '';

document.getElementById('suggestions').innerHTML = (result.suggestions || []).map(s=>'<div style="margin-bottom:8px">'+s+'</div>').join('');



// Populate per-gas totals in a grid so every GAS_ORDER appears

const gasOrder = {{gas_order|safe}};

const perGas = result.per_gas_totals_kg || {};

const grid = document.getElementById('per_gas_grid');

gasOrder.forEach(g=>{

  const v = perGas[g] !== undefined ? perGas[g] : 0;

  const div = document.createElement('div');

  div.className = 'item';

  div.innerHTML = '<strong>'+g+'</strong><div style="margin-top:6px;font-weight:600">'+(Math.round(v*1000)/1000)+'</div>';

  grid.appendChild(div);

});



const labels = result.chart_data.labels && result.chart_data.labels.length ? result.chart_data.labels : gasOrder;

const values = result.chart_data.values && result.chart_data.values.length ? result.chart_data.values : labels.map(l => perGas[l] || 0);



const ctx = document.getElementById('gasChart').getContext('2d');

new Chart(ctx, {

  type: 'bar',

  data: {

    labels: labels,

    datasets: [{ label: 'Emissions (kg)', data: values }]

  },

  options: {

    responsive: true,

    maintainAspectRatio: false,

    plugins: { legend: { display: false }, title: { display: true, text: 'Emissions by Gas (kg)' } },

    scales: { y: { beginAtZero: true } }

  }

});



// Render Top activities as a properly aligned table (activity left, numbers right)

const ta = result.top_activities || [];

const el = document.getElementById('top_activities');

if (ta.length){

  let html = '<table><thead><tr>';

  html += '<th class="col-activity">Activity</th>';

  html += '<th class="col-qty">Qty</th>';

  html += '<th class="col-unit">Unit</th>';

  html += '<th class="col-co2">CO2 (kg)</th>';

  html += '</tr></thead><tbody>';

  html += ta.map(r => {

    const activity = r.activity_type || '';

    const qty = (r.quantity !== undefined && r.quantity !== null) ? (Math.round(r.quantity*1000)/1000) : '';

    const unit = r.unit || '';

    const co2 = (r.total_co2_kg !== undefined && r.total_co2_kg !== null) ? (Math.round(r.total_co2_kg*1000)/1000) : 0;

    return `<tr>

      <td class="col-activity">${activity}</td>

      <td class="col-qty">${qty}</td>

      <td class="col-unit">${unit}</td>

      <td class="col-co2">${co2}</td>

    </tr>`;

  }).join('');

  html += '</tbody></table>';

  el.innerHTML = html;

} else {

  el.innerText = 'No activities to show.';

}



document.getElementById('download_pdf').addEventListener('click', async ()=>{

  const canvas = document.getElementById('gasChart');

  const b64 = canvas.toDataURL('image/png');

  const payload = { results: result, chart_base64: b64 };

  const res = await fetch('/download_pdf', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });

  if (!res.ok){

    alert('PDF generation failed');

    return;

  }

  const blob = await res.blob();

  const url = URL.createObjectURL(blob);

  const a = document.createElement('a'); a.href = url; a.download = 'carbon_report.pdf'; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);

});

</script>

</body>

</html>

"""

    # pass gas order so template JS knows authoritative order

    return render_template_string(html, result_json=json.dumps(result), summary_line=result.get("summary_line",""), gas_order=json.dumps(GAS_ORDER))



@app.route("/download_pdf", methods=["POST"])

def download_pdf():

    """

    Improved PDF generation using ReportLab Platypus (Table/Paragraph) for consistent alignment.

    This version prints the selected mode/gases (if present) under the run date and also

    includes the manual/input rows used to compute the results.

    """

    data = request.get_json()

    if not data:

        return jsonify({"error": "expected JSON body"}), 400

    results = data.get("results")

    chart_b64 = data.get("chart_base64", "")

    if not results:

        return jsonify({"error": "missing results"}), 400



    # prepare chart image if provided

    img_reader = None

    if chart_b64 and chart_b64.startswith("data:image"):

        header, encoded = chart_b64.split(",", 1)

        try:

            img_bytes = base64.b64decode(encoded)

            if PIL_AVAILABLE:

                im = PILImage.open(io.BytesIO(img_bytes)).convert("RGBA")

                bg = PILImage.new("RGB", im.size, (255,255,255))

                bg.paste(im, mask=im.split()[3] if im.mode == 'RGBA' else None)

                out_buf = io.BytesIO()

                bg.save(out_buf, format="PNG")

                out_buf.seek(0)

                img_reader = out_buf

            else:

                img_reader = io.BytesIO(img_bytes)

        except Exception:

            img_reader = None



    buf = io.BytesIO()

    doc = SimpleDocTemplate(buf, pagesize=A4,

                            rightMargin=36, leftMargin=36,

                            topMargin=36, bottomMargin=36)



    styles = getSampleStyleSheet()

    normal = styles["Normal"]

    h1 = ParagraphStyle('Heading1', parent=styles['Heading1'], fontSize=16, spaceAfter=6)

    h2 = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=12, spaceAfter=6)

    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#444444"))



    story = []



    # Header

    story.append(Paragraph("Carbon Footprint Estimator - Report", h1))

    story.append(Paragraph(f"Run date: {datetime.utcnow().isoformat()}", small))



    # show selected mode/gases (if present in the results)

    sel = results.get("selected_gases")

    if sel:

        if isinstance(sel, (list, tuple)):

            sel_txt = ", ".join(str(x) for x in sel)

        else:

            sel_txt = str(sel)

        story.append(Paragraph(f"Selected mode / gases: {sel_txt}", small))



    # show the input rows (manual entries) if present

    input_rows = results.get("input_rows", [])

    if input_rows:

        story.append(Spacer(1, 4))

        story.append(Paragraph("Inputs used (manual / typed entries):", h2))

        # Build table

        data_tbl = [["Activity", "Qty", "Unit", "Gas"]]

        for r in input_rows:

            act = r.get("activity_type", "")

            qty = r.get("quantity", "")

            unit = r.get("unit", "")

            gas = r.get("gas", "")

            # format qty numeric if possible

            try:

                qty_s = f"{float(qty):.3f}"

            except Exception:

                qty_s = str(qty)

            data_tbl.append([act, qty_s, unit, gas])

        col_w = [70*mm, 30*mm, 30*mm, 30*mm]

        inputs_table = Table(data_tbl, colWidths=col_w, hAlign='LEFT')

        inputs_table.setStyle(TableStyle([

            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f2f5f8")),

            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),

            ('ALIGN', (1,1), (1,-1), 'RIGHT'),

            ('ALIGN', (2,1), (2,-1), 'CENTER'),

            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),

            ('INNERGRID', (0,0), (-1,-1), 0.25, colors.HexColor("#e6eef5")),

            ('BOX', (0,0), (-1,-1), 0.25, colors.HexColor("#e6eef5")),

            ('LEFTPADDING', (0,0), (-1,-1), 6),

            ('RIGHTPADDING', (0,0), (-1,-1), 6),

            ('TOPPADDING', (0,0), (-1,-1), 6),

            ('BOTTOMPADDING', (0,0), (-1,-1), 6),

        ]))

        story.append(inputs_table)



    story.append(Spacer(1, 6))



    # Summary line

    story.append(Paragraph(results.get("summary_line", "Summary"), styles['Heading3']))

    story.append(Spacer(1, 8))



    # Chart image (if available)

    if img_reader:

        try:

            # scale to page width keeping aspect ratio

            img = RLImage(img_reader)

            max_width = A4[0] - doc.leftMargin - doc.rightMargin

            img.drawWidth = max_width

            # keep aspect ratio roughly 0.4 height if not defined

            img.drawHeight = max_width * 0.4

            story.append(img)

            story.append(Spacer(1, 10))

        except Exception:

            pass



    # Per-gas totals table (single-row key/value layout)

    story.append(Paragraph("Per-gas totals (kg):", h2))

    per_gas = results.get("per_gas_totals_kg", {})

    # Build two-column table per gas for nicer alignment

    gas_rows = []

    row = []

    for g in GAS_ORDER:

        v = per_gas.get(g, 0.0)

        row.append(Paragraph(f"<b>{g}</b>", normal))

        row.append(Paragraph(f"{v:.3f}", ParagraphStyle('num', parent=normal, alignment=2)))  # right aligned

        # if two cols filled push as row of four cells (label,val,label,val)

        if len(row) == 4:

            gas_rows.append(row)

            row = []

    if row:

        # pad remaining columns

        while len(row) < 4:

            row.append(Paragraph("", normal))

        gas_rows.append(row)



    tbl = Table(gas_rows, colWidths=[60*mm, 30*mm, 60*mm, 30*mm])

    tbl.setStyle(TableStyle([


        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),

        ('ALIGN', (1,0), (1,-1), 'RIGHT'),

        ('ALIGN', (3,0), (3,-1), 'RIGHT'),

        ('LEFTPADDING', (0,0), (-1,-1), 6),

        ('RIGHTPADDING', (0,0), (-1,-1), 6),

    ]))

    story.append(tbl)

    story.append(Spacer(1, 10))



    # Suggestions

    story.append(Paragraph("Suggestions", h2))

    for s in results.get("suggestions", []):

        story.append(Paragraph(f"• {s}", normal))

    story.append(Spacer(1, 10))


    # Build PDF

    try:

        doc.build(story)

    except Exception:

        # fallback: return an empty PDF-like blob

        buf = io.BytesIO()

        c = canvas.Canvas(buf, pagesize=A4)

        c.drawString(50, 800, "Failed to generate formatted PDF.")

        c.showPage()

        c.save()

        buf.seek(0)

        return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='carbon_report.pdf')



    buf.seek(0)

    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='carbon_report.pdf')



if __name__ == "__main__":

    port = int(os.environ.get("PORT", "5000"))
    print(f"Starting Carbon Footprint Estimator on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
