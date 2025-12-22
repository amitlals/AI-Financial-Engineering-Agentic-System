import os
import json
import asyncio
from textwrap import dedent
from typing import Dict, List, Optional, Sequence
from enum import Enum

import requests
import gradio as gr
import graphviz
from graphviz import Digraph
from dotenv import load_dotenv
import urllib3
import html
import plotly.express as px
import plotly.graph_objects as go
import logging
import time
import random
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, conint

from agent_framework import ChatAgent, AgentRunResponse
from agent_framework.azure import AzureOpenAIChatClient

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Load .env variables
load_dotenv()

# Global storage for strategy options
global_options: Dict[str, "StrategyOptionModel"] = {}

def check_env_vars(*vars):
    """Checks if specified environment variables are set."""
    missing_vars = [v for v in vars if not os.getenv(v)]
    if missing_vars:
        message = f"Missing environment variables: {', '.join(missing_vars)}. Please check your .env file or system environment."
        logging.error(message)
        return False, message
    return True, "All checked environment variables are set."

class SAPFinanceConnector:
    def __init__(self, verify_ssl=False):
        self.user = os.getenv("SAP_USERNAME")
        self.pw = os.getenv("SAP_PASSWORD")
        self.base = os.getenv("SAP_BASE_URL", "https://sapes5.sapdevcenter.com/sap/opu/odata/IWBEP/GWSAMPLE_BASIC")
        self.client = os.getenv("SAP_CLIENT", "002") # Make client configurable
        self.headers = {"Accept": "application/json", "x-csrf-token": "Fetch"}
        self.cookies = None
        self.verify_ssl = verify_ssl
        if not self.user or not self.pw:
             logging.warning("SAP_USERNAME or SAP_PASSWORD environment variable not set.")

    def test_connection(self):
        if not self.user or not self.pw:
             return False, "SAP credentials not set in environment variables."
        metadata_url = f"{self.base}/$metadata"
        try:
            logging.info(f"Attempting to connect to SAP metadata URL: {metadata_url} with client {self.client}")
            r = requests.get(
                metadata_url,
                auth=(self.user, self.pw),
                headers={"Accept": "application/xml"},
                params={"sap-client": self.client},
                verify=self.verify_ssl,
                timeout=20
            )
            r.raise_for_status()
            self.cookies = r.cookies
            tok = r.headers.get("x-csrf-token")
            if tok:
                self.headers['x-csrf-token'] = tok
                logging.info("SAP Connection successful, CSRF token fetched.")
                return True, "Connected successfully."
            else:
                logging.warning("SAP Connection successful, but x-csrf-token not found.")
                return True, "Connected (Warning: CSRF token missing)."
        except requests.exceptions.Timeout:
            logging.error(f"SAP connection timed out: {metadata_url}")
            return False, "Connection timed out."
        except requests.exceptions.HTTPError as e:
             logging.error(f"SAP connection HTTP error: {e.response.status_code} - {e.response.text[:200]}")
             return False, f"Connection failed (HTTP {e.response.status_code}). Check URL/Credentials/Client."
        except requests.exceptions.RequestException as e:
            logging.error(f"SAP connection failed: {e}")
            return False, f"Connection failed: {type(e).__name__}. Check network/URL."
        except Exception as e:
            logging.error(f"An unexpected error occurred during SAP connection test: {e}", exc_info=True)
            return False, f"An unexpected error occurred: {e}"

    def fetch(self, entity, top):
        if not self.cookies or 'x-csrf-token' not in self.headers.get('x-csrf-token', ''): # Check token value, not just key
             logging.warning(f"Attempting to fetch {entity} without established connection/CSRF token.")
             connected, msg = self.test_connection()
             if not connected:
                 logging.error(f"Cannot fetch {entity}, SAP connection failed: {msg}")
                 raise ConnectionError(f"SAP Connection failed: {msg}")
             elif 'x-csrf-token' not in self.headers.get('x-csrf-token', ''):
                 logging.warning(f"Proceeding to fetch {entity} without CSRF token. May fail.")

        url = f"{self.base}/{entity}"
        params = {
            "sap-client": self.client,
            "$format": "json",
            "$top": str(top)
        }
        logging.info(f"Fetching data from: {url} with params: {params}")
        try:
            r = requests.get(url, params=params, auth=(self.user, self.pw), headers=self.headers,
                             cookies=self.cookies, verify=self.verify_ssl, timeout=30)
            r.raise_for_status()
            content_type = r.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                # Handle potential empty response or structure variations
                response_json = r.json()
                data = response_json.get('d', {}).get('results', []) if isinstance(response_json.get('d'), dict) else []
                logging.info(f"Successfully fetched {len(data)} records from {entity}.")
                return data
            else:
                logging.error(f"Unexpected Content-Type '{content_type}' for {entity}. Response: {r.text[:200]}")
                raise ValueError(f"Expected JSON response, got {content_type}")

        except requests.exceptions.Timeout:
            logging.error(f"Timeout occurred while fetching {entity} from {url}")
            raise TimeoutError(f"Timeout fetching {entity}")
        except requests.exceptions.HTTPError as e:
             logging.error(f"HTTP error fetching {entity}: {e.response.status_code} - {e.response.text[:200]}")
             raise ConnectionError(f"HTTP {e.response.status_code} fetching {entity}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch {entity}: {e}")
            raise ConnectionError(f"Request failed for {entity}: {e}")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode JSON for {entity}: {e}. Response: {r.text[:500]}")
            raise ValueError(f"Invalid JSON received for {entity}")
        except Exception as e:
             logging.error(f"Unexpected error fetching {entity}: {e}", exc_info=True)
             raise

    fetch_orders     = lambda self, top=50: self.fetch("SalesOrderSet", top)
    fetch_products   = lambda self, top=50: self.fetch("ProductSet", top)
    fetch_line_items = lambda self, top=100: self.fetch("SalesOrderLineItemSet", top)
    fetch_partners   = lambda self, top=50: self.fetch("BusinessPartnerSet", top)


class NewsDataConnector:
    def __init__(self):
        self.key = os.getenv("CURRENTS_API_KEY")
        self.url = "https://api.currentsapi.services/v1/latest-news"
        if not self.key:
            logging.warning("CURRENTS_API_KEY environment variable not set. News features disabled.")

    def fetch_financial_news(self, count=5):
        if not self.key: return []
        logging.info(f"Fetching {count} financial news articles...")
        params = {"language": "en", "category": "business,finance", "apiKey": self.key}
        try:
            r = requests.get(self.url, params=params, timeout=15)
            r.raise_for_status()
            response_json = r.json()
            status = response_json.get('status')
            if status == 'ok':
                news_data = response_json.get('news', [])
                logging.info(f"Fetched {len(news_data)} news articles.")
                return news_data[:count]
            else:
                logging.error(f"News API returned status '{status}'. Response: {response_json}")
                return []
        except requests.exceptions.Timeout: logging.error("News API request timed out."); return []
        except requests.exceptions.HTTPError as e: logging.error(f"News API HTTP error: {e.response.status_code}. Check API Key/Plan. Response: {e.response.text[:200]}"); return []
        except requests.exceptions.RequestException as e: logging.error(f"News API request failed: {e}"); return []
        except json.JSONDecodeError as e: logging.error(f"Failed to decode News API JSON: {e}. Response: {r.text[:500]}"); return []
        except Exception as e: logging.error(f"Unexpected error fetching news: {e}", exc_info=True); return []

# Enhanced Dummy Salesforce Data
def fetch_salesforce_data():
    logging.info("Fetching dummy Salesforce data.")
    # Simulate some realistic-looking data
    pipeline = random.randint(1_000_000, 2_500_000)
    closed = random.randint(int(pipeline*0.4), int(pipeline*0.6))
    opps = random.randint(20, 50)
    closed_count = random.randint(10, opps)
    conv_rate = int((closed_count / opps) * 100) if opps > 0 else 0
    avg_deal = int(closed / closed_count) if closed_count > 0 else 0

    return {
        "TotalPipelineValue": pipeline, "ClosedDealsValue": closed,
        "OpenOpportunities": opps, "ClosedDealsCount": closed_count,
        "OpportunityConversionRate": conv_rate, "AverageDealSize": avg_deal,
        "CustomerChurnRate": random.uniform(3.5, 8.5), # Churn rate %
        "TopOpenDeals": [
            {"Name": "Project Jupiter", "Amount": random.randint(80000, 150000), "Stage": "Negotiation", "Probability": 75},
            {"Name": "Saturn Initiative", "Amount": random.randint(50000, 100000), "Stage": "Proposal", "Probability": 50},
            {"Name": "Neptune Rollout", "Amount": random.randint(100000, 200000), "Stage": "Qualification", "Probability": 25}
        ],
        "TopCustomers": [
            {"Name": "Innovate Solutions", "Revenue": random.randint(150000, 300000)},
            {"Name": "Synergy Systems", "Revenue": random.randint(100000, 200000)},
            {"Name": "Quantum Dynamics", "Revenue": random.randint(80000, 150000)}
        ]
    }

def process_salesforce_data(sf):
    """Formats Salesforce data for display."""
    if not sf: return "No Salesforce data available."
    lines = [
        f"Total Pipeline: ${sf.get('TotalPipelineValue', 0):,.0f}",
        f"Closed Won Value: ${sf.get('ClosedDealsValue', 0):,.0f}",
        f"Open Opportunities: {sf.get('OpenOpportunities', 0)}",
        f"Conversion Rate: {sf.get('OpportunityConversionRate', 0)}%",
        f"Avg Deal Size: ${sf.get('AverageDealSize', 0):,.0f}",
        f"Churn Rate (Est): {sf.get('CustomerChurnRate', 0):.1f}%"
    ]
    top_cust = sf.get('TopCustomers', [])
    if top_cust:
        lines.append("\nTop Customers (Prev. Revenue):")
        lines.extend([f"• {c.get('Name', 'N/A')}: ${c.get('Revenue', 0):,.0f}" for c in top_cust])

    top_deals = sf.get('TopOpenDeals', [])
    if top_deals:
        lines.append("\nTop Open Deals:")
        lines.extend([f"• {d.get('Name', 'N/A')} (${d.get('Amount', 0):,.0f} @ {d.get('Probability', 0)}%) - {d.get('Stage', 'N/A')}" for d in top_deals])

    return "\n".join(lines)

# Data processing for SAP
def process_sap_data(orders, products, line_items, partners):
    financial_summary = {"total_sales": 0, "order_count": 0, "avg_order": 0, "by_currency": {}}
    top_customers = []
    if not orders:
        logging.warning("No SAP orders data to process.")
        return {"financial_summary": financial_summary, "top_customers": top_customers}

    total_sales = 0; valid_orders_count = 0; by_cur = {}; sales_by_customer = {}
    for o in orders:
        try:
            gross_amount_str = o.get('GrossAmount'); amount = 0.0
            if gross_amount_str is not None: amount = float(gross_amount_str)
            else: logging.warning(f"Order {o.get('SalesOrderID', 'N/A')} missing GrossAmount."); continue # Skip orders without amount

            total_sales += amount; valid_orders_count += 1
            cur = o.get('CurrencyCode', 'NA'); by_cur[cur] = by_cur.get(cur, 0) + amount
            cid = o.get('CustomerID')
            if cid: sales_by_customer[cid] = sales_by_customer.get(cid, 0) + amount
        except (ValueError, TypeError) as e: logging.warning(f"Amount parse error order {o.get('SalesOrderID', 'N/A')}. Amount: '{gross_amount_str}', Error: {e}")
        except Exception as e: logging.error(f"Unexpected error processing order {o.get('SalesOrderID', 'N/A')}: {e}", exc_info=True)

    avg_order = total_sales / valid_orders_count if valid_orders_count else 0
    partner_map = {bp.get('BusinessPartnerID'): bp.get('CompanyName', 'Unknown') for bp in partners if bp.get('BusinessPartnerID')}
    sorted_customers = sorted(sales_by_customer.items(), key=lambda item: item[1], reverse=True)
    top_sales_data = sorted_customers[:5]
    top_customers = [{"id": cid, "name": partner_map.get(cid, f"ID: {cid}"), "sales": amt} for cid, amt in top_sales_data if cid]

    financial_summary = {"total_sales": total_sales, "order_count": valid_orders_count, "avg_order": avg_order, "by_currency": by_cur}
    logging.info(f"Processed SAP data: Sales={total_sales:.2f}, Orders={valid_orders_count}, Avg Order={avg_order:.2f}, Top Customers identified.")
    return {"financial_summary": financial_summary, "top_customers": top_customers}

