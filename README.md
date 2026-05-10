# TALASH – Smart HR Recruitment

Automated CV analysis system built with Streamlit, Groq (Llama 3), and Claude AI.

## Prerequisites

- Python 3.9+
- A Groq API key → https://console.groq.com
- An Anthropic API key → https://console.anthropic.com

## Setup & Run

**1. Clone the repository**
```bash
git clone https://github.com/abdullahjanjuas/talash.git
cd talash
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Add your API keys**

Modify the `.env.example` file and rename to `.env`:

**4. Run the app**
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

## Usage

1. Go to **Upload CV** → upload a PDF → click **Process CV**
2. View results under **All Candidates** or **Candidate Detail**
3. Export data as CSV or Excel from **Export Data**