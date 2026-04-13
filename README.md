# Talash

Talash is a Streamlit-based application for parsing and analyzing CVs.

## How to Run the App

### 1. Clone the Repository
```bash
git clone https://github.com/abdullahjanjuas/talash.git
cd talash
```

### 2. Create Virtual Environment (Recommended)
```bash
python -m venv venv
```

Activate the environment:

- **macOS/Linux**
```bash
source venv/bin/activate
```

- **Windows**
```bash
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Streamlit App
```bash
streamlit run app.py
```

### 5. Open in Browser
After running, open the URL shown in the terminal (usually):

```
http://localhost:8501
```

---

## Notes
- Make sure you have Python 3.9+ installed
- If you face issues with `fitz` (PyMuPDF), reinstall it:
  ```bash
  pip install pymupdf
  ```

---

## Requirements
All dependencies are listed in `requirements.txt`.
