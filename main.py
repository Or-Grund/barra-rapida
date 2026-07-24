
from fastapi import FastAPI, Request, Form, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import json
import qrcode
import io
import base64
import mercadopago
from datetime import datetime
import hashlib
import secrets
import os

app = FastAPI(title="Barra Rápida + Entradas")

# CORS para que los guardias puedan escanear desde sus celulares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="templates")

# Crear carpeta templates si no existe
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# ========================
# CONFIGURACIÓN
# ========================
MODO_PRUEBA = True  # Cambiar a False para producción

# Mercado Pago (TEST)
MP_ACCESS_TOKEN = "TEST-0000000000000000-000000-0000000000000000-0000000000000000"
mp_sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Claves de guardias (cambiar por las reales antes del evento)
GUARDIAS = {
    "Guardia_1": {"password": "Folklore2026!", "nombre": "Guardia 1"},
    "Guardia_2": {"password": "Folklore2026!", "nombre": "Guardia 2"},
    "Guardia_3": {"password": "Folklore2026!", "nombre": "Guardia 3"},
    "Guardia_4": {"password": "Folklore2026!", "nombre": "Guardia 4"},
    "Guardia_5": {"password": "Folklore2026!", "nombre": "Guardia 5"},
    "Guardia_6": {"password": "Folklore2026!", "nombre": "Guardia 6"},
}

# ========================
# BASE DE DATOS
# ========================
DB_PATH = "barra_rapida.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def rows_to_dicts(rows):
    """Convierte sqlite3.Row objects a listas de diccionarios"""
    return [dict(row) for row in rows]

