from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
import tkinter as tk
import subprocess
import os
import threading

from file_manager import FileManager, NCError, NCFile, ErrorType


@dataclass
class GUIError:
    nc_file: NCFile
    nc_error: NCError
    line_start: int = 0
    line_end: int = 0

    def __eq__(self, other):
        return (
            self.file == other.file
            and self.location == other.location
            and self.issue_type == other.issue_type
        )


@dataclass
class GUIDuplicate:
    nc_file: NCFile
    line_start: int = 0
    line_end: int = 0


class InfoWidget(tk.Frame):
    def __init__(self, master=None) -> None:
        super().__init__(master)
        self.text = tk.Text(self, wrap="none", state="normal", font="Arial 11")

        self.stop_thread_event = threading.Event()
        threading.Thread(target=self.update_info_widget, daemon=True).start()

        self.gui_errors: list[GUIError] = []
        self.duplicates: list[GUIDuplicate] = []

        self.text["state"] = "disabled"

        self.ys = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text["yscrollcommand"] = self.ys.set

        self.xs = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text["xscrollcommand"] = self.xs.set

        self.text.grid(row=0, column=0, sticky="nsew")
        self.ys.grid(row=0, column=1, sticky="ns")
        self.xs.grid(row=1, column=0, sticky="ew")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        if os.name == "nt":
            self.text.bind("<Button-3>", self.on_right_click)
        else:
            self.text.bind("<Button-2>", self.on_right_click)

    def get_error_by_pos(self, x, y) -> GUIError | None:
        line: int = int(self.text.index(f"@{x},{y}").split(".")[0])

        for gui_error in self.gui_errors:
            if line >= gui_error.line_start and line < gui_error.line_end:
                return gui_error
        return None

    def get_duplicate_by_pos(self, x, y) -> GUIDuplicate | None:
        line: int = int(self.text.index(f"@{x},{y}").split(".")[0])

        for gui_duplicate in self.duplicates:
            if line >= gui_duplicate.line_start and line < gui_duplicate.line_end:
                return gui_duplicate
        return None

    def render(self) -> None:
        new_text = tk.Text(
            self, wrap="none", font="Arial 11", state="disabled", cursor="arrow"
        )
        if os.name == "nt":
            new_text.bind("<Button-3>", self.on_right_click)
        else:
            new_text.bind("<Button-2>", self.on_right_click)

        new_text.tag_configure("spacer", font="Arial 3")
        new_text.tag_configure("spacer2", font="Arial 2")
        new_text.tag_configure(
            "error",
            background="#F7B0B0",
            selectforeground="white",
            selectbackground="blue",
        )
        new_text.tag_configure(
            "warning",
            background="#F7CCB0",
            selectforeground="white",
            selectbackground="blue",
        )
        new_text.tag_configure(
            "issue_message",
            font="Arial 11 bold",
            selectforeground="white",
            selectbackground="blue",
        )

        self.ys.configure(command=new_text.yview)
        new_text["yscrollcommand"] = self.ys.set

        self.xs.configure(command=new_text.xview)
        new_text["xscrollcommand"] = self.xs.set

        new_text["state"] = "normal"

        for gui_error in self.gui_errors:
            gui_error.line_start = int(new_text.index("end-1l").split(".")[0])
            new_text.insert("end", "\n", ("error", "spacer2"))
            new_text.insert(
                "end",
                f" {' '.join(gui_error.nc_error.error_type.name.split('_')).title()} Error: {gui_error.nc_error.error_msg}\n",
                (
                    "error",
                    "issue_message",
                ),
            )
            new_text.insert(
                "end", f" File: {gui_error.nc_file.path.name} \n", ("error",)
            )
            new_text.insert(
                "end", f" Location: {gui_error.nc_file.path.resolve()} \n", ("error",)
            )
            new_text.insert("end", "\n", ("error", "spacer2"))
            gui_error.line_end = int(new_text.index("end-1l").split(".")[0])
            new_text.insert("end", "\n", ("spacer"))

        for duplicate in self.duplicates:
            duplicate.line_start = int(new_text.index("end-1l").split(".")[0])
            new_text.insert("end", "\n", ("warning", "spacer2"))
            new_text.insert(
                "end",
                " Warning: Duplicate PRG\n",
                (
                    "warning",
                    "issue_message",
                ),
            )
            new_text.insert(
                "end", f" File: {duplicate.nc_file.path.name} \n", ("warning",)
            )
            new_text.insert(
                "end", f" Location: {duplicate.nc_file.path.resolve()} \n", ("warning",)
            )
            new_text.insert("end", "\n", ("warning", "spacer2"))
            duplicate.line_end = int(new_text.index("end-1l").split(".")[0])
            new_text.insert("end", "\n", ("spacer"))
        new_text.insert("end", "\n", ("spacer"))
        new_text["state"] = "disabled"

        self.text.destroy()
        self.text = new_text
        self.text.grid(column=0, row=0, sticky="nsew")

    def update_info_widget(self) -> None:
        fm: FileManager = FileManager()
        previous_data_value: int = 0
        while not self.stop_thread_event.is_set():
            data_version = fm.cur.execute("PRAGMA data_version").fetchone()
            if data_version != previous_data_value:
                previous_data_value = data_version
                self.gui_errors.clear()
                self.duplicates.clear()

                results = fm.cur.execute(
                    "SELECT nc_file_path, nc_file_modified_time, error_type, error_msg FROM nc_files JOIN errors USING (nc_file_id)"
                )
                for row in results:
                    nc_file: NCFile = NCFile(Path(row[0]), row[1])
                    nc_error: NCError = NCError(ErrorType(row[2]), row[3])
                    self.gui_errors.append(GUIError(nc_file, nc_error))

                for duplicate in fm.get_duplicates():
                    self.duplicates.append(GUIDuplicate(duplicate))

                self.render()
        fm.con.close()

    def close_connection(self) -> None:
        self.stop_thread_event.set()

    def on_right_click(self, event) -> None:
        clicked_gui_error: GUIError | None = self.get_error_by_pos(event.x, event.y)
        clicked_gui_duplicate: GUIDuplicate | None = self.get_duplicate_by_pos(
            event.x, event.y
        )

        rightClickMenu = tk.Menu(self, tearoff=False)

        if clicked_gui_error:
            rightClickMenu.add_command(
                label="Open File Location",
                command=lambda: (
                    self.open_file_location(clicked_gui_error.nc_file.path)
                ),
            )
            rightClickMenu.tk_popup(event.x_root, event.y_root)

        if clicked_gui_duplicate:
            rightClickMenu.add_command(
                label="Open File Location",
                command=lambda: (
                    self.open_file_location(clicked_gui_duplicate.nc_file.path)
                ),
            )
            rightClickMenu.tk_popup(event.x_root, event.y_root)

    def open_file_location(self, file_path: Path) -> None:
        if file_path.exists():
            if os.name == "nt":
                subprocess.Popen(f"explorer /select, {file_path}")
            else:
                subprocess.call(["open", "-R", str(file_path.resolve())])


def main() -> None:
    root = tk.Tk()
    info = InfoWidget(root)
    info.pack(expand=True, fill=tk.BOTH)
    root.mainloop()


if __name__ == "__main__":
    main()
