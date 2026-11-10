from flask import Flask, render_template, request, redirect, url_for, session
from models import UsuarioUpen
from db import get_db_connection

app = Flask(__name__)
app.secret_key = 'clave_secreta_super_segura' # Necesario para las sesiones

# Ruta de Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conexion = get_db_connection()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        conexion.close()

        if user:
            # Guardamos los datos del usuario en la sesión
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Usuario o contraseña incorrectos")

    return render_template('login.html')

# Ruta Principal (Protegida)
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    alumnos = UsuarioUpen.obtener_todos()
    return render_template('index.html', alumnos=alumnos, role=session['role'])

# Ruta para Agregar Alumno (Solo Servicios Escolares)
# Asigna automáticamente todas las materias existentes en estatus 'Ordinario'
@app.route('/agregar', methods=['GET', 'POST'])
def agregar():
    if 'username' not in session or session.get('role', '').lower() not in ['servicios', 'servicios escolares']:
        return "Acceso denegado. No tienes permisos de Servicios Escolares.", 403

    if request.method == 'POST':
        student_id = request.form['student_id']
        full_name = request.form['full_name']
        career = request.form['career']

        # 1. Guardar el alumno utilizando el modelo
        nuevo_alumno = UsuarioUpen(student_id=student_id, full_name=full_name, career=career)
        nuevo_alumno.guardar()

        # 2. Asignarle por defecto todas las materias en estatus Ordinario (Paid/Activo)
        conexion = get_db_connection()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT subject_id FROM subjects")
        subjects = cursor.fetchall()

        for sub in subjects:
            cursor.execute(
                "INSERT INTO payments (student_id, subject_id, exam_type, status) VALUES (%s, %s, %s, %s)",
                (student_id, sub['subject_id'], 'Ordinario', 'Paid')
            )
        conexion.commit()
        conexion.close()

        return redirect(url_for('index'))
        
    return render_template('agregar.html')


# Ruta para que el Profesor cambie el tipo de examen (Ordinario -> Remedial / Extraordinario)
@app.route('/asignar_remedial', methods=['GET', 'POST'])
def asignar_remedial():
    if 'username' not in session or session.get('role').lower() not in ['profesor', 'maestro']:
        return "Acceso denegado. Área exclusiva para Profesores.", 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        student_id = request.form['student_id']
        subject_id = request.form['subject_id']
        exam_type = request.form['exam_type'] # 'Ordinario', 'Remedial' o 'Extraordinario'
        
        # Si es Remedial o Extraordinario, cambia a 'Pending' para que Servicios Escolares lo vea
        # Si regresa a Ordinario, se marca como 'Paid'
        status = 'Pending' if exam_type in ['Remedial', 'Extraordinario'] else 'Paid'
        
        # ACTUALIZAR el registro existente en la tabla payments
        cursor.execute(
            """UPDATE payments 
               SET exam_type = %s, status = %s 
               WHERE student_id = %s AND subject_id = %s""",
            (exam_type, status, student_id, subject_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('pagos'))
    
    # Consultar alumnos y materias para llenar los select del formulario
    cursor.execute("SELECT student_id, full_name FROM students")
    students = cursor.fetchall()
    
    cursor.execute("SELECT subject_id, subject_name FROM subjects")
    subjects = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('asignar_remedial.html', students=students, subjects=subjects, role=session.get('role'))


# RUTA ACTUALIZADA: Permite cambiar tipo de examen (Profesor) o estatus de pago (Servicios Escolares)
@app.route('/actualizar_tipo_examen/<int:payment_id>', methods=['POST'])
def actualizar_tipo_examen(payment_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    role = session.get('role').lower()
    conexion = get_db_connection()
    cursor = conexion.cursor()
    
    # Si el usuario es Profesor, actualiza el tipo de examen y ajusta el estatus en automático
    if role in ['profesor', 'maestro']:
        nuevo_tipo = request.form.get('exam_type')
        nuevo_status = 'Pending' if nuevo_tipo in ['Remedial', 'Extraordinario'] else 'Paid'
        cursor.execute(
            "UPDATE payments SET exam_type = %s, status = %s WHERE payment_id = %s",
            (nuevo_tipo, nuevo_status, payment_id)
        )
    
    # Si el usuario es Servicios Escolares, actualiza directamente el estatus del pago
    elif role in ['servicios', 'servicios escolares']:
        nuevo_status = request.form.get('status')
        cursor.execute(
            "UPDATE payments SET status = %s WHERE payment_id = %s",
            (nuevo_status, payment_id)
        )
        
    conexion.commit()
    conexion.close()
    
    # Redirigir conservando la página previa (búsqueda o vista actual)
    return redirect(request.referrer or url_for('pagos'))


# RUTA DE PAGOS (Filtrada correctamente conectando con la tabla teachers mediante t.full_name)
@app.route('/pagos')
def pagos():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    busqueda = request.args.get('buscar', '').strip()
    ver_todos = request.args.get('ver_todos', '0')
    role = session.get('role')
    username = session.get('username')
    
    lista_pagos = []
    
    conexion = get_db_connection()
    cursor = conexion.cursor(dictionary=True)
    
    # Consulta uniendo payments, students, subjects y teachers mediante teacher_id
    base_query = """
        SELECT p.*, st.full_name AS student_name, sub.subject_name 
        FROM payments p
        LEFT JOIN students st ON p.student_id = st.student_id
        LEFT JOIN subjects sub ON p.subject_id = sub.subject_id
        LEFT JOIN teachers t ON sub.teacher_id = t.teacher_id
        WHERE 1=1
    """
    params = []

    # Si es profesor, filtramos comparando con el nombre completo del maestro en la tabla teachers
    if role.lower() in ['profesor', 'maestro']:
        base_query += " AND t.full_name = %s"
        params.append(username)

    # Si escribió algo en el buscador
    if busqueda:
        base_query += " AND (p.student_id LIKE %s OR st.full_name LIKE %s OR sub.subject_name LIKE %s)"
        param_like = '%' + busqueda + '%'
        params.extend([param_like, param_like, param_like])
        cursor.execute(base_query, tuple(params))
        lista_pagos = cursor.fetchall()
    
    # Si presionó "Ver Todos" o si es profesor cargando sus materias correspondientes
    elif ver_todos == '1' or role.lower() in ['profesor', 'maestro']:
        cursor.execute(base_query, tuple(params))
        lista_pagos = cursor.fetchall()
        
    conexion.close()

    return render_template('payment.html', pagos=lista_pagos, role=role, busqueda=busqueda, ver_todos=ver_todos)


# Ruta para Cerrar Sesión
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)