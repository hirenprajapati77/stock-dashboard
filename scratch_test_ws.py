import asyncio
import websockets

async def test_url(url):
    try:
        print(f"Testing {url}...")
        headers = {"Authorization": "dummy:token"}
        async with websockets.connect(url, additional_headers=headers) as ws:
            print(f"SUCCESS: {url}")
            return True
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"FAILED {url}: HTTP {e.status_code}")
    except Exception as e:
        print(f"FAILED {url}: {e}")
    return False

async def main():
    urls = [
        "wss://api-t1.fyers.in/socket/v3/data",
        "wss://api.fyers.in/socket/v3/data",
        "wss://api.fyers.in/socket/v2/data",
        "wss://api.fyers.in/socket/v2/data/",
        "wss://api-t1.fyers.in/data-events/v3/quotes",
        "wss://api-t1.fyers.in/socket/v2/data"
    ]
    for url in urls:
        await test_url(url)

if __name__ == "__main__":
    asyncio.run(main())
