import sqlite3
import os

DB_NAME = "barra_rapida.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Tabla de bebidas
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS bebidas
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       nombre
                       TEXT
                       NOT
                       NULL,
                       precio
                       REAL
                       NOT
                       NULL,
                       stock
                       INTEGER
                       DEFAULT
                       0,
                       activa
                       INTEGER
                       DEFAULT
                       1
                   )
                   ''')

    # Tabla de pedidos
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS pedidos
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       estado
                       TEXT
                       DEFAULT
                       'pendiente',
                       mp_preference_id
                       TEXT,
                       mp_payment_id
                       TEXT,
                       codigo_qr
                       TEXT
                       UNIQUE,
                       total
                       REAL
                       DEFAULT
                       0,
                       creado_en
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP,
                       entregado_en
                       TIMESTAMP
                   )
                   ''')

    # Tabla items del pedido
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS items_pedido
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       pedido_id
                       INTEGER
                       NOT
                       NULL,
                       bebida_id
                       INTEGER
                       NOT
                       NULL,
                       cantidad
                       INTEGER
                       NOT
                       NULL
                       DEFAULT
                       1,
                       precio_unitario
                       REAL
                       NOT
                       NULL,
                       subtotal
                       REAL
                       NOT
                       NULL,
                       FOREIGN
                       KEY
                   (
                       pedido_id
                   ) REFERENCES pedidos
                   (
                       id
                   ),
                       FOREIGN KEY
                   (
                       bebida_id
                   ) REFERENCES bebidas
                   (
                       id
                   )
                       )
                   ''')

    # Insertar bebidas de ejemplo con stock
    cursor.execute("SELECT COUNT(*) FROM bebidas")
    if cursor.fetchone()[0] == 0:
        bebidas = [
            ("Cerveza Artesanal", 800.00, 50),
            ("Vino Malbec", 1200.00, 30),
            ("Fernet con Coca", 1000.00, 40),
            ("Coca Cola", 500.00, 60),
            ("Agua Mineral", 400.00, 100),
            ("Whisky", 1500.00, 20),
            ("Gin Tonic", 1300.00, 25),
        ]
        cursor.executemany(
            "INSERT INTO bebidas (nombre, precio, stock) VALUES (?, ?, ?)",
            bebidas
        )

    conn.commit()
    conn.close()
    print("Base de datos creada/actualizada")


if __name__ == "__main__":
    init_db()