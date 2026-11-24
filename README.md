# 🌱 Carbon Footprint Estimator

### Estimate. Analyze. Reduce Your Carbon Emissions.

The **Carbon Footprint Estimator** is a web-based application developed using Python and Flask to estimate greenhouse gas emissions from daily activities and electricity consumption.

The application allows users to upload activity data through CSV files or electricity bill images, calculate emissions for selected greenhouse gases, analyze the results through visualizations, and generate downloadable PDF reports.

---

## 🌍 Project Overview

Carbon emissions from electricity consumption, transportation, and other activities contribute to environmental pollution and climate change.

This project provides a simple and interactive platform to estimate carbon emissions, understand the contribution of different activities, identify emission levels, and receive suggestions for reducing environmental impact.

## ✨ Key Features

- **Greenhouse Gas Selection:** Select the gases to include in emission calculations.
- **CSV Data Upload:** Upload activity data in CSV format for automatic processing.
- **Electricity Bill OCR:** Upload electricity bill images and extract relevant consumption information using Optical Character Recognition (OCR).
- **Transportation Analysis:** Manually enter petrol and diesel consumption to estimate vehicle-related emissions.
- **Emission Calculation:** Calculate emissions using configurable activity-based emission factors.
- **Multiple Gas Analysis:** Calculate emissions for CO₂, CH₄, N₂O and SO₂.
- **Emission Classification:** Classify the estimated carbon footprint into Low, Medium and High categories.
- **Data Visualization:** Display emission analysis through interactive charts.
- **Top Emitting Activities:** Identify activities contributing the most to total emissions.
- **Personalized Suggestions:** Provide recommendations based on the estimated emission category.
- **PDF Report Generation:** Generate and download detailed emission analysis reports.
- **Statistics Tracking:** Maintain calculation statistics and average footprint information.
- **Responsive Interface:** User-friendly interface with a consistent design across application pages.

---

## 🛠️ Technologies Used

| Category | Technologies |
|---|---|
| Programming Language | Python |
| Backend Framework | Flask |
| Frontend | HTML, CSS, JavaScript |
| Data Processing | Pandas |
| Data Visualization | Chart.js |
| Optical Character Recognition | Tesseract OCR, Pytesseract |
| Image Processing | Pillow |
| PDF Generation | ReportLab |
| Data Storage | JSON and CSV |
| Development Environment | Visual Studio Code |
| Version Control | Git and GitHub |

---

## 🧪 Greenhouse Gases Considered

The application supports the selection and calculation of the following gases:

| Gas | Name |
|---|---|
| CO₂ | Carbon Dioxide |
| CH₄ | Methane |
| N₂O | Nitrous Oxide |
| SO₂ | Sulphur Dioxide |

The application uses configurable emission factors and Global Warming Potential (GWP) values to calculate CO₂-equivalent emissions.

---

## ⚙️ How the Project Works

1. **Choose Greenhouse Gases:** Select the gases to include in the calculation.
2. **Upload Input Data:** Upload a CSV file or an electricity bill image.
3. **Extract and Process Data:** Read the uploaded information and extract the required activity details.
4. **Select Transportation Data:** Optionally enter petrol or diesel consumption manually.
5. **Calculate Emissions:** Apply the configured emission factors to the activity quantities.
6. **Calculate CO₂ Equivalent:** Convert individual gas emissions using their GWP values.
7. **Classify Emission Levels:** Categorize the total estimated footprint as Low, Medium or High.
8. **Visualize Results:** Display charts, gas-wise emissions and top contributing activities.
9. **Generate PDF Report:** Download the calculated results as a PDF report.

---

## 📂 Project Structure

```text
Carbon_Footprint_Estimator/
│
├── app.py
│
├── emission_factors.json
│
├── sample.csv
│
├── stats.json
│
├── uploads/
│   └── Uploaded bill images
│
├── results/
│   └── Generated result JSON files
│
├── requirements.txt
│
├── .gitignore
│
└── README.md
```

