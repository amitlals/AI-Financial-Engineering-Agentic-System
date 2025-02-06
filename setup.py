import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from autogen import AssistantAgent, UserProxyAgent

# Load environment variables from .env file
load_dotenv()

class DataConnector:
    def __init__(self):
        #self.base_url = "Fabric onelake link"
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        print(f"Configured Service URL: {self.base_url}")

    def test_connection(self):
        try:
            test_url = f"{self.base_url}/Products?$top=1&$format=json"
            print(f"Testing connection to: {test_url}")
            response = requests.get(test_url, headers=self.headers)
            response.raise_for_status()
            print("✅ Connection test successful")
            return True
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection Error: {str(e)}")
            return False

    def fetch_orders(self):
        try:
            url = f"{self.base_url}/Orders"
            params = {
                "$top": 20,
                "$format": "json",
                "$select": "OrderID,CustomerID,OrderDate,ShipCity,ShipCountry"
            }
            print(f"Fetching orders from: {url}")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            orders = data.get('d', [])
            print(f"✅ Successfully fetched {len(orders)} orders")
            return orders
        except Exception as e:
            print(f"Error fetching orders: {str(e)}")
            return []

    def fetch_products(self):
        try:
            url = f"{self.base_url}/Products"
            params = {
                "$top": 20,
                "$format": "json",
                "$select": "ProductID,ProductName,UnitPrice,UnitsInStock,CategoryID"
            }
            print(f"Fetching products from: {url}")
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            products = data.get('d', [])
            print(f"✅ Successfully fetched {len(products)} products")
            return products
        except Exception as e:
            print(f"Error fetching products: {str(e)}")
            return []

class NewsDataConnector:
    def __init__(self):
        self.api_key = os.getenv("CURRENTS_API_KEY")
        self.base_url = "https://api.currentsapi.services/v1/latest-news"
        if self.api_key:
            print("\n📰 News Data Connector initialized")
        else:
            print("\n⚠️ Currents API key not found in .env file - skipping news analysis")

    def fetch_financial_news(self):
        """Fetch relevant financial news using Currents API"""
        if not self.api_key:
            return []
            
        try:
            params = {
                "language": "en",
                "apiKey": self.api_key,
                "category": "business,finance"
            }
            
            print("Fetching financial news from Currents API...")
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            
            news_data = response.json()
            articles = news_data.get('news', [])
            
            processed_news = []
            for article in articles[:5]:
                processed_news.append({
                    'title': article.get('title', 'No title'),
                    'description': article.get('description', 'No description'),
                    'category': article.get('category', []),
                    'published': article.get('published', 'No date')
                })
            
            print(f"✅ Successfully fetched {len(processed_news)} news articles")
            return processed_news
            
        except Exception as e:
            print(f"❌ Error fetching news: {str(e)}")
            return []

def process_data(orders, products):
    """Process raw data into analyzable format"""
    try:
        for order in orders:
            if 'OrderDate' in order:
                timestamp = int(order['OrderDate'].replace('/Date(', '').replace(')/', ''))
                order['OrderDate'] = datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d')

        orders_analysis = {
            "total_orders": len(orders),
            "countries": list(set(order.get("ShipCountry", "") for order in orders)),
            "cities": list(set(order.get("ShipCity", "") for order in orders)),
            "customers": list(set(order.get("CustomerID", "") for order in orders))
        }

        products_analysis = {
            "total_products": len(products),
            "total_stock": sum(float(p.get("UnitsInStock", 0)) for p in products),
            "avg_price": sum(float(p.get("UnitPrice", 0)) for p in products) / len(products) if products else 0,
            "stock_value": sum(float(p.get("UnitsInStock", 0)) * float(p.get("UnitPrice", 0)) for p in products)
        }

        return {
            "orders_summary": orders_analysis,
            "products_summary": products_analysis,
            "sample_orders": orders[:5],
            "sample_products": products[:5]
        }
    except Exception as e:
        print(f"Error processing data: {str(e)}")
        return None

