import threading
import tkinter as tk
import os
from pathlib import Path

import info_widget
import file_manager

ROOT_DIR = Path(__file__).resolve().parent

class MenuBar(tk.Menu):
    def __init__(self, master=None):
        super().__init__(master)

        self.file_menu = tk.Menu(self, tearoff=False)
        self.file_menu.add_command(label='   Exit   ')

        self.help_menu = tk.Menu(self, tearoff=False)
        self.help_menu.add_command(label='   View Help   ', command=self.on_help_option)

        self.add_cascade(label='File', menu=self.file_menu)
        self.add_cascade(label='Help', menu=self.help_menu)
    
    def on_help_option(self):
        if os.name == 'nt':
            os.system(f'start {os.path.join(ROOT_DIR, "resources/help/index.html")}')
        elif os.name == 'posix':
            os.system(f'open {os.path.join(ROOT_DIR, "resources/help/index.html")}')

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # self.fm = file_manager.FileManager()
        # self.fm.load(os.path.join(ROOT_DIR, "data.json"))

        self.geometry("445x275")
        self.minsize(445, 275)
        self.iconbitmap(os.path.join(ROOT_DIR, "resources", "icons", "tru-gather.ico"))

        self.title("TruGather")
        # self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.menu_bar = MenuBar(self)

        self.auto_check = tk.BooleanVar()

        self.control_frame = tk.Frame(master=self)
        self.auto_gather_checkbutton = tk.Checkbutton(master=self.control_frame, text="Auto Gather", variable=self.auto_check, onvalue=True, offvalue=False)
        self.gather_prg_button = tk.Button(master=self.control_frame, text="Gather All NC", padx=20, pady=20)
        self.gather_asc_button = tk.Button(master=self.control_frame, text="Gather All ASC", padx=20, pady=20)

        self.info_widget = info_widget.InfoWidget()

        self.auto_gather_checkbutton.pack(side=tk.TOP)
        self.gather_prg_button.pack(fill=tk.X, side=tk.TOP)
        self.gather_asc_button.pack(fill=tk.X, side=tk.TOP)

        self.control_frame.grid(row=0, column=0, sticky='nsew')
        self.info_widget.grid(row=0, column=1, sticky='nsew')

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.config(menu=self.menu_bar)

        # self.stop_event = threading.Event()
        # self.enabled_event = threading.Event()
        # self.auto_gather_thread = threading.Thread(target=self.auto_gather, args=[self.stop_event, self.enabled_event])
        # self.auto_gather_thread.start()

    # def gather_prg(self):
    #     self.fm.copy_all_valid_files()

    # def gather_asc(self):
    #     self.fm.copy_asc_files()

    # def print_value(self):
    #     print(self.auto_check.get())

    # def on_auto_gather_toggle(self):
    #     if(self.enabled_event.is_set()):
    #         self.enabled_event.clear()
    #         self.gather_prg_button.configure(state=tk.NORMAL)
    #         self.gather_asc_button.configure(state=tk.NORMAL)
    #     else:
    #         self.enabled_event.set()
    #         self.gather_prg_button.configure(state=tk.DISABLED)
    #         self.gather_asc_button.configure(state=tk.DISABLED)

    # def on_close(self):
    #     self.stop_event.set()
    #     self.fm.save(os.path.join(ROOT_DIR, "data.json"))
    #     self.destroy()

    # def auto_gather(self, disable_event:threading.Event, enabled_event:threading.Event):
    #     while True:
    #         if self.fm.process():
    #                 self.info_widget.updateErrors(self.fm)
    #         if enabled_event.is_set():
    #             try:
    #                 self.fm.copy_all_valid_files()
    #             except (FileNotFoundError, UnicodeDecodeError, PermissionError, OSError) as e:
    #                 print(e, type(e))

                    
    #         if(disable_event.is_set()):
    #             return False

def main():
  app = App()
  app.mainloop()

if __name__ == "__main__":
   main()