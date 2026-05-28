from datetime import UTC, datetime, timedelta

from backend.app.services.conversation_memory_service import ConversationMemoryService
from database.models.ChatMessage import ChatMessage
from database.models.ChatSession import ChatSession


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *conditions):
        filtered = self.rows
        for condition in conditions:
            left = getattr(condition, "left", None)
            right = getattr(condition, "right", None)
            column_name = getattr(left, "name", "")
            table_name = getattr(getattr(left, "table", None), "name", "")
            value = getattr(right, "value", None)

            if table_name == "chat_sessions" and column_name == "id":
                filtered = [row for row in filtered if getattr(row, "id", None) == value]
            elif table_name == "chat_messages" and column_name == "chat_id":
                filtered = [row for row in filtered if getattr(row, "chat_id", None) == value]
            elif table_name == "chat_messages" and column_name == "role":
                filtered = [row for row in filtered if getattr(row, "role", None) == value]
        self.rows = filtered
        return self

    def order_by(self, *args):
        self.rows.sort(key=lambda row: (getattr(row, "created_at", datetime.min), getattr(row, "id", 0)), reverse=True)
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return FakeQuery([row for row in self.rows if isinstance(row, model)])


def message(message_id, chat_id, role, content, created_at, metadata_json=None):
    return ChatMessage(
        id=message_id,
        chat_id=chat_id,
        role=role,
        content=content,
        created_at=created_at,
        metadata_json=metadata_json,
    )


def test_recent_messages_are_chronological():
    now = datetime.now(UTC)
    rows = [
        ChatSession(id=1, user_id=1, summary="Summary"),
        message(1, 1, "user", "first", now - timedelta(minutes=2)),
        message(2, 1, "agent", "second", now - timedelta(minutes=1)),
    ]

    memory = ConversationMemoryService(FakeSession(rows)).load_memory(1)

    assert [m.content for m in memory.recent_messages] == ["first", "second"]


def test_previous_sources_are_extracted_and_deduplicated():
    now = datetime.now(UTC)
    rows = [
        ChatSession(id=1, user_id=1),
        message(
            1,
            1,
            "agent",
            "answer",
            now,
            {
                "sources": [
                    {"source_id": "S1", "article_id": 10, "title": "A"},
                    {"source_id": "S2", "article_id": 10, "title": "A duplicate"},
                    {"source_id": "S3", "article_id": 20, "title": "B"},
                ]
            },
        ),
    ]

    memory = ConversationMemoryService(FakeSession(rows)).load_memory(1)

    assert [source["article_id"] for source in memory.previous_sources] == [10, 20]


def test_memory_block_contains_summary_messages_and_sources():
    now = datetime.now(UTC)
    rows = [
        ChatSession(id=1, user_id=1, summary="User studies RAG."),
        message(1, 1, "user", "papers?", now - timedelta(minutes=1)),
        message(
            2,
            1,
            "agent",
            "answer",
            now,
            {"sources": [{"source_id": "S1", "article_id": 42, "title": "RAG Paper", "doi": "10.x", "url": "u"}]},
        ),
    ]

    block = ConversationMemoryService(FakeSession(rows)).load_memory(1).as_prompt_block()

    assert "Conversation summary:" in block
    assert "User studies RAG." in block
    assert "User: papers?" in block
    assert '[S1] article_id=42 title="RAG Paper"' in block


def test_different_sessions_do_not_mix_sources():
    now = datetime.now(UTC)
    rows = [
        ChatSession(id=1, user_id=1),
        ChatSession(id=2, user_id=1),
        message(1, 1, "agent", "answer", now, {"sources": [{"source_id": "S1", "article_id": 10, "title": "A"}]}),
        message(2, 2, "agent", "answer", now, {"sources": [{"source_id": "S1", "article_id": 20, "title": "B"}]}),
    ]

    memory = ConversationMemoryService(FakeSession(rows)).load_memory(1)

    assert [source["article_id"] for source in memory.previous_sources] == [10]
