"""Сценарии ЛР2: прогон REST API по HTTP.

Запуск (из каталога src):
    python -m app.scripts.demo_api
        приложение поднимается внутри процесса, сервер запускать не нужно;
    BASE_URL=http://localhost python -m app.scripts.demo_api
        запросы идут на уже запущенный сервер (uvicorn или Nginx на порту 80).

Перед прогоном сам вызывает seed_api (идемпотентно). Нужен пакет httpx.
Если код ответа может быть разным в зависимости от реализации сервиса,
ожидаемые коды перечислены кортежем, а фактический виден в выводе.
"""
import asyncio
import os
import uuid

import httpx

from app.core.db import engine, session_factory
from app.core.text import normalize_name
from app.models import AccessType, BookStatus, RoleTypes, UserStatus
from app.scripts import seed_api

engine.echo = False
PASSWORD = "demo-password-1"
TEXT = "Учебный текст книги. " * 20


def head(text: str) -> None:
    print(f"\n{text}")


def make_client() -> httpx.AsyncClient:
    base_url = os.getenv("BASE_URL")
    if base_url:
        return httpx.AsyncClient(base_url=base_url, timeout=10)
    from app.main import app  # импорт здесь, чтобы режим BASE_URL не создавал приложение

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=10
    )


async def call(client, label, method, url, expected, **kwargs) -> httpx.Response:
    """Один HTTP-запрос с проверкой кода (число или кортеж допустимых кодов)."""
    resp = await client.request(method, url, **kwargs)
    codes = (expected,) if isinstance(expected, int) else tuple(expected)
    detail = f" - {resp.json().get('detail')}" if resp.status_code >= 400 else ""
    mark = "OK" if resp.status_code in codes else "ОШИБКА"
    print(f"  [{mark}] {label}: {method} {url} -> {resp.status_code}{detail}")
    if resp.status_code not in codes:
        raise AssertionError(f"{label}: ожидался {codes}, получен {resp.status_code}")
    return resp


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client, email: str, password: str, label: str = "вход") -> str:
    resp = await call(client, label, "POST", "/login", 200,
                      data={"username": email, "password": password})  # форма, не JSON
    return resp.json()["access_token"]


