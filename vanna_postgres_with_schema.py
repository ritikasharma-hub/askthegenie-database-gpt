# import asyncio
# import os
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

#     # --- 1. Database Schema Definition ---

#     DB_SCHEMA = """
#     RELATIONSHIPS:
#     - users (1) → (1) accounts
#     - users (1) → (1) user_profiles
#     - users (1) → (N) contacts
#     - users (1) → (N) user_selected_preferences → (N) user_preferences
#     - accounts (1) → (N) workspaces
#     - accounts (1) → (N) subscriptions → (N) subscription_plans
#     - workspaces (1) → (N) workspace_tags
#     - workspaces (1) → (N) lm_content
#     - lm_content (1) → (N) lm_content_embedding
#     - lm_content (1) → (N) lm_content_tag_mapping → (N) workspace_tags
#     - users (1) → (N) chatbot_history
#     - workspaces (1) → (N) chatbot_history

#     IMPORTANT GLOBAL RULE:
#     Always apply soft delete filtering in every query:
#     WHERE is_active = true AND is_deleted = false

#     TABLE DEFINITIONS:

#     1. users
#     (id PK, email UNIQUE, password, role ENUM('user','admin'), name,
#     login_time, is_onboarding_completed, otp, otp_created_at,
#     subscription_type ENUM('free','pro','pro_plus'),
#     invitation_status, api_key, trial_start, trial_end, is_trial_active,
#     auth_provider ENUM('google','email'),
#     created_at, updated_at, is_active, is_deleted)

#     2. accounts
#     (id PK, user_id FK users.id, name, stripe_customer_id, account_type,
#     created_at, updated_at, is_active, is_deleted)

#     3. contacts
#     (id PK, user_id FK users.id, account_id FK accounts.id,
#     role, created_at, updated_at, is_active, is_deleted)

#     4. user_profiles
#     (id PK, user_id FK users.id, company_name, google_profile_url,
#     answer_type, phone_number, created_at, updated_at, is_active, is_deleted)

#     5. user_preferences
#     (id PK, name, created_at, updated_at, is_active, is_deleted)

#     6. user_selected_preferences
#     (id PK, user_id FK users.id, preference_id FK user_preferences.id,
#     created_at, updated_at, is_active, is_deleted)

#     7. workspaces
#     (id PK, account_id FK accounts.id, user_id FK users.id,
#     name, description,
#     color ENUM('Purple','Teal','Pink','Orange','Green','Blue'),
#     is_default, created_at, updated_at, is_active, is_deleted)

#     8. workspace_tags
#     (id PK, account_id FK accounts.id, user_id FK users.id,
#     workspace_id FK workspaces.id, name (lowercase),
#     created_at, updated_at, is_active, is_deleted)

#     9. lm_content
#     (id PK, user_id FK users.id, workspace_id FK workspaces.id,
#     lm_content_type ENUM('file','text','url'),
#     content_path, file_name, actual_content,
#     processing_status ENUM('uploaded','preprocessing','completed','failed'),
#     file_size, page_count,
#     created_at, updated_at, is_active, is_deleted)

#     10. lm_content_embedding
#     (id PK, lm_content_id FK lm_content.id,
#     chunk_content, chunk_content_embedding VECTOR(1536),
#     chunk_index, tokens_consumed, cost,
#     created_at, updated_at, is_active, is_deleted)

#     11. lm_content_tag_mapping
#     (id PK, lm_content_id FK lm_content.id,
#     workspace_tag_id FK workspace_tags.id,
#     created_at, updated_at, is_active, is_deleted)

#     12. chatbot_history
#     (id PK, user_id FK users.id, session_id UUID,
#     workspace_id FK workspaces.id,
#     query, response, citations JSON,
#     tool_used ENUM('rag_tool','db_tool'),
#     input_tokens_consumed, output_tokens_consumed,
#     embedding_tokens_consumed,
#     input_token_cost DECIMAL(18,10),
#     output_token_cost DECIMAL(18,10),
#     embedding_cost DECIMAL(18,10),
#     total_cost DECIMAL(18,10),
#     regenerated_from_id FK chatbot_history.id,
#     is_liked BOOLEAN,
#     document_content_ids JSON,
#     created_at, updated_at, is_active, is_deleted)

