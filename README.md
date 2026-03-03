# 🇧🇷 CNPJ Bulk Lookup

A Streamlit app that queries the [cnpj.ws](https://www.cnpj.ws) API in bulk, extracting company data (name, address, tax registration, IE, contacts, etc.) for up to 1,000 CNPJs at once.

---

## 📁 Project Structure

```
cnpj_bulk/
├── app.py              # Streamlit UI
├── cnpj_client.py      # API logic & data parsing
├── requirements.txt    # Python dependencies
├── render.yaml         # Render deployment config
└── .streamlit/
    └── config.toml     # Theme & server settings
```

---

## 🚀 Running Locally (VS Code)

### 1. Prerequisites
- Python 3.10+
- pip

### 2. Clone / open folder in VS Code
```bash
cd cnpj_bulk
```

### 3. Create virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the app
```bash
streamlit run app.py
```
App opens at **http://localhost:8501**

---

## 🌐 Deploy to Render

1. Push this folder to a **GitHub repository**

2. Go to [render.com](https://render.com) → **New Web Service**

3. Connect your GitHub repo

4. Render auto-detects `render.yaml` — click **Deploy**

5. Your app will be live at `https://your-app-name.onrender.com`

> **Free tier note:** Render free services spin down after inactivity. Upgrade to Starter ($7/mo) for always-on.

---

## 🔑 API Key

The free cnpj.ws tier allows **3 requests/minute**.

For paid plans with higher limits:
- Get your key at [cnpj.ws](https://www.cnpj.ws)
- Paste it in the **sidebar → API Key** field in the app

---

## 📊 Data Extracted

| Field | Description |
|---|---|
| CNPJ | Formatted tax ID |
| Razão Social | Legal company name |
| Nome Fantasia | Trade name |
| Situação Cadastral | Active / Inactive / etc. |
| Data Início Atividade | Opening date |
| Tipo | MATRIZ or FILIAL |
| Porte | Company size |
| Natureza Jurídica | Legal nature |
| Capital Social | Share capital |
| Estado / Cidade / CEP | Address fields |
| Email / Telefone | Contact info |
| IE UF + Número | State tax registration |
| Simples Nacional / MEI | Tax regime flags |
| Sócios | Partners list |

---

## ⚙️ Rate Limiting Strategy

- **Free tier:** 3 req/min → set delay to min 1.5s, max 3.5s
- **Paid tier:** 2,000 req/min → you can lower delays significantly
- The app adds a **random jitter** between requests to avoid patterns
- **Automatic retry** with exponential backoff on failures (429, timeout, errors)

---

## 📤 Export

Results export to:
- **CSV** (semicolon-separated, UTF-8 BOM for Excel compatibility)
- **Excel** (`.xlsx`) with a second sheet for failed CNPJs

---

## 🐛 Troubleshooting

| Issue | Fix |
|---|---|
| `429 Too Many Requests` | Increase delay sliders in sidebar |
| `CNPJ not found` | CNPJ may not exist or be very new |
| App slow on Render | Normal on free tier; upgrade for speed |
| Excel shows garbled text | Use CSV with UTF-8-BOM encoding |
