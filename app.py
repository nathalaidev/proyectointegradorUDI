from flask import Flask, render_template, request, redirect, url_for, session
import oracledb
import datetime

# Inicializa la aplicación Flask
app = Flask(__name__)
app.secret_key = 'mi_clave_secreta'  # Clave secreta para manejo de sesiones

# Inicializa Oracle Client (modo thick), se especifica el directorio del cliente Oracle
oracledb.init_oracle_client(lib_dir=r"C:\oraclexe\instantclient_11_2")

# DSN para conectarse a la base de datos Oracle
dsn = "localhost/XE"

# Ruta para el inicio de sesión
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Obtiene los datos del formulario
        nro_documento = request.form['nro_documento']
        contrasena = request.form['contrasena']

        try:
            # Conexión a la base de datos
            conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
            cursor = conn.cursor()
            
            # Consulta para verificar credenciales del usuario
            cursor.execute("SELECT * FROM usuario WHERE nro_documento = :1 AND contrasena = :2",
                           (nro_documento, contrasena))
            usuario = cursor.fetchone()
            
            cursor.close()
            conn.close()

            if usuario:
                # Si las credenciales son válidas, guardar en sesión
                session['usuario'] = {
                    'nro_documento': usuario[0],
                    'nombre': usuario[1],
                    'apellido': usuario[2]
                }
                return redirect(url_for('reservar'))  # Redirige a la página de reservas
            else:
                # Credenciales incorrectas
                mensaje = "Credenciales incorrectas"
                return render_template('login.html', mensaje=mensaje)
        except Exception as e:
            return f"Error: {e}"  # Muestra error en caso de excepción

    return render_template('login.html')  # Muestra el formulario de login si el método es GET

# Ruta para el registro de nuevos usuarios
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        # Obtiene los datos del formulario de registro
        documento = request.form['documento']
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        correo = request.form['correo']
        telefono = request.form['telefono']
        tipousuario = request.form['tipousuario']
        contrasena = request.form['contrasena']
        try:
            # Conexión e inserción en la tabla usuario
            connection = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO usuario (nro_documento, nombre, apellido, correo, telefono, tipousuario, contrasena)
                VALUES (:doc, :nom, :ape, :cor, :tel, :tipo, :contra)
            """, doc=documento, nom=nombre, ape=apellido, cor=correo, tel=telefono, tipo=tipousuario, contra=contrasena)
            connection.commit()
            return render_template('bienvenida.html', mensaje="Registrado exitosamente")
        except Exception as e:
            return f"Error al registrar: {e}"  # Muestra error si ocurre
    return render_template('registro.html')  # Muestra el formulario de registro

# Ruta para reservar equipos
@app.route('/reservar', methods=['GET', 'POST'])
def reservar():
    if 'usuario' not in session:
        return redirect(url_for('login'))  # Redirige al login si no hay sesión activa

    usuario = session['usuario']

    try:
        # Conexión a la base de datos
        conn = oracledb.connect(user='prestamo', password='prestamo', dsn=dsn)
        cursor = conn.cursor()

        # Verifica si el usuario tiene una sanción vigente
        hoy = datetime.date.today()
        cursor.execute("""
            SELECT COUNT(*) FROM sancion s
            JOIN prestamo p ON s.id_prestamo = p.id_prestamo
            WHERE p.nro_documento_usuario = :1
            AND s.fechafinsancion > :2
        """, (usuario['nro_documento'], hoy))
        sanciones = cursor.fetchone()[0]
        if sanciones > 0:
            return render_template("reserva.html", mensaje="No puedes reservar porque tienes una sanción activa.")

        # Verifica si ya tiene un préstamo activo
        cursor.execute("""
            SELECT COUNT(*) FROM prestamo 
            WHERE nro_documento_usuario = :1 AND estado = 'RESERVADO'
        """, (usuario['nro_documento'],))
        prestamos_activos = cursor.fetchone()[0]
        if prestamos_activos > 0:
            return render_template("reserva.html", mensaje="Ya tienes un préstamo activo.")

        if request.method == 'POST':
            # Obtiene datos del formulario de reserva
            id_equipo = request.form['id_equipo']
            fecha_inicio = datetime.datetime.strptime(request.form['fecha_inicio'], '%Y-%m-%d').date()
            fecha_fin = datetime.datetime.strptime(request.form['fecha_fin'], '%Y-%m-%d').date()

            # Verifica que el rango de fechas sea válido
            diferencia = (fecha_fin - fecha_inicio).days
            if diferencia < 1 or diferencia > 7:
                return render_template("reserva.html", mensaje="La reserva debe durar entre 1 y 7 días.")

            # Genera nuevo ID para el préstamo
            cursor.execute("SELECT NVL(MAX(id_prestamo), 0) + 1 FROM prestamo")
            nuevo_id = cursor.fetchone()[0]

            # Inserta el nuevo préstamo
            cursor.execute("""
                INSERT INTO prestamo (id_prestamo, fecha_prestamo, fecha_limite, estado, id_equipo, nro_documento_usuario)
                VALUES (:1, :2, :3, 'RESERVADO', :4, :5)
            """, (nuevo_id, fecha_inicio, fecha_fin, id_equipo, usuario['nro_documento']))

            # Actualiza el estado del equipo a 'RESERVADO'
            cursor.execute("UPDATE equipo SET estado = 'RESERVADO' WHERE id_equipo = :1", (id_equipo,))

            # Guarda los cambios
            conn.commit()
            mensaje = "Reserva realizada exitosamente."
            cursor.close()
            conn.close()
            return render_template("reserva.html", mensaje=mensaje)

        # Si el método es GET, muestra los equipos disponibles
        cursor.execute("SELECT id_equipo, tipo_equipo, descripcion FROM equipo WHERE estado = 'DISPONIBLE'")
        equipos = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template("reserva.html", usuario=usuario, equipos=equipos)

    except Exception as e:
        return f"Error al reservar: {e}"  # Muestra mensaje en caso de error

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.pop('usuario', None)  # Elimina el usuario de la sesión
    return redirect(url_for('login'))  # Redirige al login

# Inicia la aplicación
if __name__ == '__main__':
    app.run(debug=True)  # Ejecuta en modo debug
