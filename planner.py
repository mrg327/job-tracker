#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "urwid>=2.6.0",
# ]
# description = "Simple task planner TUI application"
# authors = ["Generated for standalone execution"]
# ///

"""
Simple task planner built with urwid.

A clean, cross-platform TUI application for managing tasks.
Run with: uv run planner.py
"""

import urwid
import sys
import signal
from typing import List, Optional
from dataclasses import dataclass
import json
import os


@dataclass
class Task:
    """Simple task data structure."""
    text: str
    completed: bool = False


class PlannerApp:
    """Simple task planner application."""
    
    PALETTE = [
        ('header', 'white', 'dark blue', 'bold'),
        ('footer', 'white', 'dark red'),
        ('body', 'light gray', 'black'),
        ('completed', 'dark green', 'black'),
        ('focus', 'white', 'dark gray', 'bold'),
        ('focus_completed', 'dark green', 'dark gray', 'bold'),
    ]
    
    def __init__(self):
        self.tasks: List[Task] = []
        self.task_widgets = []
        self.main_loop: Optional[urwid.MainLoop] = None
        self.task_file = os.path.expanduser("~/.planner_tasks.json")
        
        # Load saved tasks
        self.load_tasks()
        
        # Setup signal handling
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Build UI
        self.ui = self._build_ui()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.save_tasks()
        sys.exit(0)
    
    def load_tasks(self):
        """Load tasks from file if it exists."""
        try:
            if os.path.exists(self.task_file):
                with open(self.task_file, 'r') as f:
                    data = json.load(f)
                    self.tasks = [Task(item['text'], item['completed']) for item in data]
        except (json.JSONDecodeError, KeyError, IOError):
            self.tasks = []
    
    def save_tasks(self):
        """Save tasks to file."""
        try:
            data = [{'text': task.text, 'completed': task.completed} for task in self.tasks]
            with open(self.task_file, 'w') as f:
                json.dump(data, f)
        except IOError:
            pass  # Fail silently if we can't save
    
    def _build_ui(self):
        """Build the main user interface."""
        # Header
        header = urwid.AttrMap(
            urwid.Text(' Task Planner - Simple TUI for Managing Tasks ', align='center'),
            'header'
        )
        
        # Task list
        self.task_list = urwid.SimpleFocusListWalker([])
        self._refresh_task_list()
        
        listbox = urwid.ListBox(self.task_list)
        
        # Footer with instructions
        footer_text = ' [a]dd  [d]elete  [space]toggle  [j/k,↑↓]navigate  [g/G]top/bottom  [q]uit  [s]ave '
        footer = urwid.AttrMap(urwid.Text(footer_text, align='center'), 'footer')
        
        # Main frame
        return urwid.Frame(
            body=urwid.AttrMap(listbox, 'body'),
            header=header,
            footer=footer
        )
    
    def _refresh_task_list(self):
        """Refresh the task list display."""
        self.task_list.clear()
        
        if not self.tasks:
            self.task_list.append(
                urwid.Text(('body', 'No tasks yet. Press [a] to add one.'), align='center')
            )
            return
        
        for i, task in enumerate(self.tasks):
            checkbox = '☑' if task.completed else '☐'
            text = f" {checkbox} {task.text}"
            
            if task.completed:
                widget = urwid.AttrMap(
                    urwid.Text(('completed', text)),
                    None,
                    focus_map='focus_completed'
                )
            else:
                widget = urwid.AttrMap(
                    urwid.Text(text),
                    None,
                    focus_map='focus'
                )
            
            self.task_list.append(widget)
    
    def _add_task(self):
        """Show dialog to add a new task."""
        def on_done(text):
            if text.strip():
                self.tasks.append(Task(text.strip()))
                self._refresh_task_list()
                self.save_tasks()
                # Set focus to the newly added task
                if len(self.task_list) > 0:
                    self.task_list.set_focus(len(self.task_list) - 1)
        
        self._show_input_dialog("Add Task", "Enter task description:", on_done)
    
    def _show_input_dialog(self, title, prompt, callback):
        """Show an input dialog."""
        edit = urwid.Edit(f"{prompt} ")
        
        def handle_input(key):
            if key == 'enter':
                callback(edit.get_edit_text())
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            elif key == 'esc':
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            else:
                # Let other keys pass through to the edit widget
                return key
            
        dialog_content = urwid.Pile([
            urwid.Text(('header', title), align='center'),
            urwid.Divider(),
            edit,
            urwid.Divider(),
            urwid.Text("Press Enter to confirm, Esc to cancel", align='center')
        ])
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(
                    urwid.Padding(dialog_content, left=2, right=2)
                ),
                'body'
            )
        )
        
        overlay = urwid.Overlay(
            dialog,
            self.ui,
            align='center',
            width=50,
            valign='middle',
            height=7
        )
        
        # Temporarily replace the unhandled input handler
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_input
        self.main_loop.widget = overlay
        
    
    def _delete_current_task(self):
        """Delete the currently selected task."""
        if not self.tasks:
            return
            
        try:
            focus_pos = self.task_list.focus
            if 0 <= focus_pos < len(self.tasks):
                del self.tasks[focus_pos]
                self._refresh_task_list()
                self.save_tasks()
                
                # Adjust focus position
                if focus_pos >= len(self.tasks) and len(self.tasks) > 0:
                    self.task_list.set_focus(len(self.tasks) - 1)
        except (ValueError, TypeError):
            pass
    
    def _toggle_current_task(self):
        """Toggle completion status of current task."""
        if not self.tasks:
            return
            
        try:
            focus_pos = self.task_list.focus
            if 0 <= focus_pos < len(self.tasks):
                self.tasks[focus_pos].completed = not self.tasks[focus_pos].completed
                self._refresh_task_list()
                self.save_tasks()
                # Restore focus to same position
                self.task_list.set_focus(focus_pos)
        except (ValueError, TypeError):
            pass
    
    def _move_focus(self, direction):
        """Move focus up or down in the task list."""
        if not self.tasks:
            return
            
        try:
            current_pos = self.task_list.focus
            new_pos = current_pos + direction
            
            # Clamp to valid range
            if new_pos < 0:
                new_pos = 0
            elif new_pos >= len(self.task_list):
                new_pos = len(self.task_list) - 1
                
            self.task_list.set_focus(new_pos)
        except (ValueError, TypeError):
            pass
    
    def _move_to_top(self):
        """Move focus to the first task."""
        if self.tasks:
            self.task_list.set_focus(0)
    
    def _move_to_bottom(self):
        """Move focus to the last task."""
        if self.tasks:
            self.task_list.set_focus(len(self.task_list) - 1)
    
    def _handle_input(self, key):
        """Handle keyboard input."""
        if key.lower() == 'q':
            self.save_tasks()
            raise urwid.ExitMainLoop()
        elif key.lower() == 'a':
            self._add_task()
        elif key.lower() == 'd':
            self._delete_current_task()
        elif key == ' ':  # Space key
            self._toggle_current_task()
        elif key.lower() == 's':
            self.save_tasks()
        
        # VIM navigation bindings
        elif key.lower() == 'j' or key == 'down':
            self._move_focus(1)
        elif key.lower() == 'k' or key == 'up':
            self._move_focus(-1)
        elif key.lower() == 'g':
            self._move_to_top()
        elif key.lower() == 'G':
            self._move_to_bottom()
        
        # Return key for other handlers
        return key
    
    def run(self):
        """Start the application."""
        self.main_loop = urwid.MainLoop(
            self.ui,
            palette=self.PALETTE,
            unhandled_input=self._handle_input
        )
        
        try:
            self.main_loop.run()
        except KeyboardInterrupt:
            self.save_tasks()
        finally:
            self.save_tasks()


def main():
    """Main entry point."""
    try:
        import urwid
    except ImportError:
        print("Error: urwid not found. Install with: uv add urwid")
        sys.exit(1)
    
    try:
        app = PlannerApp()
        app.run()
    except Exception as e:
        print(f"Application error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()