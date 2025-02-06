import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from autogen import AssistantAgent, UserProxyAgent

# Load environment variables from .env file
load_dotenv()

if __name__ == "__main__":
    main()
