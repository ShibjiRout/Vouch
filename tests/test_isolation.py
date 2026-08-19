"""The four tests that gate everything after them.

Each one asserts that a client cannot reach data it does not own.
If any of these fail, nothing built on top of them is safe.
"""

import uuid

from app.db.qdrant import delete_thread, upsert_chunks
from app.ingest.chunk import Chunk
from app.ingest.embed import embed_texts
from app.retrieval.hybrid import search

SECRET = "The Zurich vault access code is Nightingale 4471."


def seed(tenant_id: str, thread_id: str, text: str) -> None:
    """Put one chunk into a chat."""
    upsert_chunks(
        tenant_id=uuid.UUID(tenant_id),
        thread_id=uuid.UUID(thread_id),
        document_id=uuid.uuid4(),
        filename="seed.pdf",
        chunks=[Chunk(text, 1, "text", 0)],
        vectors=embed_texts([text]),
    )


def new_thread(client, headers) -> str:
    response = client.post("/threads", json={"title": "t"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["thread_id"]


def test_cross_tenant_retrieval_returns_nothing(client, make_tenant):
    """Tenant B cannot retrieve a phrase that exists only in tenant A."""
    a, b = make_tenant(), make_tenant()
    thread_a = new_thread(client, a["headers"])
    thread_b = new_thread(client, b["headers"])

    seed(a["tenant_id"], thread_a, SECRET)
    try:
        assert search(SECRET, uuid.UUID(a["tenant_id"]), uuid.UUID(thread_a))

        # B's own thread, but B's tenant id.
        assert search(SECRET, uuid.UUID(b["tenant_id"]), uuid.UUID(thread_b)) == []
        # B's tenant id against A's thread id — a forged thread id.
        assert search(SECRET, uuid.UUID(b["tenant_id"]), uuid.UUID(thread_a)) == []
    finally:
        delete_thread(uuid.UUID(a["tenant_id"]), uuid.UUID(thread_a))


def test_cross_thread_retrieval_returns_nothing(client, make_tenant):
    """One chat cannot retrieve another chat's documents, same tenant."""
    a = make_tenant()
    first = new_thread(client, a["headers"])
    second = new_thread(client, a["headers"])

    seed(a["tenant_id"], first, SECRET)
    try:
        assert search(SECRET, uuid.UUID(a["tenant_id"]), uuid.UUID(first))
        assert search(SECRET, uuid.UUID(a["tenant_id"]), uuid.UUID(second)) == []
    finally:
        delete_thread(uuid.UUID(a["tenant_id"]), uuid.UUID(first))


def test_foreign_thread_returns_404(client, make_tenant):
    """Another tenant's thread id gives 404, never 403."""
    a, b = make_tenant(), make_tenant()
    thread_a = new_thread(client, a["headers"])

    for method, path in [
        ("get", f"/threads/{thread_a}"),
        ("delete", f"/threads/{thread_a}"),
        ("get", f"/threads/{thread_a}/documents"),
    ]:
        response = getattr(client, method)(path, headers=b["headers"])
        # 403 would confirm the id was real.
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"

    # And it still exists for its owner.
    assert client.get(f"/threads/{thread_a}", headers=a["headers"]).status_code == 200


def test_tenant_id_in_body_is_ignored(client, make_tenant):
    """A forged tenant_id in the body changes nothing."""
    a, b = make_tenant(), make_tenant()

    response = client.post(
        "/threads",
        json={"title": "forged", "tenant_id": b["tenant_id"]},
        headers=a["headers"],
    )
    assert response.status_code == 201
    thread_id = response.json()["thread_id"]

    # The thread belongs to A, whose token was used — not to B.
    assert client.get(f"/threads/{thread_id}", headers=a["headers"]).status_code == 200
    assert client.get(f"/threads/{thread_id}", headers=b["headers"]).status_code == 404


def test_member_cannot_delete_another_users_thread(client, make_tenant):
    """A member may only delete chats they created."""
    admin = make_tenant()
    email = f"member-{uuid.uuid4().hex[:12]}@example.test"
    assert (
        client.post(
            "/users",
            json={"email": email, "password": "testpass123"},
            headers=admin["headers"],
        ).status_code
        == 201
    )

    token = client.post(
        "/auth/login", data={"username": email, "password": "testpass123"}
    ).json()["access_token"]
    member_headers = {"Authorization": f"Bearer {token}"}

    thread_id = new_thread(client, admin["headers"])

    # Same tenant, so it is visible — but not deletable.
    assert client.get(f"/threads/{thread_id}", headers=member_headers).status_code == 200
    assert (
        client.delete(f"/threads/{thread_id}", headers=member_headers).status_code == 403
    )
    assert (
        client.post("/users", json={"email": "x@y.test", "password": "testpass123"},
                    headers=member_headers).status_code == 403
    )
