import asyncio
import logging
import signal

import aiofiles
from aiohttp import WSMsgType, web
from config import Configuration

logger = logging.getLogger("websocket_server")
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

clients = set()
lock = asyncio.Lock()
PING_INTERVAL = 30
API_KEY = Configuration.get("WSS_API_KEY")

LOG_FILES = [
    "/logs/nginx/error.log",
    "/logs/php/error.log",
]


def process_log_line(path: str, line: str) -> str | None:
    """Modify log lines based on source file."""
    # Example: add file source prefix and trim long lines
    if "nginx" in path:
        prefix = Configuration.get("NGINX_ERROR_TEXT")
    elif "php" in path:
        prefix = Configuration.get("PHP_ERROR_TEXT")
    line = line.strip()
    if not line:
        return None

    return f"{prefix} {line}"


async def follow_file(path):
    """Follow a file like `tail -f` and broadcast new lines."""
    try:
        async with aiofiles.open(path, "r") as f:
            # Move to end of file
            await f.seek(0, 2)
            logger.info(f"[FOLLOW] Started following {path}")
            while True:
                line = await f.readline()
                if not line:
                    await asyncio.sleep(0.5)
                    continue
                processed = process_log_line(path, line)
                if processed:
                    logger.debug(f"[FOLLOW] New line from {path}: {processed!r}")
                    await broadcast(processed)
    except Exception as e:
        logger.error(f"[FOLLOW] Error following {path}: {e}", exc_info=True)


async def websocket_handler(request):
    apikey = request.query.get("apikey")
    if apikey != API_KEY:
        logger.warning("[WS] Unauthorized connection attempt")
        return web.Response(status=403, text="Forbidden")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async with lock:
        clients.add(ws)
    logger.info(f"[WS] Client connected: {request.remote}, total clients: {len(clients)}")

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                logger.debug(f"[WS] Received message from {request.remote}: {msg.data!r}")
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"[WS] Connection closed with exception {ws.exception()}")
    finally:
        async with lock:
            clients.discard(ws)
        logger.info(f"[WS] Client disconnected: {request.remote}, total clients: {len(clients)}")

    return ws


async def handle_post(request):
    logger.debug("[POST] Received POST request")
    try:
        if request.content_type == "application/json":
            data = await request.json()
        else:
            data = await request.post()
    except Exception as error:
        logger.warning(f"Failed to parse POST body: {error}", exc_info=True)
        return web.Response(status=400, text="Invalid POST body")
    api_key = request.headers.get("X-API-Key") or data.get("api_key")
    if api_key != API_KEY:
        logger.warning("Unauthorized POST attempt with invalid API key")
        return web.Response(status=403, text="Forbidden")

    message = data.get("message", "")
    logger.info(f"[POST] Received POST message: {message}")
    if not message:
        logger.warning("POST request missing 'message' parameter")
        return web.Response(status=400, text="Missing 'message'")

    logger.info(f"Received POST message: {message}")
    await broadcast(message)
    logger.debug("[POST] Broadcast finished successfully")
    return web.Response(text="OK")


async def broadcast(message):
    logger.info(f"[BROADCAST] Attempting to send: {message!r} to {len(clients)} clients")
    async with lock:
        to_remove = set()
        for ws in clients:
            logger.debug(f"[BROADCAST] Checking client {ws}, closed={ws.closed}")
            if ws.closed:
                logger.debug("[BROADCAST] Skipping closed client")
                to_remove.add(ws)
                continue
            try:
                await ws.send_str(message)
                logger.debug(f"[BROADCAST] Sent successfully to {ws}")
            except Exception as e:
                logger.error(f"[BROADCAST] Error sending to {ws}: {e}", exc_info=True)
                await ws.close()
                to_remove.add(ws)
        for ws in to_remove:
            clients.discard(ws)
            logger.debug(f"[BROADCAST] Removed disconnected client {ws}")


async def ping_clients():
    while True:
        await asyncio.sleep(PING_INTERVAL)
        logger.debug(f"[PING] Starting ping cycle, {len(clients)} clients connected")
        async with lock:
            to_remove = set()
            for ws in clients:
                # Log basic connection state
                logger.debug(f"Pinging client {ws}, closed={ws.closed}, transport={getattr(ws._req, 'transport', None)}")

                if ws.closed or not getattr(ws._req, "transport", None):
                    logger.debug("Skipping ping: connection already closed or transport missing.")
                    to_remove.add(ws)
                    continue

                try:
                    pong_waiter = ws.ping()
                    if pong_waiter is None:
                        raise RuntimeError("ws.ping() returned None (likely disconnected)")
                    await asyncio.wait_for(pong_waiter, timeout=10)
                    logger.debug("Ping successful")
                except Exception as e:
                    logger.warning(f"Failed to ping client: {e}")
                    await ws.close()
                    to_remove.add(ws)

            for ws in to_remove:
                clients.discard(ws)


async def start_server():
    app = web.Application()
    app.router.add_post("/wss/post", handle_post)
    app.router.add_get("/ws", websocket_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    # Do not change the host or port unless you update the docker files.
    site = web.TCPSite(runner, host="0.0.0.0", port=8567)
    await site.start()

    logger.info("Server running on http://0.0.0.0:8567")
    logger.info("WebSocket endpoint at ws://0.0.0.0:8567/ws")
    logger.info("POST endpoint at http://0.0.0.0:8567/wss/post")

    # Pull the log files
    log_tasks = [asyncio.create_task(follow_file(path)) for path in LOG_FILES]

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
    for t in log_tasks:
        t.cancel()

    try:
        await asyncio.gather(*log_tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass

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
        logger.info("Server stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Server crashed with exception: {e}", exc_info=True)
