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
    def __init__(self, master=None) -> None:
        super().__init__(master)

        self.all_count: tk.IntVar = tk.IntVar()
        self.asc_count: tk.IntVar = tk.IntVar()
        self.tl_aot_count: tk.IntVar = tk.IntVar()
        self.ds_count: tk.IntVar = tk.IntVar()
        self.aotp_count: tk.IntVar = tk.IntVar()

        self.associate_lbl_map: dict[str, list[tk.Label]] = {}
        self.associate_frame: tk.Frame = tk.Frame(self, bg="white")
        self.associate_frame.grid_columnconfigure(0, weight=1)

        self.case_frame: tk.Frame = tk.Frame(self, bg="white")
        self.case_frame.grid_columnconfigure(0, weight=1)
        self.all_lbl = tk.Label(self.case_frame, text="ALL", bg="white")
        self.all_count_lbl = tk.Label(
            self.case_frame, textvariable=self.all_count, bg="white"
        )
        self.all_lbl.grid(row=0, column=0, sticky="w")
        self.all_count_lbl.grid(row=0, column=1, sticky="e", padx=5)

        self.asc_lbl = tk.Label(self.case_frame, text="ASC", bg="white")
        self.asc_count_lbl = tk.Label(
            self.case_frame, textvariable=self.asc_count, bg="white"
        )
        self.asc_lbl.grid(row=1, column=0, sticky="w")
        self.asc_count_lbl.grid(row=1, column=1, sticky="e", padx=5)

        self.tl_aot_lbl = tk.Label(self.case_frame, text="TL/AOT", bg="white")
        self.tl_aot_count_lbl = tk.Label(
            self.case_frame, textvariable=self.tl_aot_count, bg="white"
        )
        self.tl_aot_lbl.grid(row=2, column=0, sticky="w")
        self.tl_aot_count_lbl.grid(row=2, column=1, sticky="e", padx=5)

        self.ds_lbl = tk.Label(self.case_frame, text="DS", bg="white")
        self.ds_count_lbl = tk.Label(
            self.case_frame, textvariable=self.ds_count, bg="white"
        )
        self.ds_lbl.grid(row=3, column=0, sticky="w")
        self.ds_count_lbl.grid(row=3, column=1, sticky="e", padx=5)

        self.aotp_lbl = tk.Label(self.case_frame, text="AOTP", bg="white")
        self.aotp_count_lbl = tk.Label(
            self.case_frame, textvariable=self.aotp_count, bg="white"
        )
        self.aotp_lbl.grid(row=4, column=0, sticky="w")
        self.aotp_count_lbl.grid(row=4, column=1, sticky="e", padx=5)

        self.case_frame.pack(expand=True, fill=tk.X, pady=5, padx=5)
        self.associate_frame.pack(expand=True, fill=tk.X, pady=5, padx=5)

        self.a: list[tk.IntVar] = []
        self.a.append(tk.IntVar(value=0))

        self.stop_thread_event = threading.Event()
        threading.Thread(target=self.update_stat_panel, daemon=True).start()

    def update_stat_panel(self) -> None:
        fm = FileManager()
        row: int = 0

        previous_associate_data: dict[str, int] = {}
        previous_data_version: int = 0

        self.asc_count.set(fm.get_asc_count())
        self.tl_aot_count.set(fm.get_tl_count() + fm.get_aot_count())
        self.ds_count.set(fm.get_ds_count())
        self.aotp_count.set(fm.get_aotp_count())
        self.all_count.set(fm.get_gathered_count())

        while not self.stop_thread_event.is_set():
            associate_data = fm.get_associate_counts()

            if associate_data != previous_associate_data:
                previous_associate_data = associate_data
                associates_to_remove = []
                for associate in self.associate_lbl_map.keys():
                    if associate not in associate_data.keys():
                        associates_to_remove.append(associate)

                for associate in associates_to_remove:
                    labels: list[tk.Label] | None = self.associate_lbl_map.get(
                        associate
                    )
                    if labels:
                        labels[0].destroy()
                        labels[1].destroy()
                    self.associate_lbl_map.pop(associate)
                    row -= 1

                for associate, count in associate_data.items():
                    if associate not in self.associate_lbl_map.keys():
                        associate_label: tk.Label = tk.Label(
                            self.associate_frame, text=associate, bg="white"
                        )
                        count_label: tk.Label = tk.Label(
                            self.associate_frame, text=count, bg="white"
                        )

                        associate_label.grid(row=row, column=0, sticky="w")
                        count_label.grid(row=row, column=1, sticky="e", padx=5)

                        self.associate_lbl_map[associate] = [
                            associate_label,
                            count_label,
                        ]

                        row += 1
                        continue
                    self.associate_lbl_map[associate][1].configure(text=count)

            data_version: int = fm.cur.execute("PRAGMA data_version").fetchone()[0]
            if data_version != previous_data_version:
                self.asc_count.set(fm.get_asc_count())
                self.tl_aot_count.set(fm.get_tl_count() + fm.get_aot_count())
                self.ds_count.set(fm.get_ds_count())
                self.aotp_count.set(fm.get_aotp_count())
                self.all_count.set(fm.get_gathered_count())

        fm.con.close()

    def stop_stat_pane(self) -> None:
        self.stop_thread_event.set()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.fp: FileProcessor = FileProcessor()

        self.geometry("445x410")
        self.minsize(445, 410)
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
            pady=5,
            command=self.fp.gather_all_files,
        )
        self.gather_asc_button: tk.Button = tk.Button(
            master=self.control_frame,
            text="Gather All ASC",
            padx=20,
            pady=5,
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