# Agent Framework strategist setup
class InsightSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TimeHorizon(str, Enum):
    IMMEDIATE = "0-30d"
    NEAR_TERM = "30-90d"
    MID_TERM = "90-180d"
    LONG_TERM = "180d+"


class StrategyOptionModel(BaseModel):
    """Structured representation for a strategic recommendation."""

    title: str = Field(description="Concise headline for the strategy option.")
    narrative: str = Field(description="Explain how this option uses the provided data to guide the CFO.")
    kpis: List[str] = Field(default_factory=list, description="KPIs to monitor for this option.")
    actions: List[str] = Field(default_factory=list, description="Immediate follow-up actions.")
    risks: List[str] = Field(default_factory=list, description="Risks or dependencies to monitor.")
    severity: InsightSeverity = Field(description="Overall urgency or impact of pursuing this option.")
    time_horizon: TimeHorizon = Field(description="Expected time horizon for measuring the option's impact.")
    confidence: conint(ge=0, le=100) = Field(description="Confidence percentage in this option's success.", default=70)
    owner: Optional[str] = Field(default=None, description="Suggested accountable owner or team.")


class InsightItemModel(BaseModel):
    """Normalized insight emitted by domain agents."""

    title: str = Field(description="Short, action-centric title for the insight.")
    summary: str = Field(description="One-sentence summary for dashboards or briefings.")
    severity: InsightSeverity = Field(description="Operational severity of the finding.")
    time_horizon: TimeHorizon = Field(description="When the issue/opportunity matters most.")
    confidence: conint(ge=0, le=100) = Field(description="Confidence percentage derived from the data.")
    key_metric: Optional[str] = Field(default=None, description="Metric or KPI impacted (e.g., Gross Margin %).")
    supporting_points: List[str] = Field(default_factory=list, description="Bullet points with context or evidence.")
    recommended_action: Optional[str] = Field(default=None, description="Single sentence next action if relevant.")


class AgentInsightReport(BaseModel):
    """Envelope describing the output from a specialist agent."""

    agent_name: str = Field(description="Name of the agent producing insights.")
    focus_area: str = Field(description="Domain focus for the agent (e.g., Finance Health).")
    insights: List[InsightItemModel] = Field(default_factory=list, description="Structured insights.")
    recommendations: List[str] = Field(default_factory=list, description="Follow-up ideas tied to the insights.")


class NarrativeSection(BaseModel):
    """Appendix material grouped by theme for board distribution."""

    heading: str
    bullets: List[str] = Field(default_factory=list)


class BoardNarrativeModel(BaseModel):
    """Board-ready narrative synthesized from specialist agent outputs."""

    title: str = Field(description="Narrative headline for the board memo.")
    executive_summary: List[str] = Field(
        default_factory=list, description="Top highlights the CFO should open with."
    )
    risk_highlights: List[str] = Field(
        default_factory=list, description="Critical risks and mitigations to call out."
    )
    action_register: List[str] = Field(
        default_factory=list, description="Actions seeking board endorsement or visibility."
    )
    appendix: List[NarrativeSection] = Field(
        default_factory=list, description="Deeper-dive sections for reference."
    )
    closing_statement: Optional[str] = Field(
        default=None, description="Optional closing statement or call-to-action."
    )


class StrategyResponseModel(BaseModel):
    """Structured response produced by the Microsoft Agent Framework analysis."""

    executive_summary: List[str] = Field(
        description="Three board-ready talking points derived from the combined dataset."
    )
    market_signals: List[str] = Field(default_factory=list, description="Insights sourced from news and pipeline.")
    finance_health: List[str] = Field(default_factory=list, description="Observations from SAP ledgers and KPIs.")
    risk_watch: List[str] = Field(default_factory=list, description="Headwinds or dependencies to track.")
    options: Dict[str, StrategyOptionModel] = Field(
        description="Use keys 'Option 1', 'Option 2', 'Option 3' covering growth, efficiency, and resilience themes."
    )
    option_ranking_notes: List[str] = Field(
        default_factory=list,
        description="Additional sequencing guidance or caveats for the options."
    )


class StrategyAgentResult(BaseModel):
    """Bundle carrying agent outputs consumed by the dashboard."""

    insights_markdown: str
    options: Dict[str, StrategyOptionModel]
    raw_text: str
    structured: Optional[StrategyResponseModel] = None
    insight_reports: List[AgentInsightReport] = Field(default_factory=list)
    board_narrative: Optional[BoardNarrativeModel] = None


def _run_async_function(async_fn, *args, **kwargs):
    """Execute an async coroutine from synchronous code paths with safe loop handling."""

    async def runner():
        return await async_fn(*args, **kwargs)

    try:
        return asyncio.run(runner())
    except RuntimeError as runtime_error:
        logging.debug(f"asyncio.run fallback due to runtime error: {runtime_error}")
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(runner())
        finally:
            loop.close()