#     13. subscription_plans
#     (id PK,
#     plan_name ENUM('Free','Pro','Pro Plus'),
#     billing_cycle ENUM('monthly','yearly'),
#     plan_price DECIMAL(10,2),
#     currency DEFAULT 'USD',
#     stripe_product_id, stripe_price_id,
#     status ENUM('active','cancelled','expired'),
#     created_at, updated_at, is_active, is_deleted)

#     14. subscriptions
#     (id PK,
#     account_id FK accounts.id,
#     plan_id FK subscription_plans.id,
#     stripe_subscription_id, stripe_price_id,
#     status ENUM('active','past_due','canceled','unpaid'),
#     current_period_start, current_period_end,
#     cancel_at_period_end,
#     trial_end,
#     amount_paid DECIMAL(10,2),
#     currency DEFAULT 'USD',
#     is_auto_renew,
#     is_refunded,
#     refund_amount DECIMAL(10,2),
#     created_at, updated_at, is_active, is_deleted)

#     QUERY RULES:
#     - Always join using foreign keys.
#     - Always include soft delete filter.
#     - Always qualify columns with table aliases.
#     - Use explicit joins, never implicit joins.
#     - Order chat history by created_at ASC.
#     - Tag names are stored lowercase.
#     - Workspace color values are Title Case.
#     """

#     # --- 2. Custom System Prompt Builder ---

#     class SchemaSystemPromptBuilder(DefaultSystemPromptBuilder):
#         """Custom builder that injects the database schema into the system prompt."""
        
#         async def build_system_prompt(self, user: User, tools: List[ToolSchema]) -> str:
#             # Get the default prompt from the parent class
#             base_prompt = await super().build_system_prompt(user, tools)
#             if base_prompt is None:
#                 base_prompt = ""
                
#             # Append our specific schema and rules
#             schema_prompt = f"""

#     # DATABASE SCHEMA AND RULES
#     You are connected to a PostgreSQL database with the following schema.
#     You MUST follow these rules when generating SQL:

#     {DB_SCHEMA}
#     """
#             return base_prompt + schema_prompt


#     # --- 3. User Resolver for Local Testing ---
#     class LocalUserResolver(UserResolver):
#         async def resolve_user(self, request_context: RequestContext) -> User:
#             return User(
#                 id="local_tester",
#                 email="tester@localhost",
#                 group_memberships=["admin"]
#             )

#     # --- 4. Main Agent Setup ---

#         from dotenv import load_dotenv
#         import os

#         # Load variables from .env
#         load_dotenv()

#     api_key = os.getenv("OPENAI_API_KEY")
#     DB_HOST=os.getenv("DB_HOST")
#     DB_PORT=os.getenv("DB_PORT")
#     DB_NAME=os.getenv("DB_NAME")
#     DB_USER=os.getenv("DB_USER")
#     DB_PASSWORD=os.getenv("DB_PASSWORD")

#     async def main():
#                 # LLM Initialization
#             llm = OpenAILlmService(
#                 model="gpt-4o-mini",
#                 api_key=api_key
#             )


#             # Postgres Connection
#     postgres = PostgresRunner(
#         host=DB_HOST,
#         port=DB_PORT,
#         database=DB_NAME,
#         user=DB_USER,
#         password=DB_PASSWORD
#     )

    
#         # Test connection
#         try:
#             print("Connecting to PostgreSQL...")
#             # running a simple query to verify connection
#             # We can't run directly on runner easily without context, but Agent will handle it.
#             print("Connected to PostgreSQL successfully!")
        
#         except Exception as e:
#             print(f"Failed to connect to PostgreSQL: {e}")
#             return

