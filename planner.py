#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "urwid>=2.6.0",
# ]
# description = "Job application tracking TUI application"
# authors = ["Generated for standalone execution"]
# ///

"""
Job Application Tracker built with urwid.

A clean, cross-platform TUI application for managing job applications.
Features multi-step job entry, status tracking, and detailed views.
Run with: uv run planner.py
"""

import urwid
import sys
import signal
from typing import List, Optional
from dataclasses import dataclass
import json
import os
from datetime import datetime


@dataclass
class JobApplication:
    """Job application data structure."""

    company: str
    position: str
    date_applied: str
    status: str = "Applied"
    link: str = ""
    notes: str = ""

    @staticmethod
    def get_status_options():
        """Get available status options in order."""
        return ["Applied", "Interview", "Offer", "Rejected", "Withdrawn"]

    @staticmethod
    def get_status_emoji(status: str) -> str:
        """Get emoji for status."""
        emoji_map = {
            "Applied": "📋",
            "Interview": "🎯",
            "Offer": "✅",
            "Rejected": "❌",
            "Withdrawn": "🚫",
        }
        return emoji_map.get(status, "📋")


class JobTrackerApp:
    """Job application tracking system."""

    PALETTE = [
        ("header", "white", "dark blue", "bold"),
        ("footer", "white", "dark red"),
        ("body", "light gray", "black"),
        ("applied", "light blue", "black"),
        ("interview", "yellow", "black"),
        ("offer", "light green", "black"),
        ("rejected", "light red", "black"),
        ("withdrawn", "dark red", "black"),
        ("focus", "white", "dark gray", "bold"),
        ("focus_applied", "light blue", "dark gray", "bold"),
        ("focus_interview", "yellow", "dark gray", "bold"),
        ("focus_offer", "light green", "dark gray", "bold"),
        ("focus_rejected", "light red", "dark gray", "bold"),
        ("focus_withdrawn", "dark red", "dark gray", "bold"),
    ]

    def __init__(self):
        self.jobs: List[JobApplication] = []
        self.job_widgets = []
        self.main_loop: Optional[urwid.MainLoop] = None
        self.job_file = os.path.expanduser("~/.job_tracker.json")

        # Sorting state - simplified to two modes
        self.sort_by_status = False  # False = date only, True = status+date
        self.sort_ascending = False  # Default to descending (newest first)

        # Status priority for sorting (lower number = higher priority)
        self.status_priority = {
            "Interview": 1,
            "Applied": 2,
            "Offer": 3,
            "Rejected": 4,
            "Withdrawn": 5,
        }

        # Migration: check for old task file
        old_task_file = os.path.expanduser("~/.planner_tasks.json")
        if os.path.exists(old_task_file) and not os.path.exists(self.job_file):
            self._migrate_from_tasks(old_task_file)

        # Load saved jobs
        self.load_jobs()

        # Apply initial sorting
        self._sort_jobs()

        # Setup signal handling
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Build UI
        self.ui = self._build_ui()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.save_jobs()
        sys.exit(0)

    def _migrate_from_tasks(self, old_file):
        """Migrate old task data to job format."""
        try:
            with open(old_file, "r") as f:
                old_data = json.load(f)

            # Convert tasks to basic job applications
            for item in old_data:
                if isinstance(item, dict) and "text" in item:
                    # Extract company and position from text if possible
                    text = item["text"]
                    company = "Unknown Company"
                    position = text

                    # Simple heuristic: if text contains " - ", split it
                    if " - " in text:
                        parts = text.split(" - ", 1)
                        company = parts[0]
                        position = parts[1]

                    job = JobApplication(
                        company=company,
                        position=position,
                        date_applied=datetime.now().strftime("%Y-%m-%d"),
                        status="Rejected"
                        if item.get("completed", False)
                        else "Applied",
                    )
                    self.jobs.append(job)

            # Save migrated data
            self.save_jobs()

            # Optionally rename old file to prevent re-migration
            os.rename(old_file, old_file + ".bak")

        except (json.JSONDecodeError, KeyError, IOError):
            pass  # Migration failed, start fresh

    def load_jobs(self):
        """Load jobs and sort preferences from file if it exists."""
        try:
            if os.path.exists(self.job_file):
                with open(self.job_file, "r") as f:
                    data = json.load(f)
                    
                    # Load sort preferences if they exist
                    if isinstance(data, dict) and "jobs" in data:
                        # New format with metadata
                        self.sort_by_status = data.get("sort_by_status", False)
                        self.sort_ascending = data.get("sort_ascending", False)
                        jobs_data = data["jobs"]
                    else:
                        # Legacy format - just jobs array
                        jobs_data = data
                    
                    self.jobs = []
                    for item in jobs_data:
                        job = JobApplication(
                            company=item["company"],
                            position=item["position"],
                            date_applied=item["date_applied"],
                            status=item.get("status", "Applied"),
                            link=item.get("link", ""),
                            notes=item.get("notes", ""),
                        )
                        self.jobs.append(job)
        except (json.JSONDecodeError, KeyError, IOError):
            self.jobs = []

    def save_jobs(self):
        """Save jobs and sort preferences to file."""
        try:
            # Save in new format with metadata
            data = {
                "sort_by_status": self.sort_by_status,
                "sort_ascending": self.sort_ascending,
                "jobs": []
            }
            
            for job in self.jobs:
                data["jobs"].append(
                    {
                        "company": job.company,
                        "position": job.position,
                        "date_applied": job.date_applied,
                        "status": job.status,
                        "link": job.link,
                        "notes": job.notes,
                    }
                )
            with open(self.job_file, "w") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass  # Fail silently if we can't save

    def _get_sort_display_name(self):
        """Get user-friendly sort mode name."""
        return "Status+Date" if self.sort_by_status else "Date"
    
    def _build_ui(self):
        """Build the main user interface."""
        # Header with sort information and storage location
        sort_direction = "↑" if self.sort_ascending else "↓"
        sort_name = self._get_sort_display_name()
        job_count = len(self.jobs)
        storage_path = self.job_file.replace(os.path.expanduser("~"), "~")  # Show ~ instead of full path
        header_text = f" Job Tracker - Sort: {sort_name} {sort_direction} - {job_count} apps - Saved: {storage_path} "
        
        self.header_widget = urwid.AttrMap(
            urwid.Text(header_text, align="center"),
            "header"
        )

        # Job list
        self.job_list = urwid.SimpleFocusListWalker([])
        self._refresh_job_list()

        listbox = urwid.ListBox(self.job_list)

        # Footer with instructions including sorting
        footer_text = " [a]dd [d]el [s]tatus [v]iew | [t]oggle sort [o]rder | [j/k]nav [q]uit "
        self.footer_widget = urwid.AttrMap(urwid.Text(footer_text, align="center"), "footer")

        # Main frame
        return urwid.Frame(
            body=urwid.AttrMap(listbox, "body"), 
            header=self.header_widget, 
            footer=self.footer_widget
        )

    def _update_header(self):
        """Update header with current sort information and storage location."""
        sort_direction = "↑" if self.sort_ascending else "↓"
        sort_name = self._get_sort_display_name()
        job_count = len(self.jobs)
        storage_path = self.job_file.replace(os.path.expanduser("~"), "~")  # Show ~ instead of full path
        header_text = f" Job Tracker - Sort: {sort_name} {sort_direction} - {job_count} apps - Saved: {storage_path} "
        
        if hasattr(self, 'header_widget'):
            self.header_widget.original_widget.set_text(header_text)

    def _refresh_job_list(self):
        """Refresh the job list display."""
        self.job_list.clear()

        # Update header with current info
        self._update_header()

        if not self.jobs:
            self.job_list.append(
                urwid.Text(
                    ("body", "No job applications yet. Press [a] to add one."),
                    align="center",
                )
            )
            return

        for i, job in enumerate(self.jobs):
            emoji = JobApplication.get_status_emoji(job.status)
            status_text = f"[{job.status.upper()}]"
            display_text = f" {emoji} {status_text} {job.company} - {job.position} ({job.date_applied})"

            # Get color scheme based on status
            status_lower = job.status.lower()
            color_attr = (
                status_lower
                if status_lower
                in ["applied", "interview", "offer", "rejected", "withdrawn"]
                else "body"
            )

            # Check if focus attribute exists in palette
            palette_names = [item[0] for item in self.PALETTE]
            focus_attr = (
                f"focus_{status_lower}"
                if f"focus_{status_lower}" in palette_names
                else "focus"
            )

            # Create text widget with full-width highlighting using Columns
            text_widget = urwid.Text(display_text)
            # Use Columns with one column to ensure full width coverage
            columns_widget = urwid.Columns([text_widget])
            widget = urwid.AttrMap(
                columns_widget,
                color_attr,
                focus_map=focus_attr
            )

            self.job_list.append(widget)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string safely with fallback."""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            # Fallback for invalid dates - put them at the end
            return datetime.min if self.sort_ascending else datetime.max

    def _sort_jobs(self):
        """Apply current sorting mode to jobs list."""
        if self.sort_by_status:
            self._sort_by_status_date()
        else:
            self._sort_by_date()

    def _sort_by_date(self):
        """Sort jobs by application date."""
        self.jobs.sort(
            key=lambda job: self._parse_date(job.date_applied),
            reverse=not self.sort_ascending,
        )

    def _sort_by_status_date(self):
        """Sort jobs by status priority, then by date within each status."""

        def sort_key(job):
            priority = self.status_priority.get(job.status, 999)
            date = self._parse_date(job.date_applied)
            # For status+date, always sort dates newest first within status groups
            return (priority, -date.timestamp())

        self.jobs.sort(key=sort_key)

    def _toggle_sort_mode(self):
        """Toggle between date-only and status+date sorting."""
        self.sort_by_status = not self.sort_by_status
        self._apply_sort_and_refresh()

    def _toggle_sort_direction(self):
        """Toggle between ascending and descending sort."""
        self.sort_ascending = not self.sort_ascending
        self._apply_sort_and_refresh()

    def _apply_sort_and_refresh(self):
        """Apply current sort and refresh display, preserving focus if possible."""
        # Try to preserve current job focus
        focused_job = None
        try:
            if self.jobs and len(self.job_list) > 0:
                focus_pos = self.job_list.focus
                if 0 <= focus_pos < len(self.jobs):
                    focused_job = self.jobs[focus_pos]
        except (ValueError, TypeError, AttributeError):
            pass

        # Apply sorting
        self._sort_jobs()

        # Refresh display
        self._refresh_job_list()

        # Try to restore focus to the same job
        if focused_job and self.jobs:
            try:
                new_index = self.jobs.index(focused_job)
                if 0 <= new_index < len(self.job_list):
                    self.job_list.set_focus(new_index)
            except (ValueError, AttributeError):
                # Job not found or focus failed, default to top
                if len(self.job_list) > 0:
                    self.job_list.set_focus(0)

    def _add_job(self):
        """Show multi-step dialog to add a new job application."""
        self._current_job_data = {}
        self._job_entry_step = 0
        self._start_job_entry()

    def _start_job_entry(self):
        """Start the multi-step job entry process."""
        steps = [
            ("Company Name", "Enter company name:", "company", True),
            ("Job Position", "Enter job position/title:", "position", True),
            ("Application Link", "Enter job posting URL (optional):", "link", False),
            ("Notes", "Enter any notes (optional):", "notes", False),
            (
                "Application Date",
                f"Date applied ({datetime.now().strftime('%Y-%m-%d')}):",
                "date_applied",
                False,
            ),
        ]

        if self._job_entry_step < len(steps):
            title, prompt, field, required = steps[self._job_entry_step]

            # Pre-fill date field with current date
            default_value = (
                datetime.now().strftime("%Y-%m-%d") if field == "date_applied" else ""
            )

            self._show_job_input_dialog(title, prompt, field, required, default_value)
        else:
            self._finalize_job_entry()

    def _show_job_input_dialog(self, title, prompt, field, required, default_value=""):
        """Show input dialog for job entry step."""
        edit = urwid.Edit(f"{prompt} ", default_value)

        def handle_input(key):
            if key == "enter":
                value = edit.get_edit_text().strip()
                if required and not value:
                    # Show error and stay in dialog
                    return

                self._current_job_data[field] = value
                self._job_entry_step += 1
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
                self._start_job_entry()  # Move to next step

            elif key == "esc":
                # Cancel job entry
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            else:
                return key

        # Build dialog content
        step_info = f"Step {self._job_entry_step + 1} of 5"
        required_text = " (Required)" if required else " (Optional)"

        dialog_content = urwid.Pile(
            [
                urwid.Text(("header", f"{title}{required_text}"), align="center"),
                urwid.Text(("body", step_info), align="center"),
                urwid.Divider(),
                edit,
                urwid.Divider(),
                urwid.Text("Press Enter to continue, Esc to cancel", align="center"),
            ]
        )

        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )

        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=60, valign="middle", height=9
        )

        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_input
        self.main_loop.widget = overlay

    def _finalize_job_entry(self):
        """Create and save the new job application."""
        job = JobApplication(
            company=self._current_job_data.get("company", ""),
            position=self._current_job_data.get("position", ""),
            date_applied=self._current_job_data.get(
                "date_applied", datetime.now().strftime("%Y-%m-%d")
            ),
            link=self._current_job_data.get("link", ""),
            notes=self._current_job_data.get("notes", ""),
            status="Applied",
        )

        self.jobs.append(job)
        
        # Apply sorting and refresh
        self._apply_sort_and_refresh()
        self.save_jobs()
        
        # Try to focus on the newly added job
        try:
            new_index = self.jobs.index(job)
            if 0 <= new_index < len(self.job_list):
                self.job_list.set_focus(new_index)
        except (ValueError, AttributeError):
            # Fallback to top
            if len(self.job_list) > 0:
                self.job_list.set_focus(0)

    def _show_input_dialog(self, title, prompt, callback):
        """Show an input dialog."""
        edit = urwid.Edit(f"{prompt} ")

        def handle_input(key):
            if key == "enter":
                callback(edit.get_edit_text())
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            elif key == "esc":
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            else:
                # Let other keys pass through to the edit widget
                return key

        dialog_content = urwid.Pile(
            [
                urwid.Text(("header", title), align="center"),
                urwid.Divider(),
                edit,
                urwid.Divider(),
                urwid.Text("Press Enter to confirm, Esc to cancel", align="center"),
            ]
        )

        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )

        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=50, valign="middle", height=7
        )

        # Temporarily replace the unhandled input handler
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_input
        self.main_loop.widget = overlay

    def _delete_current_job(self):
        """Show confirmation dialog before deleting the currently selected job."""
        if not self.jobs:
            return

        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(self.jobs):
                job = self.jobs[focus_pos]
                self._show_delete_confirmation(job, focus_pos)
        except (ValueError, TypeError):
            pass
    
    def _show_delete_confirmation(self, job, focus_pos):
        """Show confirmation dialog for job deletion."""
        def handle_input(key):
            if key.lower() == 'y':
                # Confirm deletion
                del self.jobs[focus_pos]
                self._refresh_job_list()
                self.save_jobs()
                
                # Adjust focus position
                if focus_pos >= len(self.jobs) and len(self.jobs) > 0:
                    self.job_list.set_focus(len(self.jobs) - 1)
                    
                # Close dialog
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
                
            elif key.lower() == 'n' or key == 'esc':
                # Cancel deletion
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            else:
                return key
        
        # Build confirmation dialog
        job_info = f"{job.company} - {job.position}"
        dialog_content = urwid.Pile([
            urwid.Text(('header', 'Delete Job Application?'), align='center'),
            urwid.Divider(),
            urwid.Text(f"Company: {job.company}", align='center'),
            urwid.Text(f"Position: {job.position}", align='center'),
            urwid.Text(f"Status: {job.status}", align='center'),
            urwid.Divider(),
            urwid.Text(('focus', 'Are you sure you want to delete this job?'), align='center'),
            urwid.Divider(),
            urwid.Text("[Y]es to delete, [N]o to cancel, [Esc] to cancel", align='center')
        ])
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)),
                'body'
            )
        )
        
        overlay = urwid.Overlay(
            dialog, self.ui, align='center', width=60,
            valign='middle', height=12
        )
        
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_input
        self.main_loop.widget = overlay

    def _cycle_job_status(self):
        """Cycle through status options for current job."""
        if not self.jobs:
            return

        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(self.jobs):
                current_job = self.jobs[focus_pos]
                status_options = JobApplication.get_status_options()

                try:
                    current_index = status_options.index(current_job.status)
                    next_index = (current_index + 1) % len(status_options)
                except ValueError:
                    next_index = 0

                current_job.status = status_options[next_index]
                self._refresh_job_list()
                self.save_jobs()
                # Restore focus to same position
                self.job_list.set_focus(focus_pos)
        except (ValueError, TypeError):
            pass

    def _move_focus(self, direction):
        """Move focus up or down in the job list."""
        if not self.jobs:
            return

        try:
            current_pos = self.job_list.focus
            new_pos = current_pos + direction

            # Clamp to valid range
            if new_pos < 0:
                new_pos = 0
            elif new_pos >= len(self.job_list):
                new_pos = len(self.job_list) - 1

            self.job_list.set_focus(new_pos)
        except (ValueError, TypeError):
            pass

    def _move_to_top(self):
        """Move focus to the first job."""
        if self.jobs:
            self.job_list.set_focus(0)

    def _move_to_bottom(self):
        """Move focus to the last job."""
        if self.jobs:
            self.job_list.set_focus(len(self.job_list) - 1)

    def _view_job_details(self):
        """Show detailed view of current job application."""
        if not self.jobs:
            return

        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(self.jobs):
                job = self.jobs[focus_pos]
                self._show_job_detail_dialog(job)
        except (ValueError, TypeError):
            pass

    def _show_job_detail_dialog(self, job):
        """Show detailed information dialog for a job."""
        emoji = JobApplication.get_status_emoji(job.status)

        # Format job details
        details = [
            f"Company: {job.company}",
            f"Position: {job.position}",
            f"Status: {emoji} {job.status}",
            f"Date Applied: {job.date_applied}",
            f"Link: {job.link if job.link else 'None'}",
            f"Notes: {job.notes if job.notes else 'None'}",
        ]

        content_widgets = [
            urwid.Text(("header", f"Job Application Details"), align="center")
        ]
        content_widgets.append(urwid.Divider())

        for detail in details:
            content_widgets.append(urwid.Text(detail))

        content_widgets.append(urwid.Divider())
        content_widgets.append(urwid.Text("Press any key to close", align="center"))

        dialog_content = urwid.Pile(content_widgets)

        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )

        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=70, valign="middle", height=12
        )

        def close_dialog(key):
            self.main_loop.widget = self.ui
            self.main_loop.unhandled_input = old_handler

        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = close_dialog
        self.main_loop.widget = overlay

    def _handle_input(self, key):
        """Handle keyboard input."""
        # Convert key to string and handle special keys safely
        key_str = str(key).lower() if isinstance(key, str) else str(key)
        
        if key_str == "q":
            self.save_jobs()
            raise urwid.ExitMainLoop()
        elif key_str == "a":
            self._add_job()
        elif key_str == "d":
            self._delete_current_job()
        elif key_str == "s":
            self._cycle_job_status()
        elif key_str == "v" or key == "enter":
            self._view_job_details()

        # Sorting controls
        elif key_str == "o":
            self._toggle_sort_direction()
        elif key_str == "t":
            self._toggle_sort_mode()

        # VIM navigation bindings
        elif key_str == "j" or key == "down":
            self._move_focus(1)
        elif key_str == "k" or key == "up":
            self._move_focus(-1)
        elif key_str == "g":
            self._move_to_top()
        elif key == "G":  # Keep original case for uppercase G
            self._move_to_bottom()

        # Return key for other handlers
        return key

    def run(self):
        """Start the application."""
        self.main_loop = urwid.MainLoop(
            self.ui, palette=self.PALETTE, unhandled_input=self._handle_input
        )

        try:
            self.main_loop.run()
        except KeyboardInterrupt:
            self.save_jobs()
        finally:
            self.save_jobs()


def main():
    """Main entry point."""
    try:
        import urwid
    except ImportError:
        print("Error: urwid not found. Install with: uv add urwid")
        sys.exit(1)

    try:
        app = JobTrackerApp()
        app.run()
    except Exception as e:
        print(f"Application error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