def row_to_dict(row):
    """Convierte un sqlite3.Row object a diccionario"""
    if row is None:
        return None
    return dict(row)

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Tablas de bebidas (ya existentes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bebidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            activa INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estado TEXT DEFAULT 'pendiente',
            mp_preference_id TEXT,
            mp_payment_id TEXT,
            codigo_qr TEXT,
            total REAL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            entregado_en TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER,
            bebida_id INTEGER,
            cantidad INTEGER,
            precio_unitario REAL,
            subtotal REAL,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
            FOREIGN KEY (bebida_id) REFERENCES bebidas(id)
        )
    """)

    # ========================
    # TABLAS DE ENTRADAS
    # ========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tipos_entrada (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            precio REAL NOT NULL,
            descripcion TEXT,
            stock INTEGER DEFAULT 0,
            activa INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compras_entradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_comprador TEXT NOT NULL,
            email TEXT,
            telefono TEXT,
            dni TEXT,
            cantidad INTEGER NOT NULL,
            total REAL NOT NULL,
            estado TEXT DEFAULT 'pendiente',
            mp_preference_id TEXT,
            mp_payment_id TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pagado_en TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER,
            tipo_entrada_id INTEGER,
            numero_entrada TEXT NOT NULL,
            codigo_qr TEXT UNIQUE NOT NULL,
            estado TEXT DEFAULT 'pendiente',
            usada_en TIMESTAMP,
            usada_por_guardia TEXT,
            FOREIGN KEY (compra_id) REFERENCES compras_entradas(id),
            FOREIGN KEY (tipo_entrada_id) REFERENCES tipos_entrada(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guardias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1
        )
    """)

    # Insertar tipos de entrada de ejemplo si no existen
    cursor.execute("SELECT COUNT(*) FROM tipos_entrada")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO tipos_entrada (nombre, precio, descripcion, stock) VALUES
            ('General', 5000.00, 'Acceso general al evento', 500),
            ('VIP', 8000.00, 'Acceso VIP + zona preferencial', 100),
            ('Camping', 6500.00, 'Acceso + espacio de camping', 200)
        """)

    # Insertar guardias si no existen
    cursor.execute("SELECT COUNT(*) FROM guardias")
    if cursor.fetchone()[0] == 0:
        for username, data in GUARDIAS.items():
            cursor.execute("""
                INSERT INTO guardias (username, password, nombre) VALUES (?, ?, ?)
            """, (username, data["password"], data["nombre"]))

    conn.commit()
    conn.close()

# Inicializar DB al arrancar
init_db()

# ========================
# FUNCIONES AUXILIARES
# ========================
def generar_qr_base64(texto):
    """Genera un QR en base64 para mostrar en HTML"""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode()

def generar_codigo_entrada(compra_id, numero):
    """Genera un código único para cada entrada"""
    secreto = "FOLKLORE2026_SECRET"
    hash_input = f"{secreto}-{compra_id}-{numero}-{datetime.now().timestamp()}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16].upper()

# ========================
# PÁGINA PÚBLICA - COMPRA DE ENTRADAS
# ========================
@app.get("/entradas", response_class=HTMLResponse)
async def pagina_entradas(request: Request):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM tipos_entrada WHERE activa = 1 ORDER BY precio"
    ).fetchall()
    tipos = rows_to_dicts(rows)
    conn.close()
    return templates.TemplateResponse(request, "entradas_publico.html", {
        "tipos": tipos,
        "modo_prueba": MODO_PRUEBA
    })

@app.post("/api/entradas/crear-preferencia")
async def crear_preferencia_entradas(
    nombre: str = Form(...),
    email: str = Form(...),
    telefono: str = Form(...),
    dni: str = Form(""),
    tipo_entrada_id: int = Form(...),
    cantidad: int = Form(...)
):
    conn = get_db()
    cursor = conn.cursor()

    # Validar stock
    tipo_row = cursor.execute(
        "SELECT * FROM tipos_entrada WHERE id = ? AND activa = 1",
        (tipo_entrada_id,)
    ).fetchone()

    if not tipo_row:
        conn.close()
        raise HTTPException(status_code=400, detail="Tipo de entrada no válido")

    tipo = row_to_dict(tipo_row)

    # Validar email obligatorio y formato
    if not email or email.strip() == "":
        conn.close()
        raise HTTPException(status_code=400, detail="El email es obligatorio")

    email_lower = email.lower().strip()
    if not (email_lower.endswith("@gmail.com") or email_lower.endswith("@outlook.com") or email_lower.endswith("@hotmail.com")):
        conn.close()
        raise HTTPException(status_code=400, detail="Solo se permiten emails de Gmail, Outlook o Hotmail")

    # Validar teléfono obligatorio y formato (área Tucumán 381)
    if not telefono or telefono.strip() == "":
        conn.close()
        raise HTTPException(status_code=400, detail="El teléfono es obligatorio")

    telefono_limpio = telefono.strip().replace(" ", "").replace("-", "")
    if not telefono_limpio.startswith("381") or len(telefono_limpio) != 10 or not telefono_limpio.isdigit():
        conn.close()
        raise HTTPException(status_code=400, detail="El teléfono debe ser de área Tucumán (381) + 7 dígitos. Ej: 3816555333")

    # Contar entradas vendidas de este tipo
    vendidas_row = cursor.execute("""
    SELECT COALESCE(COUNT(*), 0) as total FROM entradas e
    JOIN compras_entradas c ON e.compra_id = c.id
    WHERE e.tipo_entrada_id = ? AND c.estado = 'pagado' 
    """, (tipo_entrada_id,)).fetchone()

    vendidas = vendidas_row[0] if vendidas_row else 0
    disponibles = tipo["stock"] - vendidas

    if cantidad > disponibles:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Solo quedan {disponibles} entradas disponibles")

    if cantidad < 1 or cantidad > 10:
        conn.close()
        raise HTTPException(status_code=400, detail="Cantidad debe ser entre 1 y 10")

    total = tipo["precio"] * cantidad

    # Crear compra
    cursor.execute("""
        INSERT INTO compras_entradas 
        (nombre_comprador, email, telefono, dni, cantidad, total, estado)
        VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
    """, (nombre, email, telefono, dni, cantidad, total))

    compra_id = cursor.lastrowid

    # Crear entradas individuales
    entradas_generadas = []
    for i in range(1, cantidad + 1):
        numero_entrada = f"{nombre} {i:03d}"
        codigo = generar_codigo_entrada(compra_id, i)

        cursor.execute("""
            INSERT INTO entradas (compra_id, tipo_entrada_id, numero_entrada, codigo_qr, estado)
            VALUES (?, ?, ?, ?, 'pendiente')
        """, (compra_id, tipo_entrada_id, numero_entrada, codigo))

        entradas_generadas.append({
            "numero": numero_entrada,
            "codigo": codigo
        })

    # Crear preferencia de MP
    if MODO_PRUEBA:
        mp_preference_id = f"TEST_PREF_{compra_id}_{secrets.token_hex(8)}"
    else:
        preference_data = {
            "items": [{
                "title": f"Entrada {tipo['nombre']} - {nombre}",
                "quantity": cantidad,
                "unit_price": tipo["precio"]
            }],
            "payer": {
                "name": nombre,
                "email": email or "test@test.com"
            },
            "back_urls": {
                "success": f"https://barra-rapida.onrender.com/entradas/exito/{compra_id}",
                "failure": f"https://barra-rapida.onrender.com/entradas/error/{compra_id}"
            },
            "auto_return": "approved",
            "external_reference": str(compra_id)
        }
        preference = mp_sdk.preference().create(preference_data)
        mp_preference_id = preference["response"]["id"]

    cursor.execute(
        "UPDATE compras_entradas SET mp_preference_id = ? WHERE id = ?",
        (mp_preference_id, compra_id)
    )

    conn.commit()
    conn.close()

    return {
        "compra_id": compra_id,
        "mp_preference_id": mp_preference_id,
        "total": total,
        "entradas": entradas_generadas,
        "modo_prueba": MODO_PRUEBA
    }

@app.get("/entradas/exito/{compra_id}", response_class=HTMLResponse)
async def exito_entradas(request: Request, compra_id: int):
    conn = get_db()
    cursor = conn.cursor()

    # Simular pago en modo prueba
    if MODO_PRUEBA:
        cursor.execute("""
            UPDATE compras_entradas 
            SET estado = 'pagado', pagado_en = ? 
            WHERE id = ?
        """, (datetime.now(), compra_id))

        cursor.execute("""
            UPDATE entradas SET estado = 'pagado' WHERE compra_id = ?
        """, (compra_id,))

        conn.commit()

    # Obtener datos de la compra
    compra_row = cursor.execute("""
        SELECT c.*, t.nombre as tipo_nombre, t.precio 
        FROM compras_entradas c
        JOIN entradas e ON c.id = e.compra_id
        JOIN tipos_entrada t ON e.tipo_entrada_id = t.id
        WHERE c.id = ?
        GROUP BY c.id
    """, (compra_id,)).fetchone()

    compra = row_to_dict(compra_row)

    entradas_rows = cursor.execute("""
        SELECT e.*, t.nombre as tipo_nombre, t.precio
        FROM entradas e
        JOIN tipos_entrada t ON e.tipo_entrada_id = t.id
        WHERE e.compra_id = ?
    """, (compra_id,)).fetchall()

    entradas = rows_to_dicts(entradas_rows)

    # Generar QR en base64 para cada entrada
    entradas_con_qr = []
    for entrada in entradas:
        qr_data = json.dumps({
            "codigo": entrada["codigo_qr"],
            "nombre": entrada["numero_entrada"],
            "tipo": entrada["tipo_nombre"],
            "comprador": compra["nombre_comprador"]
        })
        qr_b64 = generar_qr_base64(qr_data)
        entradas_con_qr.append({
            **entrada,
            "qr_base64": qr_b64,
            "qr_data": qr_data
        })

    conn.close()

    return templates.TemplateResponse(request, "entradas_exito.html", {
        "compra": compra,
        "entradas": entradas_con_qr,
        "modo_prueba": MODO_PRUEBA
    })

# ========================
# API PARA VALIDAR ENTRADA (USADO POR GUARDIAS)
# ========================
@app.post("/api/entradas/validar")
async def validar_entrada(codigo_qr: str = Form(...), guardia: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()

    entrada_row = cursor.execute("""
        SELECT e.*, c.nombre_comprador, t.nombre as tipo_nombre
        FROM entradas e
        JOIN compras_entradas c ON e.compra_id = c.id
        JOIN tipos_entrada t ON e.tipo_entrada_id = t.id
        WHERE e.codigo_qr = ?
    """, (codigo_qr,)).fetchone()

    if not entrada_row:
        conn.close()
        return {"valido": False, "mensaje": "Entrada no encontrada"}

    entrada = row_to_dict(entrada_row)

    if entrada["estado"] == "usada":
        conn.close()
        return {
            "valido": False,
            "mensaje": "Entrada YA USADA",
            "usada_en": entrada["usada_en"],
            "usada_por": entrada["usada_por_guardia"],
            "nombre": entrada["nombre_comprador"],
            "tipo": entrada["tipo_nombre"],
            "numero": entrada["numero_entrada"]
        }

    if entrada["estado"] != "pagado":
        conn.close()
        return {"valido": False, "mensaje": "Entrada no pagada"}

    # Marcar como usada
    cursor.execute("""
        UPDATE entradas 
        SET estado = 'usada', usada_en = ?, usada_por_guardia = ?
        WHERE id = ?
    """, (datetime.now(), guardia, entrada["id"]))

    conn.commit()
    conn.close()

    return {
        "valido": True,
        "mensaje": "¡Entrada válida! Acceso permitido",
        "nombre": entrada["nombre_comprador"],
        "tipo": entrada["tipo_nombre"],
        "numero": entrada["numero_entrada"],
        "guardia": guardia
    }

@app.get("/api/entradas/estado/{codigo}")
async def estado_entrada(codigo: str):
    conn = get_db()
    entrada_row = conn.execute("""
        SELECT e.*, c.nombre_comprador, t.nombre as tipo_nombre
        FROM entradas e
        JOIN compras_entradas c ON e.compra_id = c.id
        JOIN tipos_entrada t ON e.tipo_entrada_id = t.id
        WHERE e.codigo_qr = ?
    """, (codigo,)).fetchone()
    conn.close()

    if not entrada_row:
        return {"existe": False}

    entrada = row_to_dict(entrada_row)

    return {
        "existe": True,
        "estado": entrada["estado"],
        "nombre": entrada["nombre_comprador"],
        "tipo": entrada["tipo_nombre"],
        "numero": entrada["numero_entrada"],
        "usada_en": entrada["usada_en"],
        "usada_por": entrada["usada_por_guardia"]
    }

# ========================
# PÁGINA DE GUARDIAS
# ========================
@app.get("/guardia", response_class=HTMLResponse)
async def pagina_guardia(request: Request):
    return templates.TemplateResponse(request, "guardia_login.html", {})

@app.post("/guardia/login")
async def login_guardia(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    guardia_row = conn.execute(
        "SELECT * FROM guardias WHERE username = ? AND password = ? AND activo = 1",
        (username, password)
    ).fetchone()
    conn.close()

    if not guardia_row:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    guardia = row_to_dict(guardia_row)

    return {"success": True, "username": username, "nombre": guardia["nombre"]}

@app.get("/guardia/escaner", response_class=HTMLResponse)
async def escaner_guardia(request: Request, guardia: str = Query(...)):
    return templates.TemplateResponse(request, "guardia_escaner.html", {
        "guardia": guardia
    })

# ========================
# PANEL DEL ORGANIZADOR - ENTRADAS
# ========================
@app.get("/organizador/entradas", response_class=HTMLResponse)
async def panel_entradas(request: Request):
    conn = get_db()

    # Estadísticas
    stats_row = conn.execute("""
        SELECT 
            COUNT(*) as total_compras,
            SUM(CASE WHEN estado = 'pagado' THEN 1 ELSE 0 END) as pagadas,
            SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) as pendientes,
            SUM(CASE WHEN estado = 'pagado' THEN total ELSE 0 END) as recaudado
        FROM compras_entradas
    """).fetchone()

    stats = row_to_dict(stats_row)

    # Entradas usadas
    usadas_row = conn.execute("""
        SELECT COUNT(*) as total FROM entradas WHERE estado = 'usada'
    """).fetchone()

    usadas = usadas_row[0] if usadas_row else 0

    # Compras recientes
    compras_rows = conn.execute("""
        SELECT c.*, 
            (SELECT t.nombre FROM entradas e 
             JOIN tipos_entrada t ON e.tipo_entrada_id = t.id 
             WHERE e.compra_id = c.id LIMIT 1) as tipo_nombre
        FROM compras_entradas c
        ORDER BY c.creado_en DESC
        LIMIT 50
    """).fetchall()

    compras = rows_to_dicts(compras_rows)

    # Stock por tipo
    stock_rows = conn.execute("""
        SELECT t.*, 
            COALESCE((SELECT COUNT(*) FROM entradas e 
                      JOIN compras_entradas c ON e.compra_id = c.id 
                      WHERE e.tipo_entrada_id = t.id AND c.estado = 'pagado'), 0) as vendidas
        FROM tipos_entrada t
    """).fetchall()

    stock = rows_to_dicts(stock_rows)

    # Entradas usadas por guardia
    por_guardia_rows = conn.execute("""
        SELECT usada_por_guardia, COUNT(*) as cantidad
        FROM entradas WHERE estado = 'usada'
        GROUP BY usada_por_guardia
    """).fetchall()

    por_guardia = rows_to_dicts(por_guardia_rows)

    conn.close()

    return templates.TemplateResponse(request, "organizador_entradas.html", {
        "stats": stats,
        "usadas": usadas,
        "compras": compras,
        "stock": stock,
        "por_guardia": por_guardia
    })

@app.get("/organizador/entradas/qr/{compra_id}", response_class=HTMLResponse)
async def ver_qr_organizador(request: Request, compra_id: int):
    conn = get_db()

    compra_row = conn.execute("""
        SELECT c.*, t.nombre as tipo_nombre
        FROM compras_entradas c
        JOIN entradas e ON c.id = e.compra_id
        JOIN tipos_entrada t ON e.tipo_entrada_id = t.id
        WHERE c.id = ?
        GROUP BY c.id
    """, (compra_id,)).fetchone()

    compra = row_to_dict(compra_row)

    entradas_rows = conn.execute("""
        SELECT e.*, t.nombre as tipo_nombre
        FROM entradas e
        JOIN tipos_entrada t ON e.tipo_entrada_id = t.id
        WHERE e.compra_id = ?
    """, (compra_id,)).fetchall()

    entradas = rows_to_dicts(entradas_rows)

    entradas_con_qr = []
    for entrada in entradas:
        qr_data = json.dumps({
            "codigo": entrada["codigo_qr"],
            "nombre": entrada["numero_entrada"],
            "tipo": entrada["tipo_nombre"],
            "comprador": compra["nombre_comprador"]
        })
        qr_b64 = generar_qr_base64(qr_data)
        entradas_con_qr.append({
            **entrada,
            "qr_base64": qr_b64
        })

    conn.close()

    return templates.TemplateResponse(request, "organizador_qr.html", {
        "compra": compra,
        "entradas": entradas_con_qr
    })

@app.post("/api/entradas/recargar-stock")
async def recargar_stock(tipo_id: int = Form(...), cantidad: int = Form(...)):
    conn = get_db()
    conn.execute(
        "UPDATE tipos_entrada SET stock = stock + ? WHERE id = ?",
        (cantidad, tipo_id)
    )
    conn.commit()
    conn.close()
    return {"success": True}

# ========================
# PÁGINAS ORIGINALES (BEBIDAS)
# ========================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = get_db()
    rows = conn.execute("SELECT * FROM bebidas WHERE activa = 1").fetchall()
    bebidas = rows_to_dicts(rows)
    conn.close()
    return templates.TemplateResponse(request, "Bebidas_Publico.html", {
        "bebidas": bebidas
    })

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    conn = get_db()
    rows = conn.execute("""
        SELECT p.*, 
            (SELECT GROUP_CONCAT(b.nombre || ' x' || i.cantidad, ', ')
             FROM items_pedido i 
             JOIN bebidas b ON i.bebida_id = b.id 
             WHERE i.pedido_id = p.id) as items
        FROM pedidos p 
        WHERE p.estado = 'pagado' AND p.entregado_en IS NULL
        ORDER BY p.creado_en DESC
    """).fetchall()
    pedidos = rows_to_dicts(rows)
    conn.close()
    return templates.TemplateResponse(request, "Barmans.html", {
        "pedidos": pedidos
    })

@app.get("/organizador", response_class=HTMLResponse)
async def organizador(request: Request):
    conn = get_db()
    rows = conn.execute("SELECT * FROM bebidas").fetchall()
    bebidas = rows_to_dicts(rows)

    recaudacion_row = conn.execute("""
        SELECT COALESCE(SUM(total), 0) as total FROM pedidos WHERE estado = 'pagado'
    """).fetchone()
    recaudacion = recaudacion_row[0] if recaudacion_row else 0

    total_pedidos_row = conn.execute(
        "SELECT COUNT(*) FROM pedidos WHERE estado = 'pagado'"
    ).fetchone()
    total_pedidos = total_pedidos_row[0] if total_pedidos_row else 0

    conn.close()

    return templates.TemplateResponse(request, "organizador_bebidas.html", {
        "bebidas": bebidas,
        "recaudacion": recaudacion,
        "total_pedidos": total_pedidos
    })

@app.post("/api/pedido")
async def crear_pedido(items: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()

    items_list = json.loads(items)
    total = 0

    for item in items_list:
        bebida_row = cursor.execute(
            "SELECT * FROM bebidas WHERE id = ?", (item["id"],)
        ).fetchone()
        if bebida_row:
            bebida = row_to_dict(bebida_row)
            if bebida["stock"] >= item["cantidad"]:
                total += bebida["precio"] * item["cantidad"]

    cursor.execute(
        "INSERT INTO pedidos (estado, total) VALUES ('pendiente', ?)",
        (total,)
    )
    pedido_id = cursor.lastrowid

    for item in items_list:
        bebida_row = cursor.execute(
            "SELECT * FROM bebidas WHERE id = ?", (item["id"],)
        ).fetchone()
        if bebida_row:
            bebida = row_to_dict(bebida_row)
            subtotal = bebida["precio"] * item["cantidad"]
            cursor.execute("""
                INSERT INTO items_pedido (pedido_id, bebida_id, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?)
            """, (pedido_id, item["id"], item["cantidad"], bebida["precio"], subtotal))
            cursor.execute(
                "UPDATE bebidas SET stock = stock - ? WHERE id = ?",
                (item["cantidad"], item["id"])
            )

    conn.commit()
    conn.close()

    return {"pedido_id": pedido_id, "total": total}

@app.get("/api/qr/{pedido_id}")
async def get_qr(pedido_id: int):
    conn = get_db()
    pedido_row = conn.execute(
        "SELECT * FROM pedidos WHERE id = ?", (pedido_id,)
    ).fetchone()
    conn.close()

    if not pedido_row:
        raise HTTPException(status_code=404)

    qr_b64 = generar_qr_base64(str(pedido_id))
    return {"qr": qr_b64, "codigo": str(pedido_id)}

@app.post("/api/entregar")
async def entregar_pedido(pedido_id: int = Form(...)):
    conn = get_db()
    conn.execute(
        "UPDATE pedidos SET entregado_en = ? WHERE id = ?",
        (datetime.now(), pedido_id)
    )
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/bebidas/recargar")
async def recargar_bebida(bebida_id: int = Form(...), cantidad: int = Form(...)):
    conn = get_db()
    conn.execute(
        "UPDATE bebidas SET stock = stock + ? WHERE id = ?",
        (cantidad, bebida_id)
    )
    conn.commit()
    conn.close()
    return {"success": True}

# ========================
# INICIAR SERVIDOR
# ========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