def setup_agents():
    """Setup AI agents with optimized prompts"""
    config_list = [{
        "model": os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4"),
        "api_key": os.getenv("API_KEY"),
        "azure_endpoint": os.getenv("AZURE_ENDPOINT"),
        "api_type": "azure",
        "api_version": os.getenv("MODEL_API_VERSION", "2024-02-15-preview")
    }]

    llm_config = {
        "config_list": config_list,
        "temperature": 0
    }

    coordinator = UserProxyAgent(
        name="coordinator",
        system_message="""Direct the analysis flow. Key rules:
        1. Never repeat previous analyses
        2. Only pass essential insights forward
        3. Keep communication focused and non-redundant""",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=1,
        llm_config=llm_config
    )

    market_agent = AssistantAgent(
        name="Market_Agent",
        system_message="""Analyze market data for:
        1. Key market opportunities
        2. Customer behavior trends
        3. Geographic insights
        Keep responses concise and non-repetitive.""",
        llm_config=llm_config
    )

    finance_agent = AssistantAgent(
        name="Finance_Agent",
        system_message="""Analyze financial metrics for:
        1. Performance optimization
        2. Cost efficiency
        3. Growth opportunities
        4. Risk assessment
        5. balance sheet analysis
        6. profit and loss analysis
        Provide unique insights only.""",
        llm_config=llm_config
    )

    news_agent = AssistantAgent(
        name="News_Agent",
        system_message="""Extract from news:
        1. Market impacts and opportunities
        2. Industry changes and trends
        3. Strategic implications for business
        Focus on unique, non-redundant insights.""",
        llm_config=llm_config
    )

    strategy_agent = AssistantAgent(
        name="Strategy_Agent",
        system_message="""Create strategic plan with:
        1. 3 unique strategic options
        2. Implementation roadmap for each option
        3. Risk-benefit analysis for each option
        4. Final recommendation and priority actions
        Build on previous insights without repetition.""",
        llm_config=llm_config
    )

    return coordinator, market_agent, finance_agent, news_agent, strategy_agent

def wait_for_user():
    """Prompt user to continue to next step"""
    input("\nPress Enter to continue to next analysis...")

def main():
    print("\n🚀 ERP Financial Analysis System")
    
    try:
        # Initialize connectors
        connector = DataConnector()
        if not connector.test_connection():
            return

        news_connector = NewsDataConnector()

        # Fetch and process data
        print("\n📊 Fetching Data...")
        orders = connector.fetch_orders()
        products = connector.fetch_products()

        if not orders or not products:
            print("❌ Failed to fetch basic data")
            return

        processed_data = process_data(orders, products)
        if not processed_data:
            print("❌ Failed to process data")
            return

        # Fetch news if available
        news_data = news_connector.fetch_financial_news()

        # Display summary
        print("\n📊 Data Summary:")
        print(f"Total Orders: {processed_data['orders_summary']['total_orders']}")
        print(f"Total Products: {processed_data['products_summary']['total_products']}")
        print(f"Total Stock Value: ${processed_data['products_summary']['stock_value']:,.2f}")
        if news_data:
            print(f"Total News Articles: {len(news_data)}")

        # Setup agents
        coordinator, market_agent, finance_agent, news_agent, strategy_agent = setup_agents()

        # Market Analysis
        print("\n📈 MARKET ANALYSIS")
        print("=" * 50)
        market_insights = coordinator.initiate_chat(
            market_agent,
            message="Extract key market insights: " + json.dumps(processed_data)
        )
        
        wait_for_user()

        # Financial Analysis
        print("\n💰 FINANCIAL ANALYSIS")
        print("=" * 50)
        finance_insights = coordinator.initiate_chat(
            finance_agent,
            message="Extract key financial insights: " + json.dumps(processed_data)
        )
        
        wait_for_user()

        # News Analysis if available
        news_insights = ""
        if news_data:
            print("\n📰 NEWS ANALYSIS")
            print("=" * 50)
            news_insights = coordinator.initiate_chat(
                news_agent,
                message="Extract key market implications: " + json.dumps(news_data)
            )
            wait_for_user()

        # Strategic Recommendations
        print("\n🎯 STRATEGIC RECOMMENDATIONS")
        print("=" * 50)
        
        strategy_prompt = f"""Develop strategic recommendations based on:

MARKET INSIGHTS:
{str(market_insights).strip()}

FINANCIAL INSIGHTS:
{str(finance_insights).strip()}"""

        if news_insights:
            strategy_prompt += f"""

NEWS INSIGHTS:
{str(news_insights).strip()}"""

        strategy_prompt += """

Provide:
1. Three distinct strategic options (each with implementation plan and ROI)
2. Risk assessment for each option
3. Final recommendation and priority actions

Keep focus on actionable steps without repeating analysis."""

        coordinator.initiate_chat(
            strategy_agent,
            message=strategy_prompt
        )

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")

if __name__ == "__main__":
    main()
