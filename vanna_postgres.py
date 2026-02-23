from vanna.integrations.postgres import PostgresRunner
from vanna import Agent
from vanna.core.agent.config import AgentConfig
from vanna.core.user import UserResolver, User, RequestContext
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.core.registry import ToolRegistry
from vanna.core.system_prompt import SystemPromptBuilder
from typing import List, Optional
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.integrations.postgres.storage import PostgresConversationStore
from vanna.core.tool import ToolSchema
# from vanna.core.tool import ToolContext
from vanna.core.user import User

from dotenv import load_dotenv
import os

# Load variables from .env
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
DB_HOST=os.getenv("DB_HOST")
DB_PORT=os.getenv("DB_PORT")
DB_NAME=os.getenv("DB_NAME")
DB_USER=os.getenv("DB_USER")
DB_PASSWORD=os.getenv("DB_PASSWORD")

# LLM Initialization
llm = OpenAILlmService(
    model="gpt-4o-mini",
    api_key=api_key
)

# Postgres Connection
postgres = PostgresRunner(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="require"
    )



print("Connected to PostgreSQL successfully!")


#SQL execution tool
run_sql_tool = RunSqlTool(
    sql_runner=postgres
)

print("✅ Vanna OpenAI + PostgreSQL wired successfully")


