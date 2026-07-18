from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from database import get_db, init_db
from mercadopago_config import MP_ACCESS_TOKEN, MODO_PRUEBA
import qrcode
import io
import base64
import uuid
import mercadopago
from datetime import datetime

app = FastAPI(title="Barra Rapida")

init_db()

sdk = None
if not MODO_PRUEBA:
    sdk = mercadopago.SDK(MP_ACCESS_TOKEN)


# ============ PAGINA CLIENTE (MENU + CARRITO) ============
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Barra Rapida</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                min-height: 100vh;
                color: white;
            }
            .header {
                background: rgba(0,0,0,0.3);
                padding: 15px;
                text-align: center;
                position: sticky;
                top: 0;
                z-index: 100;
            }
            .header h1 { font-size: 1.5em; }
            .evento { color: #e94560; font-size: 0.9em; }
            .container { 
                max-width: 600px; 
                margin: 0 auto; 
                padding: 20px;
                padding-bottom: 250px;
            }
            .bebida {
                background: rgba(255,255,255,0.1);
                border-radius: 15px;
                padding: 15px;
                margin: 10px 0;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border: 1px solid rgba(255,255,255,0.2);
            }
            .bebida.agotada {
                opacity: 0.5;
                border-color: #666;
            }
            .bebida-info h3 { font-size: 1.1em; margin-bottom: 3px; }
            .precio { color: #e94560; font-size: 1.2em; font-weight: bold; }
            .stock {
                font-size: 0.8em;
                color: #888;
                margin-top: 3px;
            }
            .stock.bajo { color: #f39c12; }
            .stock.agotado { color: #e94560; font-weight: bold; }
            .cantidad-control {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .btn-cantidad {
                background: #e94560;
                color: white;
                border: none;
                width: 35px;
                height: 35px;
                border-radius: 50%;
                font-size: 1.2em;
                cursor: pointer;
            }
            .btn-cantidad:disabled {
                background: #666;
                cursor: not-allowed;
            }
            .cantidad-valor {
                font-size: 1.2em;
                min-width: 30px;
                text-align: center;
            }
            .tag-agotado {
                background: #e94560;
                color: white;
                padding: 5px 15px;
                border-radius: 15px;
                font-size: 0.85em;
                font-weight: bold;
            }
            .carrito-fijo {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                background: linear-gradient(180deg, #16213e 0%, #1a1a2e 100%);
                border-top: 2px solid #e94560;
                padding: 15px;
                max-height: 50vh;
                overflow-y: auto;
                z-index: 200;
            }
            .carrito-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .carrito-items {
                max-height: 150px;
                overflow-y: auto;
                margin-bottom: 10px;
            }
            .carrito-item {
                display: flex;
                justify-content: space-between;
                padding: 5px 0;
                border-bottom: 1px solid rgba(255,255,255,0.1);
                font-size: 0.9em;
            }
            .carrito-total {
                font-size: 1.3em;
                color: #e94560;
                font-weight: bold;
                text-align: right;
                margin: 10px 0;
            }
            .btn-comprar {
                width: 100%;
                padding: 15px;
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 1.2em;
                cursor: pointer;
                font-weight: bold;
            }
            .btn-comprar:disabled {
                background: #666;
                cursor: not-allowed;
            }
            .btn-vaciar {
                background: transparent;
                color: #888;
                border: 1px solid #888;
                padding: 5px 10px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
            }
            .vacio-msg {
                text-align: center;
                color: #888;
                padding: 10px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>BARRA RAPIDA</h1>
            <div class="evento">Evento de Folklore - Recaudando para el disco</div>
        </div>
        <div class="container" id="menu"></div>
        <div class="carrito-fijo">
            <div class="carrito-header">
                <h3>Tu Pedido</h3>
                <button class="btn-vaciar" onclick="vaciarCarrito()">Vaciar</button>
            </div>
            <div class="carrito-items" id="carrito-items">
                <div class="vacio-msg">Agrega bebidas al carrito</div>
            </div>
            <div class="carrito-total" id="carrito-total">Total: $0</div>
            <button class="btn-comprar" id="btn-comprar" onclick="comprar()" disabled>
                COMPRAR
            </button>
        </div>
        <script>
            let carrito = {};
            let bebidasData = [];

            async function cargarMenu() {
                const res = await fetch('/api/bebidas');
                bebidasData = await res.json();
                const menu = document.getElementById('menu');

                bebidasData.forEach(b => {
                    const agotada = b.stock <= 0;
                    const stockBajo = b.stock > 0 && b.stock <= 5;
                    const stockClass = agotada ? 'agotado' : (stockBajo ? 'bajo' : '');
                    const stockText = agotada ? 'AGOTADO' : (stockBajo ? `Quedan ${b.stock}` : `Stock: ${b.stock}`);

                    menu.innerHTML += `
                        <div class="bebida ${agotada ? 'agotada' : ''}">
                            <div class="bebida-info">
                                <h3>${b.nombre}</h3>
                                <div class="precio">$${b.precio.toFixed(2)}</div>
                                <div class="stock ${stockClass}">${stockText}</div>
                            </div>
                            ${agotada ? 
                                '<span class="tag-agotado">AGOTADO</span>' :
                                `<div class="cantidad-control">
                                    <button class="btn-cantidad" onclick="cambiarCantidad(${b.id}, -1)" ${!carrito[b.id] ? 'disabled' : ''}>-</button>
                                    <span class="cantidad-valor" id="cant-${b.id}">0</span>
                                    <button class="btn-cantidad" onclick="cambiarCantidad(${b.id}, 1)" id="btn-mas-${b.id}">+</button>
                                </div>`
                            }
                        </div>
                    `;
                });
            }

            function cambiarCantidad(bebidaId, delta) {
                const bebida = bebidasData.find(b => b.id == bebidaId);
                if (!carrito[bebidaId]) carrito[bebidaId] = 0;

                const nuevaCantidad = carrito[bebidaId] + delta;

                if (delta > 0 && nuevaCantidad > bebida.stock) {
                    alert(`Solo quedan ${bebida.stock} unidades de ${bebida.nombre}`);
                    return;
                }

                carrito[bebidaId] = nuevaCantidad;
                if (carrito[bebidaId] <= 0) delete carrito[bebidaId];

                document.getElementById(`cant-${bebidaId}`).textContent = carrito[bebidaId] || 0;

                const btnMenos = document.querySelector(`button[onclick="cambiarCantidad(${bebidaId}, -1)"]`);
                if (btnMenos) btnMenos.disabled = !carrito[bebidaId];

                const btnMas = document.getElementById(`btn-mas-${bebidaId}`);
                if (btnMas) btnMas.disabled = carrito[bebidaId] >= bebida.stock;

                actualizarCarrito();
            }

            function actualizarCarrito() {
                const itemsDiv = document.getElementById('carrito-items');
                const totalDiv = document.getElementById('carrito-total');
                const btnComprar = document.getElementById('btn-comprar');
                const items = Object.entries(carrito);

                if (items.length === 0) {
                    itemsDiv.innerHTML = '<div class="vacio-msg">Agrega bebidas al carrito</div>';
                    totalDiv.textContent = 'Total: $0';
                    btnComprar.disabled = true;
                    return;
                }

                let total = 0;
                itemsDiv.innerHTML = items.map(([bebidaId, cantidad]) => {
                    const bebida = bebidasData.find(b => b.id == bebidaId);
                    const subtotal = bebida.precio * cantidad;
                    total += subtotal;
                    return `<div class="carrito-item"><span>${cantidad}x ${bebida.nombre}</span><span>$${subtotal.toFixed(2)}</span></div>`;
                }).join('');

                totalDiv.textContent = `Total: $${total.toFixed(2)}`;
                btnComprar.disabled = false;
            }

            function vaciarCarrito() {
                carrito = {};
                bebidasData.forEach(b => {
                    const el = document.getElementById(`cant-${b.id}`);
                    if (el) el.textContent = '0';
                    const btnMenos = document.querySelector(`button[onclick="cambiarCantidad(${b.id}, -1)"]`);
                    if (btnMenos) btnMenos.disabled = true;
                    const btnMas = document.getElementById(`btn-mas-${b.id}`);
                    if (btnMas) btnMas.disabled = false;
                });
                actualizarCarrito();
            }

            async function comprar() {
                const btn = document.getElementById('btn-comprar');
                btn.disabled = true;
                btn.textContent = 'Procesando...';

                const items = Object.entries(carrito).map(([bebida_id, cantidad]) => ({
                    bebida_id: parseInt(bebida_id),
                    cantidad: cantidad
                }));

                const res = await fetch('/api/pedido', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({items: items})
                });

                const data = await res.json();

                if (data.qr_url) {
                    window.location.href = data.qr_url;
                } else {
                    alert('Error: ' + (data.error || 'Desconocido'));
                    btn.disabled = false;
                    btn.textContent = 'COMPRAR';
                }
            }

            cargarMenu();
        </script>
    </body>
    </html>
    """


@app.get("/api/bebidas")
def get_bebidas():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bebidas WHERE activa = 1 ORDER BY precio")
    bebidas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bebidas


@app.post("/api/pedido")
def crear_pedido(data: dict):
    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Carrito vacio")

    conn = get_db()
    cursor = conn.cursor()

    for item in items:
        bebida_id = item.get("bebida_id")
        cantidad = item.get("cantidad", 1)

        cursor.execute("SELECT stock, nombre FROM bebidas WHERE id = ? AND activa = 1", (bebida_id,))
        bebida = cursor.fetchone()

        if not bebida:
            conn.close()
            raise HTTPException(status_code=404, detail="Bebida no encontrada")

        if bebida["stock"] < cantidad:
            conn.close()
            raise HTTPException(status_code=400,
                                detail=f"No hay suficiente stock de {bebida['nombre']}. Quedan: {bebida['stock']}")

    total = 0
    items_validados = []

    for item in items:
        bebida_id = item.get("bebida_id")
        cantidad = item.get("cantidad", 1)

        cursor.execute("SELECT * FROM bebidas WHERE id = ?", (bebida_id,))
        bebida = cursor.fetchone()
        bebida = dict(bebida)

        subtotal = bebida["precio"] * cantidad
        total += subtotal

        items_validados.append({
            "bebida_id": bebida_id,
            "cantidad": cantidad,
            "precio_unitario": bebida["precio"],
            "subtotal": subtotal,
            "nombre": bebida["nombre"]
        })

    codigo_qr = str(uuid.uuid4())[:8].upper()

    cursor.execute("""
                   INSERT INTO pedidos (estado, codigo_qr, total)
                   VALUES ('pendiente', ?, ?)
                   """, (codigo_qr, total))

    pedido_id = cursor.lastrowid

    for item in items_validados:
        cursor.execute("""
                       INSERT INTO items_pedido (pedido_id, bebida_id, cantidad, precio_unitario, subtotal)
                       VALUES (?, ?, ?, ?, ?)
                       """, (pedido_id, item["bebida_id"], item["cantidad"], item["precio_unitario"], item["subtotal"]))

        cursor.execute("""
                       UPDATE bebidas
                       SET stock = stock - ?
                       WHERE id = ?
                       """, (item["cantidad"], item["bebida_id"]))

    conn.commit()
    conn.close()

    if MODO_PRUEBA:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE pedidos SET estado = 'pagado' WHERE id = ?", (pedido_id,))
        conn.commit()
        conn.close()
        return {"qr_url": f"/qr/{codigo_qr}"}

    items_mp = [{
        "title": f"{item['cantidad']}x {item['nombre']}",
        "quantity": 1,
        "unit_price": float(item["subtotal"]),
    } for item in items_validados]

    preference_data = {
        "items": items_mp,
        "back_urls": {
            "success": f"http://localhost:8000/pago-exitoso/{pedido_id}",
            "failure": "http://localhost:8000/pago-fallido",
            "pending": "http://localhost:8000/pago-pendiente"
        },
        "auto_return": "approved",
        "external_reference": str(pedido_id)
    }

    preference = sdk.preference().create(preference_data)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE pedidos SET mp_preference_id = ? WHERE id = ?",
                   (preference["response"]["id"], pedido_id))
    conn.commit()
    conn.close()

    return {"pago_url": preference["response"]["init_point"]}


@app.get("/qr/{codigo}", response_class=HTMLResponse)
def mostrar_qr(codigo: str):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pedidos WHERE codigo_qr = ?", (codigo,))
    pedido = cursor.fetchone()

    if not pedido:
        conn.close()
        return "<h1 style='text-align:center;color:red;'>Codigo no valido</h1>"

    pedido = dict(pedido)

    cursor.execute("""
                   SELECT ip.*, b.nombre as bebida_nombre
                   FROM items_pedido ip
                            JOIN bebidas b ON ip.bebida_id = b.id
                   WHERE ip.pedido_id = ?
                   """, (pedido["id"],))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    qr = qrcode.QRCode(version=3, box_size=10, border=2)
    qr.add_data(codigo)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    items_list = ""
    for i in items:
        items_list += f"""
        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.1);">
            <span>{i['cantidad']}x {i['bebida_nombre']}</span>
            <span style="color:#e94560;">${i['subtotal']:.2f}</span>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Tu Pedido</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                min-height: 100vh;
                color: white;
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 20px;
            }}
            .container {{
                background: rgba(255,255,255,0.1);
                border-radius: 20px;
                padding: 25px;
                max-width: 400px;
                width: 100%;
                text-align: center;
            }}
            .estado {{
                background: #27ae60;
                color: white;
                padding: 10px 20px;
                border-radius: 25px;
                font-size: 1em;
                font-weight: bold;
                margin-bottom: 15px;
                display: inline-block;
            }}
            .items-list {{
                background: rgba(0,0,0,0.2);
                border-radius: 10px;
                padding: 15px;
                margin: 15px 0;
                text-align: left;
            }}
            .total {{
                font-size: 1.5em;
                color: #e94560;
                font-weight: bold;
                margin: 15px 0;
            }}
            .qr-container {{
                background: white;
                padding: 15px;
                border-radius: 15px;
                margin: 15px 0;
                display: inline-block;
            }}
            .qr-container img {{ width: 220px; height: 220px; }}
            .codigo {{
                font-family: monospace;
                font-size: 1.8em;
                letter-spacing: 8px;
                color: #e94560;
                margin: 10px 0;
            }}
            .screenshot {{
                background: #f39c12;
                color: #1a1a2e;
                padding: 10px 20px;
                border-radius: 20px;
                font-size: 0.9em;
                margin: 10px 0;
                display: inline-block;
                font-weight: bold;
            }}
            .instruccion {{
                color: #888;
                margin-top: 10px;
                font-size: 0.95em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="estado">PAGO CONFIRMADO</div>
            <h2 style="margin-bottom:10px;">Tu Pedido</h2>
            <div class="items-list">
                {items_list}
            </div>
            <div class="total">Total: $ {pedido['total']:.2f}</div>
            <div class="qr-container">
                <img src="data:image/png;base64,{qr_base64}" alt="QR">
            </div>
            <div class="codigo">{codigo}</div>
            <div class="screenshot">Hace screenshot o guarda esta pantalla</div>
            <div class="instruccion">
                Mostra este QR en la barra para retirar TODO tu pedido
            </div>
        </div>
    </body>
    </html>
    """


# ============ PANEL BARMAN (ENTREGA + COLA DE PEDIDOS) ============
@app.get("/admin", response_class=HTMLResponse)
def panel_admin():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Panel del Barman</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #1a1a2e;
                min-height: 100vh;
                color: white;
                padding: 20px;
            }
            .container { max-width: 700px; margin: 0 auto; }
            h1 { text-align: center; margin-bottom: 20px; }

            /* SECCION ESCANEAR QR */
            .input-section {
                background: rgba(255,255,255,0.1);
                padding: 20px;
                border-radius: 15px;
                margin-bottom: 20px;
            }
            input {
                width: 100%;
                padding: 15px;
                font-size: 1.5em;
                text-align: center;
                letter-spacing: 5px;
                border: 2px solid #e94560;
                border-radius: 10px;
                background: rgba(255,255,255,0.05);
                color: white;
                text-transform: uppercase;
            }
            .btn-validar {
                width: 100%;
                padding: 15px;
                margin-top: 15px;
                background: #e94560;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 1.2em;
                cursor: pointer;
            }
            .resultado {
                padding: 20px;
                border-radius: 15px;
                margin-top: 20px;
            }
            .resultado.ok { background: rgba(39, 174, 96, 0.2); border: 2px solid #27ae60; }
            .resultado.error { background: rgba(233, 69, 96, 0.2); border: 2px solid #e94560; }
            .resultado .items-entrega {
                background: rgba(0,0,0,0.2);
                border-radius: 10px;
                padding: 15px;
                margin: 15px 0;
                text-align: left;
            }
            .resultado .items-entrega div {
                padding: 5px 0;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }

            /* SECCION COLA DE PEDIDOS */
            .cola-section {
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                padding: 20px;
            }
            .cola-section h2 {
                color: #f39c12;
                margin-bottom: 15px;
                text-align: center;
            }
            .pedido-cola {
                background: rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 10px;
                border-left: 4px solid #f39c12;
            }
            .pedido-cola.entregado {
                opacity: 0.4;
                border-left-color: #27ae60;
            }
            .pedido-numero {
                color: #888;
                font-size: 0.85em;
                margin-bottom: 5px;
            }
            .pedido-items {
                font-size: 1em;
            }
            .pedido-items div {
                padding: 3px 0;
            }
            .pedido-total {
                color: #e94560;
                font-weight: bold;
                margin-top: 8px;
                font-size: 1.1em;
            }
            .pedido-hora {
                color: #666;
                font-size: 0.8em;
                margin-top: 5px;
            }
            .sin-pedidos {
                text-align: center;
                color: #888;
                padding: 30px;
            }
            .stats-mini {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 20px;
            }
            .stat-mini {
                text-align: center;
            }
            .stat-mini .num {
                font-size: 1.5em;
                color: #e94560;
                font-weight: bold;
            }
            .stat-mini .label {
                font-size: 0.8em;
                color: #888;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PANEL DEL BARMAN</h1>

            <!-- ESCANEAR QR -->
            <div class="input-section">
                <input type="text" id="codigo-input" placeholder="INGRESA EL CODIGO QR" maxlength="8">
                <button class="btn-validar" onclick="validar()">VALIDAR Y ENTREGAR</button>
            </div>
            <div id="resultado"></div>

            <!-- COLA DE PEDIDOS -->
            <div class="cola-section">
                <h2>📋 Cola de Pedidos</h2>
                <div class="stats-mini">
                    <div class="stat-mini">
                        <div class="num" id="pendientes-count">0</div>
                        <div class="label">Pendientes</div>
                    </div>
                    <div class="stat-mini">
                        <div class="num" id="entregados-count">0</div>
                        <div class="label">Entregados</div>
                    </div>
                </div>
                <div id="cola-list"></div>
            </div>
        </div>

        <script>
            document.getElementById('codigo-input').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') validar();
            });

            async function validar() {
                const input = document.getElementById('codigo-input');
                const codigo = input.value.trim().toUpperCase();
                const resultado = document.getElementById('resultado');

                if (codigo.length !== 8) {
                    resultado.innerHTML = '<div class="resultado error">Codigo invalido (8 caracteres)</div>';
                    return;
                }

                resultado.innerHTML = '<div class="resultado" style="background:rgba(243,156,18,0.2);">Verificando...</div>';

                const res = await fetch('/api/validar-qr', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({codigo: codigo})
                });

                const data = await res.json();

                if (data.ok) {
                    let itemsHtml = data.items.map(i => 
                        `<div>${i.cantidad}x ${i.bebida} <span style="float:right;color:#e94560;">$${i.subtotal.toFixed(2)}</span></div>`
                    ).join('');

                    resultado.innerHTML = `
                        <div class="resultado ok">
                            <h2 style="margin-bottom:10px;">ENTREGAR PEDIDO</h2>
                            <div class="items-entrega">
                                ${itemsHtml}
                            </div>
                            <div style="font-size:1.3em;color:#e94560;font-weight:bold;">
                                Total: $${data.total.toFixed(2)}
                            </div>
                        </div>
                    `;
                    input.value = '';
                    cargarCola();
                } else {
                    resultado.innerHTML = `<div class="resultado error">${data.error}</div>`;
                }
            }

            async function cargarCola() {
                const res = await fetch('/api/pedidos');
                const pedidos = await res.json();
                const list = document.getElementById('cola-list');

                let pendientes = 0;
                let entregados = 0;

                pedidos.forEach(p => {
                    if (p.entregado_en) entregados++;
                    else pendientes++;
                });

                document.getElementById('pendientes-count').textContent = pendientes;
                document.getElementById('entregados-count').textContent = entregados;

                // Mostrar solo los ultimos 20, pendientes primero
                const pedidosOrdenados = pedidos.sort((a, b) => {
                    if (!a.entregado_en && b.entregado_en) return -1;
                    if (a.entregado_en && !b.entregado_en) return 1;
                    return new Date(b.creado_en) - new Date(a.creado_en);
                }).slice(0, 20);

                if (pedidosOrdenados.length === 0) {
                    list.innerHTML = '<div class="sin-pedidos">Sin pedidos aun</div>';
                    return;
                }

                list.innerHTML = pedidosOrdenados.map((p, index) => {
                    const hora = new Date(p.creado_en).toLocaleTimeString('es-AR', {hour: '2-digit', minute:'2-digit'});
                    return `
                        <div class="pedido-cola ${p.entregado_en ? 'entregado' : ''}">
                            <div class="pedido-numero">Pedido #${pedidos.length - index} ${p.entregado_en ? '- ENTREGADO' : ''}</div>
                            <div class="pedido-items">${p.items_texto}</div>
                            <div class="pedido-total">$${p.total.toFixed(2)}</div>
                            <div class="pedido-hora">${hora}</div>
                        </div>
                    `;
                }).join('');
            }

            cargarCola();
            setInterval(cargarCola, 5000);
        </script>
    </body>
    </html>
    """


# ============ PANEL ORGANIZADOR (STOCK + RECAUDACION) ============
@app.get("/organizador", response_class=HTMLResponse)
def panel_organizador():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Panel del Organizador</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                background: #1a1a2e;
                min-height: 100vh;
                color: white;
                padding: 20px;
            }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { text-align: center; margin-bottom: 20px; color: #f39c12; }
            .stats {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 15px;
                margin-bottom: 30px;
            }
            .stat-box {
                background: rgba(255,255,255,0.1);
                padding: 20px;
                border-radius: 15px;
                text-align: center;
            }
            .stat-number { font-size: 2.5em; color: #e94560; font-weight: bold; }
            .stat-label { color: #888; margin-top: 5px; }
            .section {
                background: rgba(255,255,255,0.05);
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
            }
            .section h2 {
                color: #f39c12;
                margin-bottom: 15px;
                border-bottom: 2px solid rgba(255,255,255,0.1);
                padding-bottom: 10px;
            }
            .stock-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .stock-item .nombre { font-size: 1.1em; }
            .stock-item .precio { color: #888; font-size: 0.9em; }
            .stock-controls {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .stock-actual {
                font-size: 1.3em;
                font-weight: bold;
                min-width: 40px;
                text-align: center;
            }
            .stock-actual.bajo { color: #f39c12; }
            .stock-actual.agotado { color: #e94560; }
            .stock-actual.ok { color: #27ae60; }
            .stock-input {
                width: 70px;
                padding: 8px;
                text-align: center;
                border-radius: 8px;
                border: 1px solid #27ae60;
                background: rgba(255,255,255,0.1);
                color: white;
                font-size: 1em;
            }
            .btn-recargar {
                background: #27ae60;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 1em;
            }
            .btn-recargar:hover { background: #2ecc71; }
            .pedidos-list {
                max-height: 400px;
                overflow-y: auto;
            }
            .pedido-item {
                display: flex;
                justify-content: space-between;
                padding: 12px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            .pedido-item.entregado { opacity: 0.5; }
            .pedido-info { flex: 1; }
            .pedido-codigo { font-family: monospace; color: #f39c12; font-size: 1.1em; }
            .pedido-items { color: #888; font-size: 0.9em; margin-top: 3px; }
            .pedido-total { color: #e94560; font-weight: bold; font-size: 1.2em; }
            .pedido-estado {
                font-size: 0.8em;
                padding: 3px 10px;
                border-radius: 10px;
                display: inline-block;
                margin-top: 5px;
            }
            .estado-pendiente { background: #f39c12; color: #1a1a2e; }
            .estado-entregado { background: #27ae60; color: white; }
            .refresh-btn {
                background: #e94560;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 10px;
                cursor: pointer;
                margin-bottom: 15px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PANEL DEL ORGANIZADOR</h1>

            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number" id="total-pedidos">0</div>
                    <div class="stat-label">Pedidos hoy</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="total-entregados">0</div>
                    <div class="stat-label">Entregados</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number" id="total-recaudado">$0</div>
                    <div class="stat-label">Recaudado</div>
                </div>
            </div>

            <div class="section">
                <h2>📦 Control de Stock</h2>
                <div id="stock-list"></div>
            </div>

            <div class="section">
                <h2>📋 Pedidos del Evento</h2>
                <button class="refresh-btn" onclick="cargarPedidos()">Actualizar</button>
                <div class="pedidos-list" id="pedidos-list"></div>
            </div>
        </div>

        <script>
            async function cargarStats() {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('total-pedidos').textContent = data.total_pedidos;
                document.getElementById('total-entregados').textContent = data.total_entregados;
                document.getElementById('total-recaudado').textContent = '$' + data.total_recaudado.toFixed(0);
            }

            async function cargarStock() {
                const res = await fetch('/api/bebidas');
                const bebidas = await res.json();
                const list = document.getElementById('stock-list');

                list.innerHTML = bebidas.map(b => {
                    const stockClass = b.stock <= 0 ? 'agotado' : (b.stock <= 5 ? 'bajo' : 'ok');
                    return `
                        <div class="stock-item">
                            <div>
                                <div class="nombre">${b.nombre}</div>
                                <div class="precio">$${b.precio.toFixed(2)}</div>
                            </div>
                            <div class="stock-controls">
                                <span class="stock-actual ${stockClass}">${b.stock}</span>
                                <input type="number" class="stock-input" id="stock-${b.id}" value="10" min="1">
                                <button class="btn-recargar" onclick="recargarStock(${b.id})">+ Agregar</button>
                            </div>
                        </div>
                    `;
                }).join('');
            }

            async function recargarStock(bebidaId) {
                const input = document.getElementById(`stock-${bebidaId}`);
                const cantidad = parseInt(input.value);
                if (cantidad <= 0) return;

                const res = await fetch('/api/recargar-stock', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({bebida_id: bebidaId, cantidad: cantidad})
                });

                const data = await res.json();
                if (data.ok) {
                    input.value = 10;
                    cargarStock();
                }
            }

            async function cargarPedidos() {
                const res = await fetch('/api/pedidos');
                const pedidos = await res.json();
                const list = document.getElementById('pedidos-list');

                if (pedidos.length === 0) {
                    list.innerHTML = '<p style="text-align:center;color:#888;padding:20px;">Sin pedidos aun</p>';
                    return;
                }

                list.innerHTML = pedidos.map(p => `
                    <div class="pedido-item ${p.entregado_en ? 'entregado' : ''}">
                        <div class="pedido-info">
                            <div class="pedido-codigo">${p.codigo_qr}</div>
                            <div class="pedido-items">${p.items_texto}</div>
                            <span class="pedido-estado ${p.entregado_en ? 'estado-entregado' : 'estado-pendiente'}">
                                ${p.entregado_en ? 'Entregado' : 'Pendiente'}
                            </span>
                        </div>
                        <div class="pedido-total">$${p.total.toFixed(2)}</div>
                    </div>
                `).join('');
            }

            cargarStats();
            cargarStock();
            cargarPedidos();
            setInterval(() => { cargarStats(); cargarPedidos(); }, 10000);
        </script>
    </body>
    </html>
    """


@app.post("/api/validar-qr")
def validar_qr(data: dict):
    codigo = data.get("codigo", "").upper().strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pedidos WHERE codigo_qr = ?", (codigo,))
    pedido = cursor.fetchone()

    if not pedido:
        conn.close()
        return {"ok": False, "error": "Codigo QR no encontrado"}

    pedido = dict(pedido)

    if pedido["estado"] != "pagado":
        conn.close()
        return {"ok": False, "error": "El pago no esta confirmado"}

    if pedido["entregado_en"]:
        conn.close()
        return {"ok": False, "error": "Este pedido YA FUE ENTREGADO"}

    cursor.execute("""
                   SELECT ip.*, b.nombre as bebida_nombre
                   FROM items_pedido ip
                            JOIN bebidas b ON ip.bebida_id = b.id
                   WHERE ip.pedido_id = ?
                   """, (pedido["id"],))
    items = [dict(row) for row in cursor.fetchall()]

    ahora = datetime.now().isoformat()
    cursor.execute("UPDATE pedidos SET entregado_en = ? WHERE id = ?", (ahora, pedido["id"]))
    conn.commit()
    conn.close()

    return {
        "ok": True,
        "items": [{"cantidad": i["cantidad"], "bebida": i["bebida_nombre"], "subtotal": i["subtotal"]} for i in items],
        "total": pedido["total"]
    }


@app.post("/api/recargar-stock")
def recargar_stock(data: dict):
    bebida_id = data.get("bebida_id")
    cantidad = data.get("cantidad", 0)

    if cantidad <= 0:
        return {"ok": False, "error": "Cantidad invalida"}

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE bebidas SET stock = stock + ? WHERE id = ?", (cantidad, bebida_id))
    conn.commit()
    conn.close()

    return {"ok": True}


@app.get("/api/stats")
def get_stats():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE DATE(creado_en) = DATE('now')")
    total_pedidos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE entregado_en IS NOT NULL AND DATE(creado_en) = DATE('now')")
    total_entregados = cursor.fetchone()[0]

    cursor.execute("""
                   SELECT COALESCE(SUM(total), 0)
                   FROM pedidos
                   WHERE estado = 'pagado' AND DATE (creado_en) = DATE ('now')
                   """)
    total_recaudado = cursor.fetchone()[0]

    conn.close()

    return {
        "total_pedidos": total_pedidos,
        "total_entregados": total_entregados,
        "total_recaudado": total_recaudado
    }


@app.get("/api/pedidos")
def get_pedidos():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM pedidos ORDER BY creado_en DESC LIMIT 50")
    pedidos = [dict(row) for row in cursor.fetchall()]

    for pedido in pedidos:
        cursor.execute("""
                       SELECT ip.cantidad, b.nombre
                       FROM items_pedido ip
                                JOIN bebidas b ON ip.bebida_id = b.id
                       WHERE ip.pedido_id = ?
                       """, (pedido["id"],))
        items = cursor.fetchall()
        pedido["items_texto"] = ", ".join([f"{i['cantidad']}x {i['nombre']}" for i in items])

    conn.close()
    return pedidos


@app.get("/pago-exitoso/{pedido_id}")
def pago_exitoso(pedido_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT codigo_qr FROM pedidos WHERE id = ?", (pedido_id,))
    pedido = cursor.fetchone()
    conn.close()

    if pedido:
        return f"<script>window.location.href = '/qr/{pedido[0]}';</script>"
    return "Pedido no encontrado"


@app.get("/pago-fallido")
def pago_fallido():
    return "<h1 style='text-align:center;color:red;'>Pago fallido. Intenta de nuevo.</h1>"


@app.get("/pago-pendiente")
def pago_pendiente():
    return "<h1 style='text-align:center;color:orange;'>Pago pendiente.</h1>"


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("BARRA RAPIDA - INICIADO")
    print("=" * 50)
    print("Cliente:    http://localhost:8000")
    print("Barman:     http://localhost:8000/admin")
    print("Organizador: http://localhost:8000/organizador")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)