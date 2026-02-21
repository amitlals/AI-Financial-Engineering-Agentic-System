# CFO Financial Insight Dashboard — AI-Driven Financial Engineering Agentic System

## Overview

This repository provides a structured framework for an **AI-driven financial engineering and market analysis agentic system** using **Azure AI Agent Service SDK / Microsoft Agent Framework**. It includes:

- A Gradio dashboard that blends SAP (ES5 demo) data, simulated Salesforce pipeline, and business news
- Multi-agent architecture for CFO-ready insights and strategy options
- Structured Python project with required dependencies
- Configuration file templates (`.env`)
- Step-by-step setup guide

---

## 🤖 AI Agents Overview - Microsoft Agent Framework with Azure OpenAI

The system incorporates multiple AI-driven agents specialized in different aspects of financial and market analysis:

![image](https://github.com/user-attachments/assets/7d8ba4bd-84b0-4458-90a5-dd835faab8d4)

Behind the scene multi-agent orchestration in play:

<img width="962" alt="image" src="https://github.com/user-attachments/assets/93990da8-b6eb-4c12-ad4c-3d9cabaadf81" />

### **Agent Architecture**

| Agent Name | Role |
|------------|------|
| 🌐 **market-intelligence-agent** | Analyzes market trends, news sentiment, customer pipeline, and currency exposure |
| 💰 **finance-pulse-agent** | Evaluates SAP financial health, customer/product signals, and performance metrics |
| ⚠️ **risk-monitor-agent** | Surfaces liquidity, compliance, and volatility risks across the dataset |
| 📊 **cfo-strategist** | Fuses specialist reports into three actionable strategy options |
| 📋 **board-briefing-agent** | Produces a board-ready narrative with executive summary |

### **Agent Flows**

1. **Market Analysis Agent** → Analyzes market trends, customer behavior, geographic demand
2. **Financial Analysis Agent** → Evaluates financials, balance sheets, cost efficiency
3. **Risk Monitor Agent** → Identifies compliance, liquidity, and exposure risks
4. **Strategic Planning Agent** → Develops three unique business strategies with implementation roadmaps
5. **Board Briefing Agent** → Creates executive-ready narrative for board distribution

---

## 📂 Project Structure

```
📦 Stock-Analysis-AutoGen-Multi-Agent
 ┣ 📜 sap-finance-analysis-withUI-8-FINAL-ES5-FINAL_AgentFramework.py  # Main dashboard app
 ┣ 📜 requirements.txt  # Dependencies
 ┣ 📜 .env.example  # Environment variables template
 ┣ 📜 README-financeagents.md  # This documentation
 ┗ 📜 LICENSE  # License file
```

---

## 🔧 Prerequisites

- **OS:** Windows / macOS / Linux
- **Python:** 3.10 or newer
- **Graphviz:** Required for the flow diagram (`dot` must be on PATH)
- **Azure OpenAI:** Chat deployment (GPT-4 recommended)
- **Azure Logic App:** For email automation (see setup below)
- **Optional:** Currents API Key for latest news
- **SAP ES5 demo credentials** (or your SAP OData endpoint)

---

## 🔧 Setup Instructions

### 1️⃣ Clone Repository

```bash
git clone https://github.com/amitlals/Stock-Analysis-AutoGen-Multi-Agent.git
cd Stock-Analysis-AutoGen-Multi-Agent
```

### 2️⃣ Setup Python Virtual Environment

```bash
python -m venv venv

# For Mac/Linux
source venv/bin/activate

# For Windows PowerShell
.\venv\Scripts\Activate
```

### 3️⃣ Install Dependencies

```bash
pip install -U pip setuptools wheel
pip install -r requirements.txt
```

**If requirements.txt is missing, install core libs:**
```bash
pip install gradio plotly pandas requests python-dotenv graphviz pydantic urllib3 openai
```

### 4️⃣ Microsoft Agent Framework Dependency

> ⚠️ **Note:** This version uses `agent-framework`, a Microsoft internal/preview SDK.

**Option A: If you have access to the package:**
```bash
pip install agent-framework
```

**Option B: If `agent-framework` is unavailable:**

See the [standard OpenAI SDK version](https://github.com/amitlals/AI-Financial-Engineering-Agentic-System) which uses the `openai` package directly:
```bash
pip install openai
```

### 5️⃣ Install Graphviz (for flow diagrams)

- **Windows:** Download from [graphviz.org](https://graphviz.org/download/) and add to PATH
- **macOS:** `brew install graphviz`
- **Linux:** `sudo apt-get install graphviz`

### 6️⃣ Set Up Environment Variables

Create a `.env` file in the project root:

```ini
# .env

# SAP Connection
SAP_USERNAME=your_sap_user
SAP_PASSWORD=your_sap_password
SAP_BASE_URL=https://sapes5.sapdevcenter.com/sap/opu/odata/IWBEP/GWSAMPLE_BASIC
SAP_CLIENT=002

# News API (optional; if unset, news is skipped)
CURRENTS_API_KEY=your_currents_api_key

# Azure OpenAI / Microsoft Agent Framework
API_KEY=your_azure_openai_api_key
AZURE_ENDPOINT=https://your-resource-name.openai.azure.com
MODEL_DEPLOYMENT_NAME=gpt-4
MODEL_API_VERSION=2024-10-21

# Email dispatch via Logic App (Options tab)
LOGICAPP_ENDPOINT=https://your-logicapp-url
EMAIL_RECIPIENT=recipient@example.com
```

---

## 📧 Azure Logic App Setup (Email Automation)

The dashboard uses an Azure Logic App to send strategy option emails. Follow these steps to create and configure it:

### 1️⃣ Create a New Logic App

1. Go to [Azure Portal](https://portal.azure.com)
2. Click **Create a resource** → Search for **Logic App**
3. Click **Create** and fill in:
   - **Subscription:** Your Azure subscription
   - **Resource Group:** Create new or select existing
   - **Logic App name:** `cfo-email-dispatcher` (or your choice)
   - **Region:** Select your preferred region
   - **Plan type:** **Consumption** (pay-per-execution) recommended for testing
4. Click **Review + create** → **Create**
5. Wait for deployment, then click **Go to resource**

### 2️⃣ Design the Logic App Workflow

1. In your Logic App, click **Logic app designer** (or **Edit** if prompted)
2. Select **Blank Logic App** template

#### Step A: Add HTTP Trigger

1. Search for **HTTP** → Select **When a HTTP request is received**
2. Click **Use sample payload to generate schema**
3. Paste this sample JSON:
   ```json
   {
     "Recipient": "user@example.com",
     "Subject": "CFO Strategy Pick: Option 1",
     "Body": "<html><body><h1>Strategy Details</h1></body></html>"
   }
   ```
4. Click **Done** — the schema auto-generates
5. Set **Method** to `POST`

#### Step B: Add Send Email Action

**Option A: Using Office 365 Outlook**

1. Click **+ New step**
2. Search for **Office 365 Outlook** → Select **Send an email (V2)**
3. Sign in with your Microsoft 365 account when prompted
4. Configure the action:
   - **To:** Click in field → **Dynamic content** → Select `Recipient`
   - **Subject:** Click in field → **Dynamic content** → Select `Subject`
   - **Body:** Click in field → **Dynamic content** → Select `Body`
   - Toggle **Is HTML** to `Yes`

**Option B: Using SendGrid (Alternative)**

1. Click **+ New step**
2. Search for **SendGrid** → Select **Send email (V4)**
3. Connect with your SendGrid API key
4. Configure similarly with dynamic content

**Option C: Using Gmail**

1. Click **+ New step**
2. Search for **Gmail** → Select **Send email (V2)**
3. Sign in with your Google account
4. Configure with dynamic content

#### Step C: Add Response Action

1. Click **+ New step**
2. Search for **Response** → Select **Response**
3. Configure:
   - **Status Code:** `200`
   - **Body:** `{"status": "Email sent successfully"}`

### 3️⃣ Save and Get the Endpoint URL

1. Click **Save** in the designer toolbar
2. Go back to the **HTTP trigger** step
3. Copy the **HTTP POST URL** — it looks like:
   ```
   https://prod-xx.eastus.logic.azure.com:443/workflows/abc123.../triggers/manual/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers...
   ```
4. Add this URL to your `.env` file:
   ```ini
   LOGICAPP_ENDPOINT=https://prod-xx.eastus.logic.azure.com:443/workflows/...
   ```

### 4️⃣ Complete Logic App Workflow Diagram

```
┌─────────────────────────────────────────────────────────┐
│  When a HTTP request is received                        │
│  ├─ Method: POST                                        │
│  └─ Schema: { Recipient, Subject, Body }                │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Send an email (V2) - Office 365 Outlook                │
│  ├─ To: @{triggerBody()?['Recipient']}                  │
│  ├─ Subject: @{triggerBody()?['Subject']}               │
│  ├─ Body: @{triggerBody()?['Body']}                     │
│  └─ Is HTML: Yes                                        │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  Response                                               │
│  ├─ Status Code: 200                                    │
│  └─ Body: {"status": "Email sent successfully"}         │
└─────────────────────────────────────────────────────────┘
```

### 5️⃣ Test the Logic App

**From Azure Portal:**
1. Click **Run Trigger** → **Run with payload**
2. Enter test JSON:
   ```json
   {
     "Recipient": "your-email@example.com",
     "Subject": "Test Email from Logic App",
     "Body": "<h1>Hello!</h1><p>This is a test.</p>"
   }
   ```
3. Click **Run** and check your inbox

**From Command Line (curl):**
```bash
curl -X POST "YOUR_LOGIC_APP_URL" \
  -H "Content-Type: application/json" \
  -d '{"Recipient":"your-email@example.com","Subject":"Test","Body":"<p>Test</p>"}'
```

**From PowerShell:**
```powershell
$body = @{
    Recipient = "your-email@example.com"
    Subject = "Test Email"
    Body = "<h1>Test</h1>"
} | ConvertTo-Json

Invoke-RestMethod -Uri "YOUR_LOGIC_APP_URL" -Method Post -Body $body -ContentType "application/json"
```

### 6️⃣ Troubleshooting Logic App

| Issue | Solution |
|-------|----------|
| **HTTP 400 Bad Request** | Check JSON schema matches exactly: `Recipient`, `Subject`, `Body` (case-sensitive) |
| **HTTP 401 Unauthorized** | Regenerate the trigger URL or check access policies |
| **HTTP 404 Not Found** | Verify the Logic App URL is correct and the app is enabled |
| **Email not received** | Check spam folder; verify Office 365 connection is authorized |
| **Connection expired** | Go to Logic App → API Connections → Reauthorize the email connector |

### 7️⃣ Security Best Practices

- ⚠️ **Never commit the Logic App URL** to version control — treat it as a secret
- 🔒 Consider adding **IP restrictions** in Logic App settings for production
- 🔑 Use **Azure Key Vault** to store the endpoint URL in production environments
- 📋 Enable **diagnostic logging** in Logic App for monitoring

---

## 📜 Azure AI Agent Service SDK Setup

### 1️⃣ Install Azure SDK

```bash
pip install azure-ai-agent-sdk
```

### 2️⃣ Authenticate and Set Up Azure Service

```bash
# Log in to Azure CLI
az login

# Set your subscription
az account set --subscription "<your-subscription-id>"

# Deploy AI Agent Service (optional)
az ai agent create --name StockAnalysisAgent --resource-group your-resource-group --location eastus --sku Standard
```

### 3️⃣ Retrieve API Key

Store your **Azure OpenAI API Key** in `.env` as `API_KEY`.

---

## 🚀 Running the Project

```bash
python sap-finance-analysis-withUI-8-FINAL-ES5-FINAL_AgentFramework.py
```

The app launches at **http://127.0.0.1:7860**

### Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **Performance & Analysis** | KPIs, SAP/SF charts, headline table, AI insights |
| **Strategic Options & Dispatch** | AI-generated options + email dispatch via Logic App |
| **System Flow** | Click to generate agents data-flow diagram (Graphviz) |

### What Happens on Refresh

1. ✅ Connects to SAP ES5 & fetches orders/products data
2. ✅ Retrieves market & financial news
3. ✅ Generates simulated Salesforce pipeline data
4. ✅ Processes data into structured insights
5. ✅ Utilizes 5 AI agents for market, financial & risk analysis
6. ✅ Generates three strategic recommendations
7. ✅ Produces board-ready narrative

### Email Dispatch Flow

1. Select a strategy option (Option 1, 2, or 3)
2. Click **Confirm & Dispatch**
3. The app sends a POST request to your Logic App
4. Logic App sends a formatted HTML email to the configured recipient
5. Confirmation message appears in the dashboard

---

## ✅ Requirements (`requirements.txt`)

```txt
# Core dependencies
requests>=2.31.0
urllib3>=2.0.0
python-dotenv>=1.0.0

# UI Framework
gradio>=4.0.0

# Data & Visualization
pandas>=2.0.0
plotly>=5.18.0
pydantic>=2.0.0

# Diagram Generation
graphviz>=0.20.0

# Azure OpenAI
openai>=1.3.0

# Microsoft Agent Framework (if available)
# agent-framework>=0.1.0
```

---

## 🛠️ Agent Framework Behavior (Structured Output)

- The code uses **Microsoft Agent Framework** (`agent-framework`) with `AzureOpenAIChatClient`
- Because some Azure chat models do not support JSON schema `response_format`, agents are prompted to reply with **raw JSON only**
- A tolerant parser:
  - Extracts JSON from code fences or prose
  - Unwraps extra root keys
  - Coerces fields (severity, horizon, confidence)
  - Fills defaults where needed
- Specialist outputs are merged by the **cfo-strategist** into `StrategyResponseModel`
- The **board-briefing-agent** produces a `BoardNarrativeModel`

---

## 🔌 SAP Connectivity Notes

- The demo endpoint often omits a CSRF token for GETs
- Warnings like *"Proceeding to fetch … without CSRF token"* are expected for read-only calls
- If needed:
  - Confirm `SAP_BASE_URL` and `SAP_CLIENT` are correct
  - Increase timeouts or disable SSL verification only in trusted/dev environments

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **HTTP 400: Invalid parameter 'response_format'** | Ensure you're running the updated v8 AgentFramework file |
| **Non-structured payload warnings** | Reduce agent temperature (0.05–0.2) or tighten prompts |
| **Pandas deprecation warning for 'M'** | Addressed by using 'ME' (month-end) in `simulate_sales_trend` |
| **Graphviz error (dot not found)** | Install Graphviz and ensure `dot` is on your PATH |
| **SAP CSRF warnings** | Safe to ignore if data loads; expected for read-only demo calls |
| **agent-framework not found** | Use the standard `openai` package version instead |
| **Email dispatch failed** | Check Logic App URL, verify JSON schema, test Logic App directly |

---

## ⚙️ Configuration Tips

- **Model selection:** Use GPT-4 or capable Azure OpenAI chat model for reasoning and JSON generation
- **Temperature:** If structured responses are inconsistent, lower temperature (0.05–0.2)
- **Environment isolation:** Keep this project in a clean venv to avoid library conflicts
- **Logs:** Review console logs for agent prompts/issues and SAP fetch diagnostics

---

## 🔧 Extending the Agents

- **Add new agents:** Mirror the specialist agent pattern; return `AgentInsightReport` JSON
- **Connect real Salesforce/ERP:** Replace simulated fetch with your API calls
- **Adjust UI:** Modify the option renderer to emphasize owner or confidence thresholds

---

## 🔒 Security

- ⚠️ **Do not commit `.env` files** — Treat API keys and credentials as secrets
- ⚠️ **Do not commit Logic App URLs** — They contain embedded authentication
- ⚠️ **Scrub sensitive data** before exporting or sharing screenshots
- ⚠️ **Add `.env` to `.gitignore`**

---

## 📋 Quick Commands (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
pip install gradio plotly pandas requests python-dotenv graphviz pydantic openai
python sap-finance-analysis-withUI-8-FINAL-ES5-FINAL_AgentFramework.py
```

---

## 🏁 Next Steps

- **Enhance AI Agents:** Add working-capital or liquidity agents for deeper analysis
- **Expand Data Sources:** Integrate stock market APIs for real-time analytics
- **Deploy on Azure:** Use Azure Functions or containerized service for production
- **Connect Real Systems:** Replace simulated Salesforce with actual CRM integration
- **Add Approval Workflow:** Extend Logic App with Microsoft Teams approval before email

---
## 📝 Citation

If you use this project in your research or work, please cite:
```bibtex
@article{lal2025aiagents,
  title={A Survey of AI Agent Architectures in Enterprise SAP Ecosystems},
  author={Lal, Amit},
  year={2025},
  publisher={TechRxiv},
  note={Preprint}
}
```
```bibtex
@article{lal2025rpt1,
  title={Evaluating SAP RPT-1 for Enterprise Business Process Prediction},
  author={Lal, Amit},
  year={2025},
  publisher={TechRxiv},
  note={Preprint}
}
```
```bibtex
@book{lal2024ai2040,
  title={AI in 2040},
  author={Lal, Amit},
  year={2024},
  isbn={9798346459941}
}
```
## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🔗 Related Repositories

- [📌 AI-Financial-Engineering-Agentic-System (OpenAI SDK version)](https://github.com/amitlals/AI-Financial-Engineering-Agentic-System)
- [📌 Stock-Analysis-AutoGen-Multi-Agent](https://github.com/amitlals/Stock-Analysis-AutoGen-Multi-Agent)
