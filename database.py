import sqlite3

DATABASE_NAME = "transactions.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def create_table():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            user_id INTEGER NOT NULL
        )
    """)

    cursor.execute("PRAGMA table_info(transactions)")
    columns = [column["name"] for column in cursor.fetchall()]

    if "user_id" not in columns:
        cursor.execute("""
            ALTER TABLE transactions
            ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1
        """)

    # Таблица временных кодов привязки
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS link_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)

    # Таблица связей пользователей сайта с VK
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vk_links (
            vk_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE
        )
    """)

    connection.commit()
    connection.close()


def add_transaction(transaction_type, amount, category, user_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO transactions (type, amount, category, user_id)
        VALUES (?, ?, ?, ?)
        """,
        (transaction_type, amount, category, user_id)
    )

    connection.commit()
    transaction_id = cursor.lastrowid
    connection.close()

    return transaction_id


def get_transactions(user_id, transaction_type=None):
    connection = get_connection()
    cursor = connection.cursor()

    if transaction_type:
        cursor.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ? AND type = ?
            ORDER BY id DESC
            """,
            (user_id, transaction_type)
        )
    else:
        cursor.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,)
        )

    transactions = cursor.fetchall()
    connection.close()

    return [dict(transaction) for transaction in transactions]


def get_balance(user_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM transactions WHERE user_id = ?",
        (user_id,)
    )

    transactions = cursor.fetchall()

    income = 0
    expenses = 0

    for transaction in transactions:
        if transaction["type"] == "income":
            income += transaction["amount"]
        else:
            expenses += transaction["amount"]

    connection.close()

    return {
        "income": income,
        "expenses": expenses,
        "balance": income - expenses
    }


def update_transaction(transaction_id, user_id, transaction_type, amount, category):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE transactions
        SET type = ?, amount = ?, category = ?
        WHERE id = ? AND user_id = ?
        """,
        (transaction_type, amount, category, transaction_id, user_id)
    )

    connection.commit()
    updated = cursor.rowcount > 0
    connection.close()

    return updated


def delete_transaction(transaction_id, user_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM transactions
        WHERE id = ? AND user_id = ?
        """,
        (transaction_id, user_id)
    )

    transaction = cursor.fetchone()

    if transaction is not None:
        cursor.execute(
            """
            DELETE FROM transactions
            WHERE id = ? AND user_id = ?
            """,
            (transaction_id, user_id)
        )
        connection.commit()

    connection.close()

    if transaction is not None:
        return dict(transaction)

    return None


def create_link_code(code, user_id, expires_at):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO link_codes (code, user_id, expires_at)
        VALUES (?, ?, ?)
        """,
        (code, user_id, expires_at)
    )

    connection.commit()
    connection.close()


def link_vk_account(code, vk_id, current_time):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT user_id, expires_at
        FROM link_codes
        WHERE code = ?
        """,
        (code,)
    )

    link_code = cursor.fetchone()

    if link_code is None:
        connection.close()
        return "invalid_or_expired"

    if link_code["expires_at"] <= current_time:
        cursor.execute(
            "DELETE FROM link_codes WHERE code = ?",
            (code,)
        )
        connection.commit()
        connection.close()
        return "invalid_or_expired"

    user_id = link_code["user_id"]

    try:
        cursor.execute(
            """
            INSERT INTO vk_links (vk_id, user_id)
            VALUES (?, ?)
            """,
            (vk_id, user_id)
        )

        cursor.execute(
            "DELETE FROM link_codes WHERE code = ?",
            (code,)
        )

        connection.commit()
        connection.close()
        return "linked"

    except sqlite3.IntegrityError:
        connection.rollback()
        connection.close()
        return "already_linked"


def get_user_id_by_vk(vk_id):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT user_id FROM vk_links WHERE vk_id = ?",
        (vk_id,)
    )

    result = cursor.fetchone()
    connection.close()

    if result is None:
        return None

    return result["user_id"]