class FinanceScenarioAgent:
    """Microsoft Agent Framework powered orchestrator for CFO insights."""

    def __init__(self) -> None:
        self._client = self._build_client()
        self._market_agent = self._build_specialist_agent(
            name="market-intelligence-agent",
            description="Distils market and pipeline signals into structured insights.",
            focus_prompt="Prioritise news sentiment, macro shifts, customer pipeline, and currency exposure cues.",
            temperature=0.10,
        )
        self._finance_agent = self._build_specialist_agent(
            name="finance-pulse-agent",
            description="Analyses SAP ledgers and customer movements for financial health.",
            focus_prompt="Interrogate SAP financial summary, product mix, and top customer trends.",
            temperature=0.05,
        )
        self._risk_agent = self._build_specialist_agent(
            name="risk-monitor-agent",
            description="Surfaces compliance, liquidity, and volatility risks across the dataset.",
            focus_prompt="Inspect liquidity buffers, working capital, regulatory exposure, and volatility triggers.",
            temperature=0.12,
        )
        self._strategy_agent = self._build_strategy_agent()
        self._narrative_agent = self._build_narrative_agent()

    def _build_client(self) -> AzureOpenAIChatClient:
        required_vars = ["MODEL_DEPLOYMENT_NAME", "API_KEY", "AZURE_ENDPOINT"]
        vars_ok, msg = check_env_vars(*required_vars)
        if not vars_ok:
            raise ValueError(f"Agent configuration error: {msg}")

        api_version = os.getenv("MODEL_API_VERSION", "2024-10-21")
        return AzureOpenAIChatClient(
            api_key=os.getenv("API_KEY"),
            deployment_name=os.getenv("MODEL_DEPLOYMENT_NAME"),
            endpoint=os.getenv("AZURE_ENDPOINT"),
            api_version=api_version,
        )

    def _build_specialist_agent(
        self,
        *,
        name: str,
        description: str,
        focus_prompt: str,
        temperature: float,
    ) -> ChatAgent:
        schema_hint = dedent(
            """
            Respond strictly as AgentInsightReport JSON.
            - Produce between 2 and 4 InsightItemModel entries.
            - severity must be one of low, medium, high.
            - time_horizon must be one of 0-30d, 30-90d, 90-180d, 180d+.
            - confidence is an integer 0-100 reflecting data strength.
            Add 1-3 recommendations aligned to the findings.
            Return raw JSON only with no code fences or commentary.
            Do not wrap the payload in an extra root key.
            """
        ).strip()

        instructions = dedent(
            """
            You are {agent_name} operating within the CFO agent collective.
            {focus_prompt}

            {schema_hint}
            """
        ).format(
            agent_name=name.replace("-", " "),
            focus_prompt=focus_prompt,
            schema_hint=schema_hint,
        ).strip()

        return ChatAgent(
            chat_client=self._client,
            name=name,
            description=description,
            instructions=instructions,
            temperature=temperature,
            max_tokens=900,
        )

    def _build_strategy_agent(self) -> ChatAgent:
        instructions = dedent(
            """
            Fuse the specialist insight reports and base dataset into StrategyResponseModel JSON.
            Each option must include severity, time_horizon, confidence, actions, KPIs, risks, and an owner if possible.
            Provide option_ranking_notes to explain sequencing or dependencies across the options.
            Respond with raw JSON only (no code fences or prose).
            Do not wrap the payload in an extra root key.
            """
        ).strip()

        return ChatAgent(
            chat_client=self._client,
            name="cfo-strategist",
            description="Synthesises insights and drafts CFO strategy options.",
            instructions=instructions,
            temperature=0.15,
            max_tokens=1600,
        )

    def _build_narrative_agent(self) -> ChatAgent:
        instructions = dedent(
            """
            Create a BoardNarrativeModel JSON payload using the dataset, specialist reports, and strategy output.
            Executive summary must have exactly three bullets. Highlight the top two risks and align actions to the strategy
            options. Provide a concise closing_statement if the board needs to endorse or be aware of anything specific.
            Respond with raw JSON only (no code fences or additional commentary).
            Do not wrap the payload in an extra root key.
            """
        ).strip()

        return ChatAgent(
            chat_client=self._client,
            name="board-briefing-agent",
            description="Synthesises a board-ready narrative from agent outputs.",
            instructions=instructions,
            temperature=0.20,
            max_tokens=1200,
        )

    @staticmethod
    def _compose_dataset(
        fin_summary: Dict[str, float],
        top_customers: List[Dict[str, float]],
        salesforce_summary: Dict[str, float],
        news_briefings: List[Dict[str, str]],
    ) -> Dict[str, object]:
        return {
            "sap_financial_summary": fin_summary or {},
            "sap_top_customers": top_customers or [],
            "salesforce_overview": salesforce_summary or {},
            "news_briefings": news_briefings or [],
        }

    @staticmethod
    def _extract_json_text(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        cleaned = raw.strip()
        if not cleaned:
            return None

        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            json.loads(cleaned)
            return cleaned
        except Exception:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                return None
        return None

    @staticmethod
    def _unwrap_payload(data: object, expected_name: str) -> object:
        if isinstance(data, dict) and len(data) == 1:
            [(key, value)] = data.items()
            if key.lower() == expected_name.lower():
                return value
        return data

    @staticmethod
    def _coerce_severity(value: Optional[str]) -> InsightSeverity:
        if isinstance(value, InsightSeverity):
            return value
        if isinstance(value, str):
            value_lower = value.strip().lower()
            for member in InsightSeverity:
                if member.value == value_lower or member.name.lower() == value_lower:
                    return member
        return InsightSeverity.MEDIUM

    @staticmethod
    def _coerce_horizon(value: Optional[str]) -> TimeHorizon:
        if isinstance(value, TimeHorizon):
            return value
        if isinstance(value, str):
            value_clean = value.strip().lower().replace(" ", "")
            for member in TimeHorizon:
                if member.value.lower().replace("-", "").replace("+", "") == value_clean or member.name.lower() == value_clean:
                    return member
        return TimeHorizon.MID_TERM

    @staticmethod
    def _coerce_confidence(value: Optional[object]) -> int:
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(value))))
        if isinstance(value, str):
            try:
                return max(0, min(100, int(round(float(value)))))
            except Exception:
                pass
        return 60

    def _normalize_insights(
        self,
        agent: ChatAgent,
        raw_insights: object,
    ) -> List[dict]:
        items = []
        if isinstance(raw_insights, dict):
            raw_insights = [raw_insights]

        if not isinstance(raw_insights, list):
            return items

        for raw_item in raw_insights:
            if isinstance(raw_item, dict) and len(raw_item) == 1:
                [(key, value)] = raw_item.items()
                if isinstance(value, dict):
                    raw_item = value

            if not isinstance(raw_item, dict):
                continue

            title = raw_item.get("title") or raw_item.get("heading") or raw_item.get("insight") or "Insight"
            summary = raw_item.get("summary") or raw_item.get("description") or raw_item.get("insight") or title
            severity = self._coerce_severity(raw_item.get("severity"))
            horizon = self._coerce_horizon(raw_item.get("time_horizon") or raw_item.get("horizon"))
            confidence = self._coerce_confidence(raw_item.get("confidence"))
            key_metric = raw_item.get("key_metric") or raw_item.get("metric")

            supporting = raw_item.get("supporting_points") or raw_item.get("details") or raw_item.get("bullets") or []
            if isinstance(supporting, str):
                supporting = [supporting]
            elif not isinstance(supporting, list):
                supporting = []
            supporting = [str(point) for point in supporting if str(point).strip()]

            recommended_action = raw_item.get("recommended_action") or raw_item.get("action")
            if isinstance(recommended_action, list):
                recommended_action = "; ".join(str(v) for v in recommended_action)

            items.append(
                {
                    "title": str(title),
                    "summary": str(summary),
                    "severity": severity,
                    "time_horizon": horizon,
                    "confidence": confidence,
                    "key_metric": key_metric,
                    "supporting_points": supporting,
                    "recommended_action": recommended_action,
                }
            )
        return items

    def _ensure_insight_report(
        self,
        agent: ChatAgent,
        focus: str,
        payload: object,
    ) -> AgentInsightReport:
        data = {}
        if isinstance(payload, dict):
            data = payload.copy()
        elif isinstance(payload, list):
            data = {"insights": payload}

        data.setdefault("agent_name", agent.name)
        data.setdefault("focus_area", focus.title())
        data.setdefault("recommendations", [])

        normalized_insights = self._normalize_insights(agent, data.get("insights"))
        data["insights"] = normalized_insights
        return AgentInsightReport.model_validate(data)

    def _ensure_strategy_payload(
        self,
        payload: object,
    ) -> StrategyResponseModel:
        if isinstance(payload, list):
            payload = {"options": payload}
        elif not isinstance(payload, dict):
            payload = {}

        data = payload.copy()
        exec_summary = data.get("executive_summary")
        if isinstance(exec_summary, str):
            exec_summary = [exec_summary]
        if not exec_summary:
            exec_summary = ["Key strategy insights are summarised below."]
        data["executive_summary"] = exec_summary

        market_signals = data.get("market_signals")
        if isinstance(market_signals, str):
            market_signals = [market_signals]
        data["market_signals"] = market_signals or []

        finance_health = data.get("finance_health")
        if isinstance(finance_health, str):
            finance_health = [finance_health]
        data["finance_health"] = finance_health or []

        risk_watch = data.get("risk_watch")
        if isinstance(risk_watch, str):
            risk_watch = [risk_watch]
        data["risk_watch"] = risk_watch or []

        option_entries = data.get("options")
        options_dict: Dict[str, dict] = {}
        if isinstance(option_entries, dict):
            options_dict = option_entries
        elif isinstance(option_entries, list):
            for idx, entry in enumerate(option_entries, 1):
                options_dict[f"Option {idx}"] = entry
        else:
            options_dict = {}

        normalized_options: Dict[str, StrategyOptionModel] = {}
        for key, option_payload in options_dict.items():
            if isinstance(option_payload, dict) and len(option_payload) == 1:
                [(inner_key, inner_value)] = option_payload.items()
                if isinstance(inner_value, dict):
                    option_payload = inner_value
                    key = inner_key

            if not isinstance(option_payload, dict):
                option_payload = {"narrative": str(option_payload)}

            option_payload.setdefault("title", key)
            option_payload.setdefault("narrative", "No narrative provided.")
            option_payload.setdefault("kpis", [])
            option_payload.setdefault("actions", [])
            option_payload.setdefault("risks", [])
            option_payload["severity"] = self._coerce_severity(option_payload.get("severity"))
            option_payload["time_horizon"] = self._coerce_horizon(option_payload.get("time_horizon"))
            option_payload["confidence"] = self._coerce_confidence(option_payload.get("confidence"))
            option_payload["owner"] = option_payload.get("owner") or option_payload.get("lead") or option_payload.get("team")

            normalized_options[key] = StrategyOptionModel.model_validate(option_payload)

        data["options"] = normalized_options

        ranking_notes = data.get("option_ranking_notes")
        if isinstance(ranking_notes, str):
            ranking_notes = [ranking_notes]
        data["option_ranking_notes"] = ranking_notes or []
        return StrategyResponseModel.model_validate(data)

    def _ensure_narrative_payload(
        self,
        payload: object,
    ) -> BoardNarrativeModel:
        if not isinstance(payload, dict):
            payload = {}
        data = payload.copy()
        data.setdefault("title", "CFO Board Narrative")

        executive_summary = data.get("executive_summary")
        if isinstance(executive_summary, str):
            executive_summary = [executive_summary]
        data["executive_summary"] = executive_summary or ["Executive summary not provided."]

        risk_highlights = data.get("risk_highlights")
        if isinstance(risk_highlights, str):
            risk_highlights = [risk_highlights]
        data["risk_highlights"] = risk_highlights or []

        action_register = data.get("action_register")
        if isinstance(action_register, str):
            action_register = [action_register]
        data["action_register"] = action_register or []

        appendix_sections = data.get("appendix")
        if isinstance(appendix_sections, dict):
            appendix_sections = [appendix_sections]
        elif not isinstance(appendix_sections, list):
            appendix_sections = []
        normalized_sections = []
        for section in appendix_sections:
            if not isinstance(section, dict):
                continue
            heading = section.get("heading") or section.get("title") or "Appendix"
            bullets = section.get("bullets") or section.get("points") or []
            if isinstance(bullets, str):
                bullets = [bullets]
            elif not isinstance(bullets, list):
                bullets = []
            normalized_sections.append(NarrativeSection(heading=heading, bullets=[str(b) for b in bullets]))
        data["appendix"] = normalized_sections

        closing = data.get("closing_statement")
        if isinstance(closing, list):
            closing = " ".join(str(v) for v in closing)
        data["closing_statement"] = closing
        return BoardNarrativeModel.model_validate(data)

    def _run_specialist(self, agent: ChatAgent, dataset: Dict[str, object], focus: str) -> Optional[AgentInsightReport]:
        prompt = dedent(
            """
            You are analysing the CFO dataset for {focus}.
            Respond with AgentInsightReport JSON only.

            DATASET:
            {dataset_json}
            """
        ).format(
            focus=focus,
            dataset_json=json.dumps(dataset, indent=2, ensure_ascii=False),
        ).strip()

        try:
            response = _run_async_function(agent.run, prompt)
        except Exception as exc:
            logging.error(f"{agent.name} failed: {exc}", exc_info=True)
            return None

        candidate = response.value
        if isinstance(candidate, AgentInsightReport):
            return candidate
        if candidate:
            try:
                normalized = self._unwrap_payload(candidate, "AgentInsightReport")
                return self._ensure_insight_report(agent, focus, normalized)
            except ValidationError as vex:
                logging.error(f"{agent.name} value failed validation: {vex}")
        json_text = self._extract_json_text(response.text)
        if json_text:
            try:
                parsed = json.loads(json_text)
                normalized = self._unwrap_payload(parsed, "AgentInsightReport")
                return self._ensure_insight_report(agent, focus, normalized)
            except Exception as vex:
                logging.error(f"{agent.name} JSON decode error: {vex}")
        logging.warning(f"{agent.name} returned non-structured payload.")
        return None

    def _invoke_strategy_agent(
        self,
        dataset: Dict[str, object],
        insight_reports: Sequence[AgentInsightReport],
    ) -> StrategyAgentResult:
        request_payload = {
            "dataset": dataset,
            "insight_reports": [report.model_dump() for report in insight_reports],
        }
        prompt = dedent(
            """
            Produce StrategyResponseModel JSON based on the provided payload.

            PAYLOAD:
            {payload}
            """
        ).format(payload=json.dumps(request_payload, indent=2, ensure_ascii=False)).strip()

        try:
            response = _run_async_function(
                self._strategy_agent.run,
                prompt,
            )
        except Exception as exc:
            logging.error(f"Strategy agent failed: {exc}", exc_info=True)
            return StrategyAgentResult(
                insights_markdown="Strategy agent failed to respond.",
                options={},
                raw_text=str(exc),
                structured=None,
            )

        structured: Optional[StrategyResponseModel] = None
        candidate = response.value
        if isinstance(candidate, StrategyResponseModel):
            structured = candidate
        elif candidate:
            try:
                normalized = self._unwrap_payload(candidate, "StrategyResponseModel")
                structured = self._ensure_strategy_payload(normalized)
            except ValidationError as vex:
                logging.error(f"Strategy response validation error: {vex}")
        if structured is None:
            json_text = self._extract_json_text(response.text)
            if json_text:
                try:
                    parsed = json.loads(json_text)
                    normalized = self._unwrap_payload(parsed, "StrategyResponseModel")
                    structured = self._ensure_strategy_payload(normalized)
                except Exception as vex:
                    logging.error(f"Strategy agent JSON decode error: {vex}")
            else:
                logging.error("Strategy agent returned unstructured payload.")

        options = structured.options if structured else {}
        markdown = self._format_insight_markdown(insight_reports, None)
        return StrategyAgentResult(
            insights_markdown=markdown,
            options=options,
            raw_text=response.text or "",
            structured=structured,
            insight_reports=list(insight_reports),
        )

    def _invoke_narrative_agent(
        self,
        dataset: Dict[str, object],
        insight_reports: Sequence[AgentInsightReport],
        strategy: Optional[StrategyResponseModel],
    ) -> Optional[BoardNarrativeModel]:
        payload = {
            "dataset": dataset,
            "insight_reports": [report.model_dump() for report in insight_reports],
            "strategy": strategy.model_dump() if strategy else None,
        }
        prompt = dedent(
            """
            Produce BoardNarrativeModel JSON based on the provided context.

            CONTEXT:
            {payload}
            """
        ).format(payload=json.dumps(payload, indent=2, ensure_ascii=False)).strip()

        try:
            response = _run_async_function(
                self._narrative_agent.run,
                prompt,
            )
        except Exception as exc:
            logging.error(f"Narrative agent failed: {exc}", exc_info=True)
            return None

        candidate = response.value
        if isinstance(candidate, BoardNarrativeModel):
            return candidate
        if candidate:
            try:
                normalized = self._unwrap_payload(candidate, "BoardNarrativeModel")
                return self._ensure_narrative_payload(normalized)
            except ValidationError as vex:
                logging.error(f"Narrative validation error: {vex}")
        json_text = self._extract_json_text(response.text)
        if json_text:
            try:
                parsed = json.loads(json_text)
                normalized = self._unwrap_payload(parsed, "BoardNarrativeModel")
                return self._ensure_narrative_payload(normalized)
            except Exception as vex:
                logging.error(f"Narrative agent JSON decode error: {vex}")
        logging.warning("Narrative agent response could not be parsed to BoardNarrativeModel.")
        return None

    @staticmethod
    def _format_insight_markdown(
        reports: Sequence[AgentInsightReport],
        narrative: Optional[BoardNarrativeModel],
    ) -> str:
        lines: List[str] = []
        for report in reports:
            lines.append(f"### {report.focus_area}")
            for insight in report.insights:
                meta = f"{insight.severity.value.upper()} | {insight.time_horizon.value} | {insight.confidence}%"
                lines.append(f"- **{meta}** - {insight.title}: {insight.summary}")
                for point in insight.supporting_points[:2]:
                    lines.append(f"  - {point}")
                if insight.recommended_action:
                    lines.append(f"  - _Action:_ {insight.recommended_action}")
            if report.recommendations:
                lines.append("  - **Recommendations:** " + "; ".join(report.recommendations))
            lines.append("")

        if narrative:
            lines.append("## Board Narrative Highlights")
            if narrative.executive_summary:
                lines.append("**Executive Summary**")
                lines.extend(f"- {bullet}" for bullet in narrative.executive_summary)
            if narrative.risk_highlights:
                lines.append("**Risk Highlights**")
                lines.extend(f"- {bullet}" for bullet in narrative.risk_highlights)
            if narrative.action_register:
                lines.append("**Required Actions**")
                lines.extend(f"- {bullet}" for bullet in narrative.action_register)
            if narrative.closing_statement:
                lines.append(f"_Closing:_ {narrative.closing_statement}")

        return "\n".join(lines).strip()

    def analyze(
        self,
        fin_summary: Dict[str, float],
        top_customers: List[Dict[str, float]],
        salesforce_summary: Dict[str, float],
        news_briefings: List[Dict[str, str]],
    ) -> StrategyAgentResult:
        dataset = self._compose_dataset(fin_summary, top_customers, salesforce_summary, news_briefings)

        reports: List[AgentInsightReport] = []
        for agent, label in [
            (self._market_agent, "market and pipeline dynamics"),
            (self._finance_agent, "financial health and performance"),
            (self._risk_agent, "risk and compliance posture"),
        ]:
            report = self._run_specialist(agent, dataset, label)
            if report:
                reports.append(report)

        if not reports:
            logging.warning("No specialist insights were generated; falling back to basic summary.")

        strategy_result = self._invoke_strategy_agent(dataset, reports)
        board_narrative = self._invoke_narrative_agent(dataset, reports, strategy_result.structured)
        strategy_result.board_narrative = board_narrative
        strategy_result.insight_reports = reports
        strategy_result.insights_markdown = self._format_insight_markdown(reports, board_narrative)
        return strategy_result