---

## 📊 CSV Dataset Format

The application accepts activity data in CSV format.

The recommended column structure is:

| Column | Description | Example |
|---|---|---|
| source_id | Unique activity identifier | A1 |
| activity_date | Date of activity | 2025-01-10 |
| activity_type | Type of activity | electricity |
| quantity | Activity quantity | 150 |
| unit | Measurement unit | kWh |
| gas | Greenhouse gas (optional) | CO2 |

### Sample CSV Data

```csv
source_id,activity_date,activity_type,quantity,unit,gas
A1,2025-01-10,electricity,150,kWh,CO2
A2,2025-01-12,diesel,50,liter,CO2
A3,2025-01-15,fertilizer,10,kg,N2O
```

You can also download the sample CSV directly from the application.

---

## 🚀 Installation and Setup

### Prerequisites

Make sure the following are installed:

- Python 3
- Visual Studio Code
- Git
- Tesseract OCR (required for electricity bill image extraction)

### Step 1: Clone the Repository

```bash
git clone https://github.com/Yadunandan522005/Carbon_Footprint_Estimator.git
```

### Step 2: Navigate to the Project Folder

```bash
cd Carbon_Footprint_Estimator
```

### Step 3: Create a Virtual Environment

```bash
python -m venv venv
```

### Step 4: Activate the Virtual Environment

**Windows:**

```powershell
venv\Scripts\activate
```

### Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 6: Configure Tesseract OCR

Install Tesseract OCR separately on your system.

Install the Python OCR library:

```bash
pip install pytesseract pillow
```

Make sure the Tesseract executable is available in your system PATH or configure its executable location in the Python application.

OCR functionality requires Tesseract to be installed correctly.

### Step 7: Run the Application

```bash
python app.py
```

### Step 8: Open in Browser

Visit:

```text
http://127.0.0.1:5000/
```

The Carbon Footprint Estimator application will be available locally.

---

## 📈 Emission Calculation

The application calculates emissions using activity-based emission factors.

**Basic emission calculation:**

```text
Gas Emission (kg) =
Activity Quantity × Emission Factor
```

**CO₂ Equivalent Calculation:**

```text
Total CO₂ Equivalent =
Σ (Individual Gas Emissions × GWP)
```

The emission factors and GWP values are maintained in `emission_factors.json` and can be configured according to the selected methodology and data source.

---

## 📄 PDF Report

After completing the calculation, users can generate a downloadable PDF report containing relevant emission analysis, including:

- Total estimated CO₂-equivalent emissions.
- Gas-wise emission information.
- Emission classification.
- Activity-wise analysis.
- Recommendations for emission reduction.

---

## 🎯 Project Objectives

- Develop a user-friendly carbon footprint estimation application.
- Estimate greenhouse gas emissions from different activities.
- Simplify electricity consumption analysis through image-based OCR.
- Analyze transportation-related fuel consumption.
- Visualize emission contributions through interactive charts.
- Help users understand their environmental impact.
- Encourage sustainable practices through actionable recommendations.

---

## 🌱 Sustainable Development Goals (SDGs)

This project supports the following United Nations Sustainable Development Goals:

- **SDG 7 – Affordable and Clean Energy:** Encourages awareness of energy consumption and cleaner energy alternatives.
- **SDG 11 – Sustainable Cities and Communities:** Promotes awareness of sustainable transportation and resource usage.
- **SDG 12 – Responsible Consumption and Production:** Encourages responsible energy and resource consumption.
- **SDG 13 – Climate Action:** Supports carbon emission awareness and climate-conscious decision-making.

---

## 🔮 Future Enhancements

- Integration with real-time electricity consumption data.
- Advanced emission forecasting using Machine Learning.
- Location-based emission factor selection.
- Expanded transportation categories.
- Historical emission comparison and trend analysis.
- User accounts and personalized dashboards.
- Enhanced OCR accuracy for different electricity bill formats.
- Cloud deployment and database integration.
