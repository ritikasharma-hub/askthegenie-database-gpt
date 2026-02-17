from vanna.integrations.postgres import PostgresRunner
from vanna.core.tool import ToolContext

postgres = PostgresRunner(
    host="askthegeniedb.postgres.database.azure.com",
    port=5432,
    database="postgres",
    user="askthegeniedb",
    password="atgDrdfR#sf193$g",
    sslmode="require"
)

from vanna.core.user import User
from vanna.integrations.local.agent_memory import DemoAgentMemory
import uuid

# create context
user = User(id="test", email="test@example.com", group_memberships=[])
context = ToolContext(
    user=user,
    conversation_id="test_conv",
    request_id="test_req",
    agent_memory=DemoAgentMemory()
)

import asyncio
from vanna.capabilities.sql_runner import RunSqlToolArgs

async def main():
    print("Testing connection...")
    try:
        args = RunSqlToolArgs(sql="SELECT 1")
        result = await postgres.run_sql(args, context=context)
        print("DB RESULT:", result)
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