finance_agent_runner: Optional[FinanceScenarioAgent] = None


def get_finance_agent() -> FinanceScenarioAgent:
    global finance_agent_runner
    if finance_agent_runner is None:
        finance_agent_runner = FinanceScenarioAgent()
    return finance_agent_runner


def render_option_html(option_key: str, option: StrategyOptionModel, icon: str) -> str:
    """Render a strategy option into the dashboard's HTML card format."""
    actions_html = "".join(f"<li>{html.escape(item)}</li>" for item in option.actions) or "<li>Define next steps...</li>"
    kpi_html = "".join(f"<li>{html.escape(item)}</li>" for item in option.kpis)
    risk_html = "".join(f"<li>{html.escape(item)}</li>" for item in option.risks)
    meta = f"{option.severity.value.upper()} | {option.time_horizon.value} | {option.confidence}% confidence"
    owner_line = f"<p><strong>Owner:</strong> {html.escape(option.owner)}</p>" if option.owner else ""

    return (
        f"<div class='option-box'>"
        f"<h3>{html.escape(icon)} {html.escape(option_key)} - {html.escape(option.title)}</h3>"
        f"<div class='option-content'>"
        f"<p><em>{html.escape(meta)}</em></p>"
        f"<p>{html.escape(option.narrative)}</p>"
        f"{owner_line}"
        f"<h4>Key Actions</h4><ul>{actions_html}</ul>"
        f"{'<h4>KPIs to Watch</h4><ul>' + kpi_html + '</ul>' if kpi_html else ''}"
        f"{'<h4>Risks</h4><ul>' + risk_html + '</ul>' if risk_html else ''}"
        f"</div>"
        f"</div>"
    )

# Simulate monthly sales data for trend chart
def simulate_sales_trend(base_sales, months=12):
    dates = pd.date_range(end=pd.Timestamp.today(), periods=months, freq='ME').strftime('%Y-%m')
    sales = []
    current_sales = base_sales * random.uniform(0.8, 1.2) # Start variation
    for _ in range(months):
        sales.append(max(0, int(current_sales))) # Ensure non-negative
        growth_factor = random.uniform(0.95, 1.10) # Monthly fluctuation
        current_sales *= growth_factor
    return pd.DataFrame({'Month': dates, 'Sales': sales})


