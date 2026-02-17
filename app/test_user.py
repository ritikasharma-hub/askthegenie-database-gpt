import asyncio
from user import LocalUserResolver
from vanna.core.user import RequestContext

async def main():
    resolver = LocalUserResolver()
    user = await resolver.resolve_user(RequestContext())
    print(user)

asyncio.run(main())
