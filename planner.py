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
from datetime import datetime, timedelta


@dataclass
class JobApplication:
    """Job application data structure."""

    company: str
    position: str
    date_applied: str
    status: str = "Applied"
    link: str = ""
    notes: str = ""
    
    # Interview tracking
    interview_date: str = ""  # Format: YYYY-MM-DD
    interview_time: str = ""  # Format: HH:MM
    interview_type: str = ""  # e.g., "Phone", "Video", "In-person"
    
    # Follow-up tracking
    last_contact: str = ""    # Format: YYYY-MM-DD
    next_followup: str = ""   # Format: YYYY-MM-DD
    
    # Salary information
    salary_min: str = ""      # Minimum salary range
    salary_max: str = ""      # Maximum salary range
    salary_offered: str = ""  # Actual offer amount
    
    # Contact information
    recruiter_name: str = ""
    recruiter_email: str = ""
    recruiter_phone: str = ""

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

    def has_upcoming_interview(self, days_ahead: int = 7) -> bool:
        """Check if job has an interview within the next N days."""
        if not self.interview_date:
            return False
        try:
            interview_dt = datetime.strptime(self.interview_date, "%Y-%m-%d")
            today = datetime.now()
            return today <= interview_dt <= today + timedelta(days=days_ahead)
        except ValueError:
            return False
    
    def has_overdue_followup(self) -> bool:
        """Check if job has an overdue follow-up."""
        if not self.next_followup:
            return False
        try:
            followup_dt = datetime.strptime(self.next_followup, "%Y-%m-%d")
            return datetime.now().date() > followup_dt.date()
        except ValueError:
            return False
            
    def needs_followup_soon(self, days_ahead: int = 3) -> bool:
        """Check if job needs follow-up within the next N days."""
        if not self.next_followup:
            return False
        try:
            followup_dt = datetime.strptime(self.next_followup, "%Y-%m-%d")
            today = datetime.now()
            return today <= followup_dt <= today + timedelta(days=days_ahead)
        except ValueError:
            return False

    def get_status_indicator(self) -> str:
        """Get enhanced status indicator with urgency flags."""
        base_emoji = self.get_status_emoji(self.status)
        
        # Add urgency indicators
        if self.has_upcoming_interview():
            return f"⏰{base_emoji}"  # Clock for upcoming interview
        elif self.has_overdue_followup():
            return f"🔴{base_emoji}"  # Red dot for overdue
        elif self.needs_followup_soon():
            return f"🟡{base_emoji}"  # Yellow dot for soon
        else:
            return base_emoji

    def needs_attention(self) -> bool:
        """Check if this job needs immediate attention."""
        return (self.has_upcoming_interview() or 
                self.has_overdue_followup() or 
                self.needs_followup_soon())
    
    def get_attention_level(self) -> str:
        """Get attention level: urgent, soon, or normal."""
        if self.has_overdue_followup():
            return "urgent"
        elif self.has_upcoming_interview() or self.needs_followup_soon():
            return "soon"
        else:
            return "normal"


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
        # Attention level colors
        ("urgent", "white", "dark red", "bold"),
        ("soon", "black", "yellow"),
        ("focus_urgent", "yellow", "dark red", "bold"),
        ("focus_soon", "white", "brown", "bold"),
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

        # Search/filter state
        self.filter_text = ""  # Current search filter
        self.filtered_jobs = []  # Jobs after applying filter
        
        # Multi-select state
        self.multi_select_mode = False
        self.selected_jobs = set()  # Set of job indices that are selected

        # Migration: check for old task file
        old_task_file = os.path.expanduser("~/.planner_tasks.json")
        if os.path.exists(old_task_file) and not os.path.exists(self.job_file):
            self._migrate_from_tasks(old_task_file)

        # Load saved jobs
        self.load_jobs()

        # Apply initial sorting
        self._sort_jobs()
        
        # Initialize filter (no filter initially)
        self._apply_filter()

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
                        self.filter_text = data.get("filter_text", "")
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
                            # Interview tracking
                            interview_date=item.get("interview_date", ""),
                            interview_time=item.get("interview_time", ""),
                            interview_type=item.get("interview_type", ""),
                            # Follow-up tracking
                            last_contact=item.get("last_contact", ""),
                            next_followup=item.get("next_followup", ""),
                            # Salary information
                            salary_min=item.get("salary_min", ""),
                            salary_max=item.get("salary_max", ""),
                            salary_offered=item.get("salary_offered", ""),
                            # Contact information
                            recruiter_name=item.get("recruiter_name", ""),
                            recruiter_email=item.get("recruiter_email", ""),
                            recruiter_phone=item.get("recruiter_phone", ""),
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
                "filter_text": self.filter_text,
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
                        # Interview tracking
                        "interview_date": job.interview_date,
                        "interview_time": job.interview_time,
                        "interview_type": job.interview_type,
                        # Follow-up tracking
                        "last_contact": job.last_contact,
                        "next_followup": job.next_followup,
                        # Salary information
                        "salary_min": job.salary_min,
                        "salary_max": job.salary_max,
                        "salary_offered": job.salary_offered,
                        # Contact information
                        "recruiter_name": job.recruiter_name,
                        "recruiter_email": job.recruiter_email,
                        "recruiter_phone": job.recruiter_phone,
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

        # Footer with dynamic instructions 
        self.footer_widget = urwid.AttrMap(urwid.Text("", align="center"), "footer")
        self._update_footer()  # Set initial footer text

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
        
        # Show filtered count vs total when filtering
        if self.filter_text:
            display_jobs = self._get_display_jobs()
            job_count = f"{len(display_jobs)}/{len(self.jobs)}"
            filter_info = f" Filter: '{self.filter_text}' -"
        else:
            job_count = str(len(self.jobs))
            filter_info = ""
        
        # Show multi-select status
        multiselect_info = ""
        if self.multi_select_mode:
            selected_count = len(self.selected_jobs)
            multiselect_info = f" Multi-Select: {selected_count} selected -"
            
        storage_path = self.job_file.replace(os.path.expanduser("~"), "~")  # Show ~ instead of full path
        header_text = f" Job Tracker - Sort: {sort_name} {sort_direction} -{filter_info}{multiselect_info} {job_count} apps - Saved: {storage_path} "
        
        if hasattr(self, 'header_widget'):
            self.header_widget.original_widget.set_text(header_text)
            
    def _update_footer(self):
        """Update footer based on current mode."""
        if self.multi_select_mode:
            if self.selected_jobs:
                footer_text = " Multi-Select: [Space] toggle [Ctrl+A] all [b] bulk status [Ctrl+D] delete [m] exit "
            else:
                footer_text = " Multi-Select: [Space] select jobs [Ctrl+A] select all [m] exit multi-select mode "
        else:
            footer_text = " [a]dd [d]el [s]tatus [v]iew | [/]filter [i]nfo [l]ine [r]emind [m]ulti | [c]opy | [j/k]nav [q]uit "
            
        if hasattr(self, 'footer_widget'):
            self.footer_widget.original_widget.set_text(footer_text)

    def _refresh_job_list(self):
        """Refresh the job list display."""
        self.job_list.clear()

        # Update header and footer with current info
        self._update_header()
        self._update_footer()

        display_jobs = self._get_display_jobs()
        
        if not display_jobs:
            if not self.jobs:
                # No jobs at all
                message = "No job applications yet. Press [a] to add one."
            else:
                # Jobs exist but filter excludes all
                message = f"No jobs match filter '{self.filter_text}'. Press [/] to change filter."
            
            self.job_list.append(
                urwid.Text(
                    ("body", message),
                    align="center",
                )
            )
            return

        for i, job in enumerate(display_jobs):
            emoji = job.get_status_indicator()  # Use enhanced indicator
            status_text = f"[{job.status.upper()}]"
            
            # Add selection indicator for multi-select mode
            selection_indicator = ""
            if self.multi_select_mode:
                if id(job) in self.selected_jobs:
                    selection_indicator = "☑ "  # Checked box
                else:
                    selection_indicator = "☐ "  # Empty box
            
            # Add interview info if present
            interview_info = ""
            if job.interview_date:
                interview_info = f" | Int: {job.interview_date}"
                if job.interview_time:
                    interview_info += f" {job.interview_time}"
            
            display_text = f" {selection_indicator}{emoji} {status_text} {job.company} - {job.position} ({job.date_applied}){interview_info}"

            # Get color scheme - prioritize attention level over status
            attention_level = job.get_attention_level()
            if attention_level == "urgent":
                color_attr = "urgent"
                focus_attr = "focus_urgent"
            elif attention_level == "soon":
                color_attr = "soon"
                focus_attr = "focus_soon"
            else:
                # Use normal status-based coloring
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

    def _apply_filter(self):
        """Apply current filter to jobs list."""
        if not self.filter_text:
            self.filtered_jobs = self.jobs.copy()
        else:
            filter_lower = self.filter_text.lower()
            self.filtered_jobs = [
                job for job in self.jobs
                if filter_lower in job.company.lower() or filter_lower in job.position.lower()
            ]

    def _set_filter(self, filter_text):
        """Set new filter text and apply it."""
        self.filter_text = filter_text
        self._apply_filter()

    def _clear_filter(self):
        """Clear the current filter."""
        self.filter_text = ""
        self._apply_filter()

    def _get_display_jobs(self):
        """Get the jobs to display (filtered or all jobs)."""
        return self.filtered_jobs if self.filter_text else self.jobs

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
        
        # Apply current filter to sorted jobs
        self._apply_filter()

        # Refresh display
        self._refresh_job_list()

        # Try to restore focus to the same job
        display_jobs = self._get_display_jobs()
        if focused_job and display_jobs:
            try:
                new_index = display_jobs.index(focused_job)
                if 0 <= new_index < len(self.job_list):
                    self.job_list.set_focus(new_index)
            except (ValueError, AttributeError):
                # Job not found in filtered list or focus failed, default to top
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
            # Core information (required)
            ("Company Name", "Enter company name:", "company", True),
            ("Job Position", "Enter job position/title:", "position", True),
            
            # Application details
            ("Application Link", "Enter job posting URL (optional):", "link", False),
            ("Application Date", f"Date applied ({datetime.now().strftime('%Y-%m-%d')}):", "date_applied", False),
            
            # Interview information (optional)
            ("Interview Date", "Interview date (YYYY-MM-DD, optional):", "interview_date", False),
            ("Interview Time", "Interview time (HH:MM, optional):", "interview_time", False),
            ("Interview Type", "Interview type (Phone/Video/In-person, optional):", "interview_type", False),
            
            # Contact information (optional)
            ("Recruiter Name", "Recruiter/contact name (optional):", "recruiter_name", False),
            ("Recruiter Email", "Recruiter email (optional):", "recruiter_email", False),
            
            # Salary information (optional) 
            ("Salary Range Min", "Minimum salary (optional):", "salary_min", False),
            ("Salary Range Max", "Maximum salary (optional):", "salary_max", False),
            
            # Notes and follow-up
            ("Notes", "Enter any notes (optional):", "notes", False),
            ("Next Follow-up", "Next follow-up date (YYYY-MM-DD, optional):", "next_followup", False),
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
        step_info = f"Step {self._job_entry_step + 1} of 13"
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
        # Set last_contact to application date by default
        app_date = self._current_job_data.get("date_applied", datetime.now().strftime("%Y-%m-%d"))
        
        job = JobApplication(
            company=self._current_job_data.get("company", ""),
            position=self._current_job_data.get("position", ""),
            date_applied=app_date,
            link=self._current_job_data.get("link", ""),
            notes=self._current_job_data.get("notes", ""),
            status="Applied",
            # Interview tracking
            interview_date=self._current_job_data.get("interview_date", ""),
            interview_time=self._current_job_data.get("interview_time", ""),
            interview_type=self._current_job_data.get("interview_type", ""),
            # Follow-up tracking 
            last_contact=app_date,  # Set to application date initially
            next_followup=self._current_job_data.get("next_followup", ""),
            # Salary information
            salary_min=self._current_job_data.get("salary_min", ""),
            salary_max=self._current_job_data.get("salary_max", ""),
            salary_offered=self._current_job_data.get("salary_offered", ""),
            # Contact information
            recruiter_name=self._current_job_data.get("recruiter_name", ""),
            recruiter_email=self._current_job_data.get("recruiter_email", ""),
            recruiter_phone=self._current_job_data.get("recruiter_phone", ""),
        )

        self.jobs.append(job)
        
        # Apply sorting and refresh
        self._apply_sort_and_refresh()
        self.save_jobs()
        
        # Try to focus on the newly added job
        try:
            display_jobs = self._get_display_jobs()
            new_index = display_jobs.index(job)
            if 0 <= new_index < len(self.job_list):
                self.job_list.set_focus(new_index)
        except (ValueError, AttributeError):
            # Job might be filtered out or focus failed, default to top
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

    def _show_search_dialog(self):
        """Show search/filter dialog with live filtering."""
        edit = urwid.Edit("Filter: ", self.filter_text)  # Pre-fill with current filter
        status_text = urwid.Text("", align="center")
        
        def update_filter_preview():
            """Update the preview of filter results."""
            current_text = edit.get_edit_text().strip()
            
            # Temporarily apply filter to see results
            temp_filter = self.filter_text
            self._set_filter(current_text)
            display_jobs = self._get_display_jobs()
            
            if current_text:
                if display_jobs:
                    status_text.set_text(f"Found {len(display_jobs)} matches")
                else:
                    status_text.set_text("No matches found")
            else:
                status_text.set_text(f"Showing all {len(self.jobs)} jobs")
            
            # Restore original filter for now
            self._set_filter(temp_filter)

        def handle_search_input(key):
            if key == "enter":
                # Apply the filter
                new_filter = edit.get_edit_text().strip()
                self._set_filter(new_filter)
                self._refresh_job_list()
                self.save_jobs()  # Save filter state
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
                
            elif key == "esc":
                # Cancel - restore original filter
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
                
            elif key == "ctrl d":
                # Clear filter
                edit.set_edit_text("")
                update_filter_preview()
                
            else:
                # Let the key pass through to edit widget
                result = edit.keypress((0,), key)
                update_filter_preview()  # Update preview after each keystroke
                return result

        # Initialize preview
        update_filter_preview()

        dialog_content = urwid.Pile([
            urwid.Text(("header", "Search/Filter Jobs"), align="center"),
            urwid.Divider(),
            edit,
            urwid.Divider(),
            status_text,
            urwid.Divider(),
            urwid.Text("Press Enter to apply, Esc to cancel, Ctrl+D to clear", align="center"),
        ])

        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )

        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=60, valign="middle", height=10
        )

        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_search_input
        self.main_loop.widget = overlay

    def _delete_current_job(self):
        """Show confirmation dialog before deleting the currently selected job."""
        display_jobs = self._get_display_jobs()
        if not display_jobs:
            return

        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(display_jobs):
                job = display_jobs[focus_pos]
                # Find the actual index in the main jobs list
                actual_index = self.jobs.index(job)
                self._show_delete_confirmation(job, actual_index)
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
        display_jobs = self._get_display_jobs()
        if not display_jobs:
            return

        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(display_jobs):
                current_job = display_jobs[focus_pos]
                status_options = JobApplication.get_status_options()

                try:
                    current_index = status_options.index(current_job.status)
                    next_index = (current_index + 1) % len(status_options)
                except ValueError:
                    next_index = 0

                current_job.status = status_options[next_index]
                self._apply_filter()  # Reapply filter after status change
                self._refresh_job_list()
                self.save_jobs()
                # Restore focus to same position
                self.job_list.set_focus(focus_pos)
        except (ValueError, TypeError):
            pass

    def _move_focus(self, direction):
        """Move focus up or down in the job list."""
        display_jobs = self._get_display_jobs()
        if not display_jobs:
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
        display_jobs = self._get_display_jobs()
        if display_jobs:
            self.job_list.set_focus(0)

    def _move_to_bottom(self):
        """Move focus to the last job."""
        display_jobs = self._get_display_jobs()
        if display_jobs:
            self.job_list.set_focus(len(self.job_list) - 1)

    def _view_job_details(self):
        """Show detailed view of current job application."""
        display_jobs = self._get_display_jobs()
        if not display_jobs:
            return

        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(display_jobs):
                job = display_jobs[focus_pos]
                self._show_job_detail_dialog(job)
        except (ValueError, TypeError):
            pass

    def _show_job_detail_dialog(self, job):
        """Show detailed information dialog for a job."""
        emoji = job.get_status_indicator()  # Use enhanced indicator

        # Format job details with all new fields
        details = []
        
        # Basic information
        details.extend([
            f"Company: {job.company}",
            f"Position: {job.position}",
            f"Status: {emoji} {job.status}",
            f"Date Applied: {job.date_applied}",
        ])
        
        # Interview information
        if job.interview_date or job.interview_time or job.interview_type:
            details.append("")  # Empty line for spacing
            details.append("INTERVIEW INFO:")
            if job.interview_date:
                details.append(f"  Date: {job.interview_date}")
            if job.interview_time:
                details.append(f"  Time: {job.interview_time}")
            if job.interview_type:
                details.append(f"  Type: {job.interview_type}")
        
        # Contact information
        if job.recruiter_name or job.recruiter_email or job.recruiter_phone:
            details.append("")
            details.append("CONTACT INFO:")
            if job.recruiter_name:
                details.append(f"  Name: {job.recruiter_name}")
            if job.recruiter_email:
                details.append(f"  Email: {job.recruiter_email}")
            if job.recruiter_phone:
                details.append(f"  Phone: {job.recruiter_phone}")
        
        # Salary information
        if job.salary_min or job.salary_max or job.salary_offered:
            details.append("")
            details.append("SALARY INFO:")
            if job.salary_min:
                details.append(f"  Min Range: {job.salary_min}")
            if job.salary_max:
                details.append(f"  Max Range: {job.salary_max}")
            if job.salary_offered:
                details.append(f"  Offered: {job.salary_offered}")
        
        # Follow-up tracking
        if job.last_contact or job.next_followup:
            details.append("")
            details.append("FOLLOW-UP:")
            if job.last_contact:
                details.append(f"  Last Contact: {job.last_contact}")
            if job.next_followup:
                followup_status = ""
                if job.has_overdue_followup():
                    followup_status = " (OVERDUE!)"
                elif job.needs_followup_soon():
                    followup_status = " (Due Soon)"
                details.append(f"  Next Follow-up: {job.next_followup}{followup_status}")
        
        # Link and notes
        details.append("")
        details.extend([
            f"Link: {job.link if job.link else 'None'}",
            f"Notes: {job.notes if job.notes else 'None'}",
        ])

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
            dialog, self.ui, align="center", width=80, valign="middle", height=20
        )

        def close_dialog(key):
            self.main_loop.widget = self.ui
            self.main_loop.unhandled_input = old_handler

        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = close_dialog
        self.main_loop.widget = overlay

    def _calculate_statistics(self):
        """Calculate comprehensive job application statistics."""
        if not self.jobs:
            return {}
            
        total_jobs = len(self.jobs)
        
        # Count by status
        status_counts = {}
        for status in JobApplication.get_status_options():
            status_counts[status] = sum(1 for job in self.jobs if job.status == status)
        
        # Calculate success rates
        interviews = status_counts.get("Interview", 0)
        offers = status_counts.get("Offer", 0)
        rejected = status_counts.get("Rejected", 0)
        
        interview_rate = (interviews / total_jobs * 100) if total_jobs > 0 else 0
        offer_rate = (offers / total_jobs * 100) if total_jobs > 0 else 0
        rejection_rate = (rejected / total_jobs * 100) if total_jobs > 0 else 0
        
        # Response rate (anything other than just "Applied")
        responses = total_jobs - status_counts.get("Applied", 0)
        response_rate = (responses / total_jobs * 100) if total_jobs > 0 else 0
        
        # Time-based analytics
        applications_by_week = self._get_applications_by_timeframe("week")
        applications_by_month = self._get_applications_by_timeframe("month")
        
        # Interview insights
        upcoming_interviews = sum(1 for job in self.jobs if job.has_upcoming_interview())
        overdue_followups = sum(1 for job in self.jobs if job.has_overdue_followup())
        soon_followups = sum(1 for job in self.jobs if job.needs_followup_soon())
        
        return {
            "total_jobs": total_jobs,
            "status_counts": status_counts,
            "interview_rate": interview_rate,
            "offer_rate": offer_rate,
            "rejection_rate": rejection_rate,
            "response_rate": response_rate,
            "applications_per_week": applications_by_week,
            "applications_per_month": applications_by_month,
            "upcoming_interviews": upcoming_interviews,
            "overdue_followups": overdue_followups,
            "soon_followups": soon_followups,
        }
    
    def _get_applications_by_timeframe(self, timeframe):
        """Calculate applications per week or month."""
        if not self.jobs:
            return 0.0
            
        # Get date range
        dates = []
        for job in self.jobs:
            try:
                date = datetime.strptime(job.date_applied, "%Y-%m-%d")
                dates.append(date)
            except ValueError:
                continue
                
        if not dates:
            return 0.0
            
        earliest = min(dates)
        latest = max(dates)
        
        if timeframe == "week":
            delta = (latest - earliest).days / 7
        else:  # month
            delta = (latest - earliest).days / 30.44  # Average days per month
            
        if delta == 0:
            return len(dates)
            
        return len(dates) / delta
    
    def _calculate_average_time_in_status(self):
        """Calculate average time spent in each status (simplified)."""
        # This is a simplified version - in a real app, you'd track status change dates
        # For now, we'll estimate based on application date and current status
        status_times = {}
        
        for status in JobApplication.get_status_options():
            jobs_in_status = [job for job in self.jobs if job.status == status]
            if jobs_in_status:
                total_days = 0
                for job in jobs_in_status:
                    try:
                        app_date = datetime.strptime(job.date_applied, "%Y-%m-%d")
                        days_since = (datetime.now() - app_date).days
                        total_days += days_since
                    except ValueError:
                        continue
                        
                avg_days = total_days / len(jobs_in_status) if jobs_in_status else 0
                status_times[status] = avg_days
            else:
                status_times[status] = 0
                
        return status_times

    def _show_statistics_dialog(self):
        """Show comprehensive statistics dialog."""
        stats = self._calculate_statistics()
        avg_times = self._calculate_average_time_in_status()
        
        if not stats:
            # No data available
            content = [
                urwid.Text(("header", "Job Application Statistics"), align="center"),
                urwid.Divider(),
                urwid.Text("No job applications to analyze yet.", align="center"),
                urwid.Text("Add some applications to see statistics!", align="center"),
                urwid.Divider(),
                urwid.Text("Press any key to close", align="center")
            ]
        else:
            content = [
                urwid.Text(("header", "Job Application Statistics"), align="center"),
                urwid.Divider(),
                urwid.Text(f"Total Applications: {stats['total_jobs']}", align="left"),
                urwid.Divider(),
            ]
            
            # Status breakdown
            content.append(urwid.Text("STATUS BREAKDOWN:", align="left"))
            for status, count in stats['status_counts'].items():
                percentage = (count / stats['total_jobs'] * 100) if stats['total_jobs'] > 0 else 0
                emoji = JobApplication.get_status_emoji(status)
                content.append(urwid.Text(f"  {emoji} {status}: {count} ({percentage:.1f}%)", align="left"))
            
            content.append(urwid.Divider())
            
            # Success rates
            content.extend([
                urwid.Text("SUCCESS RATES:", align="left"),
                urwid.Text(f"  Response Rate: {stats['response_rate']:.1f}%", align="left"),
                urwid.Text(f"  Interview Rate: {stats['interview_rate']:.1f}%", align="left"),
                urwid.Text(f"  Offer Rate: {stats['offer_rate']:.1f}%", align="left"),
                urwid.Divider(),
            ])
            
            # Time-based analytics
            content.extend([
                urwid.Text("APPLICATION FREQUENCY:", align="left"),
                urwid.Text(f"  Per Week: {stats['applications_per_week']:.1f}", align="left"),
                urwid.Text(f"  Per Month: {stats['applications_per_month']:.1f}", align="left"),
                urwid.Divider(),
            ])
            
            # Upcoming items
            if stats['upcoming_interviews'] or stats['overdue_followups'] or stats['soon_followups']:
                content.append(urwid.Text("UPCOMING ACTIONS:", align="left"))
                if stats['upcoming_interviews']:
                    content.append(urwid.Text(f"  ⏰ Interviews This Week: {stats['upcoming_interviews']}", align="left"))
                if stats['overdue_followups']:
                    content.append(urwid.Text(f"  🔴 Overdue Follow-ups: {stats['overdue_followups']}", align="left"))
                if stats['soon_followups']:
                    content.append(urwid.Text(f"  🟡 Follow-ups Due Soon: {stats['soon_followups']}", align="left"))
                content.append(urwid.Divider())
            
            # Average time in status
            content.extend([
                urwid.Text("AVERAGE DAYS IN STATUS:", align="left"),
            ])
            for status, days in avg_times.items():
                if days > 0:
                    emoji = JobApplication.get_status_emoji(status)
                    content.append(urwid.Text(f"  {emoji} {status}: {days:.1f} days", align="left"))
            
            content.extend([
                urwid.Divider(),
                urwid.Text("Press any key to close", align="center")
            ])
        
        dialog_content = urwid.Pile(content)
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )
        
        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=60, valign="middle", height=25
        )
        
        def close_dialog(key):
            self.main_loop.widget = self.ui
            self.main_loop.unhandled_input = old_handler
        
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = close_dialog
        self.main_loop.widget = overlay

    def _show_timeline_dialog(self):
        """Show timeline view of applications."""
        if not self.jobs:
            content = [
                urwid.Text(("header", "Application Timeline"), align="center"),
                urwid.Divider(),
                urwid.Text("No job applications to show in timeline yet.", align="center"),
                urwid.Text("Add some applications to see your progress!", align="center"),
                urwid.Divider(),
                urwid.Text("Press any key to close", align="center")
            ]
        else:
            # Sort jobs by application date
            sorted_jobs = sorted(self.jobs, key=lambda j: self._parse_date(j.date_applied))
            
            content = [
                urwid.Text(("header", "Application Timeline"), align="center"),
                urwid.Divider(),
                urwid.Text(f"Showing {len(sorted_jobs)} applications chronologically:", align="left"),
                urwid.Divider(),
            ]
            
            # Group by month for better visualization
            current_month = None
            for job in sorted_jobs:
                try:
                    app_date = datetime.strptime(job.date_applied, "%Y-%m-%d")
                    month_key = app_date.strftime("%Y-%m")
                    
                    # Add month header if changed
                    if month_key != current_month:
                        current_month = month_key
                        month_name = app_date.strftime("%B %Y")
                        content.extend([
                            urwid.Text(""),
                            urwid.Text(f"=== {month_name.upper()} ===", align="center"),
                        ])
                    
                    # Application entry
                    emoji = job.get_status_indicator()
                    date_str = app_date.strftime("%m/%d")
                    
                    # Add timeline markers
                    timeline_info = f"{date_str} {emoji} {job.company} - {job.position}"
                    
                    # Add interview info if present
                    if job.interview_date:
                        try:
                            int_date = datetime.strptime(job.interview_date, "%Y-%m-%d")
                            int_str = int_date.strftime("%m/%d")
                            timeline_info += f" → Int: {int_str}"
                        except ValueError:
                            pass
                    
                    # Add status progression indicator
                    status_indicators = {
                        "Applied": "●",
                        "Interview": "●●", 
                        "Offer": "●●●",
                        "Rejected": "●○○",
                        "Withdrawn": "○○○"
                    }
                    progress = status_indicators.get(job.status, "●")
                    timeline_info += f" [{progress}]"
                    
                    content.append(urwid.Text(f"  {timeline_info}", align="left"))
                    
                except ValueError:
                    # Skip jobs with invalid dates
                    continue
            
            content.extend([
                urwid.Divider(),
                urwid.Text("Legend: ● = Progress, ○ = End, → = Next Step", align="center"),
                urwid.Text("Press any key to close", align="center")
            ])
        
        dialog_content = urwid.Pile(content)
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )
        
        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=80, valign="middle", height=25
        )
        
        def close_dialog(key):
            self.main_loop.widget = self.ui
            self.main_loop.unhandled_input = old_handler
        
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = close_dialog
        self.main_loop.widget = overlay

    def _toggle_multi_select_mode(self):
        """Toggle multi-select mode on/off."""
        self.multi_select_mode = not self.multi_select_mode
        if not self.multi_select_mode:
            self.selected_jobs.clear()
        self._refresh_job_list()

    def _toggle_selection(self):
        """Toggle selection of current job in multi-select mode."""
        if not self.multi_select_mode:
            return
            
        display_jobs = self._get_display_jobs()
        if not display_jobs:
            return
            
        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(display_jobs):
                job = display_jobs[focus_pos]
                job_id = id(job)  # Use object ID as unique identifier
                
                if job_id in self.selected_jobs:
                    self.selected_jobs.remove(job_id)
                else:
                    self.selected_jobs.add(job_id)
                    
                self._refresh_job_list()
        except (ValueError, TypeError):
            pass

    def _select_all(self):
        """Select all visible jobs."""
        if not self.multi_select_mode:
            return
            
        display_jobs = self._get_display_jobs()
        self.selected_jobs.clear()
        
        for job in display_jobs:
            self.selected_jobs.add(id(job))
            
        self._refresh_job_list()

    def _get_selected_jobs(self):
        """Get list of currently selected jobs."""
        if not self.multi_select_mode:
            return []
            
        display_jobs = self._get_display_jobs()
        return [job for job in display_jobs if id(job) in self.selected_jobs]

    def _bulk_status_change(self):
        """Change status for all selected jobs."""
        selected = self._get_selected_jobs()
        if not selected:
            return
            
        # Show status selection dialog
        self._show_bulk_status_dialog(selected)

    def _show_bulk_status_dialog(self, selected_jobs):
        """Show dialog to select status for bulk change."""
        status_options = JobApplication.get_status_options()
        
        content = [
            urwid.Text(("header", f"Bulk Status Change ({len(selected_jobs)} jobs)"), align="center"),
            urwid.Divider(),
            urwid.Text("Selected jobs:", align="left"),
        ]
        
        # Show selected jobs (limited to first 5 for space)
        for i, job in enumerate(selected_jobs[:5]):
            emoji = job.get_status_indicator()
            content.append(urwid.Text(f"  {emoji} {job.company} - {job.position}", align="left"))
            
        if len(selected_jobs) > 5:
            content.append(urwid.Text(f"  ... and {len(selected_jobs) - 5} more", align="left"))
            
        content.extend([
            urwid.Divider(),
            urwid.Text("Choose new status:", align="left"),
        ])
        
        # Create status buttons
        status_widgets = []
        for i, status in enumerate(status_options):
            emoji = JobApplication.get_status_emoji(status)
            button_text = f"{i+1}. {emoji} {status}"
            status_widgets.append(urwid.Text(button_text, align="left"))
        
        content.extend(status_widgets)
        content.extend([
            urwid.Divider(),
            urwid.Text("Press 1-5 to select status, Esc to cancel", align="center")
        ])
        
        def handle_status_input(key):
            if key == "esc":
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            elif key in "12345":
                try:
                    status_idx = int(key) - 1
                    if 0 <= status_idx < len(status_options):
                        new_status = status_options[status_idx]
                        
                        # Apply status to all selected jobs
                        for job in selected_jobs:
                            job.status = new_status
                            
                        self._apply_filter()
                        self._refresh_job_list()
                        self.save_jobs()
                        
                        # Exit multi-select mode
                        self.multi_select_mode = False
                        self.selected_jobs.clear()
                        self._refresh_job_list()
                        
                    self.main_loop.widget = self.ui
                    self.main_loop.unhandled_input = old_handler
                except ValueError:
                    pass
            else:
                return key
                
        dialog_content = urwid.Pile(content)
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )
        
        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=70, valign="middle", height=20
        )
        
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_status_input
        self.main_loop.widget = overlay

    def _bulk_delete(self):
        """Delete all selected jobs after confirmation."""
        selected = self._get_selected_jobs()
        if not selected:
            return
            
        self._show_bulk_delete_confirmation(selected)

    def _show_bulk_delete_confirmation(self, selected_jobs):
        """Show confirmation dialog for bulk delete."""
        content = [
            urwid.Text(("header", f"Bulk Delete Confirmation"), align="center"),
            urwid.Divider(),
            urwid.Text(f"Delete {len(selected_jobs)} job applications?", align="center"),
            urwid.Divider(),
        ]
        
        # Show selected jobs (limited to first 5)
        for i, job in enumerate(selected_jobs[:5]):
            content.append(urwid.Text(f"  • {job.company} - {job.position}", align="left"))
            
        if len(selected_jobs) > 5:
            content.append(urwid.Text(f"  ... and {len(selected_jobs) - 5} more", align="left"))
            
        content.extend([
            urwid.Divider(),
            urwid.Text(("focus", "This action cannot be undone!"), align="center"),
            urwid.Divider(),
            urwid.Text("[Y]es to delete, [N]o to cancel", align="center")
        ])
        
        def handle_delete_input(key):
            if key.lower() == 'y':
                # Delete selected jobs
                for job in selected_jobs:
                    if job in self.jobs:
                        self.jobs.remove(job)
                        
                self._apply_filter()
                self._refresh_job_list()
                self.save_jobs()
                
                # Exit multi-select mode
                self.multi_select_mode = False
                self.selected_jobs.clear()
                self._refresh_job_list()
                
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
                
            elif key.lower() == 'n' or key == 'esc':
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            else:
                return key
                
        dialog_content = urwid.Pile(content)
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )
        
        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=60, valign="middle", height=15
        )
        
        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_delete_input
        self.main_loop.widget = overlay

    def _duplicate_job(self):
        """Duplicate the currently focused job."""
        display_jobs = self._get_display_jobs()
        if not display_jobs:
            return
            
        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(display_jobs):
                original_job = display_jobs[focus_pos]
                
                # Create a copy of the job with some fields reset
                duplicate = JobApplication(
                    company=original_job.company,
                    position=original_job.position,
                    date_applied=datetime.now().strftime("%Y-%m-%d"),  # Today's date
                    status="Applied",  # Reset to Applied
                    link="",  # Clear link (likely different posting)
                    notes=f"Duplicated from {original_job.company} application",
                    # Copy interview and contact info as templates
                    interview_date="",  # Clear specific dates
                    interview_time=original_job.interview_time,  # Keep time as template
                    interview_type=original_job.interview_type,  # Keep type as template
                    last_contact=datetime.now().strftime("%Y-%m-%d"),  # Today
                    next_followup="",  # Clear specific dates
                    salary_min=original_job.salary_min,  # Keep salary info
                    salary_max=original_job.salary_max,
                    salary_offered="",  # Clear offered amount
                    recruiter_name="",  # Clear specific contact
                    recruiter_email="",
                    recruiter_phone="",
                )
                
                self.jobs.append(duplicate)
                self._apply_sort_and_refresh()
                self.save_jobs()
                
                # Try to focus on the newly duplicated job
                try:
                    display_jobs = self._get_display_jobs()
                    new_index = display_jobs.index(duplicate)
                    if 0 <= new_index < len(self.job_list):
                        self.job_list.set_focus(new_index)
                except (ValueError, AttributeError):
                    if len(self.job_list) > 0:
                        self.job_list.set_focus(0)
                        
        except (ValueError, TypeError):
            pass

    def _quick_add_similar(self):
        """Quick add a job similar to the current one with minimal prompts."""
        display_jobs = self._get_display_jobs()
        if not display_jobs:
            return
            
        try:
            focus_pos = self.job_list.focus
            if 0 <= focus_pos < len(display_jobs):
                template_job = display_jobs[focus_pos]
                self._show_quick_add_dialog(template_job)
        except (ValueError, TypeError):
            pass

    def _show_quick_add_dialog(self, template_job):
        """Show quick add dialog using template job."""
        self._quick_add_data = {"template": template_job}
        self._quick_add_step = 0
        self._start_quick_add()

    def _start_quick_add(self):
        """Start quick add process with minimal required fields."""
        steps = [
            ("Company Name", f"Company name (was: {self._quick_add_data['template'].company}):", "company", True),
            ("Position", f"Position (was: {self._quick_add_data['template'].position}):", "position", False),
            ("Application Date", f"Date applied ({datetime.now().strftime('%Y-%m-%d')}):", "date_applied", False),
        ]
        
        if self._quick_add_step < len(steps):
            title, prompt, field, required = steps[self._quick_add_step]
            
            # Pre-fill with template data or current date
            if field == "date_applied":
                default_value = datetime.now().strftime("%Y-%m-%d")
            elif field == "position":
                default_value = self._quick_add_data['template'].position
            else:
                default_value = ""
                
            self._show_quick_add_input_dialog(title, prompt, field, required, default_value)
        else:
            self._finalize_quick_add()

    def _show_quick_add_input_dialog(self, title, prompt, field, required, default_value=""):
        """Show input dialog for quick add step."""
        edit = urwid.Edit(f"{prompt} ", default_value)

        def handle_input(key):
            if key == "enter":
                value = edit.get_edit_text().strip()
                if required and not value:
                    return

                self._quick_add_data[field] = value
                self._quick_add_step += 1
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
                self._start_quick_add()

            elif key == "esc":
                self.main_loop.widget = self.ui
                self.main_loop.unhandled_input = old_handler
            else:
                return key

        dialog_content = urwid.Pile([
            urwid.Text(("header", f"Quick Add - {title}"), align="center"),
            urwid.Text(("body", f"Step {self._quick_add_step + 1} of 3"), align="center"),
            urwid.Divider(),
            edit,
            urwid.Divider(),
            urwid.Text("Press Enter to continue, Esc to cancel", align="center"),
        ])

        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )

        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=50, valign="middle", height=9
        )

        old_handler = self.main_loop.unhandled_input
        self.main_loop.unhandled_input = handle_input
        self.main_loop.widget = overlay

    def _finalize_quick_add(self):
        """Create job from quick add with template data."""
        template = self._quick_add_data["template"]
        
        job = JobApplication(
            company=self._quick_add_data.get("company", ""),
            position=self._quick_add_data.get("position", template.position),
            date_applied=self._quick_add_data.get("date_applied", datetime.now().strftime("%Y-%m-%d")),
            status="Applied",
            link="",
            notes=f"Quick-added using {template.company} as template",
            # Inherit template settings
            interview_time=template.interview_time,
            interview_type=template.interview_type,
            last_contact=datetime.now().strftime("%Y-%m-%d"),
            salary_min=template.salary_min,
            salary_max=template.salary_max,
            recruiter_name=template.recruiter_name if template.recruiter_name else "",
        )
        
        self.jobs.append(job)
        self._apply_sort_and_refresh()
        self.save_jobs()
        
        # Focus on new job
        try:
            display_jobs = self._get_display_jobs()
            new_index = display_jobs.index(job)
            if 0 <= new_index < len(self.job_list):
                self.job_list.set_focus(new_index)
        except (ValueError, AttributeError):
            if len(self.job_list) > 0:
                self.job_list.set_focus(0)

    def _show_reminders_dialog(self):
        """Show smart reminders for jobs needing attention."""
        jobs_needing_attention = [job for job in self.jobs if job.needs_attention()]
        
        if not jobs_needing_attention:
            content = [
                urwid.Text(("header", "Smart Reminders"), align="center"),
                urwid.Divider(),
                urwid.Text("🎉 All caught up! No jobs need immediate attention.", align="center"),
                urwid.Text("Great job staying on top of your applications!", align="center"),
                urwid.Divider(),
                urwid.Text("Press any key to close", align="center")
            ]
        else:
            content = [
                urwid.Text(("header", "Smart Reminders"), align="center"),
                urwid.Divider(),
                urwid.Text(f"📢 {len(jobs_needing_attention)} jobs need your attention:", align="left"),
                urwid.Divider(),
            ]
            
            # Group by attention level
            urgent_jobs = [job for job in jobs_needing_attention if job.get_attention_level() == "urgent"]
            soon_jobs = [job for job in jobs_needing_attention if job.get_attention_level() == "soon"]
            
            if urgent_jobs:
                content.append(urwid.Text("🚨 URGENT - Overdue follow-ups:", align="left"))
                for job in urgent_jobs:
                    reminder_text = f"  • {job.company} - {job.position}"
                    if job.next_followup:
                        try:
                            followup_date = datetime.strptime(job.next_followup, "%Y-%m-%d")
                            days_overdue = (datetime.now() - followup_date).days
                            reminder_text += f" (overdue {days_overdue} days)"
                        except ValueError:
                            reminder_text += " (follow-up overdue)"
                    content.append(urwid.Text(reminder_text, align="left"))
                content.append(urwid.Divider())
            
            if soon_jobs:
                content.append(urwid.Text("⏰ COMING UP - Action needed soon:", align="left"))
                for job in soon_jobs:
                    reminder_text = f"  • {job.company} - {job.position}"
                    if job.has_upcoming_interview():
                        if job.interview_date:
                            try:
                                int_date = datetime.strptime(job.interview_date, "%Y-%m-%d")
                                days_until = (int_date - datetime.now()).days
                                time_info = f" at {job.interview_time}" if job.interview_time else ""
                                reminder_text += f" - Interview in {days_until} days{time_info}"
                            except ValueError:
                                reminder_text += " - Interview scheduled"
                    elif job.needs_followup_soon():
                        if job.next_followup:
                            try:
                                followup_date = datetime.strptime(job.next_followup, "%Y-%m-%d")
                                days_until = (followup_date - datetime.now()).days
                                reminder_text += f" - Follow-up due in {days_until} days"
                            except ValueError:
                                reminder_text += " - Follow-up due soon"
                    content.append(urwid.Text(reminder_text, align="left"))
            
            content.extend([
                urwid.Divider(),
                urwid.Text("💡 Tip: Use [/] to filter by company, [s] to update status", align="center"),
                urwid.Text("Press any key to close", align="center")
            ])
        
        dialog_content = urwid.Pile(content)
        
        dialog = urwid.Filler(
            urwid.AttrMap(
                urwid.LineBox(urwid.Padding(dialog_content, left=2, right=2)), "body"
            )
        )
        
        overlay = urwid.Overlay(
            dialog, self.ui, align="center", width=80, valign="middle", height=20
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

        # Search/filter control
        elif key_str == "/" or key == "/":
            self._show_search_dialog()

        # Statistics view
        elif key_str == "i":
            self._show_statistics_dialog()

        # Timeline view
        elif key_str == "l":
            self._show_timeline_dialog()

        # Smart reminders
        elif key_str == "r":
            self._show_reminders_dialog()

        # Multi-select operations
        elif key_str == "m":
            self._toggle_multi_select_mode()
        elif key_str == " " and self.multi_select_mode:  # Space to toggle selection
            self._toggle_selection()
        elif key == "ctrl a" and self.multi_select_mode:  # Ctrl+A to select all
            self._select_all()
        elif key_str == "b" and self.multi_select_mode and self.selected_jobs:  # Bulk status change
            self._bulk_status_change()
        elif key == "ctrl d" and self.multi_select_mode and self.selected_jobs:  # Ctrl+D to bulk delete
            self._bulk_delete()

        # Quick productivity features  
        elif key_str == "c" and not self.multi_select_mode:  # Copy/duplicate current job
            self._duplicate_job()
        elif key == "ctrl q" and not self.multi_select_mode:  # Quick add similar
            self._quick_add_similar()

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