# Main analysis callback for Gradio
def run_dashboard_analysis():
    logging.info("--- Starting Dashboard Analysis ---")
    start_time = time.time()
    # --- Check Env Vars ---
    sap_vars_ok, sap_msg = check_env_vars("SAP_USERNAME", "SAP_PASSWORD")
    news_vars_ok, news_msg = check_env_vars("CURRENTS_API_KEY")
    agent_vars_ok, agent_msg = check_env_vars("MODEL_DEPLOYMENT_NAME", "API_KEY", "AZURE_ENDPOINT")
    # --- Initialize Placeholders ---
    kpi_md = "Loading KPIs..."
    sap_summary_html = "<section class='summary-card'><p>Awaiting SAP...</p></section>"
    sf_summary_html = "<section class='summary-card'><p>Awaiting Salesforce...</p></section>"
    analysis_output = "AI analysis pending..."
    news_output = "News pending..."
    title_style = {'y': 0.92, 'x': 0.5, 'xanchor': 'center', 'yanchor': 'top'}
    title_font = {'size': 18, 'color': '#0F172A', 'family': 'Inter, Segoe UI, sans-serif'}
    chart_layout_defaults = {
        'paper_bgcolor': '#F8FAFC',
        'plot_bgcolor': 'rgba(255,255,255,0.95)',
        'font': {'family': 'Inter, Segoe UI, sans-serif', 'color': '#0F172A'},
        'margin': dict(l=50, r=35, t=80, b=55),
        'hoverlabel': dict(bgcolor='#0F172A', font=dict(color='#FFFFFF'))
    }
    gridline_color = '#CBD5F5'

    def apply_chart_defaults(fig, title_text, layout_overrides=None, skip_axes=False):
        """Apply a consistent, vibrant style to Plotly figures."""
        layout_overrides = layout_overrides or {}
        fig.update_layout(
            title=go.layout.Title(text=title_text, **title_style, font=title_font),
            legend=dict(bgcolor='rgba(0,0,0,0)', borderwidth=0),
            **chart_layout_defaults,
            **layout_overrides
        )
        if not skip_axes:
            fig.update_xaxes(showgrid=True, gridcolor=gridline_color, zeroline=False, linecolor=gridline_color)
            fig.update_yaxes(showgrid=True, gridcolor=gridline_color, zeroline=False, linecolor=gridline_color)
        return fig

    fig_pie = apply_chart_defaults(go.Figure(), "Revenue by Currency (Pending)", {"showlegend": False}, skip_axes=True)
    fig_bar_cust = apply_chart_defaults(go.Figure(), "Top Customers (Pending)")
    fig_bar_prod = apply_chart_defaults(go.Figure(), "Top Products (Pending)")
    fig_line_trend = apply_chart_defaults(go.Figure(), "Sales Trend (Pending)")
    fig_bar_sf = apply_chart_defaults(go.Figure(), "SF Open Deals (Pending)")
    pending_option_html = "<div class='option-box'><h3>[Pending] Option Loading...</h3></div>"
    option_1_html = option_2_html = option_3_html = pending_option_html
    # --- SAP Data ---
    proc_sap_data = {"financial_summary": {}, "top_customers": []}; sap_conn_status = "❌ Config Error"; sap_error_msg = ""; fin_summary = {}
    if sap_vars_ok:
        sap = SAPFinanceConnector(verify_ssl=False)
        try:
            sap_ok, sap_conn_msg = sap.test_connection()
            sap_conn_status = f"{'✅ Connected' if sap_ok else '❌ Failed'}: {sap_conn_msg}"
            if sap_ok:
                logging.info("Fetching SAP data..."); orders, products, line_items, partners = [], [], [], [] # Init lists
                try: orders = sap.fetch_orders()
                except Exception as e: logging.error(f"SAP Fetch Error (Orders): {e}", exc_info=True); sap_error_msg += f" Orders fetch failed."
                # Fetch others even if one fails
                try: products = sap.fetch_products()
                except Exception as e: logging.error(f"SAP Fetch Error (Products): {e}", exc_info=True)
                try: line_items = sap.fetch_line_items()
                except Exception as e: logging.error(f"SAP Fetch Error (LineItems): {e}", exc_info=True)
                try: partners = sap.fetch_partners()
                except Exception as e: logging.error(f"SAP Fetch Error (Partners): {e}", exc_info=True); sap_error_msg += f" Partners fetch failed."

                if orders: # Only process if orders were fetched
                     logging.info("Processing SAP data...")
                     proc_sap_data = process_sap_data(orders, products, line_items, partners)
                     fin_summary = proc_sap_data.get('financial_summary', {})
                else: sap_error_msg += " No orders data to process."
            else: sap_error_msg = f"<p class='error-text'>Connection failed: {sap_conn_msg}</p>"
        except ConnectionError as e: logging.error(f"SAP ConnectionError: {e}"); sap_conn_status = "❌ Fetch Error"; sap_error_msg = f"<p class='error-text'>Data fetch error: {e}</p>"
        except Exception as e: logging.error(f"SAP Unexpected Error: {e}", exc_info=True); sap_conn_status = "❌ Error"; sap_error_msg = f"<p class='error-text'>Error: {e}</p>"
    else: sap_conn_status = f"❌ Config Error: {sap_msg}"; sap_error_msg = f"<p class='error-text'>{sap_msg}</p>"
    # --- Update SAP Summary HTML ---
    sap_summary_html = (f"<section class='summary-card {'connected' if '✅ Connected' in sap_conn_status else 'error'}'><h2>SAP Data</h2>"
        f"<p>Status: {sap_conn_status}</p><p>Total Sales: ${fin_summary.get('total_sales', 0):,.2f}</p>"
        f"<p>Orders Processed: {fin_summary.get('order_count', 0)}</p><p>Avg Order Value: ${fin_summary.get('avg_order', 0):.2f}</p>"
        f"{sap_error_msg}</section>")
    # --- Salesforce Data ---
    sf_data = {}; sf_summary_html = "<section class='summary-card error'><h2>Salesforce Data</h2><p>❌ Error</p></section>"
    try:
        sf_data = fetch_salesforce_data()
        sf_summary_html = (f"<section class='summary-card connected'><h2>Salesforce Data (Sim.)</h2><p>Status: ✅ Simulated</p>"
                           f"<pre>{process_salesforce_data(sf_data)}</pre></section>")
    except Exception as e: logging.error(f"SF Dummy Data Error: {e}", exc_info=True); sf_data = {}
    # --- KPIs Markdown ---
    kpi_md = f"""
    <div class="kpi-container">
        <div class="kpi-item"><span class="kpi-value">${fin_summary.get('total_sales', 0):,.0f}</span><span class="kpi-label">Total SAP Sales</span></div>
        <div class="kpi-item"><span class="kpi-value">${fin_summary.get('avg_order', 0):,.0f}</span><span class="kpi-label">Avg SAP Order</span></div>
        <div class="kpi-item"><span class="kpi-value">{fin_summary.get('order_count', 0)}</span><span class="kpi-label">SAP Orders</span></div>
        <div class="kpi-item"><span class="kpi-value">${sf_data.get('TotalPipelineValue', 0):,.0f}</span><span class="kpi-label">SF Pipeline</span></div>
        <div class="kpi-item"><span class="kpi-value">{sf_data.get('OpportunityConversionRate', 0)}%</span><span class="kpi-label">SF Conv. Rate</span></div>
    </div>
    """
    # --- Visualizations ---
    currency = fin_summary.get('by_currency', {})
    if currency:
        try:
            currency_labels = list(currency.keys())
            currency_values = list(currency.values())
            pull_values = [0.06] + [0.03] * (len(currency_labels) - 1) if currency_labels else []
            fig_pie = go.Figure(
                data=[
                    go.Pie(
                        labels=currency_labels,
                        values=currency_values,
                        hole=0.48,
                        pull=pull_values,
                        marker=dict(colors=px.colors.qualitative.Bold),
                        textinfo='percent+label',
                        insidetextorientation='radial',
                        textfont=dict(color='#FFFFFF')
                    )
                ]
            )
        except Exception as e:
            logging.error(f"Pie Err:{e}", exc_info=True)
            fig_pie = go.Figure()
            fig_pie.add_annotation(text="Unable to render currency mix", showarrow=False,
                                   font=dict(color='#EF4444', size=14))
    else:
        fig_pie = go.Figure()
        fig_pie.add_annotation(text="Currency breakdown not available", showarrow=False,
                               font=dict(color='#64748B', size=14))
    fig_pie = apply_chart_defaults(fig_pie, "Revenue by Currency", {"showlegend": False}, skip_axes=True)

    top_customers = proc_sap_data.get('top_customers', [])
    if top_customers:
        try:
            sorted_customers = sorted(top_customers, key=lambda x: x.get('sales', 0), reverse=True)
            customer_names = [c.get('name', '?') for c in sorted_customers]
            customer_sales = [c.get('sales', 0) for c in sorted_customers]
            fig_bar_cust = go.Figure(
                data=[
                    go.Bar(
                        x=customer_names,
                        y=customer_sales,
                        text=[f'${v:,.0f}' for v in customer_sales],
                        textposition='outside',
                        marker=dict(color=px.colors.qualitative.Vivid, line=dict(color='#ffffff', width=1)),
                        textfont=dict(color='#0F172A')
                    )
                ]
            )
        except Exception as e:
            logging.error(f"Cust Bar Err:{e}", exc_info=True)
            fig_bar_cust = go.Figure()
            fig_bar_cust.add_annotation(text="Customer chart unavailable", showarrow=False,
                                        font=dict(color='#EF4444', size=14))
    else:
        fig_bar_cust = go.Figure()
        fig_bar_cust.add_annotation(text="No customer performance data", showarrow=False,
                                    font=dict(color='#64748B', size=14))
    fig_bar_cust = apply_chart_defaults(fig_bar_cust, "Top SAP Customers")
    fig_bar_cust.update_xaxes(title=None, tickangle=-18)
    fig_bar_cust.update_yaxes(title="Sales")

    product_sales_data = proc_sap_data.get('product_sales', [])
    if product_sales_data:
        try:
            product_names = [p.get('name', '?') for p in product_sales_data]
            product_sales = [p.get('sales', 0) for p in product_sales_data]
            fig_bar_prod = go.Figure(
                data=[
                    go.Bar(
                        x=product_names,
                        y=product_sales,
                        text=[f'${s:,.0f}' for s in product_sales],
                        textposition='outside',
                        marker=dict(color=px.colors.sequential.Sunset, line=dict(color='#ffffff', width=1)),
                        textfont=dict(color='#0F172A')
                    )
                ]
            )
        except Exception as e:
            logging.error(f"Prod Bar Err:{e}", exc_info=True)
            fig_bar_prod = go.Figure()
            fig_bar_prod.add_annotation(text="Product chart unavailable", showarrow=False,
                                        font=dict(color='#EF4444', size=14))
    else:
        fig_bar_prod = go.Figure()
        fig_bar_prod.add_annotation(text="No product level data", showarrow=False,
                                    font=dict(color='#64748B', size=14))
    fig_bar_prod = apply_chart_defaults(fig_bar_prod, "Top 10 Products by Sales")
    fig_bar_prod.update_xaxes(title=None, tickangle=-28)
    fig_bar_prod.update_yaxes(title="Sales Value")

    try:
        trend_df = simulate_sales_trend(fin_summary.get('total_sales', 500000) / 12)
        fig_line_trend = go.Figure(
            data=[
                go.Scatter(
                    x=trend_df['Month'],
                    y=trend_df['Sales'],
                    mode='lines+markers',
                    line=dict(color='#2563EB', width=3),
                    marker=dict(size=8, color='#38BDF8', line=dict(color='#0F172A', width=1.5)),
                    fill='tozeroy',
                    fillcolor='rgba(37, 99, 235, 0.15)'
                )
            ]
        )
    except Exception as e:
        logging.error(f"Trend Err:{e}", exc_info=True)
        fig_line_trend = go.Figure()
        fig_line_trend.add_annotation(text="Trend simulation error", showarrow=False,
                                      font=dict(color='#EF4444', size=14))
    fig_line_trend = apply_chart_defaults(fig_line_trend, "Sim. Sales Trend")
    fig_line_trend.update_xaxes(title="Month")
    fig_line_trend.update_yaxes(title="Sales")

    deals = sf_data.get('TopOpenDeals', [])
    if deals:
        try:
            deal_names = [d.get('Name', '?') for d in deals]
            deal_values = [d.get('Amount', 0) for d in deals]
            deal_prob = [d.get('Probability', 0) for d in deals]
            fig_bar_sf = go.Figure(
                data=[
                    go.Bar(
                        x=deal_names,
                        y=deal_values,
                        text=[f'${amt:,.0f} ({prob}%)' for amt, prob in zip(deal_values, deal_prob)],
                        textposition='outside',
                        marker=dict(color=px.colors.qualitative.Pastel, line=dict(color='#ffffff', width=1)),
                        textfont=dict(color='#0F172A')
                    )
                ]
            )
        except Exception as e:
            logging.error(f"SF Bar Err:{e}", exc_info=True)
            fig_bar_sf = go.Figure()
            fig_bar_sf.add_annotation(text="Salesforce deals chart unavailable", showarrow=False,
                                      font=dict(color='#EF4444', size=14))
    else:
        fig_bar_sf = go.Figure()
        fig_bar_sf.add_annotation(text="No Salesforce deals to display", showarrow=False,
                                  font=dict(color='#64748B', size=14))
    fig_bar_sf = apply_chart_defaults(fig_bar_sf, "Top SF Open Deals")
    fig_bar_sf.update_xaxes(title=None)
    fig_bar_sf.update_yaxes(title="Deal Value")

    # --- News Data ---
    news_list = []; news_stat_msg = ""
    # *** ADDED Sentiment column default ***
    news_dataframe_value = pd.DataFrame(columns=["Date", "Headline", "Source", "Sentiment"]) # Default empty DF

    # Simple keyword-based sentiment simulation
    positive_keywords = ['profit', 'growth', 'up', 'gain', 'strong', 'positive', 'record', 'expand']
    negative_keywords = ['loss', 'down', 'drop', 'fall', 'weak', 'negative', 'risk', 'warn', 'cut']

    def get_simulated_sentiment(headline):
        """Simulates sentiment based on keywords."""
        headline_lower = headline.lower()
        has_positive = any(word in headline_lower for word in positive_keywords)
        has_negative = any(word in headline_lower for word in negative_keywords)
        if has_positive and not has_negative: return "Positive (+)"
        if has_negative and not has_positive: return "Negative (-)"
        # Could add more nuanced checks here
        return "Neutral (=)"

    if news_vars_ok:
        try: nc = NewsDataConnector(); news_list = nc.fetch_financial_news(count=10)
        except Exception as e: logging.error(f"News Fetch Err: {e}", exc_info=True); news_stat_msg = f"(Error: {type(e).__name__})"
    else: news_stat_msg = f"(Config Error)"

    news_data_for_df: List[List[str]] = []
    if news_list:
        for n in news_list:
            headline = n.get('title', 'No Title')
            sentiment = get_simulated_sentiment(headline) # Simulate sentiment
            news_data_for_df.append([
                n.get('published', 'N/A')[:10],
                headline,
                n.get('source_id', 'Unknown'),
                sentiment # Add sentiment value
            ])
        # *** ADDED Sentiment column name ***
        news_dataframe_value = pd.DataFrame(news_data_for_df, columns=["Date", "Headline", "Source", "Sentiment"])
        news_status_msg = f"{len(news_list)} articles loaded."
        logging.info(news_status_msg)
    else:
        news_status_msg = f"No news found {news_stat_msg}."
        logging.warning(news_status_msg)

    # --- Agent Analysis powered by Microsoft Agent Framework ---
    strat_opts: Dict[str, StrategyOptionModel] = {}
    analysis_out = "AI analysis pending..."
    raw_resp = ""
    news_payload = [
        {"date": row[0], "headline": row[1], "source": row[2], "sentiment": row[3]}
        for row in news_data_for_df
    ] if news_list else []

    if agent_vars_ok and (fin_summary or sf_data):
        try:
            agent_runner = get_finance_agent()
            result = agent_runner.analyze(
                fin_summary,
                proc_sap_data.get('top_customers', []),
                sf_data,
                news_payload,
            )
            analysis_out = result.insights_markdown or "No insights generated."
            strat_opts = result.options
            raw_resp = result.raw_text or ""
            logging.info("Agent framework analysis completed successfully.")
            if result.structured and result.structured.option_ranking_notes:
                notes = "\n".join(f"- {note}" for note in result.structured.option_ranking_notes if note.strip())
                if notes:
                    analysis_out = f"{analysis_out}\n\n**Option Sequencing Notes**\n{notes}"
        except Exception as agent_error:
            logging.error(f"Agent framework analysis failed: {agent_error}", exc_info=True)
            analysis_out = f"AI analysis error: {agent_error}"
    else:
        analysis_out = f"AI analysis skipped: {'Agent configuration error' if not agent_vars_ok else 'Insufficient data'}."

    # --- Update Global & HTML ---
    ICON_MAP = {"Option 1": "[Growth]", "Option 2": "[Efficiency]", "Option 3": "[Resilience]"}

    def _pending_option() -> StrategyOptionModel:
        return StrategyOptionModel(
            title="Pending",
            narrative="Strategy option will populate after a successful analysis run.",
            kpis=[],
            actions=[],
            risks=[],
            severity=InsightSeverity.MEDIUM,
            time_horizon=TimeHorizon.MID_TERM,
            confidence=50,
            owner=None,
        )

    global global_options
    global_options.clear()
    global_options.update(strat_opts or {})

    option_cards = []
    for key in ["Option 1", "Option 2", "Option 3"]:
        option_model = strat_opts.get(key) or _pending_option()
        option_cards.append(render_option_html(key, option_model, ICON_MAP.get(key, key)))
        global_options[key] = option_model

    option_1_html, option_2_html, option_3_html = option_cards

    # --- Create Status Summary ---
    status_summary_parts = []
    if '✅ OK' in sap_conn_status: status_summary_parts.append("SAP: Connected")
    elif '❌' in sap_conn_status: status_summary_parts.append(f"SAP: {sap_conn_status}") # Include error details
    else: status_summary_parts.append(f"SAP: Unknown Status ({sap_conn_status})")

    if news_list: status_summary_parts.append("News: OK")
    elif news_stat_msg: status_summary_parts.append(f"News: {news_stat_msg}")
    else: status_summary_parts.append("News: Status Unknown")

    if 'AI analysis error' in analysis_out or 'Agent setup fail' in analysis_out:
        status_summary_parts.append("AI Analysis: Error")
    elif 'AI analysis skipped' in analysis_out:
         status_summary_parts.append("AI Analysis: Skipped")
    else:
         status_summary_parts.append("AI Analysis: OK")

    status_summary = " | ".join(status_summary_parts)
    # Add styling based on overall status (simple check for any error)
    status_class = "status-ok"
    if "❌" in status_summary or "Error" in status_summary or "Skipped" in status_summary:
        status_class = "status-error"

    status_md = f"<div class='status-bar {status_class}'>Status: {status_summary}</div>"

    # --- Final Logging & Return ---
    end_time = time.time()
    logging.info(f"--- Analysis Complete --- ({end_time - start_time:.2f}s)")
    # Return analysis_out for the UI textbox
    return (gr.Markdown(kpi_md), gr.Markdown(status_md), sap_summary_html, sf_summary_html, analysis_out, news_dataframe_value,
            fig_pie, fig_bar_cust, fig_line_trend, fig_bar_sf,
            option_1_html, option_2_html, option_3_html)

