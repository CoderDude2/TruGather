import tkinter as tk
import os
import time
import threading
from pathlib import Path

from file_manager import FileProcessor, FileManager
import info_widget

BASE_DIR = Path(__file__).resolve().parent


class MenuBar(tk.Menu):
    def __init__(self, master=None) -> None:
        super().__init__(master)

        self.file_menu: tk.Menu = tk.Menu(self, tearoff=False)
        self.file_menu.add_command(label="   Exit   ", command=master.on_close)

        self.help_menu: tk.Menu = tk.Menu(self, tearoff=False)
        self.help_menu.add_command(label="   View Help   ", command=self.on_help_option)

        self.add_cascade(label="File", menu=self.file_menu)
        self.add_cascade(label="Help", menu=self.help_menu)

    def on_help_option(self):
        if os.name == "nt":
            os.system(f"start {os.path.join(BASE_DIR, 'resources/help/index.html')}")
        elif os.name == "posix":
            os.system(f"open {os.path.join(BASE_DIR, 'resources/help/index.html')}")

class StatPanel(tk.Frame):
    def __init__(self, master = None) -> None:
        super().__init__(master) 

        self.case_lbl_map: dict[str, tk.Label] = {}
        self.associate_lbl_map: dict[str, list[tk.Label]] = {}

        self.grid_columnconfigure(0, weight=1)

        self.a:list[tk.IntVar] = [] 
        self.a.append(tk.IntVar(value=0))

        self.stop_thread_event = threading.Event()
        threading.Thread(target=self.update_stat_panel, daemon=True).start()

    def update_stat_panel(self) -> None:
        fm = FileManager()
        row: int = 0

        previous_associate_data: dict[str, int] = {}
        while not self.stop_thread_event.is_set(): 
            associate_data = fm.get_associate_counts()

            if associate_data != previous_associate_data:
                previous_associate_data = associate_data
                for associate, count in associate_data.items():
                    if associate not in self.associate_lbl_map.keys():
                        associate_label: tk.Label = tk.Label(self, text=associate)
                        count_label: tk.Label = tk.Label(self, text=count)

                        associate_label.grid(row=row, column=0, sticky='w')
                        count_label.grid(row=row, column=1, sticky='e', padx=5)

                        self.associate_lbl_map[associate] = [associate_label, count_label]

                        row += 1
                        continue
                    self.associate_lbl_map[associate][1].configure(text=count)
        fm.con.close()

    def stop_stat_pane(self) -> None:
        self.stop_thread_event.set()

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.fp: FileProcessor = FileProcessor()

        self.geometry("445x370")
        self.minsize(445, 275)
        self.iconbitmap(os.path.join(BASE_DIR, "resources", "icons", "tru-gather.ico"))

        self.title("TruGather")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.menu_bar: MenuBar = MenuBar(self)

        self.auto_check: tk.BooleanVar = tk.BooleanVar()

        self.control_frame: tk.Frame = tk.Frame(master=self)
        self.auto_gather_checkbutton: tk.Checkbutton = tk.Checkbutton(
            master=self.control_frame,
            text="Auto Gather",
            variable=self.auto_check,
            onvalue=True,
            offvalue=False,
            command=self.on_auto_gather_toggle,
        )
        self.gather_prg_button: tk.Button = tk.Button(
            master=self.control_frame,
            text="Gather All NC",
            padx=20,
            pady=20,
            command=self.fp.gather_all_files,
        )
        self.gather_asc_button: tk.Button = tk.Button(
            master=self.control_frame,
            text="Gather All ASC",
            padx=20,
            pady=20,
            command=self.fp.gather_all_asc_files,
        )
        self.stat_panel: StatPanel = StatPanel(self.control_frame)

        self.info_widget = info_widget.InfoWidget()

        self.auto_gather_checkbutton.pack(side=tk.TOP)
        self.gather_prg_button.pack(fill=tk.X, side=tk.TOP)
        self.gather_asc_button.pack(fill=tk.X, side=tk.TOP)
        self.stat_panel.pack(fill=tk.X, side=tk.TOP)

        self.control_frame.grid(row=0, column=0, sticky="nsew")
        self.info_widget.grid(row=0, column=1, sticky="nsew")

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.config(menu=self.menu_bar)

    def on_auto_gather_toggle(self):
        if self.auto_check.get():
            self.fp.start_gathering()
            self.gather_prg_button.configure(state=tk.DISABLED)
            self.gather_asc_button.configure(state=tk.DISABLED)
        else:
            self.fp.stop_gathering()
            self.gather_prg_button.configure(state=tk.NORMAL)
            self.gather_asc_button.configure(state=tk.NORMAL)

    def on_close(self) -> None:
        self.fp.stop_processing()
        self.info_widget.close_connection()
        self.stat_panel.stop_stat_pane()
        self.destroy()
