# 0004: Real-time alerts: Socket.IO

**Context:** The task names Socket.io; alerts must reach the dashboard live and survive flaky connections during the demo.

**Decision:** python-socketio (ASGI, mounted next to FastAPI) with `AsyncRedisManager`; workers emit through `RedisManager(write_only=True)`; socket.io-client in React. Events: `alert` (payload `Alert`), `job`, `registry`.

**Consequences:** Reconnect and heartbeat for free; workers emit directly without calling the API; replaces the raw WebSocket from the 2-person plan.