# Update details box based on Radio selection
def update_option(choice):
    if not global_options:
        return "Options not generated. Please refresh."

    selected_option = global_options.get(choice)
    if selected_option is None:
        return f"Details for {choice} not found."

    if isinstance(selected_option, StrategyOptionModel):
        meta = f"**Profile:** {selected_option.severity.value.title()} | {selected_option.time_horizon.value} | {selected_option.confidence}% confidence"
        owner_line = f"**Owner:** {selected_option.owner}" if selected_option.owner else None
        sections = [f"### {selected_option.title}", meta, selected_option.narrative]
        if owner_line:
            sections.append(owner_line)
        if selected_option.actions:
            sections.append("**Key Actions**")
            sections.extend(f"- {item}" for item in selected_option.actions)
        if selected_option.kpis:
            sections.append("**KPIs to Watch**")
            sections.extend(f"- {item}" for item in selected_option.kpis)
        if selected_option.risks:
            sections.append("**Risks / Dependencies**")
            sections.extend(f"- {item}" for item in selected_option.risks)
        return "\n".join(sections)

    try:
        if isinstance(selected_option, str) and selected_option.strip().startswith('{'):
            return json.dumps(json.loads(selected_option), indent=2)
        return str(selected_option)
    except Exception as err:
        logging.warning(f"Error formatting detail for {choice}: {err}")
        return str(selected_option)

# Confirm and dispatch email - Restore detailed HTML Body
def confirm_selection(choice):
    """Handles option confirmation and email dispatch via Logic App."""
    logging.info(f"Confirming selection: {choice}")
    load_dotenv()

    # Check env vars
    logic_app_ok, logic_app_msg = check_env_vars("LOGICAPP_ENDPOINT", "EMAIL_RECIPIENT")
    if not logic_app_ok:
        return f"✖ Config Error: {logic_app_msg}. Ensure EMAIL_RECIPIENT is set."

    recipient_addr = os.getenv("EMAIL_RECIPIENT")
    logging.info(f"Read EMAIL_RECIPIENT. Value: '{recipient_addr}'")
    if not recipient_addr:
        return "✖ Config Error: EMAIL_RECIPIENT missing/empty."

    # Check options
    if not global_options:
        return "✖ Error: Options missing. Refresh first."
    option_value = global_options.get(choice)
    if option_value is None:
        return f"✖ Error: Invalid content for {choice}."

    subject = f"CFO Strategy Pick: {choice} - Ready for Review"

    # Helper to format details (handles JSON-like strings)
    def format_email_detail(key):
        """Formats option detail for HTML email, handling JSON."""
        detail = global_options.get(key, "N/A")
        escaped_detail = ""
        try:
            if isinstance(detail, StrategyOptionModel):
                actions = "".join(f"<li>{html.escape(item)}</li>" for item in detail.actions) or "<li>Define next steps...</li>"
                kpis = "".join(f"<li>{html.escape(item)}</li>" for item in detail.kpis)
                risks = "".join(f"<li>{html.escape(item)}</li>" for item in detail.risks)
                meta = f"{detail.severity.value.title()} | {detail.time_horizon.value} | {detail.confidence}% confidence"
                owner_line = f"<p style='margin: 5px 0;'><strong>Owner:</strong> {html.escape(detail.owner)}</p>" if detail.owner else ""
                kpi_section = f"<p style=\"margin: 5px 0;\"><strong>KPIs to Watch</strong></p><ul>{kpis}</ul>" if kpis else ""
                risk_section = f"<p style=\"margin: 5px 0;\"><strong>Risks</strong></p><ul>{risks}</ul>" if risks else ""
                escaped_detail = (
                    f"<p style='margin: 5px 0;'><em>{html.escape(meta)}</em></p>"
                    f"<p style='margin: 5px 0;'>{html.escape(detail.narrative)}</p>"
                    f"{owner_line}"
                    f"<p style='margin: 5px 0;'><strong>Key Actions</strong></p><ul>{actions}</ul>"
                    f"{kpi_section}{risk_section}"
                )
                return escaped_detail
            is_json_like = isinstance(detail, str) and detail.strip().startswith('{')
            if is_json_like:
                parsed = json.loads(detail)
                pretty_json = json.dumps(parsed, indent=2)
                # Use <pre> for formatted JSON, escape it
                escaped_detail = f"<pre style='background:#f0f0f0; padding:8px; border-radius:4px; color:#333; border: 1px solid #ddd; white-space: pre-wrap; word-wrap: break-word;'>{html.escape(pretty_json)}</pre>"
            else:
                # Use <p> for plain text, escape it
                escaped_detail = f"<p style='margin: 5px 0;'>{html.escape(str(detail))}</p>"
        except Exception as fmt_e:
            logging.warning(f"Could not format detail for '{key}' as JSON for email: {fmt_e}")
            escaped_detail = f"<p style='margin: 5px 0;'>{html.escape(str(detail))}</p>" # Fallback
        return escaped_detail

    # *** FIX: Restore detailed HTML body structure ***
    email_body = f"""<!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>{html.escape(subject)}</title>
      <style>
        body {{ font-family:'Segoe UI', sans-serif; line-height: 1.6; color: #333; margin: 20px; }}
        h2 {{ color: #0F766E; border-bottom: 2px solid #99F6E4; padding-bottom: 8px; }}
        .container {{ background: #F8FAFC; padding: 20px; border-radius: 8px; border: 1px solid #E2E8F0; }}
        .option-block {{ margin-bottom: 20px; padding: 15px; border: 1px solid #E2E8F0; border-radius: 5px; background: #FFFFFF; }}
        .option-block strong {{ color: #0D9488; font-size: 1.1em; display: block; margin-bottom: 5px;}}
        .option-block pre {{ background-color: #F1F5F9; padding: 10px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 0.95em; border: 1px solid #E2E8F0; color: #333; margin: 0; }}
        .option-block p {{ margin: 5px 0; }}
        .selected-section {{ margin-top: 25px; padding-top: 15px; border-top: 1px solid #CBD5E1; }}
        .selected-highlight {{ background: #EFF6FF; color: #1D4ED8; padding: 12px 15px; border-radius: 5px; font-size: 1.1em; display: inline-block; border: 1px solid #BFDBFE; }}
        .footer {{ margin-top: 25px; font-style: italic; color: #64748B; font-size: 0.9em; }}
      </style>
    </head>
    <body>
      <div class="container">
        <h2>Final Strategic Options to Pick</h2>
        <p>The CFO office team has completed deep research using our AI-driven Agentic workflow. We request your input on these strategic options for our upcoming weekly Finance Group call.</p>

        <div class="option-block">
          <strong>Option 1: Growth [Growth]</strong>
          {format_email_detail("Option 1")}
        </div>

        <div class="option-block">
          <strong>Option 2: Efficiency [Efficiency]</strong>
          {format_email_detail("Option 2")}
        </div>

        <div class="option-block">
          <strong>Option 3: Resilience [Resilience]</strong>
          {format_email_detail("Option 3")}
        </div>

        <div class="selected-section">
          <p>
            <span class="selected-highlight">
              Final Selected Option by CFO office: <strong>{html.escape(choice)}</strong>
            </span>
          </p>
          <p style="margin-top: 10px;"><i>AI Agentic generated Email. Click on blue option button below [Placeholder for Logic App Options if used]</i></p>
        </div>

        <p class="footer">Thank you,<br>AI-Agents Finance Automated Team</p>
      </div>
    </body>
    </html>
    """

    # Payload uses "Recipient" key as per schema
    payload = {
        "Recipient": recipient_addr,
        "Subject": subject,
        "Body": email_body
    }
    endpoint_url = os.getenv("LOGICAPP_ENDPOINT")

    logging.info(f"Dispatching to {endpoint_url} for Recipient: '{payload['Recipient']}'")
    logging.debug(f"Payload Body (start): {email_body[:200]}...") # Log start of body

    try:
        headers = {'Content-Type': 'application/json'}
        r = requests.post(endpoint_url, json=payload, headers=headers, timeout=45)
        r.raise_for_status()
        logging.info(f"Dispatch successful. Status: {r.status_code}")
        return f"✔ Dispatched '{choice}' details to {recipient_addr}!"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code; text = e.response.text[:500]
        logging.error(f"HTTP Error {status} calling Logic App: {text}", exc_info=True)
        err_msg=f"HTTP {status}."+(" Check payload vs schema (Recipient,Subject,Body strings)." if status==400 else " Chk auth." if status in[401,403] else " Chk URL." if status==404 else " LA err?" if status>=500 else "")
        return f"✖ Dispatch Failed: {err_msg}"
    except requests.exceptions.ConnectionError as e: logging.error(f"Conn Err:{e}"); return f"✖ Dispatch Failed: Cannot connect."
    except requests.exceptions.Timeout as e: logging.error(f"Timeout Err:{e}"); return f"✖ Dispatch Failed: Timeout."
    except Exception as e: logging.error(f"Dispatch Err:{e}",exc_info=True); return f"✖ Dispatch Failed: Unexp err - {type(e).__name__}."

