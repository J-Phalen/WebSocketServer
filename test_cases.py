import asyncio
import logging

import pytest
import pytest_asyncio
from aiohttp import ClientSession, WSMsgType, WSServerHandshakeError

from server import API_KEY

logger = logging.getLogger("websocket_server")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S", force=True)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8567
WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws"
POST_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/wss/post"


# No idea if this is still actually needed or not, I think it was just from when I was creating
# a server with the test file, but it doesnt seem to hurt anything, but is likely dead code.
@pytest_asyncio.fixture(scope="module")
async def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


"""
# Removing this for now as it seems we don't want to run two instances of the server.
# Because that would be bad with port conflicts
@pytest_asyncio.fixture(scope="module", autouse=True)
async def server():
    # Start the WebSocket server in the background
    server_task = asyncio.create_task(start_server())
    await asyncio.sleep(1.0)  # Give server time to start
    yield
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass
"""


@pytest.mark.asyncio
async def test_websocket_connection_success():
    """
    Test asyncrynous function to make a connection to the wss using a valid key
    The server should be reachable at ws://127.0.0.1:8567/ws and run independantly.
    """
    async with ClientSession() as session:
        async with session.ws_connect(f"{WS_URL}?apikey={API_KEY}") as ws:
            assert not ws.closed
            logger.info("Creating the connection to the web socket server...")
            logger.info("We are checking that the value for closed in the ws object is False, meaning it's connection is open...")
            await ws.close()


@pytest.mark.asyncio
async def test_websocket_connection_wrong_key():
    """Test asyncrynous function to make a connection to the wss using an invalid key"""
    async with ClientSession() as session:
        logger.info("Creating the connection to the web socket server using an invalid apikey...")
        logger.info("We are expecting a 403 return.")
        with pytest.raises(WSServerHandshakeError) as response:
            await session.ws_connect(f"{WS_URL}?apikey=not_the_right_key")
        assert "403" in str(response.value)
        logger.warning("The wss return a 403 correctly due to sending an invalid apikey.")


@pytest.mark.asyncio
async def test_websocket_connection_no_key():
    """Test asyncrynous function to make a connection to the wss without using a key at all"""
    async with ClientSession() as session:
        logger.info("Creating the connection to the web socket server without using an apikey...")
        logger.info("We are expecting a 403 return.")
        with pytest.raises(WSServerHandshakeError) as response:
            await session.ws_connect(WS_URL)
        assert "403" in str(response.value)
        logger.warning("The wss return a 403 correctly due to not sending an apikey.")


@pytest.mark.asyncio
async def test_websocket_is_read_only():
    """
    Test asyncrynous function to make a connection to the wss with a valid apikey
    and attempt to post to it, which should fail as intended by the code in the server.py file.
    """
    async with ClientSession() as session:
        async with session.ws_connect(f"{WS_URL}?apikey={API_KEY}") as ws:
            logger.info("Trying to send a message to the ws endpoint, which should be setup as read only and fail...")
            await ws.send_str("hello server")

            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=2)
                # We don't actually expect a message back, but if we get one it should be empty.
                # We are anticipating to catch the error of timeout, because the receive command should never actually finish.
                assert msg.type == WSMsgType.CLOSE or not msg.data
            except asyncio.TimeoutError:
                logger.info("No confirmation from the server was received when posting to ws, which was expected...")
                pass

            assert not ws.closed, "WebSocket connection should still be open"
            await ws.close()


@pytest.mark.asyncio
async def test_post_message_success():
    """
    Test asyncrynous function to post to the http endpoint with a valid apikey.
    The server should be reachable at http://127.0.0.1:8567/wss/post and run independantly from server.py.
    """
    async with ClientSession() as session:
        logger.info("Testing an http post to the server using the API_KEY variable...")
        resp = await session.post(POST_URL, headers={"X-API-Key": API_KEY}, data={"message": "test message"})
        assert resp.status == 200
        logger.info("Response Status code was 200")
        text = await resp.text()
        assert text == "OK"
        logger.info("The server has confirmed to us it received our message.")


@pytest.mark.asyncio
async def test_post_with_wrong_api_key():
    """Test asyncrynous function to post to the http endpoint with an invalid apikey."""
    async with ClientSession() as session:
        logger.info("Testing an http post to the server using an invalid API_KEY in headers...")
        resp = await session.post(POST_URL, headers={"X-API-Key": "invalidkey"}, data={"message": "this should fail"})
        text = await resp.text()
        assert resp.status == 403
        assert "Forbidden" in text
        logger.warning(f"[Wrong API Key] Status: {resp.status}, Response: {text}")


@pytest.mark.asyncio
async def test_post_with_no_api_key():
    """Test asyncrynous function to post to the http endpoint without any apikey at all."""
    async with ClientSession() as session:
        logger.info("Testing an http post to the server without using headers...")
        resp = await session.post(POST_URL, data={"message": "this should fail too"})
        text = await resp.text()
        logger.warning(f"[No API Key] Status: {resp.status}, Response: {text}")
        assert resp.status == 403
        assert "Forbidden" in text


# This one is a little more complicated, I am trying to test reading back a message posted via http,
# but to do this, we need to essentiall build a function that does all of the other tests, once we know they pass.
@pytest.mark.asyncio
async def test_broadcast_message_reception():
    """
    Test asyncrynous function to connect to the ws endpoint with a valid apikey,
    post to the http endpoint with a valid apikey,
    and read it back from the connected client at the ws endpoint, also using a valid api key.
    NOTE: We will not be testing invalid or missing keys as this was tested earlier.
    """
    received = asyncio.Future()

    async def listen_ws():
        async with ClientSession() as session:
            async with session.ws_connect(f"{WS_URL}?apikey={API_KEY}") as ws:
                assert not ws.closed
                logger.info("Connected to ws endpoint successfully...")
                msg = await ws.receive(timeout=5)
                if msg.type == WSMsgType.TEXT:
                    received.set_result(msg.data)

    listener_task = asyncio.create_task(listen_ws())
    await asyncio.sleep(1)  # Give websocket time to connect

    # Send POST to broadcast a message
    async with ClientSession() as session:
        logger.info("Sending http post to the wss...")
        await session.post(POST_URL, headers={"X-API-Key": API_KEY}, data={"message": "hello from http post endpoint"})

    # Wait for websocket to receive message
    result = await asyncio.wait_for(received, timeout=5)
    assert result == "hello from http post endpoint"
    logger.info("WS Client has received the message.")

    listener_task.cancel()
