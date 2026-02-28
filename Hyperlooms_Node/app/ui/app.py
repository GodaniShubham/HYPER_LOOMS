
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk

import psutil

from app.agent import AgentController
from app.config import AgentConfig, get_log_dir, load_config, save_config
from app.logger import setup_logging
from app.state import AgentState


def _tail_file(path: Path, max_lines: int = 400) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])


def _safe_pct(used: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, (used / total) * 100.0))


class NodeAgentUI(tk.Tk):
    PALETTE = {
        "bg": "#0A0D14",
        "card": "#121724",
        "border": "#2A3142",
        "title": "#F2F5FC",
        "muted": "#9AA6BF",
        "primary": "#EE3C23",
        "primary_dark": "#C9301B",
        "danger": "#D9363E",
        "danger_dark": "#B22B31",
        "indigo": "#F26A2E",
        "indigo_dark": "#D75B26",
        "dark_button": "#1B2333",
        "dark_button_hover": "#151C2A",
        "badge_ok_bg": "#1A2C21",
        "badge_ok_fg": "#59D98C",
        "badge_off_bg": "#341A1D",
        "badge_off_fg": "#FF7E86",
        "terminal_bg": "#070B12",
        "terminal_head": "#101826",
        "terminal_text": "#D2DBEA",
        "status_ok": "#59D98C",
        "status_warn": "#F3A53A",
        "status_error": "#FF7E86",
        "status_info": "#66B0FF",
        "chip_bg": "#182336",
        "chip_fg": "#A8B5CC",
        "input_bg": "#050A12",
        "input_fg": "#FFFFFF",
        "nav_bg": "#070B12",
        "nav_bg_active": "#131B2A",
    }

    METRIC_ORDER = [
        ("coordinator", "Coordinator", "NET"),
        ("node_agent", "Node Agent", "AGT"),
        ("discovery", "Discovery", "DSP"),
        ("registration", "Registration", "REG"),
        ("runtime", "Runtime", "RUN"),
        ("trust", "Trust", "TRU"),
        ("node_id", "Node ID", "ID"),
        ("eligibility", "Eligibility", "ELG"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.title("Hyperlooms Node Control Center")
        self.configure(bg=self.PALETTE["bg"])

        self._config: AgentConfig = load_config()
        self._state = AgentState()
        self._events: queue.Queue = queue.Queue()
        self._logger = setup_logging(get_log_dir(), "INFO")
        self._controller = AgentController(self._config, self._state, self._events, self._logger)

        self._console_lines: list[str] = []
        self._log_cache = ""
        self._last_net_sent = 0
        self._last_net_recv = 0
        self._last_net_ts = time.monotonic()
        self._net_initialized = False

        self._metric_vars: dict[str, tk.StringVar] = {}
        self._metric_icon_labels: dict[str, tk.Label] = {}
        self._metric_value_labels: dict[str, tk.Label] = {}
        self._metric_strip: tk.Frame | None = None
        self._metric_cards: list[tk.Frame] = []
        self._metric_column_count = len(self.METRIC_ORDER)

        self._operations_board: ttk.Frame | None = None
        self._operations_left: ttk.Frame | None = None
        self._operations_mid: ttk.Frame | None = None
        self._operations_right: ttk.Frame | None = None
        self._operations_activity: tk.Frame | None = None
        self._operations_layout_mode: str | None = None
        self._readiness_vars: dict[str, tk.StringVar] = {}
        self._readiness_value_labels: dict[str, tk.Label] = {}
        self._guided_start_btn: ttk.Button | None = None
        self._tasks_summary_var = tk.StringVar(value="Assigned: 0 | Network Active: 0 | Completed: 0 | Failed: 0")
        self._tasks_list: tk.Listbox | None = None
        self._tasks_detail: tk.Text | None = None
        self._distributed_tasks: dict[str, dict] = {}
        self._distributed_task_order: list[str] = []

        self._apply_responsive_window()

        self._init_style()
        self._build_ui()
        self._install_global_mousewheel_support()

        self.after(250, self._drain_events)
        self.after(500, self._refresh_status)
        self.after(1200, self._refresh_logs)

        self._append_console("control_center_ready")

    def _apply_responsive_window(self) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        target_width = min(1560, max(1180, screen_width - 60))
        target_height = min(980, max(700, screen_height - 80))

        min_width = min(1280, max(980, screen_width - 180))
        min_height = min(860, max(620, screen_height - 180))

        self.minsize(min_width, min_height)

        pos_x = max((screen_width - target_width) // 2, 0)
        pos_y = max((screen_height - target_height) // 2, 0)
        self.geometry(f"{target_width}x{target_height}+{pos_x}+{pos_y}")

    def _install_global_mousewheel_support(self) -> None:
        # Route mouse-wheel events to the closest scrollable widget under cursor,
        # so users can scroll without first clicking the scrollbar.
        self.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.bind_all("<Button-4>", self._on_global_mousewheel, add="+")
        self.bind_all("<Button-5>", self._on_global_mousewheel, add="+")

    def _normalize_wheel_delta(self, event: tk.Event) -> int:
        delta = int(getattr(event, "delta", 0) or 0)
        if delta != 0:
            if abs(delta) >= 120:
                return -int(delta / 120)
            return -1 if delta > 0 else 1

        num = int(getattr(event, "num", 0) or 0)
        if num == 4:
            return -1
        if num == 5:
            return 1
        return 0

    def _find_scroll_target(self, widget: tk.Misc | None) -> tk.Misc | None:
        current = widget
        while current is not None:
            if callable(getattr(current, "yview_scroll", None)):
                return current
            current = getattr(current, "master", None)
        return None

    def _on_global_mousewheel(self, event: tk.Event) -> str | None:
        step = self._normalize_wheel_delta(event)
        if step == 0:
            return None

        target = self._find_scroll_target(self.winfo_containing(event.x_root, event.y_root))
        if target is None:
            return None

        try:
            target.yview_scroll(step, "units")
        except tk.TclError:
            return None
        return "break"

    def _init_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=self.PALETTE["bg"])
        style.configure("CardBody.TFrame", background=self.PALETTE["card"])
        style.configure(
            "Card.TLabelframe",
            background=self.PALETTE["card"],
            bordercolor=self.PALETTE["border"],
            borderwidth=1,
            relief="solid",
            padding=16,
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=self.PALETTE["card"],
            foreground=self.PALETTE["muted"],
            font=("Segoe UI", 10, "bold"),
        )

        style.configure("Subtitle.TLabel", background=self.PALETTE["card"], foreground=self.PALETTE["muted"], font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.PALETTE["card"], foreground=self.PALETTE["muted"], font=("Segoe UI", 10, "bold"))
        style.configure("Field.TLabel", background=self.PALETTE["card"], foreground=self.PALETTE["muted"], font=("Segoe UI", 9, "bold"))
        style.configure("Value.TLabel", background=self.PALETTE["card"], foreground=self.PALETTE["title"], font=("Segoe UI", 11, "bold"))

        style.configure("Main.TNotebook", background=self.PALETTE["nav_bg"], borderwidth=0)
        style.configure(
            "Main.TNotebook.Tab",
            background=self.PALETTE["nav_bg"],
            foreground=self.PALETTE["input_fg"],
            borderwidth=1,
            lightcolor=self.PALETTE["nav_bg"],
            darkcolor=self.PALETTE["nav_bg"],
            bordercolor=self.PALETTE["border"],
            padding=(26, 14),
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Main.TNotebook.Tab",
            background=[("selected", self.PALETTE["nav_bg_active"]), ("active", self.PALETTE["dark_button"])],
            foreground=[("selected", self.PALETTE["input_fg"]), ("active", self.PALETTE["input_fg"])],
            bordercolor=[("selected", self.PALETTE["primary"]), ("active", self.PALETTE["border"])],
        )

        style.configure(
            "TEntry",
            fieldbackground=self.PALETTE["input_bg"],
            foreground=self.PALETTE["input_fg"],
            insertcolor=self.PALETTE["input_fg"],
            bordercolor=self.PALETTE["border"],
            lightcolor=self.PALETTE["border"],
            darkcolor=self.PALETTE["border"],
            padding=6,
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", "#101826"), ("disabled", "#101826")],
            foreground=[("readonly", self.PALETTE["input_fg"]), ("disabled", self.PALETTE["muted"])],
        )

        style.configure(
            "ActionNeutral.TButton",
            padding=(14, 9),
            font=("Segoe UI", 10, "bold"),
            background=self.PALETTE["chip_bg"],
            foreground=self.PALETTE["chip_fg"],
            borderwidth=1,
        )
        style.map(
            "ActionNeutral.TButton",
            background=[("active", self.PALETTE["dark_button"]), ("disabled", "#1E2636")],
            foreground=[("disabled", "#6D7A91")],
        )

        style.configure("ActionPrimary.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"), background=self.PALETTE["primary"], foreground="#ffffff", borderwidth=0)
        style.map("ActionPrimary.TButton", background=[("active", self.PALETTE["primary_dark"]), ("disabled", "#6D2F2A")], foreground=[("disabled", "#FAD0CA")])

        style.configure("ActionDanger.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"), background=self.PALETTE["danger"], foreground="#ffffff", borderwidth=0)
        style.map("ActionDanger.TButton", background=[("active", self.PALETTE["danger_dark"]), ("disabled", "#6A3135")], foreground=[("disabled", "#FFD7DA")])

        style.configure("ActionDark.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"), background=self.PALETTE["dark_button"], foreground="#ffffff", borderwidth=0)
        style.map("ActionDark.TButton", background=[("active", self.PALETTE["dark_button_hover"]), ("disabled", "#556176")], foreground=[("disabled", "#D2DBEA")])

        style.configure("ActionIndigo.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"), background=self.PALETTE["indigo"], foreground="#ffffff", borderwidth=0)
        style.map("ActionIndigo.TButton", background=[("active", self.PALETTE["indigo_dark"]), ("disabled", "#70422D")], foreground=[("disabled", "#FFE1D2")])

        style.configure(
            "Ram.Horizontal.TProgressbar",
            troughcolor=self.PALETTE["chip_bg"],
            background=self.PALETTE["status_ok"],
            lightcolor=self.PALETTE["status_ok"],
            darkcolor=self.PALETTE["status_ok"],
            thickness=10,
        )
        style.configure(
            "Vram.Horizontal.TProgressbar",
            troughcolor=self.PALETTE["chip_bg"],
            background=self.PALETTE["status_info"],
            lightcolor=self.PALETTE["status_info"],
            darkcolor=self.PALETTE["status_info"],
            thickness=10,
        )
        style.configure(
            "Disk.Horizontal.TProgressbar",
            troughcolor=self.PALETTE["chip_bg"],
            background=self.PALETTE["status_warn"],
            lightcolor=self.PALETTE["status_warn"],
            darkcolor=self.PALETTE["status_warn"],
            thickness=10,
        )

    def _create_scrollable_tab(self, tab: ttk.Frame) -> ttk.Frame:
        container = tk.Frame(tab, bg=self.PALETTE["bg"], highlightthickness=0, bd=0)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, bg=self.PALETTE["bg"], highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        content = ttk.Frame(canvas, style="App.TFrame")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _update_scrollregion(_: object) -> None:
            bbox = canvas.bbox("all")
            if bbox is not None:
                canvas.configure(scrollregion=bbox)

        def _sync_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", _update_scrollregion)
        canvas.bind("<Configure>", _sync_width)
        return content

    def _refresh_metric_layout(self, *_: object) -> None:
        if self._metric_strip is None:
            return

        width = self._metric_strip.winfo_width()
        if width <= 1:
            self.after(80, self._refresh_metric_layout)
            return

        if width >= 1280:
            columns = len(self.METRIC_ORDER)
        elif width >= 880:
            columns = 4
        else:
            columns = 2

        if columns == self._metric_column_count:
            return

        total_columns = len(self.METRIC_ORDER)
        for col in range(total_columns):
            self._metric_strip.columnconfigure(col, weight=0)

        for index, card in enumerate(self._metric_cards):
            row = index // columns
            col = index % columns
            card.grid_configure(
                row=row,
                column=col,
                padx=(0 if col == 0 else 8, 0),
                pady=(0 if row == 0 else 8, 0),
            )

        for col in range(columns):
            self._metric_strip.columnconfigure(col, weight=1)

        self._metric_column_count = columns

    def _refresh_operations_layout(self, *_: object) -> None:
        if (
            self._operations_board is None
            or self._operations_left is None
            or self._operations_mid is None
            or self._operations_right is None
            or self._operations_activity is None
        ):
            return

        width = self._operations_board.winfo_width()
        if width <= 1:
            self.after(80, self._refresh_operations_layout)
            return

        if width < 1160:
            mode = "stacked"
        elif width < 1560:
            mode = "double"
        else:
            mode = "wide"
        if mode == self._operations_layout_mode:
            return

        if mode == "stacked":
            self._operations_left.grid_configure(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
            self._operations_mid.grid_configure(row=1, column=0, sticky="nsew", padx=0, pady=(0, 10))
            self._operations_right.grid_configure(row=2, column=0, sticky="nsew", padx=0, pady=0)
            self._operations_activity.grid_configure(row=3, column=0, columnspan=1, sticky="nsew", pady=(14, 0))

            self._operations_board.columnconfigure(0, weight=1)
            self._operations_board.columnconfigure(1, weight=0)
            self._operations_board.columnconfigure(2, weight=0)
            self._operations_board.rowconfigure(0, weight=0)
            self._operations_board.rowconfigure(1, weight=0)
            self._operations_board.rowconfigure(2, weight=0)
            self._operations_board.rowconfigure(3, weight=1)
        elif mode == "double":
            self._operations_left.grid_configure(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
            self._operations_mid.grid_configure(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
            self._operations_right.grid_configure(row=1, column=0, columnspan=2, sticky="nsew", padx=0, pady=(10, 0))
            self._operations_activity.grid_configure(row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0))

            self._operations_board.columnconfigure(0, weight=1)
            self._operations_board.columnconfigure(1, weight=1)
            self._operations_board.columnconfigure(2, weight=0)
            self._operations_board.rowconfigure(0, weight=0)
            self._operations_board.rowconfigure(1, weight=0)
            self._operations_board.rowconfigure(2, weight=1)
            self._operations_board.rowconfigure(3, weight=0)
        else:
            self._operations_left.grid_configure(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
            self._operations_mid.grid_configure(row=0, column=1, sticky="nsew", padx=10, pady=0)
            self._operations_right.grid_configure(row=0, column=2, sticky="nsew", padx=(10, 0), pady=0)
            self._operations_activity.grid_configure(row=1, column=0, columnspan=3, sticky="nsew", pady=(14, 0))

            self._operations_board.columnconfigure(0, weight=1)
            self._operations_board.columnconfigure(1, weight=1)
            self._operations_board.columnconfigure(2, weight=1)
            self._operations_board.rowconfigure(0, weight=0)
            self._operations_board.rowconfigure(1, weight=1)
            self._operations_board.rowconfigure(2, weight=0)
            self._operations_board.rowconfigure(3, weight=0)

        self._operations_layout_mode = mode

    def _build_ui(self) -> None:
        app = ttk.Frame(self, style="App.TFrame")
        app.pack(fill="both", expand=True, padx=22, pady=18)

        self._build_header(app)
        self._build_metric_strip(app)

        self._notebook = ttk.Notebook(app, style="Main.TNotebook")
        self._notebook.pack(fill="both", expand=True, pady=(14, 0))

        self._build_operations_tab()
        self._build_hardware_tab()
        self._build_settings_tab()
        self._build_logs_tab()
    def _build_header(self, parent: ttk.Frame) -> None:
        header = tk.Frame(parent, bg=self.PALETTE["card"], highlightthickness=1, highlightbackground=self.PALETTE["border"], bd=0)
        header.pack(fill="x")

        left = tk.Frame(header, bg=self.PALETTE["card"])
        left.pack(side="left", fill="x", expand=True, padx=24, pady=16)

        tk.Label(left, text="Hyperlooms Node", bg=self.PALETTE["card"], fg=self.PALETTE["title"], font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(
            left,
            text="Enterprise Node Agent   |   AMD-style operations skin   |   local workload runtime",
            bg=self.PALETTE["card"],
            fg=self.PALETTE["muted"],
            font=("Segoe UI", 12),
        ).pack(anchor="w", pady=(4, 0))

        right = tk.Frame(header, bg=self.PALETTE["card"])
        right.pack(side="right", padx=20, pady=16)

        self._clock_label = tk.Label(right, text="--:--:--", bg=self.PALETTE["card"], fg=self.PALETTE["muted"], font=("Consolas", 12, "bold"))
        self._clock_label.pack(anchor="e")

        self._overall_badge = tk.Label(
            right,
            text="RUNTIME OFFLINE",
            bg=self.PALETTE["badge_off_bg"],
            fg=self.PALETTE["badge_off_fg"],
            padx=16,
            pady=8,
            font=("Segoe UI", 11, "bold"),
            highlightthickness=1,
            highlightbackground=self.PALETTE["status_error"],
        )
        self._overall_badge.pack(anchor="e", pady=(10, 0))

    def _build_metric_strip(self, parent: ttk.Frame) -> None:
        strip = tk.Frame(parent, bg=self.PALETTE["bg"])
        strip.pack(fill="x", pady=(14, 0))
        self._metric_strip = strip
        self._metric_cards = []

        self._metric_vars = {
            "coordinator": tk.StringVar(value="unknown"),
            "node_agent": tk.StringVar(value="stopped"),
            "discovery": tk.StringVar(value="unknown"),
            "registration": tk.StringVar(value="not-registered"),
            "runtime": tk.StringVar(value="stopped"),
            "trust": tk.StringVar(value="0.90"),
            "node_id": tk.StringVar(value="-"),
            "eligibility": tk.StringVar(value="-"),
        }

        for index, (key, title, icon) in enumerate(self.METRIC_ORDER):
            card = tk.Frame(strip, bg=self.PALETTE["card"], highlightthickness=1, highlightbackground=self.PALETTE["border"], bd=0, padx=14, pady=12)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))

            tk.Label(card, text=title.upper(), bg=self.PALETTE["card"], fg=self.PALETTE["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")

            value_row = tk.Frame(card, bg=self.PALETTE["card"])
            value_row.pack(anchor="w", pady=(8, 0), fill="x")

            icon_label = tk.Label(
                value_row,
                text=icon,
                bg=self.PALETTE["chip_bg"],
                fg=self.PALETTE["chip_fg"],
                font=("Consolas", 8, "bold"),
                padx=6,
                pady=2,
            )
            icon_label.pack(side="left")

            value_label = tk.Label(value_row, textvariable=self._metric_vars[key], bg=self.PALETTE["card"], fg=self.PALETTE["title"], font=("Segoe UI", 11, "bold"), padx=8)
            value_label.pack(side="left")

            self._metric_cards.append(card)
            self._metric_icon_labels[key] = icon_label
            self._metric_value_labels[key] = value_label
            strip.columnconfigure(index, weight=1)

        strip.bind("<Configure>", self._refresh_metric_layout)
        self.after(0, self._refresh_metric_layout)

    def _build_operations_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="App.TFrame")
        self._notebook.add(tab, text="Operations")

        tab_content = self._create_scrollable_tab(tab)

        board = ttk.Frame(tab_content, style="App.TFrame")
        board.pack(fill="both", expand=True, padx=6, pady=10)
        board.columnconfigure(0, weight=1)
        board.columnconfigure(1, weight=1)
        board.columnconfigure(2, weight=1)
        board.rowconfigure(0, weight=0)
        board.rowconfigure(1, weight=1)

        controls_col = ttk.Frame(board, style="App.TFrame")
        controls_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        controls_col.columnconfigure(0, weight=1)
        controls_col.rowconfigure(0, weight=1)
        self._build_controls_card(controls_col)

        onboarding_col = ttk.Frame(board, style="App.TFrame")
        onboarding_col.grid(row=0, column=1, sticky="nsew", padx=10)
        onboarding_col.columnconfigure(0, weight=1)
        onboarding_col.rowconfigure(0, weight=1)
        self._build_onboarding_card(onboarding_col)

        telemetry_col = ttk.Frame(board, style="App.TFrame")
        telemetry_col.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        telemetry_col.columnconfigure(0, weight=1)
        telemetry_col.rowconfigure(0, weight=0)
        telemetry_col.rowconfigure(1, weight=1)
        self._build_telemetry_card(telemetry_col)
        self._build_distributed_tasks_card(telemetry_col)

        activity_panel = self._build_activity_panel(board)

        self._operations_board = board
        self._operations_left = controls_col
        self._operations_mid = onboarding_col
        self._operations_right = telemetry_col
        self._operations_activity = activity_panel
        board.bind("<Configure>", self._refresh_operations_layout)
        self.after(0, self._refresh_operations_layout)

    def _build_controls_card(self, parent: ttk.Frame) -> None:
        controls = ttk.LabelFrame(parent, text="NODE CONTROLS", style="Card.TLabelframe")
        controls.grid(row=0, column=0, sticky="nsew")

        body = ttk.Frame(controls, style="CardBody.TFrame")
        body.pack(fill="x")

        row1 = ttk.Frame(body, style="CardBody.TFrame")
        row1.pack(fill="x", pady=(4, 0))

        self._start_services_btn = ttk.Button(row1, text="Start Services", style="ActionNeutral.TButton", command=self._start_services)
        self._stop_services_btn = ttk.Button(row1, text="Stop Services", style="ActionDanger.TButton", command=self._stop_services)
        self._refresh_status_btn = ttk.Button(row1, text="Refresh Status", style="ActionDark.TButton", command=self._controller.refresh_status)

        self._start_services_btn.pack(side="left", padx=(0, 8))
        self._stop_services_btn.pack(side="left", padx=(0, 8))
        self._refresh_status_btn.pack(side="left")

        row2 = ttk.Frame(body, style="CardBody.TFrame")
        row2.pack(fill="x", pady=(10, 0))
        self._guided_start_btn = ttk.Button(row2, text="Start Node Flow", style="ActionPrimary.TButton", command=self._start_guided_flow)
        self._run_discovery_btn = ttk.Button(row2, text="Run Discovery", style="ActionDark.TButton", command=self._controller.run_discovery)
        self._guided_start_btn.pack(side="left", padx=(0, 8))
        self._run_discovery_btn.pack(side="left")

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=14)

        self._demo_var = tk.BooleanVar(value=self._config.demo_mode)
        ttk.Checkbutton(body, text="Demo Mode (CPU)", variable=self._demo_var, command=self._toggle_demo).pack(anchor="w")

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=14)

        readiness = tk.Frame(
            body,
            bg=self.PALETTE["chip_bg"],
            highlightthickness=1,
            highlightbackground=self.PALETTE["border"],
            padx=10,
            pady=8,
        )
        readiness.pack(fill="x")

        tk.Label(
            readiness,
            text="RUN READINESS",
            bg=self.PALETTE["chip_bg"],
            fg=self.PALETTE["chip_fg"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        self._readiness_vars = {
            "consent": tk.StringVar(value="Pending"),
            "discovery": tk.StringVar(value="Pending"),
            "coordinator": tk.StringVar(value="Pending"),
            "services": tk.StringVar(value="Pending"),
            "registration": tk.StringVar(value="Pending"),
            "runtime": tk.StringVar(value="Pending"),
        }
        self._readiness_value_labels = {}

        labels = [
            ("consent", "Consent"),
            ("discovery", "Discovery"),
            ("coordinator", "Coordinator"),
            ("services", "Services"),
            ("registration", "Registration"),
            ("runtime", "Runtime"),
        ]
        for key, title in labels:
            row = tk.Frame(readiness, bg=self.PALETTE["chip_bg"])
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text=f"{title}:",
                bg=self.PALETTE["chip_bg"],
                fg=self.PALETTE["muted"],
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left")
            value_label = tk.Label(
                row,
                textvariable=self._readiness_vars[key],
                bg=self.PALETTE["chip_bg"],
                fg=self.PALETTE["muted"],
                font=("Segoe UI", 9),
            )
            value_label.pack(side="right")
            self._readiness_value_labels[key] = value_label

    def _build_onboarding_card(self, parent: ttk.Frame) -> None:
        onboarding = ttk.LabelFrame(parent, text="ONBOARDING & REGISTRATION", style="Card.TLabelframe")
        onboarding.grid(row=0, column=0, sticky="nsew")

        body = ttk.Frame(onboarding, style="CardBody.TFrame")
        body.pack(fill="x")

        ttk.Label(body, text="User Name", style="Field.TLabel").pack(anchor="w")

        row1 = ttk.Frame(body, style="CardBody.TFrame")
        row1.pack(fill="x", pady=(6, 0))
        self._user_name = ttk.Entry(row1, width=28)
        self._user_name.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self._accept_consent_btn = ttk.Button(row1, text="Accept Consent", style="ActionPrimary.TButton", command=self._accept_consent)
        self._accept_consent_btn.pack(side="right")

        self._terms_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="I accept platform terms and conditions", variable=self._terms_var).pack(anchor="w", pady=(14, 0))

        row2 = ttk.Frame(body, style="CardBody.TFrame")
        row2.pack(fill="x", pady=(14, 0))

        self._register_btn = ttk.Button(row2, text="Register Node", style="ActionIndigo.TButton", command=self._controller.register_node)
        self._start_runtime_btn = ttk.Button(row2, text="Start Runtime", style="ActionNeutral.TButton", command=self._controller.start_runtime)
        self._stop_runtime_btn = ttk.Button(row2, text="Stop Runtime", style="ActionDanger.TButton", command=self._controller.stop_runtime)
        self._submit_job_btn = ttk.Button(row2, text="Submit Test Job", style="ActionDark.TButton", command=self._controller.submit_test_job)

        self._register_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))
        self._start_runtime_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))
        self._stop_runtime_btn.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self._submit_job_btn.grid(row=1, column=1, sticky="ew", padx=(6, 0))
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)

    def _build_telemetry_card(self, parent: ttk.Frame) -> None:
        telemetry = ttk.LabelFrame(parent, text="LIVE TELEMETRY", style="Card.TLabelframe")
        telemetry.grid(row=0, column=0, sticky="nsew")
        parent.rowconfigure(0, weight=0)

        body = ttk.Frame(telemetry, style="CardBody.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(7, weight=1)

        top = ttk.Frame(body, style="CardBody.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        self._job_badge = tk.Label(
            top,
            text="Current Job: idle",
            bg=self.PALETTE["chip_bg"],
            fg=self.PALETTE["chip_fg"],
            padx=8,
            pady=3,
            font=("Segoe UI", 9, "bold"),
        )
        self._job_badge.grid(row=0, column=1, sticky="e")

        self._ram_progress = tk.DoubleVar(value=0.0)
        self._vram_progress = tk.DoubleVar(value=0.0)
        self._disk_progress = tk.DoubleVar(value=0.0)

        self._telemetry_labels = {
            "ram": tk.StringVar(value="0.00 / 0.00 GB"),
            "vram": tk.StringVar(value="0.00 / 0.00 GB"),
            "disk": tk.StringVar(value="0.00 / 0.00 GB"),
            "job": tk.StringVar(value="idle"),
            "net_up": tk.StringVar(value="0 KB/s"),
            "net_down": tk.StringVar(value="0 KB/s"),
        }
        self._add_telemetry_row(body, row=1, label="RAM", text_var=self._telemetry_labels["ram"], progress_var=self._ram_progress, style_name="Ram.Horizontal.TProgressbar")
        self._add_telemetry_row(body, row=3, label="VRAM", text_var=self._telemetry_labels["vram"], progress_var=self._vram_progress, style_name="Vram.Horizontal.TProgressbar")
        self._add_telemetry_row(body, row=5, label="Disk", text_var=self._telemetry_labels["disk"], progress_var=self._disk_progress, style_name="Disk.Horizontal.TProgressbar")

        footer = ttk.Frame(body, style="CardBody.TFrame")
        footer.grid(row=7, column=0, sticky="ew", pady=(26, 0))
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)

        up_card = tk.Frame(
            footer,
            bg=self.PALETTE["card"],
            highlightthickness=1,
            highlightbackground=self.PALETTE["border"],
            padx=14,
            pady=12,
        )
        up_card.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        tk.Label(up_card, text="NETWORK UP", bg=self.PALETTE["card"], fg=self.PALETTE["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="center")
        tk.Label(
            up_card,
            textvariable=self._telemetry_labels["net_up"],
            bg=self.PALETTE["card"],
            fg=self.PALETTE["status_ok"],
            font=("Consolas", 17, "bold"),
        ).pack(anchor="center", pady=(4, 0))

        down_card = tk.Frame(
            footer,
            bg=self.PALETTE["card"],
            highlightthickness=1,
            highlightbackground=self.PALETTE["border"],
            padx=14,
            pady=12,
        )
        down_card.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        tk.Label(down_card, text="NETWORK DOWN", bg=self.PALETTE["card"], fg=self.PALETTE["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="center")
        tk.Label(
            down_card,
            textvariable=self._telemetry_labels["net_down"],
            bg=self.PALETTE["card"],
            fg=self.PALETTE["status_info"],
            font=("Consolas", 17, "bold"),
        ).pack(anchor="center", pady=(4, 0))

    def _build_distributed_tasks_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="DISTRIBUTED TASKS", style="Card.TLabelframe")
        card.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        parent.rowconfigure(1, weight=1)

        body = ttk.Frame(card, style="CardBody.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)

        head = ttk.Frame(body, style="CardBody.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        head.columnconfigure(0, weight=1)

        ttk.Label(head, textvariable=self._tasks_summary_var, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(
            head,
            text="Refresh Tasks",
            style="ActionDark.TButton",
            command=self._controller.refresh_distributed_tasks,
        ).grid(row=0, column=1, sticky="e")

        list_wrap = ttk.Frame(body, style="CardBody.TFrame")
        list_wrap.grid(row=1, column=0, sticky="nsew")
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        self._tasks_list = tk.Listbox(
            list_wrap,
            font=("Consolas", 10),
            bg=self.PALETTE["terminal_bg"],
            fg=self.PALETTE["terminal_text"],
            selectbackground="#243147",
            selectforeground=self.PALETTE["title"],
            activestyle="none",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.PALETTE["border"],
        )
        self._tasks_list.grid(row=0, column=0, sticky="nsew")
        self._tasks_list.bind("<<ListboxSelect>>", self._on_task_selected)

        list_scroll = ttk.Scrollbar(list_wrap, command=self._tasks_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self._tasks_list.configure(yscrollcommand=list_scroll.set)

        detail_wrap = ttk.Frame(body, style="CardBody.TFrame")
        detail_wrap.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        detail_wrap.columnconfigure(0, weight=1)
        detail_wrap.rowconfigure(0, weight=1)

        self._tasks_detail = tk.Text(
            detail_wrap,
            height=6,
            wrap="word",
            font=("Consolas", 10),
            bg=self.PALETTE["input_bg"],
            fg=self.PALETTE["terminal_text"],
            insertbackground=self.PALETTE["status_ok"],
            bd=0,
            highlightthickness=1,
            highlightbackground=self.PALETTE["border"],
            padx=8,
            pady=6,
        )
        self._tasks_detail.grid(row=0, column=0, sticky="nsew")
        self._tasks_detail.configure(state="disabled")

    def _add_telemetry_row(self, parent: ttk.Frame, row: int, label: str, text_var: tk.StringVar, progress_var: tk.DoubleVar, style_name: str) -> None:
        head = ttk.Frame(parent, style="CardBody.TFrame")
        head.grid(row=row, column=0, sticky="ew", pady=(14 if row > 1 else 10, 4))
        head.columnconfigure(0, weight=1)

        ttk.Label(head, text=label, style="Value.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(head, textvariable=text_var, style="Section.TLabel").grid(row=0, column=1, sticky="e")

        ttk.Progressbar(parent, variable=progress_var, maximum=100, style=style_name).grid(row=row + 1, column=0, sticky="ew")

    def _build_activity_panel(self, board: ttk.Frame) -> tk.Frame:
        panel = tk.Frame(
            board,
            bg=self.PALETTE["terminal_bg"],
            highlightthickness=1,
            highlightbackground=self.PALETTE["border"],
            bd=0,
        )
        panel.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(14, 0))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        head = tk.Frame(panel, bg=self.PALETTE["terminal_head"], height=36)
        head.grid(row=0, column=0, sticky="ew")
        head.pack_propagate(False)

        circles = tk.Frame(head, bg=self.PALETTE["terminal_head"])
        circles.pack(side="left", padx=10)
        tk.Label(circles, text="o", fg=self.PALETTE["status_error"], bg=self.PALETTE["terminal_head"], font=("Consolas", 10, "bold")).pack(side="left", padx=2)
        tk.Label(circles, text="o", fg=self.PALETTE["status_warn"], bg=self.PALETTE["terminal_head"], font=("Consolas", 10, "bold")).pack(side="left", padx=2)
        tk.Label(circles, text="o", fg=self.PALETTE["status_ok"], bg=self.PALETTE["terminal_head"], font=("Consolas", 10, "bold")).pack(side="left", padx=2)

        tk.Label(head, text="ACTIVITY STREAM", bg=self.PALETTE["terminal_head"], fg=self.PALETTE["chip_fg"], font=("Segoe UI", 10, "bold")).pack(side="left", padx=12)
        tk.Label(head, text="SSH: LOCALHOST:22", bg=self.PALETTE["terminal_head"], fg=self.PALETTE["muted"], font=("Consolas", 9, "bold")).pack(side="right", padx=10)

        content = tk.Frame(panel, bg=self.PALETTE["terminal_bg"])
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        self._console = tk.Text(
            content,
            wrap="none",
            font=("Consolas", 12),
            bg=self.PALETTE["terminal_bg"],
            fg=self.PALETTE["terminal_text"],
            insertbackground=self.PALETTE["status_ok"],
            relief="flat",
            padx=12,
            pady=12,
        )
        self._console.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(content, command=self._console.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._console.configure(yscrollcommand=scroll.set, state="disabled")

        self._console.tag_configure("line", foreground=self.PALETTE["terminal_text"])
        self._console.tag_configure("ok", foreground=self.PALETTE["status_ok"])
        self._console.tag_configure("warn", foreground=self.PALETTE["status_warn"])
        self._console.tag_configure("error", foreground=self.PALETTE["status_error"])
        self._console.tag_configure("telemetry", foreground=self.PALETTE["status_info"])
        self._console.tag_configure("cursor", foreground=self.PALETTE["status_ok"])
        return panel

    def _build_hardware_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="App.TFrame")
        self._notebook.add(tab, text="Hardware")

        controls = ttk.Frame(tab, style="App.TFrame")
        controls.pack(fill="x", padx=10, pady=8)
        ttk.Button(controls, text="Fetch Device Details", style="ActionDark.TButton", command=self._controller.fetch_device_details).pack(side="left", padx=4)
        ttk.Button(controls, text="Run Discovery", style="ActionDark.TButton", command=self._controller.run_discovery).pack(side="left", padx=4)

        snapshot_frame = ttk.LabelFrame(tab, text="Device Snapshot", style="Card.TLabelframe")
        snapshot_frame.pack(fill="both", expand=True, padx=10, pady=8)
        self._snapshot_text = tk.Text(
            snapshot_frame,
            wrap="none",
            font=("Consolas", 11),
            bg=self.PALETTE["card"],
            fg=self.PALETTE["title"],
            insertbackground=self.PALETTE["status_ok"],
        )
        self._snapshot_text.pack(fill="both", expand=True, side="left")
        snap_scroll = ttk.Scrollbar(snapshot_frame, command=self._snapshot_text.yview)
        snap_scroll.pack(side="right", fill="y")
        self._snapshot_text.configure(yscrollcommand=snap_scroll.set, state="disabled")

        debug_frame = ttk.LabelFrame(tab, text="Hardware Trace", style="Card.TLabelframe")
        debug_frame.pack(fill="both", expand=True, padx=10, pady=8)
        self._debug_text = tk.Text(
            debug_frame,
            wrap="none",
            font=("Consolas", 11),
            bg=self.PALETTE["terminal_bg"],
            fg=self.PALETTE["terminal_text"],
            insertbackground=self.PALETTE["status_ok"],
        )
        self._debug_text.pack(fill="both", expand=True, side="left")
        dbg_scroll = ttk.Scrollbar(debug_frame, command=self._debug_text.yview)
        dbg_scroll.pack(side="right", fill="y")
        self._debug_text.configure(yscrollcommand=dbg_scroll.set, state="disabled")

    def _build_models_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="App.TFrame")
        self._notebook.add(tab, text="Models")

        outer = ttk.LabelFrame(tab, text="Model Management", style="Card.TLabelframe")
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        body = ttk.Frame(outer, style="CardBody.TFrame")
        body.pack(fill="both", expand=True)

        self._models_list = tk.Listbox(body, height=14, font=("Segoe UI", 10), bd=0, highlightthickness=1, highlightbackground=self.PALETTE["border"])
        self._models_list.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        actions = ttk.Frame(body, style="CardBody.TFrame")
        actions.pack(side="right", fill="y", padx=10, pady=10)
        ttk.Label(actions, text="Model Name", style="Field.TLabel").pack(anchor="w")
        self._model_entry = ttk.Entry(actions, width=32)
        self._model_entry.pack(fill="x", pady=4)

        ttk.Button(actions, text="Refresh Installed Models", style="ActionDark.TButton", command=self._controller.request_models).pack(fill="x", pady=4)
        ttk.Button(actions, text="Use Selected as Default", style="ActionIndigo.TButton", command=self._use_selected_model).pack(fill="x", pady=4)

        self._model_status = ttk.Label(actions, text="", style="Section.TLabel")
        self._model_status.pack(anchor="w", pady=8)
    def _build_settings_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="App.TFrame")
        self._notebook.add(tab, text="Settings")
        tab_content = self._create_scrollable_tab(tab)

        self._settings_vars = {
            "coordinator_url": tk.StringVar(value=self._config.coordinator_url),
            "api_token": tk.StringVar(value=self._config.api_token),
            "node_join_token": tk.StringVar(value=self._config.node_join_token),
            "node_auth_token": tk.StringVar(value=self._config.node_auth_token),
            "tls_verify": tk.BooleanVar(value=self._config.tls_verify),
            "tls_ca_cert_path": tk.StringVar(value=self._config.tls_ca_cert_path),
            "tls_client_cert_path": tk.StringVar(value=self._config.tls_client_cert_path),
            "tls_client_key_path": tk.StringVar(value=self._config.tls_client_key_path),
            "execution_mode": tk.StringVar(value=self._config.execution_mode),
            "model_name": tk.StringVar(value=self._config.model_name),
            "container_image": tk.StringVar(value=self._config.container_image),
            "container_timeout": tk.StringVar(value=str(self._config.container_timeout_sec)),
            "container_cpus": tk.StringVar(value=str(self._config.container_cpus)),
            "container_memory_mb": tk.StringVar(value=str(self._config.container_memory_mb)),
            "container_enable_gpu": tk.BooleanVar(value=self._config.container_enable_gpu),
            "container_network": tk.StringVar(value=self._config.container_network),
            "container_readonly_rootfs": tk.BooleanVar(value=self._config.container_readonly_rootfs),
            "container_pids_limit": tk.StringVar(value=str(self._config.container_pids_limit)),
            "container_no_new_privileges": tk.BooleanVar(value=self._config.container_no_new_privileges),
            "container_fallback_to_local": tk.BooleanVar(value=self._config.container_fallback_to_local),
            "heartbeat_interval": tk.StringVar(value=str(self._config.heartbeat_interval_sec)),
            "job_poll_interval": tk.StringVar(value=str(self._config.job_poll_interval_sec)),
            "region": tk.StringVar(value=self._config.region),
            "node_id": tk.StringVar(value=self._config.node_id or ""),
            "require_gpu": tk.BooleanVar(value=self._config.require_gpu),
            "min_vram": tk.StringVar(value=str(self._config.min_vram_gb)),
            "min_ram": tk.StringVar(value=str(self._config.min_ram_gb)),
            "min_disk": tk.StringVar(value=str(self._config.min_disk_gb)),
        }

        form = ttk.LabelFrame(tab_content, text="Runtime Configuration", style="Card.TLabelframe")
        form.pack(fill="x", expand=True, padx=10, pady=10)

        body = ttk.Frame(form, style="CardBody.TFrame")
        body.pack(fill="both", expand=True)

        fields = [
            ("Coordinator URL", "coordinator_url"),
            ("API Token", "api_token"),
            ("Node Join Token", "node_join_token"),
            ("Node Auth Token", "node_auth_token"),
            ("TLS Verify", "tls_verify"),
            ("TLS CA Cert Path", "tls_ca_cert_path"),
            ("TLS Client Cert Path", "tls_client_cert_path"),
            ("TLS Client Key Path", "tls_client_key_path"),
            ("Execution Mode", "execution_mode"),
            ("Default Workload Model", "model_name"),
            ("Container Image", "container_image"),
            ("Container Timeout (sec)", "container_timeout"),
            ("Container CPUs", "container_cpus"),
            ("Container Memory (MB)", "container_memory_mb"),
            ("Container GPU Access", "container_enable_gpu"),
            ("Container Network", "container_network"),
            ("Container Readonly RootFS", "container_readonly_rootfs"),
            ("Container PIDs Limit", "container_pids_limit"),
            ("Container No New Privileges", "container_no_new_privileges"),
            ("Container Fallback Local", "container_fallback_to_local"),
            ("Heartbeat Interval (sec)", "heartbeat_interval"),
            ("Job Poll Interval (sec)", "job_poll_interval"),
            ("Region", "region"),
            ("Require GPU", "require_gpu"),
            ("Min VRAM (GB)", "min_vram"),
            ("Min RAM (GB)", "min_ram"),
            ("Min Disk (GB)", "min_disk"),
            ("Node ID", "node_id"),
        ]

        for idx, (label, key) in enumerate(fields):
            ttk.Label(body, text=label + ":", style="Field.TLabel", width=24).grid(row=idx, column=0, sticky="w", padx=10, pady=7)
            if key in {
                "auto_download",
                "require_gpu",
                "tls_verify",
                "container_enable_gpu",
                "container_readonly_rootfs",
                "container_no_new_privileges",
                "container_fallback_to_local",
            }:
                ttk.Checkbutton(body, variable=self._settings_vars[key]).grid(row=idx, column=1, sticky="w", padx=4)
            elif key in {"api_token", "node_join_token", "node_auth_token"}:
                ttk.Entry(body, textvariable=self._settings_vars[key], show="*").grid(row=idx, column=1, sticky="ew", padx=4)
            else:
                entry = ttk.Entry(body, textvariable=self._settings_vars[key])
                if key == "node_id":
                    entry.configure(state="readonly")
                entry.grid(row=idx, column=1, sticky="ew", padx=4)

        body.columnconfigure(1, weight=1)

        actions = ttk.Frame(body, style="CardBody.TFrame")
        actions.grid(row=len(fields), column=0, columnspan=2, sticky="w", padx=10, pady=12)
        ttk.Button(actions, text="Save Settings", style="ActionPrimary.TButton", command=self._save_settings).pack(side="left", padx=4)
        ttk.Button(actions, text="Reload Settings", style="ActionDark.TButton", command=self._reload_config).pack(side="left", padx=4)

    def _build_logs_tab(self) -> None:
        tab = ttk.Frame(self._notebook, style="App.TFrame")
        self._notebook.add(tab, text="Logs")

        frame = ttk.LabelFrame(tab, text="Node Agent Logs", style="Card.TLabelframe")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self._log_text = tk.Text(
            frame,
            wrap="none",
            font=("Consolas", 10),
            bg=self.PALETTE["terminal_bg"],
            fg=self.PALETTE["terminal_text"],
            insertbackground=self.PALETTE["status_ok"],
        )
        self._log_text.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(frame, command=self._log_text.yview)
        scroll.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=scroll.set, state="disabled")

    def _append_console(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._console_lines.append(f"[{timestamp}] {message}")
        self._console_lines = self._console_lines[-1200:]
        self._render_console()

    def _render_console(self) -> None:
        if not hasattr(self, "_console"):
            return

        self._console.configure(state="normal")
        self._console.delete("1.0", tk.END)

        for line in self._console_lines:
            lower = line.lower()
            tag = "line"
            if "failed" in lower or "error" in lower:
                tag = "error"
            elif "status_update" in lower or "registered" in lower or "completed" in lower:
                tag = "ok"
            elif "telemetry" in lower:
                tag = "telemetry"
            elif "ineligible" in lower or "warning" in lower:
                tag = "warn"
            self._console.insert(tk.END, line + "\n", tag)

        self._console.insert(tk.END, "_", "cursor")
        self._console.see(tk.END)
        self._console.configure(state="disabled")

    def _start_guided_flow(self) -> None:
        if self._state.consent_status != "accepted":
            name = self._user_name.get().strip()
            if not name:
                messagebox.showerror("Missing Name", "Enter user name before starting node flow.")
                return
            if not self._terms_var.get():
                messagebox.showerror("Terms Required", "Please accept platform terms before starting node flow.")
                return
            self._controller.accept_consent(name)

        self._append_console("guided_flow_started")
        self._controller.run_discovery()
        self._controller.refresh_status()
        self._controller.start_runtime()

    def _refresh_readiness_panel(self) -> None:
        if not self._readiness_vars:
            return

        consent_ready = self._state.consent_status == "accepted"
        discovery_ready = self._state.discovery_status == "eligible" or self._config.demo_mode
        coordinator_ready = self._state.coordinator_status == "ok"
        services_ready = self._state.node_agent_status in {"ok", "starting"}
        registration_ready = self._state.registration_status in {"registered", "already_registered"} or self._state.registered
        runtime_ready = self._state.runtime_status == "running"

        statuses = {
            "consent": (consent_ready, "Accepted" if consent_ready else "Pending"),
            "discovery": (discovery_ready, self._state.eligibility_reason or ("eligible" if discovery_ready else "pending")),
            "coordinator": (coordinator_ready, self._state.coordinator_status),
            "services": (services_ready, self._state.node_agent_status),
            "registration": (registration_ready, self._state.registration_status),
            "runtime": (runtime_ready, self._state.runtime_status),
        }

        for key, (ready, detail) in statuses.items():
            if key not in self._readiness_vars:
                continue
            self._readiness_vars[key].set(f"{'READY' if ready else 'WAIT'} - {detail}")
            label = self._readiness_value_labels.get(key)
            if label:
                label.configure(fg=self.PALETTE["status_ok"] if ready else self.PALETTE["status_warn"])

    def _start_services(self) -> None:
        self._controller.start_services()

    def _stop_services(self) -> None:
        self._controller.stop_services()

    def _toggle_demo(self) -> None:
        enabled = bool(self._demo_var.get())
        self._config.demo_mode = enabled
        save_config(self._config)
        self._controller.set_demo_mode(enabled)

    def _accept_consent(self) -> None:
        name = self._user_name.get().strip()
        if not name:
            messagebox.showerror("Missing Name", "Enter your name before accepting consent.")
            return
        if not self._terms_var.get():
            messagebox.showerror("Terms Required", "Please accept platform terms.")
            return
        self._controller.accept_consent(name)

    def _use_selected_model(self) -> None:
        selection = self._models_list.curselection()
        if not selection:
            return
        model_name = self._models_list.get(selection[0])
        self._settings_vars["model_name"].set(model_name)
        self._model_status.configure(text=f"Selected model: {model_name}")
    def _save_settings(self) -> None:
        try:
            self._config.coordinator_url = self._settings_vars["coordinator_url"].get().strip()
            self._config.api_token = self._settings_vars["api_token"].get().strip()
            self._config.node_join_token = self._settings_vars["node_join_token"].get().strip()
            self._config.node_auth_token = self._settings_vars["node_auth_token"].get().strip()
            self._config.tls_verify = bool(self._settings_vars["tls_verify"].get())
            self._config.tls_ca_cert_path = self._settings_vars["tls_ca_cert_path"].get().strip()
            self._config.tls_client_cert_path = self._settings_vars["tls_client_cert_path"].get().strip()
            self._config.tls_client_key_path = self._settings_vars["tls_client_key_path"].get().strip()
            self._config.model_name = self._settings_vars["model_name"].get().strip() or "fabric-workload-v1"
            self._config.provider_hint = "fabric"
            self._config.execution_mode = self._settings_vars["execution_mode"].get().strip() or "local"
            self._config.container_image = self._settings_vars["container_image"].get().strip() or "computefabric-node-sandbox:latest"
            self._config.container_timeout_sec = int(self._settings_vars["container_timeout"].get())
            self._config.container_cpus = float(self._settings_vars["container_cpus"].get())
            self._config.container_memory_mb = int(self._settings_vars["container_memory_mb"].get())
            self._config.container_enable_gpu = bool(self._settings_vars["container_enable_gpu"].get())
            self._config.container_network = self._settings_vars["container_network"].get().strip() or "bridge"
            self._config.container_readonly_rootfs = bool(self._settings_vars["container_readonly_rootfs"].get())
            self._config.container_pids_limit = int(self._settings_vars["container_pids_limit"].get())
            self._config.container_no_new_privileges = bool(self._settings_vars["container_no_new_privileges"].get())
            self._config.container_fallback_to_local = bool(self._settings_vars["container_fallback_to_local"].get())
            self._config.heartbeat_interval_sec = int(self._settings_vars["heartbeat_interval"].get())
            self._config.job_poll_interval_sec = int(self._settings_vars["job_poll_interval"].get())
            self._config.region = self._settings_vars["region"].get().strip() or "local"
            self._config.require_gpu = bool(self._settings_vars["require_gpu"].get())
            self._config.min_vram_gb = float(self._settings_vars["min_vram"].get())
            self._config.min_ram_gb = float(self._settings_vars["min_ram"].get())
            self._config.min_disk_gb = float(self._settings_vars["min_disk"].get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Check numeric settings fields.")
            return

        save_config(self._config)
        messagebox.showinfo("Saved", "Settings saved. Restart services for guaranteed consistency.")

    def _reload_config(self) -> None:
        self._config = load_config()
        self._settings_vars["coordinator_url"].set(self._config.coordinator_url)
        self._settings_vars["api_token"].set(self._config.api_token)
        self._settings_vars["node_join_token"].set(self._config.node_join_token)
        self._settings_vars["node_auth_token"].set(self._config.node_auth_token)
        self._settings_vars["tls_verify"].set(self._config.tls_verify)
        self._settings_vars["tls_ca_cert_path"].set(self._config.tls_ca_cert_path)
        self._settings_vars["tls_client_cert_path"].set(self._config.tls_client_cert_path)
        self._settings_vars["tls_client_key_path"].set(self._config.tls_client_key_path)
        self._settings_vars["execution_mode"].set(self._config.execution_mode)
        self._settings_vars["model_name"].set(self._config.model_name)
        self._settings_vars["container_image"].set(self._config.container_image)
        self._settings_vars["container_timeout"].set(str(self._config.container_timeout_sec))
        self._settings_vars["container_cpus"].set(str(self._config.container_cpus))
        self._settings_vars["container_memory_mb"].set(str(self._config.container_memory_mb))
        self._settings_vars["container_enable_gpu"].set(self._config.container_enable_gpu)
        self._settings_vars["container_network"].set(self._config.container_network)
        self._settings_vars["container_readonly_rootfs"].set(self._config.container_readonly_rootfs)
        self._settings_vars["container_pids_limit"].set(str(self._config.container_pids_limit))
        self._settings_vars["container_no_new_privileges"].set(self._config.container_no_new_privileges)
        self._settings_vars["container_fallback_to_local"].set(self._config.container_fallback_to_local)
        self._settings_vars["heartbeat_interval"].set(str(self._config.heartbeat_interval_sec))
        self._settings_vars["job_poll_interval"].set(str(self._config.job_poll_interval_sec))
        self._settings_vars["region"].set(self._config.region)
        self._settings_vars["node_id"].set(self._config.node_id or "")
        self._settings_vars["require_gpu"].set(self._config.require_gpu)
        self._settings_vars["min_vram"].set(str(self._config.min_vram_gb))
        self._settings_vars["min_ram"].set(str(self._config.min_ram_gb))
        self._settings_vars["min_disk"].set(str(self._config.min_disk_gb))

    def _refresh_logs(self) -> None:
        log_content = _tail_file(get_log_dir() / "node.log")
        if log_content != self._log_cache:
            self._log_cache = log_content
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", tk.END)
            self._log_text.insert(tk.END, log_content)
            self._log_text.see(tk.END)
            self._log_text.configure(state="disabled")

        self.after(1500, self._refresh_logs)

    def _format_rate(self, bytes_per_sec: float) -> str:
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        if bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.0f} KB/s"
        if bytes_per_sec < 1024 * 1024 * 1024:
            return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
        return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"

    def _update_network_telemetry(self) -> None:
        try:
            counters = psutil.net_io_counters()
        except Exception:
            self._telemetry_labels["net_up"].set("-")
            self._telemetry_labels["net_down"].set("-")
            return

        now = time.monotonic()
        if not self._net_initialized:
            self._last_net_sent = counters.bytes_sent
            self._last_net_recv = counters.bytes_recv
            self._last_net_ts = now
            self._net_initialized = True
            self._telemetry_labels["net_up"].set("0 KB/s")
            self._telemetry_labels["net_down"].set("0 KB/s")
            return

        elapsed = max(now - self._last_net_ts, 1e-6)
        up_rate = max(0.0, counters.bytes_sent - self._last_net_sent) / elapsed
        down_rate = max(0.0, counters.bytes_recv - self._last_net_recv) / elapsed

        self._last_net_sent = counters.bytes_sent
        self._last_net_recv = counters.bytes_recv
        self._last_net_ts = now

        self._telemetry_labels["net_up"].set(self._format_rate(up_rate))
        self._telemetry_labels["net_down"].set(self._format_rate(down_rate))

    def _refresh_status(self) -> None:
        state = self._state

        self._metric_vars["coordinator"].set(state.coordinator_status)
        self._metric_vars["node_agent"].set(state.node_agent_status)
        self._metric_vars["discovery"].set(state.discovery_status)
        self._metric_vars["registration"].set(state.registration_status)
        self._metric_vars["runtime"].set(state.runtime_status)
        self._metric_vars["trust"].set(f"{state.trust_score:.2f}")
        self._metric_vars["node_id"].set(state.node_id or "-")
        self._metric_vars["eligibility"].set(state.eligibility_reason or "-")

        ram_used = max(0.0, state.ram_total_gb - state.ram_free_gb)
        disk_used = max(0.0, state.disk_total_gb - state.disk_free_gb)
        self._ram_progress.set(_safe_pct(ram_used, state.ram_total_gb))
        self._vram_progress.set(_safe_pct(state.vram_used_gb, state.vram_total_gb))
        self._disk_progress.set(_safe_pct(disk_used, state.disk_total_gb))

        self._telemetry_labels["ram"].set(f"{ram_used:.2f} / {state.ram_total_gb:.2f} GB")
        self._telemetry_labels["vram"].set(f"{state.vram_used_gb:.2f} / {state.vram_total_gb:.2f} GB")
        self._telemetry_labels["disk"].set(f"{disk_used:.2f} / {state.disk_total_gb:.2f} GB")

        self._update_network_telemetry()

        self._job_badge.configure(text=f"Current Job: {state.current_job_status or 'idle'}")
        self._clock_label.configure(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        self._refresh_badge()
        self._refresh_button_states()
        self._refresh_metric_tones()
        self._refresh_readiness_panel()
        self.after(600, self._refresh_status)

    def _refresh_badge(self) -> None:
        if self._state.runtime_status == "running":
            self._overall_badge.configure(
                text="RUNTIME ACTIVE",
                bg=self.PALETTE["badge_ok_bg"],
                fg=self.PALETTE["badge_ok_fg"],
                highlightbackground=self.PALETTE["status_ok"],
            )
            self._job_badge.configure(bg=self.PALETTE["badge_ok_bg"], fg=self.PALETTE["badge_ok_fg"])
        elif self._state.node_agent_status in {"ok", "starting"}:
            self._overall_badge.configure(
                text="SERVICES ONLINE",
                bg=self.PALETTE["chip_bg"],
                fg=self.PALETTE["status_info"],
                highlightbackground=self.PALETTE["status_info"],
            )
            self._job_badge.configure(bg=self.PALETTE["chip_bg"], fg=self.PALETTE["chip_fg"])
        else:
            self._overall_badge.configure(
                text="RUNTIME OFFLINE",
                bg=self.PALETTE["badge_off_bg"],
                fg=self.PALETTE["badge_off_fg"],
                highlightbackground=self.PALETTE["status_error"],
            )
            self._job_badge.configure(bg=self.PALETTE["badge_off_bg"], fg=self.PALETTE["badge_off_fg"])

    def _refresh_metric_tones(self) -> None:
        for key, _, _ in self.METRIC_ORDER:
            value = self._metric_vars[key].get().lower()
            color = self.PALETTE["muted"]
            if key == "coordinator":
                color = self.PALETTE["status_ok"] if value == "ok" else self.PALETTE["status_error"]
            elif key == "node_agent":
                color = self.PALETTE["status_ok"] if value in {"ok", "starting"} else self.PALETTE["status_error"]
            elif key == "discovery":
                color = self.PALETTE["status_ok"] if value == "eligible" else (self.PALETTE["status_error"] if value == "ineligible" else self.PALETTE["muted"])
            elif key == "registration":
                color = self.PALETTE["status_ok"] if value in {"registered", "already_registered"} else self.PALETTE["status_error"]
            elif key == "runtime":
                color = (
                    self.PALETTE["status_ok"]
                    if value == "running"
                    else (
                        self.PALETTE["status_warn"]
                        if value in {"starting", "stopping", "awaiting-registration"}
                        else (self.PALETTE["status_error"] if value == "awaiting-services" else self.PALETTE["muted"])
                    )
                )
            elif key == "trust":
                try:
                    trust = float(self._metric_vars[key].get())
                except ValueError:
                    trust = 0.0
                color = self.PALETTE["status_ok"] if trust >= 0.85 else (self.PALETTE["status_warn"] if trust >= 0.6 else self.PALETTE["status_error"])
            elif key == "eligibility":
                color = self.PALETTE["status_ok"] if value in {"ok", "demo_mode"} else self.PALETTE["status_error"]

            self._metric_icon_labels[key].configure(fg=color)
            self._metric_value_labels[key].configure(fg=color if key != "node_id" else self.PALETTE["title"])

    def _refresh_button_states(self) -> None:
        services_on = self._state.node_agent_status in {"ok", "starting"}
        runtime_on = self._state.runtime_status == "running"
        runtime_transition = self._state.runtime_status in {"starting", "stopping", "awaiting-registration", "awaiting-services"}
        consent_ready = self._state.consent_status == "accepted"
        registered = self._state.registration_status in {"registered", "already_registered"}
        discovery_ready = self._state.discovery_status == "eligible" or self._config.demo_mode
        coordinator_ready = self._state.coordinator_status in {"ok", "unknown"}
        runtime_start_ready = consent_ready and discovery_ready and coordinator_ready and not runtime_transition

        self._start_services_btn.configure(state=("disabled" if services_on else "normal"))
        self._stop_services_btn.configure(state=("normal" if services_on else "disabled"))
        self._start_runtime_btn.configure(state=("normal" if runtime_start_ready and not runtime_on else "disabled"))
        self._stop_runtime_btn.configure(state=("normal" if runtime_on or runtime_transition else "disabled"))
        self._register_btn.configure(state=("normal" if consent_ready else "disabled"))
        self._submit_job_btn.configure(state=("normal" if runtime_on else "disabled"))
        if self._guided_start_btn:
            self._guided_start_btn.configure(state=("normal" if runtime_start_ready and not runtime_on else "disabled"))

    def _task_sort_key(self, item: dict) -> tuple[str, str]:
        updated = str(item.get("updated_at") or "")
        job_id = str(item.get("job_id") or "")
        return (updated, job_id)

    def _refresh_tasks_summary(self) -> None:
        assigned = 0
        network_active = 0
        completed = 0
        failed = 0
        for item in self._distributed_tasks.values():
            status = str(item.get("status") or "").lower()
            scope = str(item.get("scope") or "").lower()
            if scope == "assigned":
                assigned += 1
            if status in {"pending", "running", "verifying"}:
                network_active += 1
            elif status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
        self._tasks_summary_var.set(
            f"Assigned: {assigned} | Network Active: {network_active} | Completed: {completed} | Failed: {failed}"
        )

    def _render_distributed_tasks(self) -> None:
        if self._tasks_list is None:
            return

        selected_job_id = ""
        current = self._tasks_list.curselection()
        if current and current[0] < len(self._distributed_task_order):
            selected_job_id = self._distributed_task_order[current[0]]

        items = sorted(self._distributed_tasks.values(), key=self._task_sort_key, reverse=True)[:120]
        self._distributed_task_order = [str(item.get("job_id") or "") for item in items if item.get("job_id")]

        self._tasks_list.delete(0, tk.END)
        for item in items:
            status = str(item.get("status") or "unknown").upper()
            mode = str(item.get("mode") or "inference")
            scope = str(item.get("scope") or "network")
            job_id = str(item.get("job_id") or "-")
            progress = float(item.get("progress") or 0.0)
            line = f"[{status:<9}] {job_id} | {mode} | {scope} | {progress:5.1f}%"
            self._tasks_list.insert(tk.END, line)

        if selected_job_id and selected_job_id in self._distributed_task_order:
            index = self._distributed_task_order.index(selected_job_id)
            self._tasks_list.selection_set(index)
            self._tasks_list.activate(index)
            self._tasks_list.see(index)
            self._write_task_detail(selected_job_id)
        elif self._distributed_task_order:
            self._tasks_list.selection_set(0)
            self._tasks_list.activate(0)
            self._write_task_detail(self._distributed_task_order[0])
        else:
            self._write_task_detail("")

        self._refresh_tasks_summary()

    def _write_task_detail(self, job_id: str) -> None:
        if self._tasks_detail is None:
            return
        payload = self._distributed_tasks.get(job_id)
        lines: list[str] = []
        if payload is None:
            lines = ["No distributed task selected."]
        else:
            lines = [
                f"Job ID      : {payload.get('job_id', '-')}",
                f"Status      : {payload.get('status', '-')}",
                f"Mode        : {payload.get('mode', '-')}",
                f"Scope       : {payload.get('scope', '-')}",
                f"Progress    : {payload.get('progress', 0)}%",
                f"Updated At  : {payload.get('updated_at', '-')}",
                "",
                "Prompt Preview:",
                str(payload.get("prompt_preview") or "-"),
            ]
            result_preview = str(payload.get("result_preview") or "").strip()
            if result_preview:
                lines.extend(["", "Result Preview:", result_preview])
            error = str(payload.get("error") or "").strip()
            if error:
                lines.extend(["", "Error:", error])

        self._tasks_detail.configure(state="normal")
        self._tasks_detail.delete("1.0", tk.END)
        self._tasks_detail.insert(tk.END, "\n".join(lines))
        self._tasks_detail.configure(state="disabled")

    def _on_task_selected(self, _event: tk.Event) -> None:
        if self._tasks_list is None:
            return
        selection = self._tasks_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index < 0 or index >= len(self._distributed_task_order):
            return
        self._write_task_detail(self._distributed_task_order[index])

    def _upsert_distributed_task(self, payload: dict) -> None:
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            return

        existing = self._distributed_tasks.get(job_id, {})
        merged = {
            **existing,
            **payload,
            "job_id": job_id,
            "status": str(payload.get("status") or existing.get("status") or "unknown"),
            "scope": str(payload.get("scope") or existing.get("scope") or "network"),
            "mode": str(payload.get("mode") or existing.get("mode") or "inference"),
            "progress": float(payload.get("progress") or existing.get("progress") or 0.0),
            "updated_at": str(payload.get("updated_at") or existing.get("updated_at") or datetime.now().isoformat()),
            "prompt_preview": str(payload.get("prompt_preview") or existing.get("prompt_preview") or ""),
            "result_preview": str(payload.get("result_preview") or existing.get("result_preview") or ""),
            "error": str(payload.get("error") or existing.get("error") or ""),
        }
        self._distributed_tasks[job_id] = merged
        if len(self._distributed_tasks) > 320:
            keep_ids = {
                str(item.get("job_id") or "")
                for item in sorted(self._distributed_tasks.values(), key=self._task_sort_key, reverse=True)[:240]
            }
            self._distributed_tasks = {key: value for key, value in self._distributed_tasks.items() if key in keep_ids}

    def _handle_task_update_event(self, payload: dict) -> None:
        self._upsert_distributed_task(payload)
        self._render_distributed_tasks()

    def _handle_distributed_tasks_event(self, payload: dict) -> None:
        for item in payload.get("items", []):
            if isinstance(item, dict):
                self._upsert_distributed_task(item)
        self._render_distributed_tasks()

    def _drain_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break

            event_type = event.get("type")
            payload = event.get("payload", {})

            if event_type == "console":
                self._append_console(payload.get("message", ""))
            elif event_type == "status":
                self._append_console(
                    "status_update "
                    f"coord={payload.get('coordinator')} "
                    f"agent={payload.get('agent')} "
                    f"runtime={payload.get('runtime')}"
                )
            elif event_type == "device_details":
                self._snapshot_text.configure(state="normal")
                self._snapshot_text.delete("1.0", tk.END)
                self._snapshot_text.insert(tk.END, payload.get("snapshot", ""))
                self._snapshot_text.configure(state="disabled")

                self._debug_text.configure(state="normal")
                self._debug_text.delete("1.0", tk.END)
                self._debug_text.insert(tk.END, payload.get("debug", ""))
                self._debug_text.configure(state="disabled")
            elif event_type == "models":
                if hasattr(self, "_models_list") and hasattr(self, "_model_status"):
                    self._models_list.delete(0, tk.END)
                    for item in payload.get("items", []):
                        self._models_list.insert(tk.END, item)
                    self._model_status.configure(text=f"{len(payload.get('items', []))} models available")
            elif event_type == "model_downloaded":
                if hasattr(self, "_model_status"):
                    self._model_status.configure(text=f"Downloaded: {payload.get('model')}")
                self._append_console(f"model_downloaded name={payload.get('model')}")
                self._controller.request_models()
            elif event_type == "model_download_failed":
                if hasattr(self, "_model_status"):
                    self._model_status.configure(text=f"Download failed: {payload.get('error')}")
                self._append_console(f"model_download_failed error={payload.get('error')}")
            elif event_type == "task_update":
                self._handle_task_update_event(payload)
            elif event_type == "distributed_tasks":
                self._handle_distributed_tasks_event(payload)

        self.after(250, self._drain_events)


def run_ui() -> None:
    app = NodeAgentUI()
    app.mainloop()
