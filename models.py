from db import get_db_connection

# Clase base con los datos generales de cualquier persona
class Persona:
    """Clase principal que guarda los datos básicos de identidad."""
    def __init__(self, student_id=None, full_name=None):
        self.student_id = student_id
        self.full_name = full_name


# Clase hija que hereda de Persona y agrega datos específicos del alumno
class UsuarioUpen(Persona):
    """   para manejar la información de los alumnos y su conexión con la base de datos."""
    
    def __init__(self, student_id=None, full_name=None, career=None):
        # Heredamos los atributos básicos usando super()
        super().__init__(student_id, full_name)
        self.career = career  # Atributo propio del estudiante

    @classmethod
    def obtener_todos(cls):
        """Consulta y trae a todos los alumnos registrados en la base de datos."""
        # Nos conectamos a la BD
        conexion = get_db_connection()
        cursor = conexion.cursor(dictionary=True)
        
        # Ejecutamos la consulta para traer los campos principales
        cursor.execute("SELECT student_id, full_name, career FROM students")
        resultados = cursor.fetchall()
        
        # Cerramos la conexión para liberar recursos
        conexion.close()
        return resultados

    def guardar(self):
        """Guarda un nuevo alumno en la base de datos usando los datos de este objeto."""
        # Nos conectamos a la BD
        conexion = get_db_connection()
        cursor = conexion.cursor()
        
        # Preparamos el comando SQL de inserción de forma segura
        sql = "INSERT INTO students (student_id, full_name, career) VALUES (%s, %s, %s)"
        valores = (self.student_id, self.full_name, self.career)
        
        # Ejecutamos, guardamos cambios y cerramos la conexión
        cursor.execute(sql, valores)
        conexion.commit()
        conexion.close()