# Generate System Flow Diagram - Definitive Fix for fillcolor v2
def generate_agent_flow():
    """Generates SVG diagram of the system flow."""
    logging.info("Generating system flow diagram.")
    try:
        dot = Digraph(comment='Insight Dashboard Flow')
        dot.attr(rankdir='TB', size='10,8', bgcolor='transparent',
                 label='System Flow Diagram', fontname='Segoe UI', fontsize='14',
                 labeljust='l', compound='true')

        # Node Styles
        node_attrs = {'style': 'filled', 'fontname': 'Segoe UI', 'fontsize': '10'}
        data_src_style = {**node_attrs, 'shape': 'cylinder', 'fillcolor': '#374151', 'fontcolor': '#E5E7EB'}
        agent_style = {**node_attrs, 'shape': 'box', 'fillcolor': '#4B5563', 'fontcolor': '#E5E7EB'}
        action_style = {**node_attrs, 'shape': 'box', 'fillcolor': '#059669', 'fontcolor': '#D1FAE5'}
        external_style = {**node_attrs, 'shape': 'box', 'fillcolor': '#7C2D12', 'fontcolor': '#FFEDD5'}
        # ui_node_style removed as we define explicitly

        # Edge styles
        edge_attrs = {'arrowhead': 'vee', 'fontsize': '9', 'fontname': 'Segoe UI', 'color': '#9CA3AF'}
        ctrl_edge = {**edge_attrs, 'style': 'dashed'}
        data_edge = {**edge_attrs, 'style': 'solid'}

        # Define Nodes explicitly
        dot.node("SAP", "SAP System", **data_src_style)
        dot.node("NEWS_API", "News API", **data_src_style)
        dot.node("SF_DUMMY", "Salesforce (Sim.)", **data_src_style)

        with dot.subgraph(name='cluster_ui') as ui_cluster:
            ui_cluster.attr(label='Gradio UI', style='filled', color='#374151',
                            fontcolor='#E5E7EB', fontname='Segoe UI', fontsize='12')
            # *** FIX: Define ALL attributes explicitly, do not spread node_attrs ***
            ui_cluster.node("UI_INPUT", "User Input", style='filled', fontname='Segoe UI',
                            fontsize='10', shape='ellipse', fillcolor='#1F2937', fontcolor='#E5E7EB')
            ui_cluster.node("UI_DISPLAY", "Dashboard Display", style='filled', fontname='Segoe UI',
                            fontsize='10', shape='box', fillcolor='#1F2937', fontcolor='#E5E7EB')
            # Action nodes use their specific style correctly
            ui_cluster.node("REFRESH_BTN", "Refresh", **action_style)
            ui_cluster.node("CONFIRM_BTN", "Confirm", **action_style)

        with dot.subgraph(name='cluster_agents') as agent_cluster:
            agent_cluster.attr(label='Agent Framework', style='filled', color='#4B5563',
                               fontcolor='#E5E7EB', fontname='Segoe UI', fontsize='12')
            agent_cluster.node("MAF_MARKET", "Market Intel", **agent_style)
            agent_cluster.node("MAF_FIN", "Finance Pulse", **agent_style)
            agent_cluster.node("MAF_RISK", "Risk Monitor", **agent_style)
            agent_cluster.node("MAF_STRAT", "Strategy Synthesiser", **agent_style)
            agent_cluster.node("MAF_NARR", "Board Narrative", **agent_style)

        dot.node("LOGIC_APP", "Logic App (Email)", **external_style)

        # Edges (remain the same)
        dot.edge("REFRESH_BTN", "SAP", label="Fetch", **ctrl_edge)
        dot.edge("REFRESH_BTN", "NEWS_API", label="Fetch", **ctrl_edge)
        dot.edge("REFRESH_BTN", "SF_DUMMY", label="Fetch", **ctrl_edge)
        dot.edge("REFRESH_BTN", "MAF_MARKET", label="Trigger", **ctrl_edge)
        dot.edge("REFRESH_BTN", "MAF_FIN", label="Trigger", **ctrl_edge)
        dot.edge("REFRESH_BTN", "MAF_RISK", label="Trigger", **ctrl_edge)
        dot.edge("MAF_MARKET", "MAF_STRAT", label="Market packets", **data_edge)
        dot.edge("MAF_FIN", "MAF_STRAT", label="Finance packets", **data_edge)
        dot.edge("MAF_RISK", "MAF_STRAT", label="Risk packets", **data_edge)
        dot.edge("MAF_STRAT", "MAF_NARR", label="Options + briefs", **data_edge)
        dot.edge("MAF_NARR", "UI_DISPLAY", label="Narrative & KPIs", **data_edge, lhead='cluster_ui')
        dot.edge("UI_INPUT", "CONFIRM_BTN", label="Select", **ctrl_edge)
        dot.edge("CONFIRM_BTN", "LOGIC_APP", label="5. Dispatch", **ctrl_edge)

        svg_output = dot.pipe(format='svg', encoding='utf-8')
        logging.info("Flow diagram generated successfully.")
        return svg_output

    except FileNotFoundError:
        err_msg = "Error: Graphviz 'dot' command not found. Ensure Graphviz installed & in PATH."
        logging.error(err_msg)
        return f"<div class='graphviz-error'>{err_msg}</div>"
    except Exception as e:
        logging.error(f"Diagram generation error: {e}", exc_info=True)
        return f"<div class='graphviz-error'>Diagram Error: {e}.</div>"

# CSS for Enhanced CFO Dashboard
default_css = """
:root {
    --surface: rgba(255, 255, 255, 0.96);
    --surface-alt: rgba(255, 255, 255, 0.82);
    --surface-strong: #ffffff;
    --primary: #2563EB;
    --primary-soft: #BFDBFE;
    --accent: #F97316;
    --success: #10B981;
    --danger: #EF4444;
    --text-strong: #0F172A;
    --text-secondary: #475569;
}
body, html {
    font-family: 'Inter', 'Segoe UI', sans-serif;
    background: radial-gradient(circle at 20% 20%, #ECFEFF 0%, #E0F2FE 45%, #EEF2FF 100%);
    color: var(--text-strong);
    font-size: 15px;
}
.gradio-container {
    max-width: 1400px;
    margin: auto;
    padding: 1.6rem 1.5rem 2.6rem;
}

/* KPI Bar */
.kpi-container {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    background: linear-gradient(120deg, rgba(37, 99, 235, 0.94), rgba(16, 185, 129, 0.9));
    padding: 20px 26px;
    border-radius: 20px;
    box-shadow: 0 22px 45px rgba(15, 23, 42, 0.18);
    margin-bottom: 32px;
    border: 1px solid rgba(255, 255, 255, 0.18);
}
.kpi-item {
    flex: 1;
    min-width: 160px;
    text-align: left;
    padding: 14px 18px;
    border-right: 1px solid rgba(255, 255, 255, 0.25);
    color: #F8FAFC;
    backdrop-filter: blur(8px);
}
.kpi-item:last-child { border-right: none; }
.kpi-value {
    display: block;
    font-size: 1.75rem;
    font-weight: 700;
    color: #FDFDFE;
    line-height: 1.25;
    letter-spacing: -0.02em;
}
.kpi-label {
    display: block;
    font-size: 0.9rem;
    color: rgba(241, 245, 249, 0.85);
    margin-top: 6px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}

/* Header & Summary Cards */
.header-row {
    display: flex;
    flex-wrap: wrap;
    gap: 28px;
    margin-bottom: 28px;
}
.summary-card {
    flex: 1 1 360px;
    padding: 22px 26px;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(219, 234, 254, 0.82));
    border-radius: 18px;
    box-shadow: 0 20px 40px rgba(15, 23, 42, 0.12);
    border: 1px solid rgba(148, 163, 184, 0.24);
    min-width: 320px;
    position: relative;
    overflow: hidden;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.summary-card::after {
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at top right, rgba(59, 130, 246, 0.18), transparent 60%);
    pointer-events: none;
}
.summary-card:hover {
    transform: translateY(-6px);
    box-shadow: 0 26px 50px rgba(30, 64, 175, 0.18);
}
.summary-card h2 {
    font-size: 1.25rem;
    color: var(--text-strong);
    margin: 0 0 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 10px;
}
.summary-card h2::before {
    content: "";
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background-color: var(--primary);
    box-shadow: 0 0 0 6px rgba(37, 99, 235, 0.15);
}
.summary-card.connected h2::before {
    background-color: var(--success);
    box-shadow: 0 0 0 6px rgba(16, 185, 129, 0.2);
}
.summary-card.error h2::before {
    background-color: var(--danger);
    box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.2);
}
.summary-card p {
    font-size: 0.95rem;
    color: var(--text-secondary);
    margin: 6px 0;
    line-height: 1.55;
}
.summary-card pre {
    background-color: rgba(239, 246, 255, 0.85);
    padding: 12px;
    border-radius: 10px;
    overflow-x: auto;
    font-size: 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.24);
    margin-top: 12px;
    color: #1F2937;
    max-height: 190px;
    overflow-y: auto;
}
.summary-card .error-text {
    color: var(--danger);
    font-weight: 600;
    font-size: 0.9rem;
}

/* Option Boxes */
.option-box {
    background: var(--surface);
    color: var(--text-strong);
    padding: 22px 26px;
    border-radius: 16px;
    margin: 16px 0;
    border: 1px solid rgba(148, 163, 184, 0.24);
    box-shadow: 0 18px 36px rgba(100, 116, 139, 0.12);
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    backdrop-filter: blur(6px);
}
.option-box:hover {
    transform: translateY(-4px);
    box-shadow: 0 28px 45px rgba(37, 99, 235, 0.14);
}
.option-box h3 {
    margin: 0 0 16px;
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--primary);
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    padding-bottom: 12px;
}
.option-box .option-content {
    font-size: 0.92rem;
    line-height: 1.7;
}
.option-box .option-content p { margin-bottom: 0.6em; }
.option-box .option-content code {
    display: block;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 260px;
    overflow-y: auto;
    background: rgba(248, 250, 252, 0.9);
    padding: 14px;
    border-radius: 10px;
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: 0.85rem;
    color: var(--text-strong);
    border: 1px solid rgba(148, 163, 184, 0.26);
}
.option-box .option-content code::-webkit-scrollbar { width: 6px; }
.option-box .option-content code::-webkit-scrollbar-track { background: rgba(226, 232, 240, 0.8); border-radius: 3px; }
.option-box .option-content code::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.7); border-radius: 3px; }
.option-box .option-content code::-webkit-scrollbar-thumb:hover { background: rgba(100, 116, 139, 0.8); }

/* Buttons */
.gr-button {
    margin-top: 10px;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 11px 18px !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.02em;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
.gr-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 24px rgba(59, 130, 246, 0.18) !important;
}
button.primary {
    background: linear-gradient(120deg, #2563EB, #38BDF8) !important;
    border: none !important;
    color: #F8FAFC !important;
}
button.primary:hover {
    background: linear-gradient(120deg, #1D4ED8, #2563EB) !important;
}
button.secondary {
    background: linear-gradient(120deg, rgba(255, 255, 255, 0.9), rgba(226, 232, 240, 0.9)) !important;
    border: 1px solid rgba(148, 163, 184, 0.45) !important;
    color: var(--text-strong) !important;
}
button.secondary:hover {
    border-color: rgba(37, 99, 235, 0.45) !important;
    color: #1D4ED8 !important;
}
.sturdy {
    background: linear-gradient(120deg, #F97316, #FB923C) !important;
    border: none !important;
    color: #451A03 !important;
}
.sturdy:hover {
    background: linear-gradient(120deg, #EA580C, #F97316) !important;
    color: #FFF7ED !important;
}

/* Confirmation/Status Box */
#confirm-message textarea {
    font-weight: 500;
    font-size: 0.95rem !important;
    border-radius: 10px !important;
    border: 1px solid rgba(148, 163, 184, 0.35) !important;
    background-color: rgba(249, 250, 251, 0.95) !important;
}

/* Flow Diagram Styling */
#flow-diagram {
    background: var(--surface-alt);
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 18px 28px rgba(15, 23, 42, 0.12);
    border: 1px solid rgba(148, 163, 184, 0.24);
    margin-top: 12px;
    backdrop-filter: blur(6px);
}
#flow-diagram svg { width: 100%; height: auto; display: block; }
.graphviz-error {
    color: var(--danger);
    background-color: rgba(254, 242, 242, 0.92);
    padding: 15px;
    border: 1px solid rgba(248, 113, 113, 0.6);
    border-radius: 10px;
    font-weight: 600;
}

/* Tab Styling */
.gr-tabs { margin-top: 24px; }
.gr-tabitem {
    background: var(--surface);
    padding: 28px;
    border-radius: 0 18px 18px 18px;
    box-shadow: 0 20px 36px rgba(15, 23, 42, 0.12);
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-top: none;
    backdrop-filter: blur(8px);
}

/* Accordion Styling */
.gr-accordion {
    margin-bottom: 16px;
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(255, 255, 255, 0.92);
}
.gr-accordion > .gr-block { border: none; }
.gr-accordion button[aria-expanded] {
    background: rgba(226, 232, 240, 0.65);
    padding: 12px 18px;
    font-weight: 600;
    color: var(--text-strong);
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}
.gr-accordion button[aria-expanded]:hover { background: rgba(191, 219, 254, 0.7); }
.gr-accordion > div { padding: 16px; }

/* Plotly Chart Styling */
.plotly-chart {
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(148, 163, 184, 0.24);
    margin-top: 12px;
    min-height: 360px;
    background: var(--surface-strong);
    box-shadow: 0 18px 32px rgba(15, 23, 42, 0.12);
}

/* Textbox & Markdown Styling */
.gr-textbox textarea, .gr-markdown {
    font-size: 0.96rem !important;
    line-height: 1.65 !important;
    color: var(--text-strong);
}
.gr-textbox[aria-label*='Insights'] textarea,
.gr-markdown[aria-label*='Headlines'] {
    background: rgba(248, 250, 252, 0.95);
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.24);
}
.gr-markdown h4 {
    font-weight: 600;
    margin-bottom: 10px;
    color: var(--primary);
    letter-spacing: 0.02em;
}
.gr-markdown p { margin-bottom: 6px; }
.gr-markdown em { color: var(--text-secondary); }

/* Radio Button Styling */
.gr-radio .gr-form { gap: 12px !important; }
.gr-radio label span {
    font-size: 1rem !important;
    font-weight: 500;
    color: var(--text-strong);
}

/* Status Bar */
.status-bar {
    padding: 10px 18px;
    margin-bottom: 22px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 0.95rem;
    text-align: center;
    border: 1px solid transparent;
    box-shadow: 0 16px 30px rgba(15, 23, 42, 0.12);
}
.status-ok {
    background: linear-gradient(120deg, rgba(16, 185, 129, 0.92), rgba(74, 222, 128, 0.92));
    color: #ECFDF5;
    border-color: rgba(5, 150, 105, 0.45);
}
.status-error {
    background: linear-gradient(120deg, rgba(239, 68, 68, 0.92), rgba(248, 113, 113, 0.92));
    color: #FEF2F2;
    border-color: rgba(220, 38, 38, 0.45);
}

/* Dataframe Sentiment Styling */
.dataframe-container table.table td:nth-child(4):contains('Positive') {
    color: #22C55E;
    font-weight: 600;
}
.dataframe-container table.table td:nth-child(4):contains('Negative') {
    color: #F87171;
    font-weight: 600;
}
.dataframe-container table.table td:nth-child(4):contains('Neutral') {
    color: var(--text-secondary);
}
"""

