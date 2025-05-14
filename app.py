from flask import Flask, flash, jsonify, render_template, request, redirect, url_for, session
import oracledb
import re
from datetime import datetime, timedelta  # CORRECTO: así puedes usar datetime.strptime

app = Flask(__name__)
app.secret_key = 'mi_clave_secreta'

# Oracle Instant Client
oracledb.init_oracle_client(lib_dir=r"C:\oraclexe\instantclient_11_2")
dsn = "localhost/XE"

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nro_documento = request.form['nro_documento']
        contrasena = request.form['contrasena']

        try:
            conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usuario WHERE nro_documento = :1 AND contrasena = :2",
                           (nro_documento, contrasena))
            usuario = cursor.fetchone()
            cursor.close()
            conn.close()

            if usuario:
                session['usuario'] = {
                    'nro_documento': usuario[0],
                    'nombre': usuario[1],
                    'apellido': usuario[2]
                }
                return redirect(url_for('reservar'))
            else:
                mensaje = "Credenciales incorrectas"
                return render_template('login.html', mensaje=mensaje)

        except Exception as e:
            return f"Error: {e}"

    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        documento = request.form['documento']
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        correo = request.form['correo']
        telefono = request.form['telefono']
        tipousuario = request.form['tipousuario']
        contrasena = request.form['contrasena']

        if not re.match(r'^[^@]+@[^@]+\.[a-zA-Z]{2,}$', correo):
            flash("Correo inválido. Debe contener '@' y un dominio válido.")
            return render_template('registro.html')

        try:
            conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usuario (nro_documento, nombre, apellido, correo, telefono, tipousuario, contrasena)
                VALUES (:doc, :nom, :ape, :cor, :tel, :tipo, :contra)
            """, doc=documento, nom=nombre, ape=apellido, cor=correo, tel=telefono, tipo=tipousuario, contra=contrasena)
            conn.commit()
            return render_template('bienvenida.html', mensaje="Registrado exitosamente")
        except Exception as e:
            return f"Error al registrar: {e}"

    return render_template('registro.html')


@app.route('/reservar', methods=['GET', 'POST'])
def reservar():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    mensaje = ""
    try:
        conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
        cursor = conn.cursor()

        # Equipos funcionales
        cursor.execute("SELECT id_equipo, tipo_equipo, descripcion FROM equipo WHERE estado = 'FUNCIONAL'")
        equipos = cursor.fetchall()

        if request.method == 'POST':
            id_equipo = int(request.form['equipo'])
            fecha_inicio = request.form['fecha_inicio']
            fecha_fin = request.form['fecha_fin']

            f_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            f_fin = datetime.strptime(fecha_fin, '%Y-%m-%d')

            if f_fin < f_inicio:
                mensaje = "La fecha de fin no puede ser anterior a la de inicio."
                return render_template('reserva.html', equipos=equipos, mensaje=mensaje)

            dias = (f_fin - f_inicio).days + 1
            if dias < 1 or dias > 7:
                mensaje = "La reserva debe durar mínimo 1 día y máximo 7 días."
                return render_template('reserva.html', equipos=equipos, mensaje=mensaje)

            nro_doc = session['usuario']['nro_documento']

            # ¿Tiene préstamo activo?
            cursor.execute("""
                SELECT COUNT(*) FROM prestamo
                WHERE nro_documento_usuario = :doc AND fecha_devolucion IS NULL
            """, {'doc': nro_doc})
            prestamo_activo = cursor.fetchone()[0]

            if prestamo_activo > 0:
                mensaje = "Ya tienes un préstamo activo. Devuélvelo antes de hacer uno nuevo."
                return render_template('reserva.html', equipos=equipos, mensaje=mensaje)

            # ¿Equipo disponible en fechas?
            cursor.execute("""
                SELECT COUNT(*) FROM prestamo
                WHERE id_equipo = :id
                AND (
                    (fecha_prestamo <= :fin AND fecha_limite >= :inicio)
                )
            """, {'id': id_equipo, 'inicio': f_inicio, 'fin': f_fin})
            conflicto = cursor.fetchone()[0]

            if conflicto > 0:
                mensaje = "El equipo no está disponible en las fechas seleccionadas."
                return render_template('reserva.html', equipos=equipos, mensaje=mensaje)

            # Obtener nuevo ID
            cursor.execute("SELECT NVL(MAX(id_prestamo), 0) + 1 FROM prestamo")
            nuevo_id = cursor.fetchone()[0]

            # Insertar préstamo
            cursor.execute("""
                INSERT INTO prestamo (id_prestamo, fecha_prestamo, fecha_limite, estado, id_equipo, nro_documento_usuario)
                VALUES (:id, :inicio, :fin, 'RESERVADO', :id_equipo, :doc)
            """, {
                'id': nuevo_id,
                'inicio': f_inicio,
                'fin': f_fin,
                'id_equipo': id_equipo,
                'doc': nro_doc
            })

            conn.commit()
            mensaje = "Reserva realizada exitosamente."

        return render_template('reserva.html', equipos=equipos, mensaje=mensaje)

    except Exception as e:
        return f"Error al reservar: {e}"

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
