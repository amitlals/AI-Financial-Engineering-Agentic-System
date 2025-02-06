# Repository Template for AI-Driven Financial and Market Analysis

## Overview

This repository provides a structured framework for setting up an **AI-driven financial engineering and marketing analysis agentic system** using **Azure AI Agent Service SDK**. It includes:

- A structured Python project template
- Required dependencies (`requirements.txt`)
- Configuration file templates (`.env`, `config.ini`)
- Step-by-step setup guide
- Automated AI agents for data and news analysis

---

## 📂 Project Structure

```
📦 Stock-Analysis-AutoGen-Multi-Agent
 ┣ 📂 src
 ┃ ┣ 📜 main.py  # Main entry point for analysis
 ┃ ┣ 📜 connectors.py  # Handles data retrieval (ERP + News API)
 ┃ ┣ 📜 agents.py  # Configures AI agents for financial & market insights
 ┃ ┣ 📜 processing.py  # Data processing & transformation
 ┃ ┗ 📜 config.py  # Loads configurations & API keys
 ┣ 📜 requirements.txt  # Dependencies
 ┣ 📜 .env.example  # Environment variables template
 ┣ 📜 README.md  # Project documentation
 ┣ 📜 setup_azure_ai_sdk.md  # Step-by-step guide for Azure AI Agent setup
 ┗ 📜 LICENSE  # License file
```

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
source venv/bin/activate  # For Mac/Linux
venv\Scripts\activate    # For Windows
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Set Up Environment Variables

1. **Create a `.env` file** (or copy from `.env.example`)
   ```bash
   cp .env.example .env
   ```
2. **Add API keys & Azure configuration**:
   ```ini
   # .env
   CURRENTS_API_KEY=your_currents_api_key
   API_KEY=your_azure_openai_api_key
   AZURE_ENDPOINT=your_azure_openai_endpoint
   MODEL_DEPLOYMENT_NAME=gpt-4
   MODEL_API_VERSION=2024-02-15-preview
   ```

---

## 📜 Azure AI Agent Service SDK Setup

Follow the steps below to configure **Azure AI Agent Service SDK**:

### 1️⃣ Install Azure SDK

```bash
pip install azure-ai-agent-sdk
```

### 2️⃣ Authenticate and Set Up Azure Service

1. Log in to Azure CLI:
   ```bash
   az login
   ```
2. Set your subscription:
   ```bash
   az account set --subscription "<your-subscription-id>"
   ```
3. Deploy AI Agent Service:
   ```bash
   az ai agent create --name StockAnalysisAgent --resource-group your-resource-group --location eastus --sku Standard
   ```
4. Retrieve and store your **Azure AI Agent API Key** in `.env`.

---

## 🚀 Running the Project

To start the AI-driven financial and market analysis system, run:

```bash
python src/main.py
```

This will:

1. Connect to ERP system & fetch orders/products data
2. Retrieve market & financial news
3. Process the data into structured insights
4. Utilize AI agents for market & financial analysis
5. Generate strategic recommendations

---

## ✅ Requirements (`requirements.txt`)

```txt
requests
dotenv
autogen
azure-ai-agent-sdk
```

---

## 📌 Notes

- **Keep your `.env` file secure** and never commit it to version control.
- Follow best practices for **Azure OpenAI API usage** to avoid exceeding quotas.
- **Modify AI agent prompts** as per specific business needs.

---

## 🏁 Next Steps

- **Enhance AI Agents:** Add more specialized AI agents for deeper financial analysis.
- **Expand Data Sources:** Integrate stock market APIs for real-time analytics.
- **Deploy on Azure:** Use Azure Functions or a containerized service for production deployment.

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

### 🔗 GitHub Repository

[📌 GitHub Repository Link](https://github.com/amitlals/Stock-Analysis-AutoGen-Multi-Agent)