async def run_api_demo() -> None:
    tag = uuid.uuid4().hex[:6]
    email = f"anna.{tag}@example.com"

    async with session_factory() as s:
        await seed_api.ensure_seed(s)
        await s.commit()

    async with make_client() as client:
        head("0. Сервис доступен")
        await call(client, "проверка", "GET", "/health", 200)

        # ---------------------------------------------------------------
        head("1. Регистрация")
        resp = await call(client, "регистрация", "POST", "/register", 201, json={
            "full_name": "Анна Иванова", "email": email, "password": PASSWORD,
            "role": "ADMIN",  # попытка выдать себе роль: поле должно игнорироваться
        })
        print(f"         создан пользователь id={resp.json()['id']}, статус {resp.json()['status']}")
        await call(client, "повторный email", "POST", "/register", 409, json={
            "full_name": "Аня", "email": email.upper(), "password": PASSWORD})
        await call(client, "короткий пароль", "POST", "/register", 422, json={
            "full_name": "Т", "email": f"x.{tag}@example.com", "password": "123"})

        head("2. Вход и токен")
        await call(client, "неверный пароль", "POST", "/login", 401,
                   data={"username": email, "password": "wrong-password"})
        await call(client, "неизвестный email", "POST", "/login", 401,
                   data={"username": f"nobody.{tag}@example.com", "password": PASSWORD})
        token = await login(client, email, PASSWORD)
        print(f"         токен выдан ({len(token)} символов)")

        head("3. Профиль (/me)")
        await call(client, "без токена", "GET", "/me", 401)
        await call(client, "испорченный токен", "GET", "/me", 401,
                   headers=bearer(token + "x"))
        me = (await call(client, "с токеном", "GET", "/me", 200,
                         headers=bearer(token))).json()
        assert me["role"] == RoleTypes.READER.value, "роль из /register должна быть READER"
        print(f"         роль {me['role']}: поле role из запроса проигнорировано")

        head("4. Интересы читателя")
        genres = {g["name"]: g["id"] for g in (await call(
            client, "список жанров", "GET", "/genres", 200, headers=bearer(token))).json()}
        classic = genres[normalize_name("Классика")]
        scifi = genres[normalize_name("Фантастика")]
        await call(client, "сохранить", "PUT", "/me/interests", 200,
                   headers=bearer(token), json={"genre_ids": [classic, scifi]})
        got = (await call(client, "прочитать", "GET", "/me/interests", 200,
                          headers=bearer(token))).json()
        assert set(got["genre_ids"]) == {classic, scifi}
        print(f"         жанры сохранены: {sorted(got['genre_ids'])}")

        # ---------------------------------------------------------------
        head("5. Роли и права доступа")
        admin_token = await login(client, seed_api.ADMIN_EMAIL,
                                  seed_api.ADMIN_PASSWORD, "вход администратора")
        admin_me = (await call(client, "профиль админа", "GET", "/me", 200,
                               headers=bearer(admin_token))).json()
        print(f"         роль {admin_me['role']}")
        await call(client, "админ на эндпоинте читателя", "GET", "/me/interests", 403,
                   headers=bearer(admin_token))
        await call(client, "читатель в админке", "GET", "/admin/users", 403,
                   headers=bearer(token))
        await call(client, "читатель меняет справочник", "POST", "/genres", 403,
                   headers=bearer(token), json={"name": "Хак"})
        await call(client, "справочник без токена", "GET", "/genres", 401)

        # ---------------------------------------------------------------
        head("6. Администратор: пользователи и библиотекари")
        users = (await call(client, "список пользователей", "GET", "/admin/users", 200,
                            headers=bearer(admin_token), params={"limit": 100})).json()
        assert any(u["email"] == seed_api.ADMIN_EMAIL for u in users)
        print(f"         получено пользователей: {len(users)}")
        await call(client, "неверный limit", "GET", "/admin/users", 422,
                   headers=bearer(admin_token), params={"limit": 1000})

        lib_email = f"lib.{tag}@example.com"
        lib = (await call(client, "создание библиотекаря", "POST", "/admin/librarians", 201,
                          headers=bearer(admin_token), json={
                              "full_name": "Ольга Книгина", "email": lib_email,
                              "password": PASSWORD})).json()
        await call(client, "повторный email библиотекаря", "POST", "/admin/librarians", 409,
                   headers=bearer(admin_token), json={
                       "full_name": "Ольга", "email": lib_email, "password": PASSWORD})
        lib_token = await login(client, lib_email, PASSWORD, "вход библиотекаря")
        lib_me = (await call(client, "профиль библиотекаря", "GET", "/me", 200,
                             headers=bearer(lib_token))).json()
        assert lib_me["role"] == RoleTypes.LIBRARIAN.value
        print(f"         создан библиотекарь id={lib['id']}, роль {lib_me['role']}")
        await call(client, "читатель создаёт библиотекаря", "POST", "/admin/librarians", 403,
                   headers=bearer(token), json={
                       "full_name": "Х", "email": f"h.{tag}@example.com", "password": PASSWORD})
        await call(client, "блокировка несуществующего", "POST",
                   "/admin/users/999999999/block", 404, headers=bearer(admin_token))

        # ---------------------------------------------------------------
        head("7. Справочники (администратор)")
        genre = (await call(client, "создание жанра", "POST", "/genres", 201,
                            headers=bearer(admin_token),
                            json={"name": f"Демо жанр {tag}"})).json()
        await call(client, "дубликат жанра", "POST", "/genres", 409,
                   headers=bearer(admin_token), json={"name": f"демо  ЖАНР {tag}"})
        await call(client, "пустое имя", "POST", "/genres", 422,
                   headers=bearer(admin_token), json={"name": "   "})
        await call(client, "переименование жанра", "PATCH", f"/genres/{genre['id']}", 200,
                   headers=bearer(admin_token), json={"name": f"Демо жанр {tag} ред"})
        author = (await call(client, "создание автора", "POST", "/authors", 201,
                             headers=bearer(admin_token),
                             json={"name": f"Автор Демо {tag}"})).json()
        listed = (await call(client, "список авторов читателю", "GET", "/authors", 200,
                             headers=bearer(token))).json()
        assert any(a["id"] == author["id"] for a in listed)
        await call(client, "библиотекарь меняет справочник", "POST", "/authors", 403,
                   headers=bearer(lib_token), json={"name": "Хак"})
        temp = (await call(client, "жанр без связей", "POST", "/genres", 201,
                           headers=bearer(admin_token),
                           json={"name": f"Временный жанр {tag}"})).json()
        await call(client, "удаление жанра без связей", "DELETE",
                   f"/genres/{temp['id']}", 204, headers=bearer(admin_token))
        await call(client, "удаление несуществующего жанра", "DELETE",
                   f"/genres/{temp['id']}", 404, headers=bearer(admin_token))

        # ---------------------------------------------------------------
        head("8. Каталог: библиотекарь заводит книгу, читатель её находит")
        title = f"Демо-книга {tag}"
        draft = (await call(client, "создание черновика", "POST", "/librarian/books", 201,
                            headers=bearer(lib_token), json={
                                "title": title, "description": "Описание демо-книги",
                                "publication_year": 2024,
                                "author_ids": [author["id"]], "genre_ids": [genre["id"]],
                            })).json()
        book_id = draft["id"]
        assert draft["status"] == BookStatus.DRAFT.value
        await call(client, "читатель создаёт книгу", "POST", "/librarian/books", 403,
                   headers=bearer(token), json={"title": "Хак"})
        found = (await call(client, "поиск читателем (черновик)", "GET", "/books", 200,
                            headers=bearer(token), params={"title": tag})).json()
        assert found == [], "черновик не должен быть виден читателю"
        await call(client, "карточка черновика читателю", "GET", f"/books/{book_id}",
                   (404, 409), headers=bearer(token))
        await call(client, "библиотекарь видит черновик", "GET",
                   f"/librarian/books/{book_id}", 200, headers=bearer(lib_token))
        edited = (await call(client, "правка названия", "PATCH",
                             f"/librarian/books/{book_id}", 200, headers=bearer(lib_token),
                             json={"title": f"{title} (изд. 2)"})).json()
        assert edited["title"].endswith("(изд. 2)")
        await call(client, "публикация без текста и экземпляров", "POST",
                   f"/librarian/books/{book_id}/publish", 409, headers=bearer(lib_token))
        await call(client, "электронная версия", "PUT",
                   f"/librarian/books/{book_id}/electronic", 200, headers=bearer(lib_token),
                   json={"access_type": AccessType.FREE.value, "text_content": TEXT})
        published = (await call(client, "публикация", "POST",
                                f"/librarian/books/{book_id}/publish", 200,
                                headers=bearer(lib_token))).json()
        assert published["status"] == BookStatus.PUBLISHED.value
        await call(client, "повторная публикация", "POST",
                   f"/librarian/books/{book_id}/publish", 409, headers=bearer(lib_token))
        await call(client, "удаление опубликованной книги", "DELETE",
                   f"/librarian/books/{book_id}", 409, headers=bearer(lib_token))

        found = (await call(client, "поиск читателем (опубликована)", "GET", "/books", 200,
                            headers=bearer(token), params={"title": tag})).json()
        assert [b["id"] for b in found] == [book_id]
        card = (await call(client, "карточка книги", "GET", f"/books/{book_id}", 200,
                           headers=bearer(token))).json()
        assert "text_content" not in card, "текст книги не должен попадать в карточку"
        print(f"         доступна онлайн: {card['available_online']}, "
              f"экземпляров: {card['copies_available']}, оценок: {card['rating']['count']}")

        bare = (await call(client, "черновик без автора и жанра", "POST",
                           "/librarian/books", 201, headers=bearer(lib_token),
                           json={"title": f"Пустой черновик {tag}",
                                 "description": "Описание"})).json()
        await call(client, "электронная версия пустого черновика", "PUT",
                   f"/librarian/books/{bare['id']}/electronic", 200,
                   headers=bearer(lib_token),
                   json={"access_type": AccessType.FREE.value, "text_content": TEXT})
        await call(client, "публикация без автора и жанра", "POST",
                   f"/librarian/books/{bare['id']}/publish", 409, headers=bearer(lib_token))
        await call(client, "удаление черновика", "DELETE",
                   f"/librarian/books/{bare['id']}", 204, headers=bearer(lib_token))
        await call(client, "черновик удалён", "GET", f"/librarian/books/{bare['id']}", 404,
                   headers=bearer(lib_token))

        await call(client, "удаление жанра со связями", "DELETE", f"/genres/{genre['id']}",
                   204, headers=bearer(admin_token))
        await call(client, "удаление автора со связями", "DELETE",
                   f"/authors/{author['id']}", 204, headers=bearer(admin_token))

        # ---------------------------------------------------------------
        head("9. Оценки (читатель из seed дочитал книгу)")
        reader_token = await login(client, seed_api.READER_EMAIL,
                                   seed_api.READER_PASSWORD, "вход читателя из seed")
        reader_id = (await call(client, "профиль читателя", "GET", "/me", 200,
                                headers=bearer(reader_token))).json()["id"]
        rated = (await call(client, "поиск книги из seed", "GET", "/books", 200,
                            headers=bearer(reader_token),
                            params={"title": seed_api.RATED_BOOK_TITLE})).json()
        rated_id = next(b["id"] for b in rated if b["title"] == seed_api.RATED_BOOK_TITLE)

        await call(client, "оценка вне диапазона (11)", "PUT", f"/books/{rated_id}/rating",
                   422, headers=bearer(reader_token), json={"score": 11})
        await call(client, "оценка вне диапазона (0)", "PUT", f"/books/{rated_id}/rating",
                   422, headers=bearer(reader_token), json={"score": 0})
        r1 = (await call(client, "оценка дочитанной книги", "PUT",
                         f"/books/{rated_id}/rating", 200, headers=bearer(reader_token),
                         json={"score": 8, "comment": "  Хорошо  "})).json()
        assert (r1["score"], r1["comment"], r1["user_id"]) == (8, "Хорошо", reader_id)
        r2 = (await call(client, "изменение оценки", "PUT", f"/books/{rated_id}/rating",
                         200, headers=bearer(reader_token), json={"score": 9})).json()
        assert r2["score"] == 9
        rows = (await call(client, "список оценок книги", "GET",
                           f"/books/{rated_id}/ratings", 200,
                           headers=bearer(reader_token))).json()
        mine = [r for r in rows if r["user_id"] == reader_id]
        assert len(mine) == 1 and mine[0]["score"] == 9, "оценка читателя одна и обновлена"
        card = (await call(client, "сводка в карточке", "GET", f"/books/{rated_id}", 200,
                           headers=bearer(reader_token))).json()
        print(f"         в карточке: оценок {card['rating']['count']}, "
              f"средняя {card['rating']['average']}")

        await call(client, "оценка недочитанной книги", "PUT", f"/books/{book_id}/rating",
                   (403, 409, 422), headers=bearer(reader_token), json={"score": 5})
        await call(client, "библиотекарь оценивает", "PUT", f"/books/{rated_id}/rating",
                   403, headers=bearer(lib_token), json={"score": 5})
        await call(client, "оценки без токена", "GET", f"/books/{rated_id}/ratings", 401)
        await call(client, "удаление оценки", "DELETE", f"/books/{rated_id}/rating", 204,
                   headers=bearer(reader_token))
        await call(client, "повторное удаление оценки", "DELETE",
                   f"/books/{rated_id}/rating", (404, 409), headers=bearer(reader_token))

        # ---------------------------------------------------------------
        head("10. Рекомендации (заглушка до ЛР3)")
        recs = (await call(client, "рекомендации читателю", "GET", "/me/recommendations",
                           200, headers=bearer(token))).json()
        assert recs == {"items": []}
        await call(client, "рекомендации библиотекарю", "GET", "/me/recommendations", 403,
                   headers=bearer(lib_token))
        await call(client, "рекомендации без токена", "GET", "/me/recommendations", 401)

        # ---------------------------------------------------------------
        head("11. Блокировка действует сразу, токен уже выдан")
        blocked = (await call(client, "блокировка читателя", "POST",
                              f"/admin/users/{me['id']}/block", 200,
                              headers=bearer(admin_token))).json()
        assert blocked["status"] == UserStatus.BLOCKED.value
        await call(client, "заблокированный, старый токен", "GET", "/me", 403,
                   headers=bearer(token))
        await call(client, "читатель блокирует других", "POST",
                   f"/admin/users/{lib['id']}/block", 403, headers=bearer(token))
        await call(client, "разблокировка читателя", "POST",
                   f"/admin/users/{me['id']}/unblock", 200, headers=bearer(admin_token))
        await call(client, "после разблокировки, тот же токен", "GET", "/me", 200,
                   headers=bearer(token))

    print("\nСценарии ЛР2 выполнены.")


async def _main() -> None:
    try:
        await run_api_demo()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())