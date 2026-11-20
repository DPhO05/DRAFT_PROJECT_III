"""The assistant's conversation store: data/chat.db, one LangGraph thread per conversation."""

import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver


class ChatStore:
    """data/chat.db: one LangGraph thread per conversation (id = conversation id), one shared connection."""

    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA auto_vacuum = INCREMENTAL")  # takes effect with the VACUUM below
        self.conn.execute("VACUUM")  # prune frees pages but never shrinks the file; once per start is enough
        self.saver = SqliteSaver(self.conn)
        self.saver.setup()

    def prune(self, cid: str) -> None:
        """Keep the newest checkpoint of the thread. `SqliteSaver.prune` is not implemented (K28)."""
        with self.saver.cursor() as cur:
            for sql in (
                "DELETE FROM writes WHERE thread_id = ? AND checkpoint_id !="
                " (SELECT MAX(checkpoint_id) FROM checkpoints WHERE thread_id = ?)",
                "DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id !="
                " (SELECT MAX(checkpoint_id) FROM checkpoints WHERE thread_id = ?)",
            ):
                cur.execute(sql, (cid, cid))
        with self.saver.lock:  # give the freed pages and the WAL back, or the files stay at the turn's peak
            self.conn.execute("PRAGMA incremental_vacuum").fetchall()  # it frees one page per row fetched
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def head(self, cid: str) -> str | None:
        t = self.saver.get_tuple({"configurable": {"thread_id": cid}})
        return t.config["configurable"]["checkpoint_id"] if t else None

    def answered(self, cid: str) -> bool:
        """True when no call of the thread's newest AI message is left without a tool answer, so nothing waits."""
        t = self.saver.get_tuple({"configurable": {"thread_id": cid}})
        msgs = t.checkpoint["channel_values"].get("messages", []) if t else []
        calls = next((m.tool_calls for m in reversed(msgs) if isinstance(m, AIMessage) and m.tool_calls), [])
        done = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
        return all(c["id"] in done for c in calls)

    def reset_pause(self, cid: str, checkpoint_id: str) -> None:
        """A retried decision starts from the paused checkpoint: its finished writes would replay the first answer."""
        with self.saver.cursor() as cur:
            cur.execute(
                "DELETE FROM writes WHERE thread_id = ? AND checkpoint_id = ? AND channel != '__interrupt__'",
                (cid, checkpoint_id),
            )

    def close(self) -> None:
        self.conn.close()
