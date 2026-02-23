# import asyncio
# import os
# import sys

# # Add the current directory to sys.path to ensure we can import if needed, 
# # though we'll likely define the classes inline to be self-contained and avoid the input() blocking.
# sys.path.append(os.getcwd())

# from typing import List, Optional
# from vanna import Agent
# from vanna.core.agent.config import AgentConfig
# from vanna.core.system_prompt import DefaultSystemPromptBuilder
# from vanna.core.tool import ToolSchema
# from vanna.core.user import User, UserResolver, RequestContext
# from vanna.tools import RunSqlTool
# from vanna.core.registry import ToolRegistry
# from vanna.integrations.openai import OpenAILlmService
# from vanna.integrations.postgres import PostgresRunner
# from vanna.integrations.local.agent_memory import DemoAgentMemory

# # --- REPEAT SCHEMA DEFINITION ---
# DB_SCHEMA = """
# RELATIONSHIPS:
# - users (1) → (1) accounts
# - users (1) → (1) user_profiles
# - users (1) → (N) contacts
# - users (1) → (N) user_selected_preferences → (N) user_preferences
# - accounts (1) → (N) workspaces
# - accounts (1) → (N) subscriptions → (N) subscription_plans
# - workspaces (1) → (N) workspace_tags
# - workspaces (1) → (N) lm_content
# - lm_content (1) → (N) lm_content_embedding
# - lm_content (1) → (N) lm_content_tag_mapping → (N) workspace_tags
# - users (1) → (N) chatbot_history
# - workspaces (1) → (N) chatbot_history

# IMPORTANT GLOBAL RULE:
# Always apply soft delete filtering in every query:
# WHERE is_active = true AND is_deleted = false

# TABLE DEFINITIONS:

# 1. users
# (id PK, email UNIQUE, password, role ENUM('user','admin'), name,
#  login_time, is_onboarding_completed, otp, otp_created_at,
#  subscription_type ENUM('free','pro','pro_plus'),
#  invitation_status, api_key, trial_start, trial_end, is_trial_active,
#  auth_provider ENUM('google','email'),
#  created_at, updated_at, is_active, is_deleted)
# """

# class SchemaSystemPromptBuilder(DefaultSystemPromptBuilder):
#     async def build_system_prompt(self, user: User, tools: List[ToolSchema]) -> str:
#         base_prompt = await super().build_system_prompt(user, tools) or ""
#         return base_prompt + f"\n\n# DATABASE SCHEMA AND RULES\nYou MUST follow these rules:\n{DB_SCHEMA}"

# class LocalUserResolver(UserResolver):
#     async def resolve_user(self, request_context: RequestContext) -> User:
#         return User(id="test_user", email="test@localhost", group_memberships=["admin"])

# async def main():
#     print("Initializing Agent...")

# from dotenv import load_dotenv
# import os

# # Load variables from .env
# load_dotenv()

# api_key = os.getenv("OPENAI_API_KEY")
# DB_HOST=os.getenv("DB_HOST")
# DB_PORT=os.getenv("DB_PORT")
# DB_NAME=os.getenv("DB_NAME")
# DB_USER=os.getenv("DB_USER")
# DB_PASSWORD=os.getenv("DB_PASSWORD")


    
    
# llm = OpenAILlmService(
#     model="gpt-4o-mini",
#     api_key=api_key
# )

# postgres = PostgresRunner(
#         host=DB_HOST,
#         port=DB_PORT,
#         database=DB_NAME,
#         user=DB_USER,
#         password=DB_PASSWORD
# )

# tools = ToolRegistry()
# tools.register_local_tool(RunSqlTool(sql_runner=postgres), access_groups=[])

# agent = Agent(
#     llm_service=llm,
#     tool_registry=tools,
#     user_resolver=LocalUserResolver(),
#     agent_memory=DemoAgentMemory(),
#     system_prompt_builder=SchemaSystemPromptBuilder(),
#     config=AgentConfig(include_thinking_indicators=False, stream_responses=False)
# )

# question = "How many active users are there?"
# print(f"\nAsking: '{question}'")