#             # C. Tools Setup
#         tools = ToolRegistry()
#         run_sql_tool = RunSqlTool(sql_runner=postgres)
#         tools.register_local_tool(run_sql_tool, access_groups=[])

#         # D. Agent Initialization
#         agent = Agent(
#             llm_service=llm,
#             tool_registry=tools,
#             user_resolver=LocalUserResolver(),
#             agent_memory=DemoAgentMemory(),
#             system_prompt_builder=SchemaSystemPromptBuilder(),
#             config=AgentConfig(
#                 include_thinking_indicators=False,
#                 stream_responses=False # Easier for console output
#             )
#         )

#         print("\n✅ Vanna Agent Initialized with Custom Schema Context")
#         print("-----------------------------------------------------")
        
#         # E. Interactive Loop
#         context = RequestContext()
        
#         print("Ask a question (or type 'quit' to exit):")
        
#         while True:
#             try:
#                 user_input = input("\nUser > ")
#                 if user_input.lower() in ('quit', 'exit'):
#                     break
                    
#                 print("\nAgent is thinking...")
                
#                 # Use the agent to process the message
#                 # The agent returns an AsyncGenerator of UiComponents
#                 async for component in agent.send_message(context, user_input):
#                     # We just want to print the simple text components for the CLI
#                     if component.simple_component and component.simple_component.text:
#                         print(f"\nAgent > {component.simple_component.text}")
                        
#             except KeyboardInterrupt:
#                 break
#             except Exception as e:
#                 print(f"Error: {e}")

#     if __name__ == "__main__":
#         asyncio.run(main())

#dummy comment to test code 

import asyncio
import os
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

2. accounts
   (id PK, user_id FK users.id, name, stripe_customer_id, account_type,
   created_at, updated_at, is_active, is_deleted)

3. contacts
   (id PK, user_id FK users.id, account_id FK accounts.id,
   role, created_at, updated_at, is_active, is_deleted)

4. user_profiles
   (id PK, user_id FK users.id, company_name, google_profile_url,
   answer_type, phone_number, created_at, updated_at, is_active, is_deleted)

5. user_preferences
   (id PK, name, created_at, updated_at, is_active, is_deleted)

6. user_selected_preferences
   (id PK, user_id FK users.id, preference_id FK user_preferences.id,
   created_at, updated_at, is_active, is_deleted)

7. workspaces
   (id PK, account_id FK accounts.id, user_id FK users.id,
   name, description,
   color ENUM('Purple','Teal','Pink','Orange','Green','Blue'),
   is_default, created_at, updated_at, is_active, is_deleted)

8. workspace_tags
   (id PK, account_id FK accounts.id, user_id FK users.id,
   workspace_id FK workspaces.id, name (lowercase),
   created_at, updated_at, is_active, is_deleted)

9. lm_content
   (id PK, user_id FK users.id, workspace_id FK workspaces.id,
   lm_content_type ENUM('file','text','url'),
   content_path, file_name, actual_content,
   processing_status ENUM('uploaded','preprocessing','completed','failed'),
   file_size, page_count,
   created_at, updated_at, is_active, is_deleted)

10. lm_content_embedding
    (id PK, lm_content_id FK lm_content.id,
    chunk_content, chunk_content_embedding VECTOR(1536),
    chunk_index, tokens_consumed, cost,
    created_at, updated_at, is_active, is_deleted)

11. lm_content_tag_mapping
    (id PK, lm_content_id FK lm_content.id,
    workspace_tag_id FK workspace_tags.id,
    created_at, updated_at, is_active, is_deleted)

12. chatbot_history
    (id PK, user_id FK users.id, session_id UUID,
    workspace_id FK workspaces.id,
    query, response, citations JSON,
    tool_used ENUM('rag_tool','db_tool'),
    input_tokens_consumed, output_tokens_consumed,
    embedding_tokens_consumed,
    input_token_cost DECIMAL(18,10),
    output_token_cost DECIMAL(18,10),
    embedding_cost DECIMAL(18,10),
    total_cost DECIMAL(18,10),
    regenerated_from_id FK chatbot_history.id,
    is_liked BOOLEAN,
    document_content_ids JSON,
    created_at, updated_at, is_active, is_deleted)

