from src.handlers.payment_handler import handler

event = {
    "version": "2.0",
    "routeKey": "POST /payments",
    "rawPath": "/payments",
    "requestContext": {
        "http": {
            "method": "POST",
            "path": "/payments",
            "protocol": "HTTP/1.1",
            "sourceIp": "127.0.0.1",   # 👈 required field
            "userAgent": "pytest"
        }
    },
    "headers": {"content-type": "application/json"},
    "body": "{\"vendor_id\": \"VENDOR-001\", \"amount\": 250.0, \"currency\": \"USD\", \"reference_id\": \"REF-456\"}",
    "isBase64Encoded": False
}

result = handler(event, None)
print(result)
