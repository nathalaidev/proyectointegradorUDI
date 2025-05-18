from flask import Flask, flash, jsonify, render_template, request, redirect, url_for, session
import oracledb
import re
from datetime import datetime, timedelta  # CORRECTO: así puedes usar datetime.strptime


app = Flask(__name__)
app.secret_key = 'mi_clave_secreta'

# Oracle Instant Client
oracledb.init_oracle_client(lib_dir=r"C:\oraclexe\instantclient_11_2")
dsn = "localhost/XE"

#login
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nro_documento = request.form['nro_documento']
        contrasena = request.form['contrasena']

        try:
            conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
            cursor = conn.cursor()

            # Buscar si el usuario existe
            cursor.execute("SELECT * FROM usuario WHERE nro_documento = :1", (nro_documento,))
            usuario = cursor.fetchone()

            if not usuario:
                mensaje = "El usuario no existe."
                return render_template('login.html', mensaje=mensaje)

            # Comparar contraseña
            if usuario[6] != contrasena:  # Índice 6 es 'contrasena'
                mensaje = "Credenciales incorrectas."
                return render_template('login.html', mensaje=mensaje)

            # Inicio de sesión correcto
            session['usuario'] = {
                'nro_documento': usuario[0],
                'nombre': usuario[1],
                'apellido': usuario[2],
                'tipousuario': usuario[5]  # Índice 5 es TIPOUSUARIO
            }
            if usuario[5].lower() == 'encargado':
                 return redirect(url_for('home_encargado'))
            else:
                return redirect(url_for('home'))

        except Exception as e:
            return f"Error: {e}"

        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

    return render_template('login.html')

@app.route('/home')
def home():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    return render_template('home.html')

@app.route('/home_encargado')
def home_encargado():
    if 'usuario' not in session or session['usuario']['tipousuario'].lower() != 'encargado':
        return redirect(url_for('login'))
    return render_template('home_encargado.html')

