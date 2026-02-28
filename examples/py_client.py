import time

import websocket

"""Start the WebSocket client."""
websocket.enableTrace(True)
ws_url = "wss://wss.sitea.dev/ws?apikey=changethistosomethingthenpassinheaders"
ws = websocket.WebSocket()
ws.connect(ws_url)
ws.settimeout(0.1)  # non-blocking-ish recv timeout

# Normally there is a ws.run_forever() that covers all this, but I'm special and cant do that.

while True:
    try:
        opcode, data = ws.recv_data(control_frame=True)
        if opcode == websocket.ABNF.OPCODE_PING:
            ws.pong(data)
        elif opcode == websocket.ABNF.OPCODE_TEXT:
            data = data.decode("utf-8") if isinstance(data, bytes) else data
            print(data)
    except websocket.WebSocketTimeoutException:
        time.sleep(0.1)
    except websocket.WebSocketConnectionClosedException:
        print("WebSocket connection closed")
        break
    except Exception as e:
        print(f"Unexpected error: {e}")
        break
