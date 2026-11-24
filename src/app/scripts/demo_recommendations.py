"""Read-only демонстрация ЛР3 на запущенном API и отдельном gRPC-процессе.

Токен читателя передаётся через BOOKSHELF_DEMO_TOKEN; скрипт не наполняет БД.
python -m app.scripts.demo_recommendations --base-url http://127.0.0.1:8000
"""

import argparse
import asyncio
import os

import httpx


async def run(base_url: str, token: str, limit: int):
    async with httpx.AsyncClient(base_url=base_url, timeout=310) as client:
        response = await client.get("/me/recommendations", params={"limit": limit},
                                    headers={"Authorization": f"Bearer {token}"})
        print(f"GET /me/recommendations?limit={limit} -> HTTP {response.status_code}")
        response.raise_for_status()
        items = response.json()["items"]
        assert len(items) <= limit
        assert len({item["book_id"] for item in items}) == len(items)
        for item in items:
            assert set(item) == {"book_id", "title", "score"}
            print(f"  {item['book_id']:>6}  {item['score']:.4f}  {item['title']}")
        print(f"Получено рекомендаций: {len(items)}. В логах API и gRPC видны вызов и вычисление.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    token = os.getenv("BOOKSHELF_DEMO_TOKEN")
    if not token:
        parser.error("Задайте BOOKSHELF_DEMO_TOKEN: JWT существующего читателя из POST /login")
    if not 1 <= args.limit <= 100:
        parser.error("--limit должен быть от 1 до 100")
    asyncio.run(run(args.base_url, token, args.limit))


if __name__ == "__main__":
    main()
