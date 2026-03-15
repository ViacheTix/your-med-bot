"""При первом запуске заполняет БД тестовыми данными, затем запускает бота."""
import os
import subprocess
import sys


def main() -> None:
    from db.connection import get_connection, init_db

    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) AS n FROM doctors")
        n = cur.fetchone()["n"]
    finally:
        conn.close()

    if n == 0:
        subprocess.run([sys.executable, "-m", "scripts.seed_db"], check=True, env=os.environ)
    os.execv(sys.executable, [sys.executable, "-m", "bot.main"])


if __name__ == "__main__":
    main()
