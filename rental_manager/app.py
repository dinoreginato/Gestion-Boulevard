from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from datetime import datetime
import sqlite3
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

DATABASE = 'rental_manager.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabla de locales
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            metros_cuadrados REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla de UF diarias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uf_diarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL UNIQUE,
            valor_uf REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla de arriendos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arriendos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            valor_uf_arriendo REAL NOT NULL,
            uf_aplicada REAL NOT NULL,
            iva REAL NOT NULL,
            total_pesos REAL NOT NULL,
            fecha_gestion DATE NOT NULL,
            estado TEXT DEFAULT 'pendiente',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (local_id) REFERENCES locales(id)
        )
    ''')
    
    # Tabla de gastos comunes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_comunes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT NOT NULL,
            valor_uf REAL,
            valor_pesos REAL,
            uf_aplicada REAL,
            total_uf REAL NOT NULL,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            fecha_gestion DATE NOT NULL,
            tipo TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla de prorrrateo de gastos comunes por local
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos_comunes_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gasto_comun_id INTEGER NOT NULL,
            local_id INTEGER NOT NULL,
            porcentaje REAL NOT NULL,
            monto_uf REAL NOT NULL,
            monto_pesos REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gasto_comun_id) REFERENCES gastos_comunes(id),
            FOREIGN KEY (local_id) REFERENCES locales(id)
        )
    ''')
    
    # Tabla de consumos de agua
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consumos_agua (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            lectura_inicial REAL NOT NULL,
            lectura_final REAL NOT NULL,
            consumo_m3 REAL NOT NULL,
            porcentaje_consumo REAL NOT NULL,
            costo_total_agua REAL NOT NULL,
            monto_a_pagar REAL NOT NULL,
            fecha_gestion DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (local_id) REFERENCES locales(id)
        )
    ''')
    
    # Tabla de consumos de luz
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consumos_luz (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            lectura_inicial REAL NOT NULL,
            lectura_final REAL NOT NULL,
            consumo_kwh REAL NOT NULL,
            precio_kwh REAL NOT NULL,
            monto_a_pagar REAL NOT NULL,
            fecha_gestion DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (local_id) REFERENCES locales(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Inicializar la base de datos al iniciar
with app.app_context():
    init_db()

@app.route('/')
def index():
    conn = get_db()
    locales = conn.execute('SELECT * FROM locales').fetchall()
    conn.close()
    return render_template('index.html', locales=locales)

@app.route('/locales')
def listar_locales():
    conn = get_db()
    locales = conn.execute('SELECT * FROM locales ORDER BY nombre').fetchall()
    conn.close()
    return render_template('locales/listar.html', locales=locales)

@app.route('/locales/agregar', methods=['GET', 'POST'])
def agregar_local():
    if request.method == 'POST':
        nombre = request.form['nombre']
        metros = float(request.form['metros'])
        
        conn = get_db()
        conn.execute('INSERT INTO locales (nombre, metros_cuadrados) VALUES (?, ?)', (nombre, metros))
        conn.commit()
        conn.close()
        
        flash('Local agregado exitosamente', 'success')
        return redirect(url_for('listar_locales'))
    
    return render_template('locales/agregar.html')

@app.route('/uf')
def gestionar_uf():
    conn = get_db()
    uf_registros = conn.execute('SELECT * FROM uf_diarias ORDER BY fecha DESC').fetchall()
    conn.close()
    return render_template('uf/gestionar.html', uf_registros=uf_registros)

@app.route('/uf/agregar', methods=['GET', 'POST'])
def agregar_uf():
    if request.method == 'POST':
        fecha = request.form['fecha']
        valor = float(request.form['valor'])
        
        conn = get_db()
        try:
            conn.execute('INSERT OR REPLACE INTO uf_diarias (fecha, valor_uf) VALUES (?, ?)', (fecha, valor))
            conn.commit()
            flash('UF registrada exitosamente', 'success')
        except Exception as e:
            flash(f'Error al registrar UF: {str(e)}', 'error')
        finally:
            conn.close()
        
        return redirect(url_for('gestionar_uf'))
    
    return render_template('uf/agregar.html')

@app.route('/arriendos')
def listar_arriendos():
    conn = get_db()
    arriendos = conn.execute('''
        SELECT a.*, l.nombre as nombre_local 
        FROM arriendos a 
        JOIN locales l ON a.local_id = l.id 
        ORDER BY a.anio DESC, a.mes DESC, a.fecha_gestion DESC
    ''').fetchall()
    conn.close()
    return render_template('arriendos/listar.html', arriendos=arriendos)

@app.route('/arriendos/agregar', methods=['GET', 'POST'])
def agregar_arriendo():
    conn = get_db()
    
    if request.method == 'POST':
        local_id = int(request.form['local_id'])
        mes = int(request.form['mes'])
        anio = int(request.form['anio'])
        valor_uf_arriendo = float(request.form['valor_uf'])
        fecha_gestion = request.form['fecha_gestion']
        
        # Obtener UF del día de gestión
        uf_row = conn.execute('SELECT valor_uf FROM uf_diarias WHERE fecha = ?', (fecha_gestion,)).fetchone()
        if not uf_row:
            flash('No hay UF registrada para la fecha seleccionada', 'error')
            conn.close()
            return redirect(url_for('agregar_arriendo'))
        
        uf_aplicada = uf_row['valor_uf']
        subtotal = valor_uf_arriendo * uf_aplicada
        iva = subtotal * 0.19
        total = subtotal + iva
        
        conn.execute('''
            INSERT INTO arriendos (local_id, mes, anio, valor_uf_arriendo, uf_aplicada, iva, total_pesos, fecha_gestion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (local_id, mes, anio, valor_uf_arriendo, uf_aplicada, iva, total, fecha_gestion))
        conn.commit()
        conn.close()
        
        flash('Arriendo registrado exitosamente', 'success')
        return redirect(url_for('listar_arriendos'))
    
    locales = conn.execute('SELECT * FROM locales ORDER BY nombre').fetchall()
    conn.close()
    return render_template('arriendos/agregar.html', locales=locales)

