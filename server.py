import asyncio
import logging
import signal

from aiohttp import WSMsgType, web

logger = logging.getLogger("websocket_server")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

clients = set()
lock = asyncio.Lock()
PING_INTERVAL = 30
API_KEY = "changethistosomethingthenpassinheaders"


async def websocket_handler(request):
    apikey = request.query.get("apikey")
    if apikey != API_KEY:
        logger.warning("Unauthorized websocket connection attempt")
        return web.Response(status=403, text="Forbidden")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async with lock:
        clients.add(ws)
    logger.info(f"Client connected: {request.remote}, total clients: {len(clients)}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # Handle incoming messages if needed
                pass
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket connection closed with exception {ws.exception()}")
    finally:
        async with lock:
            clients.discard(ws)
        logger.info(f"Client disconnected: {request.remote}, total clients: {len(clients)}")

    return ws


async def handle_post(request):
    data = await request.post()
    api_key = request.headers.get("X-API-Key") or data.get("api_key")
    if api_key != API_KEY:
        logger.warning("Unauthorized POST attempt with invalid API key")
        return web.Response(status=403, text="Forbidden")

    message = data.get("message", "")
    if not message:
        logger.warning("POST request missing 'message' parameter")
        return web.Response(status=400, text="Missing 'message'")

    logger.info(f"Received POST message: {message}")
    await broadcast(message)
    return web.Response(text="OK")


async def broadcast(message):
    async with lock:
        to_remove = set()
        for ws in clients:
            if ws.closed:
                to_remove.add(ws)
                continue
            try:
                await ws.send_str(message)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                to_remove.add(ws)
        for ws in to_remove:
            clients.discard(ws)


async def ping_clients():
    while True:
        await asyncio.sleep(PING_INTERVAL)
        async with lock:
            to_remove = set()
            for ws in clients:
                if ws.closed:
                    to_remove.add(ws)
                    continue
                try:
                    await ws.ping()
                    logger.debug(f"Sent ping to client {ws}")
                except Exception as e:
                    logger.warning(f"Failed to ping client: {e}")
                    to_remove.add(ws)
            for ws in to_remove:
                clients.discard(ws)


async def start_server():
    app = web.Application()
    app.router.add_post("/wss/post", handle_post)
    app.router.add_get("/ws", websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=8567)
    await site.start()

    logger.info("Server running on http://127.0.0.1:8567")
    logger.info("WebSocket endpoint at ws://127.0.0.1:8567/ws")
    logger.info("POST endpoint at http://127.0.0.1:8567/wss/post")

    # Start the ping task in the background
    ping_task = asyncio.create_task(ping_clients())

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown():
        logger.info("Received stop signal, shutting down...")
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, shutdown)
        loop.add_signal_handler(signal.SIGTERM, shutdown)
    except NotImplementedError:
        # Add warning for Windows systems that I guess cannot support signal handlers to catch shut down.
        logger.warning("Signal handlers are not implemented on this platform.")

    await stop_event.wait()

    logger.info("Cleaning up server...")
    ping_task.cancel()
    try:
        await ping_task
    except asyncio.CancelledError:
        pass
    await runner.cleanup()
    logger.info("Server shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        # Need this for windows I guess because the signal_handlers arnt supported.
        logger.info("Server stoppyed by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Server crashed with exception: {e}", exc_info=True)
