import requests
import time

URL = "https://clob.polymarket.com/health"

def measure_ttfb():
    start = time.time()

    response = requests.get(URL, stream=True)

    first_byte_time = time.time()
    ttfb = first_byte_time - start

    total_time = response.elapsed.total_seconds()

    return {
        "TTFB_ms": round(ttfb * 1000, 2),
        "Total_ms": round(total_time * 1000, 2),
        "status": response.status_code
    }

if __name__ == "__main__":
    results = [measure_ttfb() for _ in range(10)]
    for r in results:
        print(r)