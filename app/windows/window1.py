import tkinter as tk
from tkinter import ttk

from config import settings

class Window1(tk.Frame):
    def __init__(self, master, controlador):
        super().__init__(master)
        self.controlador = controlador
        self.pack(fill="both", expand=True)
        self.configure(bg=settings.COLORS["background"])
        
        # Crear el Treeview (tabla)
        columns = ("col1", "col2", "col3")  # Nombres de las columnas
        self.tree = ttk.Treeview(self, columns=columns, show="headings")

        # Configurar encabezados de las columnas
        self.tree.heading("col1", text="Files")
        self.tree.heading("col2", text="Offset")
        self.tree.heading("col3", text="Size")

        # Ajustar el ancho de las columnas
        self.tree.column("col1", width=150, anchor="center")
        self.tree.column("col2", width=150, anchor="center")
        self.tree.column("col3", width=150, anchor="center")

        # Insertar datos en la tabla
        data = [
            ("Dato 1", "Dato 2", "Accion 1"),
            ("Valor 1", "Valor 2", "Accion 2"),
            ("Ejemplo 1", "Ejemplo 2", "Accion 3"),
        ]

        for row in data:
            self.tree.insert("", tk.END, values=row)

        # Funcion para importar datos
        def import_data():
            selected_item = self.tree.selection()
            if selected_item:
                item_values = self.tree.item(selected_item, "values")
                print(f"Importando datos... {item_values[2]}")

        # Funcion para exportar datos
        def export_data():
            selected_item = self.tree.selection()
            if selected_item:
                item_values = self.tree.item(selected_item, "values")
                print(f"Exportando datos... {item_values[2]}")

        # Crear el menu contextual
        context_menu = tk.Menu(self, tearoff=0)
        context_menu.add_command(label="Import", command=import_data)
        context_menu.add_command(label="Export", command=export_data)

        # Funcion para mostrar el menu contextual al hacer clic derecho
        def show_context_menu(event):
            context_menu.post(event.x_root, event.y_root)

        # Asociar el evento de clic derecho (Button-3) al Treeview
        self.tree.bind("<Button-3>", show_context_menu)

        # Colocar el Treeview en la ventana
        self.pack(expand=True, fill="both")