# Gradio UI Definition - Added Status Bar, Sentiment Column
with gr.Blocks(title="📊 CFO Financial Insight Dashboard", css=default_css, theme=gr.themes.Soft(primary_hue="teal", secondary_hue="blue")) as demo:

    gr.Markdown("# CFO Financial Insight Dashboard") # Main Title

    # --- KPI Row ---
    with gr.Row():
         kpi_display = gr.Markdown(value="Initializing KPIs...")

    # *** ADDED Status Bar Display ***
    with gr.Row(): status_display = gr.Markdown(value="")

    with gr.Tabs():
        # --- Main Analysis Tab ---
        with gr.TabItem("📈 Performance & Analysis", id="tab-main"):
            with gr.Row():
                run_btn = gr.Button("🔄 Refresh Dashboard & Run AI Analysis", variant="primary", scale=1)

            with gr.Row(equal_height=False):
                with gr.Column(scale=2): # Wider column for summaries
                    with gr.Row():
                        sap_summary_html = gr.HTML("<section class='summary-card'><p>Awaiting SAP...</p></section>")
                        sf_summary_html = gr.HTML("<section class='summary-card'><p>Awaiting Salesforce...</p></section>")
                    with gr.Accordion("🤖 AI Analysis & Insights", open=True):
                        analysis_box = gr.Textbox(lines=15, interactive=False, label="AI Insights", placeholder="Insights from Market, Finance, and News analysis...")
                with gr.Column(scale=1): # Narrower column for news
                    with gr.Accordion("📰 News Headlines & Sentiment", open=True): # Renamed Accordion
                        # *** UPDATE: Add Sentiment column ***
                        news_table = gr.Dataframe(
                            headers=["Date", "Headline", "Source", "Sentiment"],
                            datatype=["str", "str", "str", "str"], # Add str type for Sentiment
                            row_count=(5, "dynamic"),
                            col_count=(4, "fixed"), # Now 4 columns
                            # Adjust column widths if needed, e.g., make Headline wider
                            # column_widths=["10%", "50%", "20%", "20%"],
                            wrap=True,
                            label=None,
                            elem_classes="dataframe-container"
                        )

            with gr.Row(): gr.Markdown("---") # Separator

            with gr.Row(equal_height=False):
                 with gr.Column(scale=1, min_width=350):
                    gr.Markdown("#### Revenue by Currency (SAP)")
                    revenue_pie_chart = gr.Plot(elem_classes="plotly-chart", show_label=False)
                 with gr.Column(scale=1, min_width=350):
                    gr.Markdown("#### Top Customers by Sales (SAP)")
                    customer_bar_chart = gr.Plot(elem_classes="plotly-chart", show_label=False)
                 with gr.Column(scale=1, min_width=350):
                    gr.Markdown("#### Simulated Sales Trend (Monthly)")
                    sales_trend_line_chart = gr.Plot(elem_classes="plotly-chart", show_label=False)
                 with gr.Column(scale=1, min_width=350):
                    gr.Markdown("#### Top Open Deals (Salesforce)")
                    sf_deals_bar_chart = gr.Plot(elem_classes="plotly-chart", show_label=False)

        # --- Strategic Options Tab ---
        with gr.TabItem("🎯 Strategic Options & Dispatch", id="tab-options"):
            gr.Markdown("### 🚩 AI-Generated Strategic Options Review")
            gr.Markdown("Select one option generated from the analysis for further discussion and validation by SMEs.")
            with gr.Row(equal_height=False): # Allow option boxes to have different heights
                with gr.Column(scale=1, min_width=350): option_html1 = gr.HTML()
                with gr.Column(scale=1, min_width=350): option_html2 = gr.HTML()
                with gr.Column(scale=1, min_width=350): option_html3 = gr.HTML()

            gr.Markdown("#### Select and Dispatch Option:")
            with gr.Row():
                with gr.Column(scale=3):
                    option_radio = gr.Radio(["Option 1", "Option 2", "Option 3"], label="Choose Strategy", info="Select an option to view details.", value="Option 1")
                    selected_box = gr.Textbox(lines=10, interactive=False, label="Selected Option Details", placeholder="Details of the chosen option...")
                with gr.Column(scale=1, min_width=200):
                    gr.Markdown("&nbsp;") # Spacer for alignment
                    confirm_btn = gr.Button("✅ Confirm & Dispatch to SMEs", variant="secondary", elem_classes="sturdy")
                    confirmation_msg = gr.Textbox(lines=3, interactive=False, label="Dispatch Status", elem_id="confirm-message", placeholder="Email dispatch status...")

        # --- System Flow Tab ---
        with gr.TabItem("🔗 System Flow", id="tab-flow"):
            gr.Markdown("### Agent Interaction & Data Flow Diagram")
            with gr.Row(): flow_btn = gr.Button("▶️ Generate Flow Diagram", variant="secondary", scale=1)
            with gr.Row(): flow_html = gr.HTML(label="System Flow", elem_id="flow-diagram", value="Click button to generate diagram...")

    # --- Event Handlers ---
    run_btn.click(
        fn=run_dashboard_analysis,
        outputs=[
            kpi_display,
            status_display, # *** ADDED status display output ***
            sap_summary_html, sf_summary_html,
            analysis_box,
            news_table,
            revenue_pie_chart, customer_bar_chart,
            sales_trend_line_chart, sf_deals_bar_chart,
            option_html1, option_html2, option_html3
        ],
        api_name="run_analysis"
    )
    option_radio.change(fn=update_option, inputs=option_radio, outputs=selected_box, api_name="update_option_display")
    confirm_btn.click(fn=confirm_selection, inputs=option_radio, outputs=confirmation_msg, api_name="confirm_and_dispatch")
    flow_btn.click(fn=generate_agent_flow, outputs=flow_html, api_name="generate_flow_diagram")

# Main Execution Block - Check for at least one Recipient Env Var
if __name__ == "__main__":
    print("--- CFO Dashboard (Fixed Desktop Dark) ---")
    print("Checking required environment variables...")
    # Define essential vars excluding recipient initially
    essential_base = ["SAP_USERNAME", "SAP_PASSWORD", "CURRENTS_API_KEY", "MODEL_DEPLOYMENT_NAME", "API_KEY", "AZURE_ENDPOINT", "LOGICAPP_ENDPOINT"]
    all_base_ok, base_msg = check_env_vars(*essential_base)

    # Check recipient separately
    mail_rec = os.getenv("MAIL_RECIPIENT")
    email_rec = os.getenv("EMAIL_RECIPIENT")
    recipient_ok = bool(mail_rec) or bool(email_rec) # True if at least one is set and not empty
    recipient_msg = ""
    if not recipient_ok:
        recipient_msg = "Missing environment variable: Neither MAIL_RECIPIENT nor EMAIL_RECIPIENT is set. Email dispatch will fail."
        logging.error(recipient_msg)

    # Combine results
    all_ok = all_base_ok and recipient_ok
    final_msg = base_msg + ("\n" + recipient_msg if not recipient_ok else "")

    if not all_ok: print(f"\n!!! WARNING: MISSING ENV VARS !!!\n{final_msg}\nFeatures WILL FAIL. Check .env file.\n")
    else: print("Essential environment variables seem set.")

    print("Launching Gradio Interface...")
    # Use 127.0.0.1 for local access only
    demo.launch(debug=True, server_name="127.0.0.1", server_port=7860)


