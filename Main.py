import sys
import traceback

def excepthook(exc_type, exc_value, exc_traceback):
    """Imprime excepciones no controladas en CMD/PowerShell."""

    error_text = "".join(
        traceback.format_exception(
            exc_type,
            exc_value,
            exc_traceback
        )
    )

    print()
    print("=" * 80)
    print("ERROR NO CONTROLADO AL EJECUTAR LA APLICACION / UNHANDLED ERROR WHILE RUNNING THE APPLICATION")
    print("=" * 80)
    print(error_text)
    print("=" * 80)
    print()

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass


# Capturar excepciones no controladas en cualquier parte del programa.
sys.excepthook = excepthook


if __name__ == "__main__":
    try:
        # Importar dentro del try para capturar errores de carga.
        from app_md.base_app import BaseApp

        app = BaseApp()
        app.run()

    except Exception:
        # Usar el mismo manejador para mostrar el error en consola.
        exc_type, exc_value, exc_traceback = sys.exc_info()
        excepthook(exc_type, exc_value, exc_traceback)
