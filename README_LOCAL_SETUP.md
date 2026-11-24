# Local setup – automatic electricity bill reading

This version automatically reads the kWh value from electricity bill images and PDFs using **local Tesseract OCR**. It does not require OCR.space, an API key, or manual kWh entry.

## Windows: one-time OCR engine installation

1. Install the free Tesseract OCR for Windows from the UB Mannheim distribution: https://github.com/UB-Mannheim/tesseract/wiki
2. During installation, include the English language data.
3. The usual install path is `C:\Program Files\Tesseract-OCR\tesseract.exe`. The app detects this path automatically. If you installed it elsewhere, add its folder to Windows PATH and restart VS Code.

## Run the Flask app

Open PowerShell in the folder containing `app.py` and `requirements.txt`, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. Select the gases, upload a clear electricity bill JPG/PNG/WEBP or PDF, and click Calculate. The app extracts a number explicitly labelled kWh and uses it for the existing emissions calculation.

## Important limitations

- OCR quality depends on bill clarity, resolution, orientation, and language. English bills are best supported by the default setup.
- If the bill has several kWh values, the app uses the last clearly labelled kWh value it finds. Always compare the result with the bill.
- This local Tesseract setup is for running on your Windows computer. Vercel does not automatically include the Tesseract executable; a separate serverless OCR deployment setup is needed before deploying this exact OCR feature to Vercel.
