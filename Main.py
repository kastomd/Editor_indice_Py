import sys
import traceback
from pathlib import Path


def excepthook(exc_type, exc_value, exc_traceback):
    """Muestra excepciones en CMD/PowerShell y las guarda en un log."""

    error_text = "".join(
        traceback.format_exception(
            exc_type,
            exc_value,
            exc_traceback
        )
    )

    mensaje = (
        "\n" + "=" * 80 + "\n"
        "ERROR NO CONTROLADO AL EJECUTAR LA APLICACION\n"
        + "=" * 80 + "\n"
        + error_text
        + "=" * 80 + "\n"
    )

    # Intentar mostrar el error en la consola.
    try:
        if sys.stderr is not None:
            sys.stderr.write(mensaje)
            sys.stderr.flush()
        elif sys.stdout is not None:
            sys.stdout.write(mensaje)
            sys.stdout.flush()
    except Exception:
        pass

    # Guardar el error incluso si el EXE no tiene consola.
    try:
        log_path = Path(sys.executable).resolve().parent / "error.log"

        with open(log_path, "a", encoding="utf-8") as log:
            log.write(mensaje + "\n")
    except Exception:
        # Si no es posible escribir junto al EXE,
        # intentar guardarlo en la carpeta actual.
        try:
            with open("error.log", "a", encoding="utf-8") as log:
                log.write(mensaje + "\n")
        except Exception:
            pass


sys.excepthook = excepthook


if __name__ == "__main__":
    try:
        from app_md.base_app import BaseApp

        app = BaseApp()
        app.run()

    except BaseException:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        excepthook(exc_type, exc_value, exc_traceback)
        raise