# context = RequestContext()
# async for component in agent.send_message(context, question):
#     if hasattr(component, 'simple_component') and component.simple_component:
#                 print(f"RESPONSE: {component.simple_component.text}")
#          elif hasattr(component, 'rich_component') and component.rich_component:
#                 # Try to print SQL if it's in a rich component (like StatusUpdate or similar)
#                 # Vanna 2.0 often puts the SQL in a tool execution status or similar.
#                 pass

# if __name__ == "__main__":
#     asyncio.run(main())


import asyncio
import os
import sys
from typing import List, Optional

from dotenv import load_dotenv
from vanna import Agent
from vanna.core.agent.config import AgentConfig
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.core.tool import ToolSchema
from vanna.core.user import User, UserResolver, RequestContext
from vanna.tools import RunSqlTool
from vanna.core.registry import ToolRegistry
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.postgres import PostgresRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory


# --- 1. Database Schema Definition ---

DB_SCHEMA = """
RELATIONSHIPS:
- users (1) → (1) accounts
- users (1) → (1) user_profiles
- users (1) → (N) contacts
- users (1) → (N) user_selected_preferences → (N) user_preferences
- accounts (1) → (N) workspaces
- accounts (1) → (N) subscriptions → (N) subscription_plans
- workspaces (1) → (N) workspace_tags
- workspaces (1) → (N) lm_content
- lm_content (1) → (N) lm_content_embedding
- lm_content (1) → (N) lm_content_tag_mapping → (N) workspace_tags
- users (1) → (N) chatbot_history
- workspaces (1) → (N) chatbot_history

IMPORTANT GLOBAL RULE:
Always apply soft delete filtering in every query:
WHERE is_active = true AND is_deleted = false

TABLE DEFINITIONS:

1. users
   (id PK, email UNIQUE, password, role ENUM('user','admin'), name,
   login_time, is_onboarding_completed, otp, otp_created_at,
   subscription_type ENUM('free','pro','pro_plus'),
   invitation_status, api_key, trial_start, trial_end, is_trial_active,
   auth_provider ENUM('google','email'),
   created_at, updated_at, is_active, is_deleted)
"""


# --- 2. Custom System Prompt Builder ---

class SchemaSystemPromptBuilder(DefaultSystemPromptBuilder):
    async def build_system_prompt(self, user: User, tools: List[ToolSchema]) -> str:
        base_prompt = await super().build_system_prompt(user, tools) or ""
        return base_prompt + f"\n\n# DATABASE SCHEMA AND RULES\nYou MUST follow these rules:\n{DB_SCHEMA}"


# --- 3. User Resolver for Local Testing ---

class LocalUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(
            id="test_user",
            email="test@localhost",
            group_memberships=["admin"]
        )


# --- 4. Environment & Configuration ---

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# --- 5. Main Entry Point ---

async def main():
    print("Initializing Agent...")

    # A. LLM Initialization
    llm = OpenAILlmService(
        model="gpt-4o-mini",
        api_key=api_key
    )

    # B. Postgres Connection
    postgres = PostgresRunner(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="require"
    )

    # C. Tools Setup
    tools = ToolRegistry()
    tools.register_local_tool(RunSqlTool(sql_runner=postgres), access_groups=[])

    # D. Agent Initialization
    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=LocalUserResolver(),
        agent_memory=DemoAgentMemory(),
        system_prompt_builder=SchemaSystemPromptBuilder(),
        config=AgentConfig(
            include_thinking_indicators=False,
            stream_responses=False
        )
    )

    # E. Send a Question
    question = "How many active users are there?"
    print(f"\nAsking: '{question}'")

    context = RequestContext()

    async for component in agent.send_message(context, question):
        if hasattr(component, 'simple_component') and component.simple_component:
            print(f"RESPONSE: {component.simple_component.text}")
        elif hasattr(component, 'rich_component') and component.rich_component:
            # Rich components (e.g. SQL status updates) can be handled here if needed
            pass


if __name__ == "__main__":
    asyncio.run(main())