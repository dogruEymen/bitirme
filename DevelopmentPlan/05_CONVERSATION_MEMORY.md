# 05_CONVERSATION_MEMORY.md — Session Memory for Chat

## Role

You are a Senior AI Engineer implementing conversation memory. The goal is not to create user profiling or long-term memory. The goal is continuity inside one chat session.

## Target file

Create:

```text
backend/app/services/conversation_memory_service.py
```

Modify:

```text
database/models/ChatSession.py
database/models/ChatMessage.py
backend/app/api/routes/chat.py
backend/app/services/chat_orchestrator.py
```

## Memory scope

Memory is session-local.

The assistant may remember:

- previous user messages in the same chat session,
- previous assistant answers in the same chat session,
- previous RAG sources saved in message metadata,
- session summary saved in `chat_sessions.summary`.

The assistant must not remember across sessions unless a future feature explicitly implements that.

## Memory block structure

Build this block for both routing and final answer prompts:

```text
Conversation summary:
{summary or "No summary yet."}

Recent messages:
User: ...
Assistant: ...

Previous cited sources:
[S1] article_id=123 title="..." doi="..." url="..."
[S2] article_id=456 title="..." doi="..." url="..."
```

## Loading recent messages

Use `CHAT_HISTORY_LIMIT`, default 12.

Query:

```text
WHERE chat_id = session_id
ORDER BY created_at DESC
LIMIT CHAT_HISTORY_LIMIT
```

Then reverse the list before formatting so the prompt is chronological.

## Previous source extraction

Look at recent assistant messages where `metadata_json.sources` exists.

Flatten recent sources in recency order, then deduplicate by `article_id`. Keep a small maximum, for example 10 sources.

This enables follow-up references:

- “ikinci makale”,
- “S2 ne diyor?”,
- “bunları karşılaştır”,
- “önceki kaynakların DOI’lerini ver”.

## Summary update

When total message count exceeds `CHAT_SUMMARY_TRIGGER_MESSAGES`, update the session summary.

Use Ollama with `stream=false`.

Summary prompt:

```text
Summarize this chat session for future assistant continuity.
Keep it factual and compact.
Include:
- the user's research intent,
- mentioned topics/clusters/papers,
- important cited article IDs/titles,
- unresolved follow-up tasks.
Do not include hidden reasoning.
```

Store result in:

```text
chat_sessions.summary
chat_sessions.summary_updated_at
chat_sessions.updated_at
```

## What not to do

Do not store hidden reasoning.
Do not store user profile memory.
Do not summarize every turn.
Do not send the entire conversation forever.
Do not use a vector DB for chat memory in MVP.

## Acceptance criteria

- Follow-up questions work without repeating the paper title.
- Previous RAG sources can be reused.
- The prompt stays bounded as conversation length grows.
- Different chat sessions do not share memory.
