import asyncio
import sys
import os

# Add local src to path to ensure we use the local version of vanna
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from dotenv import load_dotenv
load_dotenv()

from typing import List, Optional, Tuple

from vanna import Agent
from vanna.core.agent.config import AgentConfig, UiFeature, UiFeatures
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.core.system_prompt import DefaultSystemPromptBuilder
from vanna.core.tool import ToolSchema, ToolContext, ToolResult
from vanna.core.user import User, UserResolver, RequestContext
from vanna.tools import RunSqlTool
from vanna.core.registry import ToolRegistry
from vanna.integrations.openai import OpenAILlmService
from vanna.integrations.postgres import PostgresRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.servers.flask import VannaFlaskServer
from vanna.tools.visualize_data import VisualizeDataTool, VisualizeDataArgs
from vanna.integrations.plotly import PlotlyChartGenerator
from pydantic import Field
import pandas as pd
import uuid
import json
import plotly.io as pio
import plotly.express as px

# --- 1. Database Schema and Rules ---

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
- Always include soft delete filter used in priming examples.
- Always qualify columns with table aliases.
- Use explicit joins, never implicit joins.
- Order chat history by created_at ASC.
- Tag names are stored lowercase.
- Workspace color values are Title Case.
"""

class SchemaSystemPromptBuilder(DefaultSystemPromptBuilder):
    """Custom builder that injects the database schema into the system prompt."""
    
    async def build_system_prompt(self, user: User, tools: List[ToolSchema]) -> str:
        base_prompt = await super().build_system_prompt(user, tools) or ""
        return base_prompt + f"\n\n# DATABASE SCHEMA AND RULES\nYou MUST follow these rules:\n{DB_SCHEMA}"

# --- 2. User Resolver ---

class LocalUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(
            id="dashboard_admin",
            email="admin@askgenie.ai",
            group_memberships=["admin"]
        )

# --- 3. Agent Priming ---

async def prime_agent(agent: Agent):
    """
    Seeds the agent's memory with specific training examples for the dashboard metrics.
    """
    print("\nTraining agent with dashboard metrics...")

    # Define training examples (Question, SQL)
    # Note: We include the tool filtering in the SQL to enforce the global rules
    training_data: List[Tuple[str, str]] = [
        (
            "Show me Daily Active Users",
            "SELECT date_trunc('day', created_at) as day, count(distinct user_id) as dau FROM chatbot_history WHERE is_active = true AND is_deleted = false GROUP BY 1 ORDER BY 1 DESC"
        ),
        (
            "Show Token Consumption vs Total Cost",
            "SELECT session_id, sum(input_tokens_consumed) as input_tokens, sum(output_tokens_consumed) as output_tokens, sum(total_cost) as cost FROM chatbot_history WHERE is_active = true AND is_deleted = false GROUP BY 1 ORDER BY cost DESC LIMIT 100"
        ),
        (
            "Show Document Processing Status",
            "SELECT processing_status, count(*) as count FROM lm_content WHERE is_active = true AND is_deleted = false GROUP BY 1 ORDER BY count DESC"
        )
    ]
    
    # We need a dummy context to save memories
    user = User(id="admin", email="system", group_memberships=["admin"])
    context = ToolContext(
        user=user, 
        conversation_id="training", 
        request_id="init",
        agent_memory=agent.agent_memory
    )
    
    for question, sql in training_data:
        # Save as tool usage memory
        await agent.agent_memory.save_tool_usage(
            question=question,
            tool_name="run_sql",
            args={"sql": sql},
            context=context,
            success=True
        )
        print(f"  Saved training example: '{question}'")

    print("Agent priming complete.\n")

# --- 3.5 Custom Tools ---

# --- 3.5 Custom Tools ---

class CustomPlotlyChartGenerator(PlotlyChartGenerator):
    def generate_chart(self, df: pd.DataFrame, title: str = "Chart", chart_type: str = None) -> dict:
        """
        Custom generate_chart that accepts an explicit chart_type.
        """
        if df.empty:
            raise ValueError("Cannot visualize empty DataFrame")

        # If chart_type is provided, force it (simple mapping based on first 2 cols)
        # Fallback to default heuristic if no chart_type
        if not chart_type:
            return super().generate_chart(df, title)
            
        chart_type = chart_type.lower()
        cols = df.columns.tolist()
        
        # Helper to identify column types
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        non_numeric_cols = df.select_dtypes(exclude=['number']).columns.tolist()
        date_cols = df.select_dtypes(include=['datetime']).columns.tolist()
        
        # Heuristic: If we have numeric columns that look like IDs, we might want to exclude them from Y-axis candidates if possible
        # But for now, let's just picking the "best" X and Y.
        
        # X-Axis / Label Candidate: Prioritize Date > String > Numeric (if it's an ID or Year)
        # Y-Axis / Value Candidate: Prioritize Numeric
        
        x_col = None
        y_col = None
        
        # Try to find a good X column (Label/Category)
        if non_numeric_cols:
            x_col = non_numeric_cols[0]
        elif numeric_cols:
            # If only numeric, maybe the first one is an ID or Year? Use it as X.
            x_col = numeric_cols[0]
            
        # Try to find a good Y column (Value)
        # We want a numeric column that IS NOT the x_col
        possible_y = [c for c in numeric_cols if c != x_col]
        
        if possible_y:
            # Sort possible_y to prioritize "metric-like" names and de-prioritize "id-like" names
            def score_y_col(col_name):
                col_lower = col_name.lower()
                score = 0
                if any(x in col_lower for x in ["count", "sum", "total", "amount", "cost", "price", "value", "revenue", "sales", "qty", "quantity"]):
                    score += 10
                if "id" in col_lower or "code" in col_lower or "index" in col_lower:
                    score -= 5
                # Prefer later columns if scores are tied (often ID is first)
                return score
            
            # Sort descending by score
            possible_y.sort(key=score_y_col, reverse=True)
            y_col = possible_y[0]
        
        if "bar" in chart_type:
            if x_col and y_col:
                return json.loads(pio.to_json(self._create_bar_chart(df, x_col, y_col, title)))
            # Fallback
            if len(cols) >= 2:
                return json.loads(pio.to_json(self._create_bar_chart(df, cols[0], cols[1], title)))
        
        elif "line" in chart_type:
             if x_col and possible_y:
                 return json.loads(pio.to_json(self._create_time_series_chart(df, x_col, possible_y, title)))
             if len(cols) >= 2:
                 # Fallback
                 numeric_cols_fallback = df.select_dtypes(include=["number"]).columns.tolist()
                 return json.loads(pio.to_json(self._create_time_series_chart(df, cols[0], numeric_cols_fallback, title)))

        elif "pie" in chart_type:
             if x_col and y_col:
                fig = px.pie(df, names=x_col, values=y_col, title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))
             if len(cols) >= 2:
                fig = px.pie(df, names=cols[0], values=cols[1], title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))

        elif "scatter" in chart_type:
            # Scatter usually needs 2 numeric columns
            if len(numeric_cols) >= 2:
                return json.loads(pio.to_json(self._create_scatter_plot(df, numeric_cols[0], numeric_cols[1], title)))
            elif x_col and y_col:
                 return json.loads(pio.to_json(self._create_scatter_plot(df, x_col, y_col, title)))
            elif len(cols) >= 2:
                return json.loads(pio.to_json(self._create_scatter_plot(df, cols[0], cols[1], title)))

        elif "area" in chart_type:
             if x_col and y_col:
                fig = px.area(df, x=x_col, y=y_col, title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))
             if len(cols) >= 2:
                fig = px.area(df, x=cols[0], y=cols[1], title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))

        elif "histogram" in chart_type:
             if possible_y:
                fig = px.histogram(df, x=possible_y[0], title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))
             if len(numeric_cols) > 0:
                fig = px.histogram(df, x=numeric_cols[0], title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))
             elif len(cols) > 0:
                fig = px.histogram(df, x=cols[0], title=title, color_discrete_sequence=self.COLOR_PALETTE)
                return json.loads(pio.to_json(fig))

        # Fallback to default heuristic if chart_type didn't match or failed
        return super().generate_chart(df, title)

class CustomVisualizeDataArgs(VisualizeDataArgs):
    chart_type: Optional[str] = Field(default=None, description="The specific chart type to generate (e.g., 'bar', 'line', 'pie', 'scatter').")

class CustomVisualizeDataTool(VisualizeDataTool):
    def __init__(self, file_system=None, plotly_generator=None):
        super().__init__(file_system=file_system, plotly_generator=plotly_generator or CustomPlotlyChartGenerator())

    def get_args_schema(self):
        return CustomVisualizeDataArgs

    async def execute(self, context: ToolContext, args: CustomVisualizeDataArgs) -> ToolResult:
        # Override execute to pass chart_type to the generator
        # We need to mostly copy the original logic or rely on the custom generator handling the chart_type
        # But the original `VisualizeDataTool.execute` calls `self.plotly_generator.generate_chart(df, title)`
        # It doesn't pass extra kwargs. So we MUST override execute to pass `chart_type`.
        
        # ... Wait, to avoid copying all the code, we can monkey-patch the generator call or just copy-paste the logic.
        # Given the requirements, copy-paste is safer to ensure `chart_type` is passed.
        
        try:
            # Read the CSV file using FileSystem
            csv_content = await self.file_system.read_file(args.filename, context)
            
            import io
            import plotly.io as pio # Need pio for to_json in the generator, checking imports
            import json # Need json
            
            df = pd.read_csv(io.StringIO(csv_content))
            title = args.title or f"Visualization of {args.filename}"
            
            # CALL CUSTOM GENERATOR WITH CHART_TYPE
            chart_dict = self.plotly_generator.generate_chart(df, title, chart_type=args.chart_type)
            
            row_count = len(df)
            col_count = len(df.columns)
            result_msg = f"Created {args.chart_type or 'automatic'} chart from '{args.filename}'."

            from vanna.components import ChartComponent, UiComponent, SimpleTextComponent
            
            chart_component = ChartComponent(
                chart_type="plotly",
                data=chart_dict,
                title=title,
                config={
                    "data_shape": {"rows": row_count, "columns": col_count},
                    "source_file": args.filename,
                },
            )
            
            return ToolResult(
                success=True,
                result_for_llm=result_msg,
                ui_component=UiComponent(
                    rich_component=chart_component,
                    simple_component=SimpleTextComponent(text=result_msg),
                ),
                metadata={
                    "filename": args.filename,
                    "rows": row_count,
                    "columns": col_count,
                    "chart": chart_dict,
                },
            )
        except Exception as e:
            return ToolResult(success=False, result_for_llm=f"Error: {str(e)}", error=str(e))


class RunSqlWithSaveTool(RunSqlTool):
    """
    Extends RunSqlTool to specificly save the results to a CSV file for visualization.
    """
    def __init__(self, sql_runner):
        super().__init__(sql_runner=sql_runner)

    async def execute(self, context: ToolContext, args) -> ToolResult:
        # 1. Execute the SQL using the parent class logic
        # RunSqlTool returns a ToolResult object
        result = await super().execute(context, args)
        
        # 2. Check if execution was successful and we have results
        if result.success and isinstance(result.metadata, dict):
            # The parent tool already saves to a CSV if "results" are present!
            # See RunSqlTool.execute lines 90-96 in vanna/tools/run_sql.py
            # It saves it to `query_results_{uuid}.csv` and puts it in metadata['output_file']
            
            output_file = result.metadata.get("output_file")
            
            if output_file:
                # 3. Append the visualization instruction to the result text
                # This is crucial for guiding the LLM to the next step
                vis_instruction = f"\n\n**INFO:** The query results have been saved to `{output_file}`. If a visualization is requested, call the `visualize_data` tool with this filename."
                result.result_for_llm += vis_instruction
        
        return result

# --- 4. Main Application ---

def create_app():
    # A. Init Services
    # Load environment variables
    from dotenv import load_dotenv
    import os
    load_dotenv()

    llm = OpenAILlmService(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY")
    )

    postgres = PostgresRunner(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        sslmode="require"
    )

    tools = ToolRegistry()
    
    # 1. SQL Tool (Custom)
    run_sql_tool = RunSqlWithSaveTool(sql_runner=postgres)
    tools.register_local_tool(run_sql_tool, access_groups=[])
    
    # 2. Visualization Tool
    visualize_tool = CustomVisualizeDataTool()
    tools.register_local_tool(visualize_tool, access_groups=[])

    # B. Init Agent
    agent = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=LocalUserResolver(),
        agent_memory=DemoAgentMemory(),
        system_prompt_builder=SchemaSystemPromptBuilder(),
        config=AgentConfig(
            include_thinking_indicators=True,
            stream_responses=True,
            ui_features=UiFeatures(default_access=True)
        )
    )

    # C. Prime the Agent (async)
    # Adding a visualization example
    async def prime_visualization(agent: Agent):
        user = User(id="admin", email="system", group_memberships=["admin"])
        context = ToolContext(user=user, conversation_id="training", request_id="vis_init", agent_memory=agent.agent_memory)
        
        # 1. Map Question -> SQL (Step 1)
        await agent.agent_memory.save_tool_usage(
            question="Show me top 5 active users with the count of documents uploaded through bar chart",
            tool_name="run_sql",
            args={"sql": "SELECT u.name, count(l.id) as document_count FROM users u JOIN lm_content l ON u.id = l.user_id WHERE u.is_active = true AND u.is_deleted = false AND l.is_active = true AND l.is_deleted = false GROUP BY u.name ORDER BY document_count DESC LIMIT 5"},
            context=context,
            success=True
        )

        # 2. Map Follow-up -> Visualization (Step 2)
        # Teach agent to use chart_type
        await agent.agent_memory.save_tool_usage(
            question="Visualize the results from query_results_123.csv as a bar chart",
            tool_name="visualize_data",
            args={"filename": "query_results_123.csv", "chart_type": "bar", "title": "Top 5 Users by Document Count"},
            context=context,
            success=True
        )

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(prime_agent(agent))
    loop.run_until_complete(prime_visualization(agent))

    # D. Create Flask App
    server = VannaFlaskServer(agent)
    return server.create_app()

if __name__ == "__main__":
    app = create_app()
    print("Starting Vanna Flask Dashboard at http://localhost:8084")
    app.run(host="0.0.0.0", port=8084, debug=True)