@app.route('/gastos-comunes')
def listar_gastos_comunes():
    conn = get_db()
    gastos = conn.execute('SELECT * FROM gastos_comunes ORDER BY anio DESC, mes DESC, fecha_gestion DESC').fetchall()
    conn.close()
    return render_template('gastos_comunes/listar.html', gastos=gastos)

@app.route('/gastos-comunes/agregar', methods=['GET', 'POST'])
def agregar_gasto_comun():
    conn = get_db()
    
    if request.method == 'POST':
        descripcion = request.form['descripcion']
        tipo = request.form['tipo']  # 'uf' o 'pesos'
        valor = float(request.form['valor'])
        mes = int(request.form['mes'])
        anio = int(request.form['anio'])
        fecha_gestion = request.form['fecha_gestion']
        
        # Obtener UF del día
        uf_row = conn.execute('SELECT valor_uf FROM uf_diarias WHERE fecha = ?', (fecha_gestion,)).fetchone()
        if not uf_row:
            flash('No hay UF registrada para la fecha seleccionada', 'error')
            conn.close()
            return redirect(url_for('agregar_gasto_comun'))
        
        uf_aplicada = uf_row['valor_uf']
        
        if tipo == 'uf':
            valor_uf = valor
            valor_pesos = None
            total_uf = valor
        else:
            valor_uf = None
            valor_pesos = valor
            total_uf = valor / uf_aplicada
        
        conn.execute('''
            INSERT INTO gastos_comunes (descripcion, valor_uf, valor_pesos, uf_aplicada, total_uf, mes, anio, fecha_gestion, tipo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (descripcion, valor_uf, valor_pesos, uf_aplicada, total_uf, mes, anio, fecha_gestion, tipo))
        
        gasto_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        
        # Prorratear entre todos los locales
        locales = conn.execute('SELECT * FROM locales').fetchall()
        total_metros = sum(l['metros_cuadrados'] for l in locales)
        
        for local in locales:
            porcentaje = (local['metros_cuadrados'] / total_metros) * 100
            monto_uf = total_uf * (local['metros_cuadrados'] / total_metros)
            monto_pesos = monto_uf * uf_aplicada
            
            conn.execute('''
                INSERT INTO gastos_comunes_detalle (gasto_comun_id, local_id, porcentaje, monto_uf, monto_pesos)
                VALUES (?, ?, ?, ?, ?)
            ''', (gasto_id, local['id'], porcentaje, monto_uf, monto_pesos))
        
        conn.commit()
        conn.close()
        
        flash('Gasto común registrado y prorrateado exitosamente', 'success')
        return redirect(url_for('listar_gastos_comunes'))
    
    conn.close()
    return render_template('gastos_comunes/agregar.html')

@app.route('/gastos-comunes/descargar/<int:gasto_id>')
def descargar_pdf_gasto(gasto_id):
    conn = get_db()
    
    gasto = conn.execute('SELECT * FROM gastos_comunes WHERE id = ?', (gasto_id,)).fetchone()
    detalle = conn.execute('''
        SELECT d.*, l.nombre as nombre_local, l.metros_cuadrados
        FROM gastos_comunes_detalle d
        JOIN locales l ON d.local_id = l.id
        WHERE d.gasto_comun_id = ?
        ORDER BY l.nombre
    ''', (gasto_id,)).fetchall()
    
    conn.close()
    
    # Crear PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20,
        alignment=1  # Center
    )
    
    elements.append(Paragraph(f"Detalle de Gasto Común", title_style))
    elements.append(Paragraph(f"{gasto['descripcion']}", styles['Heading2']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Información del gasto
    info_data = [
        ['Fecha de Gestión:', gasto['fecha_gestion']],
        ['Mes/Año:', f"{gasto['mes']}/{gasto['anio']}"],
        ['Tipo:', 'UF' if gasto['tipo'] == 'uf' else 'Pesos'],
        ['Valor Original:', f"${gasto['valor_uf']:,.2f} UF" if gasto['tipo'] == 'uf' else f"${gasto['valor_pesos']:,.2f}"],
        ['UF Aplicada:', f"${gasto['uf_aplicada']:,.2f}"],
        ['Total en UF:', f"${gasto['total_uf']:,.2f}"],
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 2*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Tabla de prorrrateo
    elements.append(Paragraph("Prorrateo por Local", styles['Heading2']))
    elements.append(Spacer(1, 0.2*inch))
    
    table_data = [['Local', 'Metros²', '% Participación', 'Monto (UF)', 'Monto (Pesos)']]
    
    for item in detalle:
        table_data.append([
            item['nombre_local'],
            f"{item['metros_cuadrados']:.2f}",
            f"{item['porcentaje']:.2f}%",
            f"${item['monto_uf']:,.4f}",
            f"${item['monto_pesos']:,.2f}"
        ])
    
    # Agregar totales
    total_metros = sum(item['metros_cuadrados'] for item in detalle)
    total_monto_uf = sum(item['monto_uf'] for item in detalle)
    total_monto_pesos = sum(item['monto_pesos'] for item in detalle)
    
    table_data.append([
        'TOTALES',
        f"{total_metros:.2f}",
        '100.00%',
        f"${total_monto_uf:,.4f}",
        f"${total_monto_pesos:,.2f}"
    ])
    
    table = Table(table_data, colWidths=[2*inch, 0.8*inch, 1*inch, 1*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.lightgrey]),
    ]))
    
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"gasto_comun_{gasto_id}_{gasto['descripcion'].replace(' ', '_')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route('/consumos')
def listar_consumos():
    conn = get_db()
    aguas = conn.execute('''
        SELECT c.*, l.nombre as nombre_local 
        FROM consumos_agua c 
        JOIN locales l ON c.local_id = l.id 
        ORDER BY c.anio DESC, c.mes DESC
    ''').fetchall()
    
    luces = conn.execute('''
        SELECT c.*, l.nombre as nombre_local 
        FROM consumos_luz c 
        JOIN locales l ON c.local_id = l.id 
        ORDER BY c.anio DESC, c.mes DESC
    ''').fetchall()
    
    conn.close()
    return render_template('consumos/listar.html', aguas=aguas, luces=luces)

@app.route('/consumos/agregar', methods=['GET', 'POST'])
def agregar_consumo():
    conn = get_db()
    
    if request.method == 'POST':
        tipo = request.form['tipo']  # 'agua' o 'luz'
        local_id = int(request.form['local_id'])
        mes = int(request.form['mes'])
        anio = int(request.form['anio'])
        lectura_inicial = float(request.form['lectura_inicial'])
        lectura_final = float(request.form['lectura_final'])
        fecha_gestion = request.form['fecha_gestion']
        
        consumo = lectura_final - lectura_inicial
        
        if tipo == 'agua':
            # Para agua, necesitamos calcular el porcentaje respecto al total
            # Primero verificamos si ya hay otros consumos de agua este mes
            otros_consumos = conn.execute('''
                SELECT SUM(consumo_m3) as total 
                FROM consumos_agua 
                WHERE mes = ? AND anio = ? AND local_id != ?
            ''', (mes, anio, local_id)).fetchone()['total'] or 0
            
            total_consumo = consumo + otros_consumos
            porcentaje = (consumo / total_consumo * 100) if total_consumo > 0 else 0
            
            # El costo total del agua debe ser ingresado o calculado
            costo_total = float(request.form['costo_total_agua'])
            monto_a_pagar = costo_total * (consumo / total_consumo) if total_consumo > 0 else 0
            
            conn.execute('''
                INSERT INTO consumos_agua 
                (local_id, mes, anio, lectura_inicial, lectura_final, consumo_m3, porcentaje_consumo, costo_total_agua, monto_a_pagar, fecha_gestion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (local_id, mes, anio, lectura_inicial, lectura_final, consumo, porcentaje, costo_total, monto_a_pagar, fecha_gestion))
            
        else:  # luz
            precio_kwh = float(request.form['precio_kwh'])
            monto_a_pagar = consumo * precio_kwh
            
            conn.execute('''
                INSERT INTO consumos_luz 
                (local_id, mes, anio, lectura_inicial, lectura_final, consumo_kwh, precio_kwh, monto_a_pagar, fecha_gestion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (local_id, mes, anio, lectura_inicial, lectura_final, consumo, precio_kwh, monto_a_pagar, fecha_gestion))
        
        conn.commit()
        conn.close()
        
        flash(f'Consumo de {tipo} registrado exitosamente', 'success')
        return redirect(url_for('listar_consumos'))
    
    locales = conn.execute('SELECT * FROM locales ORDER BY nombre').fetchall()
    conn.close()
    return render_template('consumos/agregar.html', locales=locales)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