@app.route('/ver_historial_usuario', methods=['POST'])
def ver_historial_usuario():
    documento = request.form['documento']
    
    try:
        conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT e.tipo_equipo, p.fecha_prestamo, p.fecha_devolucion, p.fecha_limite
            FROM prestamo p
            JOIN equipo e ON p.id_equipo = e.id_equipo
            WHERE p.nro_documento_usuario = :doc
            ORDER BY p.fecha_prestamo DESC
        """, {'doc': documento})

        prestamos = cursor.fetchall()
        
    except Exception as e:
        return f"Error al obtener historial: {e}"

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

    return render_template("historial.html", prestamos=prestamos, documento=documento)


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

            # Verificar si el usuario ya existe
            cursor.execute("SELECT COUNT(*) FROM usuario WHERE nro_documento = :doc", {'doc': documento})
            existe = cursor.fetchone()[0]

            if existe > 0:
                flash("El usuario ya está registrado. Por favor contacte a soporte.")
                return render_template('registro.html')

            # Insertar nuevo usuario
            cursor.execute("""
                INSERT INTO usuario (nro_documento, nombre, apellido, correo, telefono, tipousuario, contrasena)
                VALUES (:doc, :nom, :ape, :cor, :tel, :tipo, :contra)
            """, doc=documento, nom=nombre, ape=apellido, cor=correo, tel=telefono, tipo=tipousuario, contra=contrasena)
            conn.commit()
            return render_template('bienvenida.html', mensaje="Registrado exitosamente")

        except Exception as e:
            return f"Error al registrar: {e}"

        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()

    return render_template('registro.html')


#reservar equipo
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

            # ¿Tiene préstamo activo actual (fecha_devolución NULL y aún no ha vencido)?
            cursor.execute("""
                SELECT COUNT(*) FROM prestamo
                WHERE nro_documento_usuario = :doc 
                AND fecha_devolucion IS NULL
                AND fecha_limite >= TRUNC(SYSDATE)
            """, {'doc': nro_doc})
            prestamo_activo = cursor.fetchone()[0]
            if prestamo_activo > 0:
                mensaje = "Ya tienes un préstamo activo. Devuélvelo antes de hacer uno nuevo."
                return render_template('reserva.html', equipos=equipos, mensaje=mensaje)

            # ¿Tiene sanciones activas?
            cursor.execute("""
                SELECT COUNT(*) FROM sancion s
                JOIN prestamo p ON s.id_prestamo = p.id_prestamo
                WHERE p.nro_documento_usuario = :doc
                AND s.fechafinsancion >= TRUNC(SYSDATE)
            """, {'doc': nro_doc})
            sanciones_activas = cursor.fetchone()[0]
            if sanciones_activas > 0:
                mensaje = "Tienes una sanción activa. No puedes hacer préstamos actualmente."
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

            # Obtener nuevo ID de préstamo
            cursor.execute("SELECT NVL(MAX(id_prestamo), 0) + 1 FROM prestamo")
            nuevo_id = cursor.fetchone()[0]

            # Insertar el nuevo préstamo
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



#sanciones
@app.route('/sanciones')
def sanciones():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    nro_documento = session['usuario']['nro_documento']

    conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
    cursor = conn.cursor()
    query = """
        SELECT s.ID_SANCION, s.MOTIVO, s.DESCRIPCION, s.FECHA_SANCION, s.FECHAFINSANCION
        FROM SANCION s
        JOIN PRESTAMO p ON s.ID_PRESTAMO = p.ID_PRESTAMO
        WHERE p.NRO_DOCUMENTO_USUARIO = :nro_documento
          AND SYSDATE BETWEEN s.FECHA_SANCION AND s.FECHAFINSANCION
    """
    cursor.execute(query, nro_documento=nro_documento)
    sanciones_activas = cursor.fetchall()
    cursor.close()

    return render_template('sanciones.html', sanciones=sanciones_activas)

#historialPrestamos
@app.route('/historial')
def historial():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    try:
        conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
        cursor = conn.cursor()
        nro_doc = session['usuario']['nro_documento']

        cursor.execute("""
            SELECT e.tipo_equipo, p.fecha_prestamo, p.fecha_devolucion, p.fecha_limite
            FROM prestamo p
            JOIN equipo e ON p.id_equipo = e.id_equipo
            WHERE p.nro_documento_usuario = :doc
            ORDER BY p.fecha_prestamo DESC
        """, {'doc': nro_doc})

        prestamos = cursor.fetchall()
        return render_template("historial.html", prestamos=prestamos)

    except Exception as e:
        return f"Error al obtener historial: {e}"

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@app.route('/historial_encargado', methods=['GET', 'POST'])
def historial_encargado():
    if 'usuario' not in session or session['usuario']['tipousuario'].lower() != 'encargado':
        return redirect(url_for('login'))

    prestamos = []
    documento = None
    mensaje = ""

    if request.method == 'POST':
        documento = request.form.get('documento')
        if documento:
            try:
                conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT e.tipo_equipo, p.fecha_prestamo, p.fecha_devolucion, p.fecha_limite, u.nombre, u.apellido
                    FROM prestamo p
                    JOIN equipo e ON p.id_equipo = e.id_equipo
                    JOIN usuario u ON p.nro_documento_usuario = u.nro_documento
                    WHERE p.nro_documento_usuario = :doc
                    ORDER BY p.fecha_prestamo DESC
                """, {'doc': documento})

                prestamos = cursor.fetchall()

            except Exception as e:
                mensaje = f"Error al obtener historial: {e}"

            finally:
                if 'cursor' in locals():
                    cursor.close()
                if 'conn' in locals():
                    conn.close()
        else:
            mensaje = "Por favor ingrese un número de documento."

    return render_template('historial_encargado.html', prestamos=prestamos, documento=documento, mensaje=mensaje)




@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))



if __name__ == '__main__':
    app.run(debug=True)