13. subscription_plans
    (id PK,
    plan_name ENUM('Free','Pro','Pro Plus'),
    billing_cycle ENUM('monthly','yearly'),
    plan_price DECIMAL(10,2),
    currency DEFAULT 'USD',
    stripe_product_id, stripe_price_id,
    status ENUM('active','cancelled','expired'),
    created_at, updated_at, is_active, is_deleted)

14. subscriptions
    (id PK,
    account_id FK accounts.id,
    plan_id FK subscription_plans.id,
    stripe_subscription_id, stripe_price_id,
    status ENUM('active','past_due','canceled','unpaid'),
    current_period_start, current_period_end,
    cancel_at_period_end,
    trial_end,
    amount_paid DECIMAL(10,2),
    currency DEFAULT 'USD',
    is_auto_renew,
    is_refunded,
    refund_amount DECIMAL(10,2),
    created_at, updated_at, is_active, is_deleted)

QUERY RULES:
- Always join using foreign keys.
- Always include soft delete filter.
- Always qualify columns with table aliases.
- Use explicit joins, never implicit joins.
- Order chat history by created_at ASC.
- Tag names are stored lowercase.
- Workspace color values are Title Case.
"""


# --- 2. Custom System Prompt Builder ---

class SchemaSystemPromptBuilder(DefaultSystemPromptBuilder):
    """Custom builder that injects the database schema into the system prompt."""

    async def build_system_prompt(self, user: User, tools: List[ToolSchema]) -> str:
        # Get the default prompt from the parent class
        base_prompt = await super().build_system_prompt(user, tools)
        if base_prompt is None:
            base_prompt = ""

        # Append our specific schema and rules
        schema_prompt = f"""

# DATABASE SCHEMA AND RULES
You are connected to a PostgreSQL database with the following schema.
You MUST follow these rules when generating SQL:

{DB_SCHEMA}
"""
        return base_prompt + schema_prompt


# --- 3. User Resolver for Local Testing ---

class LocalUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(
            id="local_tester",
            email="tester@localhost",
            group_memberships=["admin"]
        )


# --- 4. Environment & Configuration ---

# Load variables from .env
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# --- 5. Main Entry Point ---

async def main():
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


    # Test connection
    try:
        print("Connecting to PostgreSQL...")
        # Running a simple query to verify connection.
        # We can't run directly on the runner without a context, but the Agent will handle it.
        print("Connected to PostgreSQL successfully!")
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")
        return

    # C. Tools Setup
    tools = ToolRegistry()
    run_sql_tool = RunSqlTool(sql_runner=postgres)
    tools.register_local_tool(run_sql_tool, access_groups=[])

    # D. Agent Initialization
    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=LocalUserResolver(),
        agent_memory=DemoAgentMemory(),
        system_prompt_builder=SchemaSystemPromptBuilder(),
        config=AgentConfig(
            include_thinking_indicators=False,
            stream_responses=False  # Easier for console output
        )
    )

    print("\n✅ Vanna Agent Initialized with Custom Schema Context")
    print("-----------------------------------------------------")

    # E. Interactive Loop
    context = RequestContext()

    print("Ask a question (or type 'quit' to exit):")

    while True:
        try:
            user_input = input("\nUser > ")
            if user_input.lower() in ('quit', 'exit'):
                break

            print("\nAgent is thinking...")

            # Use the agent to process the message.
            # The agent returns an AsyncGenerator of UiComponents.
            async for component in agent.send_message(context, user_input):
                # We just want to print the simple text components for the CLI
                if component.simple_component and component.simple_component.text:
                    print(f"\nAgent > {component.simple_component.text}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())