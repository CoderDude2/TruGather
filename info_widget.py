import os
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from file_manager import FileManager, NCError, NCFile
import subprocess

@dataclass
class GUIError:
    nc_file: NCFile
    nc_error: NCError
    line_start:int = 0
    line_end:int = 0

    def __eq__(self, other):
        return self.file == other.file and self.location == other.location and self.issue_type == other.issue_type

class InfoWidget(tk.Frame):
    def __init__(self, master=None) -> None:
        super().__init__(master)
        self.text = tk.Text(self, wrap='none', state='normal', font="Arial 11")

        self.gui_errors: list[GUIError] = []
        
        self.text['state'] = 'disabled'

        self.ys = ttk.Scrollbar(self, orient='vertical', command=self.text.yview)
        self.text['yscrollcommand'] = self.ys.set

        self.xs = ttk.Scrollbar(self, orient='horizontal', command=self.text.xview)
        self.text['xscrollcommand'] = self.xs.set

        self.text.grid(column=0, row=0, sticky='nsew')
        self.ys.grid(column=1, row=0, sticky='ns')
        self.xs.grid(column=0, row=1, sticky='ew')

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        if os.name == 'nt':
            self.text.bind("<Button-3>", self.on_right_click)
        else:
            self.text.bind("<Button-2>", self.on_right_click)

    def get_error_by_pos(self, x, y) -> GUIError|None:
        line = int(self.text.index(f'@{x},{y}').split('.')[0])

        for issue in self.issue_list:
            if line >= issue.line_start and line < issue.line_end:
                return issue
        return None
        
    def render(self):
        new_text = tk.Text(self,wrap='none', font="Arial 11", state='disabled', cursor='arrow')
        if os.name == 'nt':
            new_text.bind("<Button-3>", self.on_right_click)
        else:
            new_text.bind("<Button-2>", self.on_right_click)

        new_text.tag_configure('spacer', font='Arial 3')
        new_text.tag_configure('spacer2', font='Arial 2')
        new_text.tag_configure('error', background='#F7B0B0', selectforeground="white", selectbackground="blue")
        new_text.tag_configure('warning', background='#F7CCB0', selectforeground="white", selectbackground="blue")
        new_text.tag_configure('issue_message', font="Arial 11 bold", selectforeground="white", selectbackground="blue")

        self.ys.configure(command=new_text.yview)
        new_text['yscrollcommand'] = self.ys.set

        self.xs.configure(command=new_text.xview)
        new_text['xscrollcommand'] = self.xs.set

        new_text['state'] = 'normal'
        for i in self.issue_list:
            match i.issue_type:
                case IssueType.SUBPROGRAM_0_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: $0 Subprogram Missing\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.SUBPROGRAM_1_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: $1 Subprogram Missing\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.SUBPROGRAM_2_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: $2 Subprogram Missing\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.INVALID_NAME_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: Invalid Name\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.PART_LENGTH_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: Part-Length does not equal Cut-off\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.MISSING_UG_VALUES_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: Missing one or more UG values\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.INTERNAL_NAME_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    new_text.insert('end'," Error: File name and internal name don't match\n", ('error', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('error',))
                    new_text.insert('end', f' Location: {i.location} \n', ('error',))
                    new_text.insert('end', '\n', ('error', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
                case IssueType.DUPLICATE_PRG_ERR:
                    i.line_start = int(new_text.index('end-1l').split('.')[0])
                    new_text.insert('end', '\n', ('warning', 'spacer2'))
                    new_text.insert('end'," Warning: Duplicate PRG\n", ('warning', 'issue_message',))
                    new_text.insert('end', f' File: {i.file} \n', ('warning',))
                    new_text.insert('end', f' Location: {i.location} \n', ('warning',))
                    new_text.insert('end', '\n', ('warning', 'spacer2'))
                    i.line_end = int(new_text.index('end-1l').split('.')[0])
            new_text.insert('end', '\n', ('spacer'))
        new_text['state'] = 'disabled'

        self.text.destroy()
        self.text = new_text
        new_text.grid(column=0, row=0, sticky='nsew')
        self.grid(row=0, column=1, sticky='nsew')
    
    def updateErrors(self, fm:FileManager):
        self.issue_list = []
        for entry in fm.processed_files:
            if len(fm.processed_files[entry]['errors']) > 0:
                for error in fm.processed_files[entry]['errors']:
                    gui_error = GUIError(entry, fm.processed_files[entry]['location'], error)
                    if gui_error not in self.issue_list:
                        self.issue_list.append(gui_error)
            if len(fm.processed_files[entry]['duplicates']) > 0:
                for duplicate in fm.processed_files[entry]['duplicates']:
                    for error in duplicate['errors']:
                        gui_error = GUIError(entry, duplicate['location'], error)
                        if gui_error not in self.issue_list:
                            self.issue_list.append(gui_error)
        self.render()

    def on_right_click(self, event):
        clicked_gui_error:GUIError = self.get_issue_by_pos(event.x, event.y)

        rightClickMenu = tk.Menu(self, tearoff=False)
        if clicked_gui_error:
            rightClickMenu.add_command(label="Open File Location", command=lambda:(self.open_file_location(clicked_gui_error.location)))
        rightClickMenu.tk_popup(event.x_root, event.y_root)
    
    def open_file_location(self, path):
        if path:
            if os.name == 'nt':
                subprocess.Popen(f'explorer {path}')
            else:
                subprocess.call("open", "-R", path)