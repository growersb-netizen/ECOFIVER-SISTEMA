import sqlite3
import json
from datetime import datetime, date
from contextlib import contextmanager
from config import DATABASE_URL


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT NOT NULL,
                client_name TEXT,
                agent TEXT,
                product TEXT,
                modality TEXT,
                locality TEXT,
                lead_score TEXT DEFAULT 'frio',
                status TEXT DEFAULT 'activo',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                client_name TEXT,
                agent TEXT,
                product TEXT,
                modality TEXT,
                locality TEXT,
                lead_score TEXT,
                summary TEXT,
                notified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date TEXT NOT NULL,
                total_conversations INTEGER DEFAULT 0,
                total_leads INTEGER DEFAULT 0,
                hot_leads INTEGER DEFAULT 0,
                pablo_conv INTEGER DEFAULT 0,
                pablo_leads INTEGER DEFAULT 0,
                laura_conv INTEGER DEFAULT 0,
                laura_leads INTEGER DEFAULT 0,
                sabrina_conv INTEGER DEFAULT 0,
                sabrina_leads INTEGER DEFAULT 0,
                claudio_conv INTEGER DEFAULT 0,
                claudio_leads INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_or_create_conversation(phone_number: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE phone_number = ? AND status = 'activo' ORDER BY created_at DESC LIMIT 1",
            (phone_number,)
        ).fetchone()
        if row:
            return dict(row)
        cursor = conn.execute(
            "INSERT INTO conversations (phone_number) VALUES (?)",
            (phone_number,)
        )
        return {"id": cursor.lastrowid, "phone_number": phone_number, "agent": None,
                "product": None, "modality": None, "locality": None,
                "lead_score": "frio", "status": "activo", "client_name": None}


def update_conversation(conv_id: int, **kwargs):
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now().isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [conv_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE conversations SET {fields} WHERE id = ?", values)


def save_message(conversation_id: int, role: str, content: str, message_type: str = "text"):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, message_type) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, message_type)
        )


def get_conversation_messages(conversation_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, message_type, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def save_lead(conversation_id: int, phone_number: str, agent: str, client_name: str,
              product: str, modality: str, locality: str, lead_score: str, summary: str):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE leads SET agent=?, client_name=?, product=?, modality=?,
                   locality=?, lead_score=?, summary=? WHERE conversation_id=?""",
                (agent, client_name, product, modality, locality, lead_score, summary, conversation_id)
            )
            return existing["id"]
        cursor = conn.execute(
            """INSERT INTO leads (conversation_id, phone_number, agent, client_name,
               product, modality, locality, lead_score, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conversation_id, phone_number, agent, client_name, product,
             modality, locality, lead_score, summary)
        )
        return cursor.lastrowid


def mark_lead_notified(lead_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE leads SET notified = 1 WHERE id = ?", (lead_id,))


def get_lead_notified_status(lead_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT notified FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return bool(row["notified"]) if row else False


def get_today_stats() -> dict:
    today = date.today().isoformat()
    with get_conn() as conn:
        total_conv = conn.execute(
            "SELECT COUNT(*) as c FROM conversations WHERE DATE(created_at) = ?", (today,)
        ).fetchone()["c"]

        total_leads = conn.execute(
            "SELECT COUNT(*) as c FROM leads WHERE DATE(created_at) = ?", (today,)
        ).fetchone()["c"]

        hot_leads = conn.execute(
            "SELECT COUNT(*) as c FROM leads WHERE DATE(created_at) = ? AND lead_score = 'caliente'", (today,)
        ).fetchone()["c"]

        agents = ["pablo", "laura", "sabrina", "claudio"]
        agent_stats = {}
        for agent in agents:
            conv = conn.execute(
                "SELECT COUNT(*) as c FROM conversations WHERE DATE(created_at) = ? AND agent = ?",
                (today, agent)
            ).fetchone()["c"]
            leads = conn.execute(
                "SELECT COUNT(*) as c FROM leads WHERE DATE(created_at) = ? AND agent = ?",
                (today, agent)
            ).fetchone()["c"]
            agent_stats[agent] = {"conversations": conv, "leads": leads}

        return {
            "date": today,
            "total_conversations": total_conv,
            "total_leads": total_leads,
            "hot_leads": hot_leads,
            "agents": agent_stats,
            "conversion_rate": round((total_leads / total_conv * 100) if total_conv > 0 else 0, 1)
        }


def get_all_conversations(limit: int = 50, agent: str = None, score: str = None) -> list:
    with get_conn() as conn:
        query = "SELECT c.*, l.lead_score as lead_score_lead FROM conversations c LEFT JOIN leads l ON c.id = l.conversation_id WHERE 1=1"
        params = []
        if agent:
            query += " AND c.agent = ?"
            params.append(agent)
        if score:
            query += " AND c.lead_score = ?"
            params.append(score)
        query += " ORDER BY c.updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_all_leads(limit: int = 100, score: str = None, agent: str = None) -> list:
    with get_conn() as conn:
        query = "SELECT * FROM leads WHERE 1=1"
        params = []
        if score:
            query += " AND lead_score = ?"
            params.append(score)
        if agent:
            query += " AND agent = ?"
            params.append(agent)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_conversation_detail(conv_id: int) -> dict:
    with get_conn() as conn:
        conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not conv:
            return None
        messages = get_conversation_messages(conv_id)
        lead = conn.execute("SELECT * FROM leads WHERE conversation_id = ?", (conv_id,)).fetchone()
        return {
            "conversation": dict(conv),
            "messages": messages,
            "lead": dict(lead) if lead else None
        }
