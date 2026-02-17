from vanna.core.user import User, UserResolver, RequestContext

class LocalUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(
            id="local_user",
            email="local@localhost",
            group_memberships=["admin"]
        )
