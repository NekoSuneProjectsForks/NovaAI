"""NovaAI - PySide6 docked-style GUI (qt_gui.py)"""
from __future__ import annotations

import html
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QObject, QSize, Qt, QThread, QTimer, Signal, Slot,
)
from PySide6.QtGui import (
    QColor, QFont, QKeySequence, QShortcut, QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpacerItem, QSplitter, QStackedWidget,
    QStatusBar, QTextEdit, QVBoxLayout, QWidget,
)

from .audio_input import (
    describe_selected_microphone,
    describe_stt_backend,
    list_input_devices_compact,
    recalibrate_microphone,
    recognize_speech,
)
from .chat import request_reply
from .config import Config
from .features import (
    handle_feature_request,
    check_due_reminders,
    check_due_alarms,
    add_reminder,
    list_reminders,
    delete_reminder_by_id,
    add_alarm,
    list_alarms,
    cancel_alarm_by_id,
    cancel_all_alarms,
    add_todo,
    list_todos,
    toggle_todo,
    delete_todo,
    add_shopping_item,
    list_shopping,
    toggle_shopping_item,
    clear_shopping_done,
    clear_shopping_all,
    add_calendar_event,
    list_calendar_events,
    delete_calendar_event,
    _fmt_time,
)
from .media import handle_media_request
from .media_player import stop_media_playback
from .models import SessionState
from .storage import (
    append_history,
    create_profile,
    delete_profile,
    ensure_runtime_dirs,
    get_active_profile_id,
    list_profiles,
    load_profile,
    load_profile_by_id,
    read_recent_history,
    reset_history,
    save_profile_by_id,
    set_active_profile,
)
from .tts import (
    describe_selected_speaker,
    describe_tts_voice,
    get_xtts_device,
    list_output_devices_compact,
    play_audio_file,
    should_play_audio_after_synthesis,
    speak_text,
)
from .web_search import (
    extract_web_query_from_request,
    fetch_web_context,
    should_auto_search,
)

# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
_C = {
    "bg":          "#0f0f14",
    "nav_bg":      "#0a0a10",
    "surface":     "#15151e",
    "surface2":    "#1c1c28",
    "surface3":    "#222232",
    "border":      "#252538",
    "border2":     "#2e2e44",
    "text":        "#e8e8f2",
    "muted":       "#7070a0",
    "muted2":      "#9898c0",
    "input_bg":    "#0c0c18",
    "accent":      "#8b5cf6",
    "accent_h":    "#7c3aed",
    "accent_d":    "#6d28d9",
    "accent_bg":   "#1a0e30",
    "accent_b":    "#3d2070",
    "success":     "#22c55e",
    "success_bg":  "#081a10",
    "success_b":   "#14532d",
    "warning":     "#f59e0b",
    "warning_bg":  "#1a1100",
    "warning_b":   "#78350f",
    "danger":      "#f87171",
    "danger_bg":   "#1a0808",
    "danger_b":    "#7f1d1d",
    "user_bg":     "#1a1408",
    "user_b":      "#7c5a1a",
    "asst_bg":     "#0b1822",
    "asst_b":      "#1e4a6e",
    "sys_bg":      "#0c1020",
    "sys_b":       "#1e2d4a",
}

# ─────────────────────────────────────────────────────────────────────────────
# QSS Stylesheet
# ─────────────────────────────────────────────────────────────────────────────
QSS = f"""
/* ── Base ── */
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    outline: 0;
}}
QWidget {{
    background-color: {_C['bg']};
    color: {_C['text']};
    border: none;
}}

/* ── Nav sidebar ── */
#nav_sidebar {{
    background-color: {_C['nav_bg']};
    border-right: 1px solid {_C['border']};
    min-width: 206px;
    max-width: 206px;
}}
#nav_logo_area {{
    background-color: {_C['nav_bg']};
    padding: 0px;
    border-bottom: 1px solid {_C['border']};
}}
#nav_logo_title {{
    color: {_C['text']};
    font-size: 17px;
    font-weight: 700;
}}
#nav_logo_sub {{
    color: {_C['muted']};
    font-size: 10px;
}}
QPushButton#nav_item {{
    background-color: transparent;
    color: {_C['muted2']};
    text-align: left;
    padding: 10px 18px 10px 18px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    font-size: 13px;
}}
QPushButton#nav_item:hover {{
    background-color: {_C['surface']};
    color: {_C['text']};
}}
QPushButton#nav_item[active="true"] {{
    background-color: {_C['accent_bg']};
    color: #c4b5fd;
    border-left: 3px solid {_C['accent']};
    font-weight: 600;
}}
#nav_bottom {{
    background-color: {_C['nav_bg']};
    border-top: 1px solid {_C['border']};
    padding: 8px 12px;
}}

/* ── Content area ── */
#content_stack {{
    background-color: {_C['bg']};
}}
#page_header {{
    background-color: {_C['surface']};
    border-bottom: 1px solid {_C['border']};
}}
#page_title {{
    font-size: 18px;
    font-weight: 700;
    color: {_C['text']};
}}
#page_sub {{
    font-size: 11px;
    color: {_C['muted']};
}}
#page_scroll {{
    background-color: {_C['bg']};
    border: none;
}}
#page_scroll_inner {{
    background-color: {_C['bg']};
}}

/* ── Cards ── */
QFrame#card {{
    background-color: {_C['surface']};
    border: 1px solid {_C['border']};
    border-radius: 8px;
}}
QFrame#card_alt {{
    background-color: {_C['surface2']};
    border: 1px solid {_C['border2']};
    border-radius: 8px;
}}
QFrame#inset {{
    background-color: {_C['input_bg']};
    border: 1px solid {_C['border']};
    border-radius: 6px;
}}

/* ── Labels ── */
QLabel#sec_title {{
    font-size: 13px;
    font-weight: 700;
    color: {_C['text']};
}}
QLabel#muted {{
    color: {_C['muted']};
    font-size: 11px;
}}
QLabel#badge {{
    background-color: {_C['accent_bg']};
    color: #c4b5fd;
    border: 1px solid {_C['accent_b']};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#badge_success {{
    background-color: {_C['success_bg']};
    color: #4ade80;
    border: 1px solid {_C['success_b']};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#badge_warning {{
    background-color: {_C['warning_bg']};
    color: #fbbf24;
    border: 1px solid {_C['warning_b']};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#badge_danger {{
    background-color: {_C['danger_bg']};
    color: #f87171;
    border: 1px solid {_C['danger_b']};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {_C['accent']};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {_C['accent_h']};
}}
QPushButton:pressed {{
    background-color: {_C['accent_d']};
}}
QPushButton:disabled {{
    background-color: {_C['surface2']};
    color: {_C['muted']};
}}
QPushButton#btn_secondary {{
    background-color: {_C['surface2']};
    color: {_C['muted2']};
    border: 1px solid {_C['border2']};
}}
QPushButton#btn_secondary:hover {{
    background-color: {_C['surface3']};
    color: {_C['text']};
}}
QPushButton#btn_secondary:disabled {{
    background-color: {_C['surface']};
    color: {_C['muted']};
}}
QPushButton#btn_danger {{
    background-color: {_C['danger_bg']};
    color: {_C['danger']};
    border: 1px solid {_C['danger_b']};
}}
QPushButton#btn_danger:hover {{
    background-color: #2a0c0c;
}}
QPushButton#btn_success {{
    background-color: {_C['success_bg']};
    color: {_C['success']};
    border: 1px solid {_C['success_b']};
}}
QPushButton#btn_success:hover {{
    background-color: #0a2815;
}}
QPushButton#btn_active {{
    background-color: {_C['accent_bg']};
    color: #c4b5fd;
    border: 1px solid {_C['accent_b']};
}}
QPushButton#btn_active:hover {{
    background-color: #22103e;
}}

/* ── Inputs ── */
QLineEdit, QTextEdit {{
    background-color: {_C['input_bg']};
    border: 1px solid {_C['border2']};
    border-radius: 6px;
    padding: 7px 11px;
    color: {_C['text']};
    font-size: 13px;
    selection-background-color: {_C['accent']};
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {_C['accent']};
}}
QLineEdit:disabled {{
    background-color: {_C['surface']};
    color: {_C['muted']};
}}

/* ── ComboBox ── */
QComboBox {{
    background-color: {_C['input_bg']};
    border: 1px solid {_C['border2']};
    border-radius: 6px;
    padding: 7px 11px;
    color: {_C['text']};
    font-size: 13px;
    min-height: 32px;
}}
QComboBox:focus {{
    border-color: {_C['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-style: solid;
    border-width: 5px 4px 0 4px;
    border-color: {_C['muted']} transparent transparent transparent;
    width: 0; height: 0;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {_C['surface2']};
    border: 1px solid {_C['border2']};
    color: {_C['text']};
    selection-background-color: {_C['accent_bg']};
    selection-color: #c4b5fd;
    padding: 4px;
    outline: none;
}}

/* ── List widget ── */
QListWidget {{
    background-color: {_C['input_bg']};
    border: 1px solid {_C['border2']};
    border-radius: 6px;
    color: {_C['text']};
    font-size: 13px;
    outline: none;
}}
QListWidget::item {{
    padding: 7px 12px;
    border-bottom: 1px solid {_C['surface2']};
}}
QListWidget::item:selected {{
    background-color: {_C['accent_bg']};
    color: #c4b5fd;
}}
QListWidget::item:hover:!selected {{
    background-color: {_C['surface']};
}}

/* ── Scrollbars ── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {_C['surface3']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {_C['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {_C['surface3']};
    border-radius: 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {_C['accent']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Checkbox ── */
QCheckBox {{
    color: {_C['text']};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {_C['border2']};
    border-radius: 4px;
    background-color: {_C['input_bg']};
}}
QCheckBox::indicator:checked {{
    background-color: {_C['accent']};
    border-color: {_C['accent']};
}}

/* ── Status bar ── */
QStatusBar {{
    background-color: {_C['surface']};
    border-top: 1px solid {_C['border']};
    color: {_C['muted2']};
    font-size: 11px;
    padding: 0 8px;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background-color: {_C['border']};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ── Chat log ── */
#chat_log {{
    background-color: {_C['input_bg']};
    border: 1px solid {_C['border2']};
    border-radius: 6px;
    color: {_C['text']};
    font-size: 13px;
    padding: 4px;
    selection-background-color: {_C['accent']};
}}

/* ── Dashboard: toggle rows ── */
#dash_toggle_card {{
    background-color: {_C['surface']};
    border: 1px solid {_C['border']};
    border-radius: 8px;
}}
#dash_toggle_row {{
    background-color: transparent;
    border-bottom: 1px solid {_C['border']};
    padding: 0;
}}
#dash_toggle_row_last {{
    background-color: transparent;
    border-bottom: none;
    padding: 0;
}}
#dot_on {{
    color: {_C['success']};
    font-size: 18px;
}}
#dot_off {{
    color: {_C['muted']};
    font-size: 18px;
}}
#toggle_label {{
    color: {_C['text']};
    font-size: 13px;
    font-weight: 500;
}}
#toggle_sub {{
    color: {_C['muted']};
    font-size: 11px;
}}
#toggle_value_on {{
    color: {_C['success']};
    font-size: 12px;
    font-weight: 600;
}}
#toggle_value_off {{
    color: {_C['muted']};
    font-size: 12px;
    font-weight: 600;
}}

/* ── Dashboard: stat cards ── */
#stat_card {{
    background-color: {_C['surface']};
    border: 1px solid {_C['border']};
    border-radius: 8px;
}}
#stat_value {{
    color: {_C['text']};
    font-size: 22px;
    font-weight: 700;
}}
#stat_label {{
    color: {_C['muted']};
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.5px;
}}

/* ── Dashboard: action buttons ── */
QPushButton#dash_action {{
    background-color: {_C['surface2']};
    color: {_C['muted2']};
    border: 1px solid {_C['border2']};
    border-radius: 6px;
    padding: 10px 16px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#dash_action:hover {{
    background-color: {_C['surface3']};
    color: {_C['text']};
    border-color: {_C['accent_b']};
}}
QPushButton#dash_action:disabled {{
    background-color: {_C['surface']};
    color: {_C['muted']};
    border-color: {_C['border']};
}}

/* ── Dashboard: session button ── */
QPushButton#dash_session_start {{
    background-color: {_C['accent']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 14px 20px;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}
QPushButton#dash_session_start:hover {{
    background-color: {_C['accent_h']};
}}
QPushButton#dash_session_running {{
    background-color: {_C['success_bg']};
    color: {_C['success']};
    border: 1px solid {_C['success_b']};
    border-radius: 8px;
    padding: 14px 20px;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}
QPushButton#dash_session_running:hover {{
    background-color: #0a2815;
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Worker threads
# ─────────────────────────────────────────────────────────────────────────────

class _ReplyThread(QThread):
    append_msg  = Signal(str, str, str)   # author, text, role
    system_msg  = Signal(str)
    set_status  = Signal(str)
    features_ok = Signal()
    done        = Signal(str)             # final status text

    def __init__(self, win: "NovaAIWindow", text: str, from_voice: bool) -> None:
        super().__init__()
        self._win        = win
        self._text       = text
        self._from_voice = from_voice

    def run(self) -> None:
        status = "System idle. Ready when you are."
        try:
            status = self._win._pipeline(self._text, self._from_voice, self)
        except Exception as exc:
            status = f"Companion error: {exc}"
            self.system_msg.emit(status)
        finally:
            self.done.emit(status)


class _VoiceThread(QThread):
    append_msg  = Signal(str, str, str)
    system_msg  = Signal(str)
    set_status  = Signal(str)
    features_ok = Signal()
    done        = Signal(str)

    def __init__(self, win: "NovaAIWindow", auto: bool) -> None:
        super().__init__()
        self._win  = win
        self._auto = auto

    def run(self) -> None:
        status = "System idle. Ready when you are."
        try:
            result = recognize_speech(self._win.config, self._win.state, announce=False)
            if result.status == "timeout":
                status = "No speech detected."
                return
            if result.status == "unknown":
                status = "Heard something but couldn't transcribe clearly."
                return
            if result.status != "ok":
                raise RuntimeError(result.error or "Speech recognition failed.")
            text = result.text.strip()
            if not text:
                status = "No speech detected."
                return
            status = self._win._pipeline(text, True, self)
        except Exception as exc:
            status = f"Audio error: {exc}"
            self.system_msg.emit(status)
        finally:
            self.done.emit(status)


class _RecalibThread(QThread):
    done = Signal(str)

    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win

    def run(self) -> None:
        status = "Microphone calibration complete."
        try:
            self._win.state.speech_recognizer = None
            self._win.state.speech_recognizer_signature = None
            self._win.state.mic_calibrated = False
            recalibrate_microphone(self._win.config, self._win.state, announce=False)
        except Exception as exc:
            status = f"Calibration failed: {exc}"
        finally:
            self.done.emit(status)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_card(parent: QWidget | None = None, alt: bool = False) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("card_alt" if alt else "card")
    return f


def _label(text: str, obj: str = "", parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    if obj:
        lbl.setObjectName(obj)
    return lbl


def _btn(text: str, obj: str = "", parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    if obj:
        b.setObjectName(obj)
    return b


def _badge(text: str, tone: str = "accent") -> QLabel:
    lbl = QLabel(text)
    name = "badge" if tone == "accent" else f"badge_{tone}"
    lbl.setObjectName(name)
    return lbl


def _msg_html(author: str, text: str, role: str) -> str:
    """Return HTML for one chat message bubble."""
    if role == "user":
        bg, bord = _C["user_bg"], _C["user_b"]
        a_col, t_col = "#fbbf24", "#fef3c7"
    elif role == "assistant":
        bg, bord = _C["asst_bg"], _C["asst_b"]
        a_col, t_col = "#93c5fd", "#dbeafe"
    else:
        bg, bord = _C["sys_bg"], _C["sys_b"]
        a_col, t_col = "#6b7280", "#9ca3af"
    safe_text = html.escape(text).replace("\n", "<br>")
    safe_author = html.escape(author)
    return (
        f'<div style="background:{bg};border-left:4px solid {bord};'
        f'border-radius:6px;margin:5px 2px;padding:10px 14px;">'
        f'<div style="color:{a_col};font-weight:600;font-size:11px;'
        f'margin-bottom:5px;letter-spacing:0.5px;">{safe_author}</div>'
        f'<div style="color:{t_col};font-size:13px;line-height:1.55;">'
        f'{safe_text}</div></div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page: Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class DashboardPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._toggle_dots:   dict[str, QLabel] = {}
        self._toggle_values: dict[str, QLabel] = {}
        self._build()

    # ── layout helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _restyle(widget: QWidget, name: str) -> None:
        widget.setObjectName(name)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _stat_card(self, value_text: str, label_text: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("stat_card")
        card.setFixedHeight(72)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(2)
        val = QLabel(value_text)
        val.setObjectName("stat_value")
        val.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        lay.addWidget(val)
        lbl = QLabel(label_text.upper())
        lbl.setObjectName("stat_label")
        lay.addWidget(lbl)
        return card, val

    def _toggle_row(
        self, key: str, title: str, sub: str, last: bool = False,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("dash_toggle_row_last" if last else "dash_toggle_row")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 10, 16, 10)
        rl.setSpacing(10)

        dot = QLabel("●")
        dot.setObjectName("dot_off")
        dot.setFixedWidth(18)
        dot.setAlignment(Qt.AlignCenter)
        rl.addWidget(dot)
        self._toggle_dots[key] = dot

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        tl = QLabel(title)
        tl.setObjectName("toggle_label")
        text_col.addWidget(tl)
        sl = QLabel(sub)
        sl.setObjectName("toggle_sub")
        text_col.addWidget(sl)
        rl.addLayout(text_col, 1)

        val = QLabel("OFF")
        val.setObjectName("toggle_value_off")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val.setFixedWidth(44)
        rl.addWidget(val)
        self._toggle_values[key] = val

        btn = QPushButton("Toggle")
        btn.setObjectName("dash_action")
        btn.setFixedWidth(64)
        btn.setFixedHeight(30)
        rl.addWidget(btn)

        setattr(self, f"btn_{key}", btn)
        return row

    # ── build ─────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("page_scroll")
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        inner.setObjectName("page_scroll_inner")
        scroll.setWidget(inner)

        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(16)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # ── Row 1: status strip (4 small stat cards) ─────────────────────────
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)

        sc_session, self._stat_session = self._stat_card("Standby", "Session")
        sc_model,   self._stat_model   = self._stat_card("--",      "Model")
        sc_mode,    self._stat_mode    = self._stat_card("Text",    "Input Mode")
        sc_status,  self._stat_status  = self._stat_card("Ready",   "Status")

        for sc in (sc_session, sc_model, sc_mode, sc_status):
            stat_row.addWidget(sc, 1)
        root.addLayout(stat_row)

        # ── Row 2: Session button ────────────────────────────────────────────
        self.btn_start = QPushButton("Start Session")
        self.btn_start.setObjectName("dash_session_start")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setMinimumHeight(48)
        root.addWidget(self.btn_start)

        # ── Row 3: two-column content ────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Left column: Toggles card
        toggle_card = QFrame()
        toggle_card.setObjectName("dash_toggle_card")
        tc_l = QVBoxLayout(toggle_card)
        tc_l.setContentsMargins(0, 0, 0, 0)
        tc_l.setSpacing(0)

        tc_header = QLabel("  Controls")
        tc_header.setObjectName("sec_title")
        tc_header.setStyleSheet(
            f"color:{_C['text']};font-size:13px;font-weight:700;"
            f"padding:14px 16px 8px 16px;"
        )
        tc_l.addWidget(tc_header)

        tc_l.addWidget(self._toggle_row("voice",     "Voice Replies",  "Spoken TTS output"))
        tc_l.addWidget(self._toggle_row("handsfree", "Hands-Free",     "Auto-listen after each reply"))
        tc_l.addWidget(self._toggle_row("mic",       "Microphone",     "App-level mic mute"))
        tc_l.addWidget(self._toggle_row("websearch", "Web Search",     "Let the LLM search the web", last=True))
        cols.addWidget(toggle_card, 3)

        # Right column: Quick actions
        action_card = _make_card()
        ac_l = QVBoxLayout(action_card)
        ac_l.setContentsMargins(16, 14, 16, 16)
        ac_l.setSpacing(8)
        ac_l.addWidget(_label("Quick Actions", "sec_title"))

        self.btn_listen  = QPushButton("Listen Now")
        self.btn_recal   = QPushButton("Recalibrate Mic")
        self.btn_clrhist = QPushButton("Clear History")
        self.btn_perf    = QPushButton("Performance Info")

        for b in (self.btn_listen, self.btn_recal, self.btn_clrhist, self.btn_perf):
            b.setObjectName("dash_action")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(36)
            ac_l.addWidget(b)

        ac_l.addStretch()
        cols.addWidget(action_card, 2)
        root.addLayout(cols)

        # ── Row 4: companion info ────────────────────────────────────────────
        info_card = _make_card()
        il = QHBoxLayout(info_card)
        il.setContentsMargins(16, 12, 16, 12)
        il.setSpacing(12)

        self._companion_lbl = QLabel("")
        self._companion_lbl.setStyleSheet(
            f"color:{_C['text']};font-size:14px;font-weight:600;"
        )
        il.addWidget(self._companion_lbl)

        self._subtitle_lbl = QLabel("")
        self._subtitle_lbl.setStyleSheet(f"color:{_C['muted']};font-size:12px;")
        self._subtitle_lbl.setWordWrap(True)
        il.addWidget(self._subtitle_lbl, 1)
        root.addWidget(info_card)

        root.addStretch()

        # ── Wire signals ─────────────────────────────────────────────────────
        self.btn_start.clicked.connect(self._win.start_session)
        self.btn_voice.clicked.connect(self._win.toggle_voice_output)
        self.btn_handsfree.clicked.connect(self._win.toggle_hands_free)
        self.btn_mic.clicked.connect(self._win.toggle_mic_muted)
        self.btn_websearch.clicked.connect(self._toggle_web_search)
        self.btn_listen.clicked.connect(self._win.start_listen_once)
        self.btn_recal.clicked.connect(self._win.start_recalibration)
        self.btn_clrhist.clicked.connect(self._win.clear_history)
        self.btn_perf.clicked.connect(self._win.show_performance)

    def _toggle_web_search(self) -> None:
        cfg = self._win.config
        cfg.web_browsing_enabled = not cfg.web_browsing_enabled
        self.refresh()

    # ── toggle dot/value updater ─────────────────────────────────────────────
    def _set_toggle(self, key: str, on: bool, label: str | None = None) -> None:
        dot = self._toggle_dots.get(key)
        val = self._toggle_values.get(key)
        if dot:
            self._restyle(dot, "dot_on" if on else "dot_off")
        if val:
            val.setText(label or ("ON" if on else "OFF"))
            self._restyle(val, "toggle_value_on" if on else "toggle_value_off")

    # ── refresh ───────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        win = self._win
        busy = win.busy
        active = win.session_started

        # Companion info
        self._companion_lbl.setText(
            win.profile.get("companion_name", "NovaAI")
        )
        self._subtitle_lbl.setText(win.profile.get("description", ""))

        # Stat cards
        if busy:
            self._stat_session.setText("Busy")
            self._stat_session.setStyleSheet(
                f"color:{_C['warning']};font-size:22px;font-weight:700;"
            )
        elif active:
            self._stat_session.setText("Active")
            self._stat_session.setStyleSheet(
                f"color:{_C['success']};font-size:22px;font-weight:700;"
            )
        else:
            self._stat_session.setText("Standby")
            self._stat_session.setStyleSheet(
                f"color:{_C['muted2']};font-size:22px;font-weight:700;"
            )

        self._stat_model.setText(win.config.model)
        self._stat_mode.setText("Voice" if win.hands_free_enabled else "Text")

        # Session button
        if active:
            self.btn_start.setText("Session Running")
            self._restyle(self.btn_start, "dash_session_running")
            self.btn_start.setEnabled(False)
        else:
            self.btn_start.setText("Start Session")
            self._restyle(self.btn_start, "dash_session_start")
            self.btn_start.setEnabled(not busy)

        # Toggles — voice, hands-free, mic work BEFORE session start
        self._set_toggle("voice",     win.state.voice_enabled)
        self._set_toggle("handsfree", win.hands_free_enabled)
        self._set_toggle("mic",       not win.mic_muted, "LIVE" if not win.mic_muted else "MUTED")
        self._set_toggle("websearch", win.config.web_browsing_enabled)

        # Toggle buttons always enabled (except when busy)
        self.btn_voice.setEnabled(not busy)
        self.btn_handsfree.setEnabled(not busy)
        self.btn_mic.setEnabled(not busy)
        self.btn_websearch.setEnabled(not busy)

        # Action buttons
        self.btn_listen.setEnabled(active and not busy and not win.mic_muted)
        self.btn_recal.setEnabled(not busy)
        self.btn_clrhist.setEnabled(not busy)

    def set_status(self, msg: str) -> None:
        self._stat_status.setText(msg[:40])
        self._stat_status.setToolTip(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Chat
# ─────────────────────────────────────────────────────────────────────────────

class ChatPage(QWidget):
    send_requested = Signal(str)

    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Chat log
        self.chat_log = QTextEdit()
        self.chat_log.setObjectName("chat_log")
        self.chat_log.setReadOnly(True)
        self.chat_log.document().setDefaultStyleSheet(
            "body { margin:0; padding:0; }"
        )
        root.addWidget(self.chat_log, 1)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type a message... (Enter to send)")
        self.input_box.setMinimumHeight(38)
        self.input_box.returnPressed.connect(self._on_send)
        input_row.addWidget(self.input_box, 1)

        self.btn_send = QPushButton("Send")
        self.btn_send.setMinimumHeight(38)
        self.btn_send.setMinimumWidth(70)
        self.btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self.btn_send)

        self.btn_voice = QPushButton("🎙 Voice")
        self.btn_voice.setObjectName("btn_secondary")
        self.btn_voice.setMinimumHeight(38)
        self.btn_voice.setMinimumWidth(80)
        self.btn_voice.clicked.connect(self._win.start_listen_once)
        input_row.addWidget(self.btn_voice)

        root.addLayout(input_row)

    def _on_send(self) -> None:
        text = self.input_box.text().strip()
        if text:
            self.input_box.clear()
            self._win.send_message(text)

    def append_message(self, author: str, text: str, role: str) -> None:
        self.chat_log.moveCursor(QTextCursor.End)
        self.chat_log.insertHtml(_msg_html(author, text, role))
        self.chat_log.moveCursor(QTextCursor.End)

    def refresh_controls(self) -> None:
        win = self._win
        active = win.session_started and not win.busy
        self.input_box.setEnabled(active)
        self.btn_send.setEnabled(active)
        self.btn_voice.setEnabled(
            win.session_started and not win.busy and not win.mic_muted
        )


# ─────────────────────────────────────────────────────────────────────────────
# Page: Reminders (includes Alarms section)
# ─────────────────────────────────────────────────────────────────────────────

class RemindersPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)

        # ── Reminders ────────────────────────────────────────────────────────
        rem_card = _make_card()
        rem_l = QVBoxLayout(rem_card)
        rem_l.setContentsMargins(16, 14, 16, 14)
        rem_l.setSpacing(8)
        rem_l.addWidget(_label("Reminders", "sec_title"))
        rem_l.addWidget(_label('One-shot timed reminders. Say remind me to... on DATE TIME to add one.', "muted"))
        self.rem_list = QListWidget()
        rem_l.addWidget(self.rem_list, 1)
        rb = QHBoxLayout(); rb.setSpacing(8)
        self.btn_add_rem = QPushButton("Add Reminder")
        self.btn_del_rem = QPushButton("Delete"); self.btn_del_rem.setObjectName("btn_danger")
        rb.addWidget(self.btn_add_rem); rb.addWidget(self.btn_del_rem); rb.addStretch()
        rem_l.addLayout(rb)
        splitter.addWidget(rem_card)

        # ── Alarms ───────────────────────────────────────────────────────────
        alm_card = _make_card()
        alm_l = QVBoxLayout(alm_card)
        alm_l.setContentsMargins(16, 14, 16, 14)
        alm_l.setSpacing(8)
        alm_l.addWidget(_label("Alarms", "sec_title"))
        alm_l.addWidget(_label('Recurring alarms. Say: set an alarm for TIME to add one.', "muted"))
        self.alm_list = QListWidget()
        alm_l.addWidget(self.alm_list, 1)
        ab = QHBoxLayout(); ab.setSpacing(8)
        self.btn_add_alm    = QPushButton("Add Alarm")
        self.btn_toggle_alm = QPushButton("Toggle"); self.btn_toggle_alm.setObjectName("btn_secondary")
        self.btn_del_alm    = QPushButton("Delete");  self.btn_del_alm.setObjectName("btn_danger")
        self.btn_clr_alm    = QPushButton("Clear All"); self.btn_clr_alm.setObjectName("btn_secondary")
        for b in (self.btn_add_alm, self.btn_toggle_alm, self.btn_del_alm, self.btn_clr_alm):
            ab.addWidget(b)
        ab.addStretch()
        alm_l.addLayout(ab)
        splitter.addWidget(alm_card)

        root.addWidget(splitter, 1)

        # Wire
        self.btn_add_rem.clicked.connect(self._add_reminder)
        self.btn_del_rem.clicked.connect(self._del_reminder)
        self.btn_add_alm.clicked.connect(self._add_alarm)
        self.btn_toggle_alm.clicked.connect(self._toggle_alarm)
        self.btn_del_alm.clicked.connect(self._del_alarm)
        self.btn_clr_alm.clicked.connect(self._clear_alarms)

    # ── Reminder actions ──────────────────────────────────────────────────────
    def _add_reminder(self) -> None:
        text, ok = QInputDialog.getText(self, "Add Reminder", "Reminder text (e.g. Call doctor at 3pm):")
        if not ok or not text.strip():
            return
        when, ok2 = QInputDialog.getText(self, "Add Reminder", "Due date/time (e.g. 2026-05-01 15:00):")
        if not ok2 or not when.strip():
            return
        win = self._win
        try:
            import dateparser
            due_dt = dateparser.parse(when.strip())
            if not due_dt:
                due_dt = datetime.now()
            add_reminder(win.profile, text.strip(), due_dt)
            win.profile = save_profile_by_id(win.active_profile_id, win.profile)
            self.refresh_reminders()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _del_reminder(self) -> None:
        item = self.rem_list.currentItem()
        if not item:
            return
        rid = item.data(Qt.UserRole)
        if rid:
            delete_reminder_by_id(self._win.profile, rid)
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
        self.refresh_reminders()

    # ── Alarm actions ─────────────────────────────────────────────────────────
    def _add_alarm(self) -> None:
        label_text, ok = QInputDialog.getText(self, "Add Alarm", "Alarm label:")
        if not ok or not label_text.strip():
            return
        time_str, ok2 = QInputDialog.getText(self, "Add Alarm", "Time (HH:MM 24h):")
        if not ok2 or not time_str.strip():
            return
        win = self._win
        try:
            add_alarm(win.profile, time_str.strip(), label=label_text.strip())
            win.profile = save_profile_by_id(win.active_profile_id, win.profile)
            self.refresh_alarms()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _toggle_alarm(self) -> None:
        item = self.alm_list.currentItem()
        if not item:
            return
        aid = item.data(Qt.UserRole)
        if not aid:
            return
        for a in list_alarms(self._win.profile):
            if str(a.get("id")) == str(aid):
                a["active"] = not a.get("active", True)
        self._win.profile = save_profile_by_id(
            self._win.active_profile_id, self._win.profile
        )
        self.refresh_alarms()

    def _del_alarm(self) -> None:
        item = self.alm_list.currentItem()
        if not item:
            return
        aid = item.data(Qt.UserRole)
        if aid:
            cancel_alarm_by_id(self._win.profile, str(aid))
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
        self.refresh_alarms()

    def _clear_alarms(self) -> None:
        r = QMessageBox.question(self, "Clear All Alarms", "Delete all alarms?")
        if r == QMessageBox.Yes:
            cancel_all_alarms(self._win.profile)
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
            self.refresh_alarms()

    # ── Refresh ───────────────────────────────────────────────────────────────
    def refresh_reminders(self) -> None:
        self.rem_list.clear()
        for r in list_reminders(self._win.profile):
            due = r.get("due", "")
            label = r.get("title", "")
            item = QListWidgetItem(f"{label}   -   {due}")
            item.setData(Qt.UserRole, r.get("id"))
            self.rem_list.addItem(item)

    def refresh_alarms(self) -> None:
        self.alm_list.clear()
        for a in list_alarms(self._win.profile):
            active = a.get("active", True)
            label  = a.get("label", "")
            t      = a.get("time", "")
            marker = "✔" if active else "✖"
            item = QListWidgetItem(f"{marker}  {label}   -   {t}")
            item.setData(Qt.UserRole, a.get("id"))
            self.alm_list.addItem(item)

    def refresh_all(self) -> None:
        self.refresh_reminders()
        self.refresh_alarms()


# ─────────────────────────────────────────────────────────────────────────────
# Page: Calendar
# ─────────────────────────────────────────────────────────────────────────────

class CalendarPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        card = _make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)
        cl.addWidget(_label("Calendar Events", "sec_title"))
        cl.addWidget(_label('Upcoming events. Say: add event TITLE on DATE to create one.', "muted"))
        self.evt_list = QListWidget()
        cl.addWidget(self.evt_list, 1)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.btn_add = QPushButton("Add Event")
        self.btn_del = QPushButton("Delete"); self.btn_del.setObjectName("btn_danger")
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_del); btn_row.addStretch()
        cl.addLayout(btn_row)
        root.addWidget(card, 1)

        self.btn_add.clicked.connect(self._add_event)
        self.btn_del.clicked.connect(self._del_event)

    def _add_event(self) -> None:
        title, ok = QInputDialog.getText(self, "Add Event", "Event title:")
        if not ok or not title.strip():
            return
        date_str, ok2 = QInputDialog.getText(self, "Add Event", "Date (YYYY-MM-DD):")
        if not ok2:
            return
        time_str, ok3 = QInputDialog.getText(self, "Add Event", "Time (HH:MM, or leave blank):")
        if not ok3:
            return
        win = self._win
        try:
            add_calendar_event(
                win.profile, title.strip(),
                event_date=date_str.strip() or None,
                event_time=time_str.strip() or None,
            )
            win.profile = save_profile_by_id(win.active_profile_id, win.profile)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _del_event(self) -> None:
        item = self.evt_list.currentItem()
        if not item:
            return
        eid = item.data(Qt.UserRole)
        if eid:
            delete_calendar_event(self._win.profile, str(eid))
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
        self.refresh()

    def refresh(self) -> None:
        self.evt_list.clear()
        for e in list_calendar_events(self._win.profile):
            title = e.get("title", "")
            when  = f"{e.get('date', '')} {e.get('time', '')}".strip()
            item  = QListWidgetItem(f"{title}   -   {when}")
            item.setData(Qt.UserRole, e.get("id"))
            self.evt_list.addItem(item)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Shopping
# ─────────────────────────────────────────────────────────────────────────────

class ShoppingPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        card = _make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)
        cl.addWidget(_label("Shopping List", "sec_title"))
        cl.addWidget(_label('Your shopping list. Say: add ITEM to shopping list to add via chat.', "muted"))
        self.shop_list = QListWidget()
        cl.addWidget(self.shop_list, 1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.btn_add      = QPushButton("Add Item")
        self.btn_toggle   = QPushButton("Toggle Done"); self.btn_toggle.setObjectName("btn_secondary")
        self.btn_clr_done = QPushButton("Clear Done");  self.btn_clr_done.setObjectName("btn_secondary")
        self.btn_clr_all  = QPushButton("Clear All");   self.btn_clr_all.setObjectName("btn_danger")
        for b in (self.btn_add, self.btn_toggle, self.btn_clr_done, self.btn_clr_all):
            btn_row.addWidget(b)
        btn_row.addStretch()
        cl.addLayout(btn_row)
        root.addWidget(card, 1)

        self.btn_add.clicked.connect(self._add_item)
        self.btn_toggle.clicked.connect(self._toggle_item)
        self.btn_clr_done.clicked.connect(self._clear_done)
        self.btn_clr_all.clicked.connect(self._clear_all)

    def _add_item(self) -> None:
        text, ok = QInputDialog.getText(self, "Add Item", "Item name:")
        if ok and text.strip():
            add_shopping_item(self._win.profile, text.strip())
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
            self.refresh()

    def _toggle_item(self) -> None:
        item = self.shop_list.currentItem()
        if not item:
            return
        iid = item.data(Qt.UserRole)
        if iid:
            toggle_shopping_item(self._win.profile, str(iid))
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
        self.refresh()

    def _clear_done(self) -> None:
        clear_shopping_done(self._win.profile)
        self._win.profile = save_profile_by_id(
            self._win.active_profile_id, self._win.profile
        )
        self.refresh()

    def _clear_all(self) -> None:
        r = QMessageBox.question(self, "Clear All", "Clear the entire shopping list?")
        if r == QMessageBox.Yes:
            clear_shopping_all(self._win.profile)
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
            self.refresh()

    def refresh(self) -> None:
        self.shop_list.clear()
        for item in list_shopping(self._win.profile):
            done  = item.get("done", False)
            name  = item.get("text", "")
            text  = ("✔  " if done else "○  ") + name
            li    = QListWidgetItem(text)
            li.setData(Qt.UserRole, item.get("id"))
            if done:
                li.setForeground(QColor(_C["muted"]))
            self.shop_list.addItem(li)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Todo
# ─────────────────────────────────────────────────────────────────────────────

class TodoPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        card = _make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)
        cl.addWidget(_label("To-Do List", "sec_title"))
        cl.addWidget(_label('Track tasks. Say: add todo TASK to add one via chat.', "muted"))
        self.todo_list = QListWidget()
        cl.addWidget(self.todo_list, 1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.btn_add    = QPushButton("Add Task")
        self.btn_toggle = QPushButton("Toggle Done"); self.btn_toggle.setObjectName("btn_secondary")
        self.btn_del    = QPushButton("Delete");       self.btn_del.setObjectName("btn_danger")
        for b in (self.btn_add, self.btn_toggle, self.btn_del):
            btn_row.addWidget(b)
        btn_row.addStretch()
        cl.addLayout(btn_row)
        root.addWidget(card, 1)

        self.btn_add.clicked.connect(self._add_todo)
        self.btn_toggle.clicked.connect(self._toggle_todo)
        self.btn_del.clicked.connect(self._del_todo)

    def _add_todo(self) -> None:
        text, ok = QInputDialog.getText(self, "Add Task", "Task description:")
        if ok and text.strip():
            add_todo(self._win.profile, text.strip())
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
            self.refresh()

    def _toggle_todo(self) -> None:
        item = self.todo_list.currentItem()
        if not item:
            return
        iid = item.data(Qt.UserRole)
        if iid:
            toggle_todo(self._win.profile, str(iid))
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
        self.refresh()

    def _del_todo(self) -> None:
        item = self.todo_list.currentItem()
        if not item:
            return
        iid = item.data(Qt.UserRole)
        if iid:
            delete_todo(self._win.profile, str(iid))
            self._win.profile = save_profile_by_id(
                self._win.active_profile_id, self._win.profile
            )
        self.refresh()

    def refresh(self) -> None:
        self.todo_list.clear()
        for item in list_todos(self._win.profile):
            done  = item.get("done", False)
            text  = item.get("text", item.get("title", ""))
            label = ("✔  " if done else "○  ") + text
            li    = QListWidgetItem(label)
            li.setData(Qt.UserRole, item.get("id"))
            if done:
                li.setForeground(QColor(_C["muted"]))
            self.todo_list.addItem(li)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Profiles
# ─────────────────────────────────────────────────────────────────────────────

class ProfilesPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._profile_ids: list[str] = []
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Left: profile list ────────────────────────────────────────────────
        left = _make_card()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 14, 14, 14)
        ll.setSpacing(8)
        ll.addWidget(_label("Profiles", "sec_title"))
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self._on_select)
        ll.addWidget(self.profile_list, 1)

        pb = QHBoxLayout(); pb.setSpacing(6)
        self.btn_create   = QPushButton("New")
        self.btn_create.setObjectName("btn_success")
        self.btn_clone    = QPushButton("Clone");    self.btn_clone.setObjectName("btn_secondary")
        self.btn_activate = QPushButton("Activate"); self.btn_activate.setObjectName("btn_active" if False else "btn_secondary")
        self.btn_del_prof = QPushButton("Delete");   self.btn_del_prof.setObjectName("btn_danger")
        for b in (self.btn_create, self.btn_clone, self.btn_activate, self.btn_del_prof):
            pb.addWidget(b)
        ll.addLayout(pb)
        root.addWidget(left, 1)

        # ── Right: editor ─────────────────────────────────────────────────────
        right = _make_card()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(8)
        rl.addWidget(_label("Edit Profile", "sec_title"))

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.f_name      = QLineEdit(); self.f_name.setPlaceholderText("Profile name")
        self.f_cname     = QLineEdit(); self.f_cname.setPlaceholderText("Companion name (e.g. Nova)")
        self.f_uname     = QLineEdit(); self.f_uname.setPlaceholderText("Your name")
        self.f_desc      = QLineEdit(); self.f_desc.setPlaceholderText("Short description")
        self.f_tags      = QLineEdit(); self.f_tags.setPlaceholderText("Comma-separated tags")
        self.f_sysprompt = QTextEdit(); self.f_sysprompt.setPlaceholderText("System prompt...")
        self.f_sysprompt.setMaximumHeight(120)

        form.addRow("Name:",           self.f_name)
        form.addRow("Companion Name:", self.f_cname)
        form.addRow("Your Name:",      self.f_uname)
        form.addRow("Description:",    self.f_desc)
        form.addRow("Tags:",           self.f_tags)
        form.addRow("System Prompt:",  self.f_sysprompt)
        rl.addWidget(form_w)

        save_row = QHBoxLayout(); save_row.setSpacing(8)
        self.btn_save = QPushButton("Save Changes")
        save_row.addWidget(self.btn_save); save_row.addStretch()
        rl.addLayout(save_row)
        rl.addStretch()
        root.addWidget(right, 2)

        # Wire
        self.btn_create.clicked.connect(self._create_profile)
        self.btn_clone.clicked.connect(self._clone_profile)
        self.btn_activate.clicked.connect(self._activate_profile)
        self.btn_del_prof.clicked.connect(self._delete_profile)
        self.btn_save.clicked.connect(self._save_profile)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _create_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if not ok or not name.strip():
            return
        cname, ok2 = QInputDialog.getText(self, "New Profile", "Companion name:")
        if not ok2 or not cname.strip():
            return
        try:
            base = {"companion_name": cname.strip()}
            create_profile(name.strip(), base_profile=base)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _clone_profile(self) -> None:
        pid = self._selected_id()
        if not pid:
            return
        name, ok = QInputDialog.getText(self, "Clone Profile", "New profile name:")
        if not ok or not name.strip():
            return
        src = load_profile_by_id(pid)
        if not src:
            return
        try:
            create_profile(name.strip(), base_profile=src)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _activate_profile(self) -> None:
        pid = self._selected_id()
        if not pid:
            return
        set_active_profile(pid)
        self._win.active_profile_id = pid
        self._win.profile = load_profile_by_id(pid) or self._win.profile
        self._win.dash_page.refresh()
        self._win.status_bar.showMessage("Profile activated.")
        self.refresh()

    def _delete_profile(self) -> None:
        pid = self._selected_id()
        if not pid:
            return
        if pid == self._win.active_profile_id:
            QMessageBox.warning(self, "Cannot Delete", "Cannot delete the active profile.")
            return
        r = QMessageBox.question(self, "Delete Profile", "Delete this profile?")
        if r == QMessageBox.Yes:
            delete_profile(pid)
            self.refresh()

    def _save_profile(self) -> None:
        pid = self._selected_id()
        if not pid:
            return
        profile = load_profile_by_id(pid) or {}
        profile["profile_name"]   = self.f_name.text().strip()
        profile["companion_name"] = self.f_cname.text().strip()
        profile["user_name"]      = self.f_uname.text().strip()
        profile["description"]    = self.f_desc.text().strip()
        profile["tags"]           = [t.strip() for t in self.f_tags.text().split(",") if t.strip()]
        details = profile.setdefault("profile_details", {})
        details["system_prompt"]  = self.f_sysprompt.toPlainText().strip()
        save_profile_by_id(pid, profile)
        if pid == self._win.active_profile_id:
            self._win.profile = profile
            self._win.dash_page.refresh()
        self._win.status_bar.showMessage("Profile saved.")

    def _selected_id(self) -> str | None:
        row = self.profile_list.currentRow()
        if row < 0 or row >= len(self._profile_ids):
            return None
        return self._profile_ids[row]

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._profile_ids):
            return
        pid = self._profile_ids[row]
        p   = load_profile_by_id(pid) or {}
        self.f_name.setText(p.get("profile_name", ""))
        self.f_cname.setText(p.get("companion_name", ""))
        self.f_uname.setText(p.get("user_name", ""))
        self.f_desc.setText(p.get("description", ""))
        self.f_tags.setText(", ".join(p.get("tags", [])))
        details = p.get("profile_details", {})
        self.f_sysprompt.setPlainText(details.get("system_prompt", ""))

        is_active = pid == self._win.active_profile_id
        self.btn_activate.setObjectName("btn_active" if is_active else "btn_secondary")
        self.btn_activate.setText("✔ Active" if is_active else "Activate")
        self.btn_activate.style().unpolish(self.btn_activate)
        self.btn_activate.style().polish(self.btn_activate)

    def refresh(self) -> None:
        profiles = list_profiles()
        self._profile_ids = [p["profile_id"] for p in profiles]
        self.profile_list.clear()
        active_id = self._win.active_profile_id
        for p in profiles:
            label = p.get("profile_name", p["profile_id"])
            if p["profile_id"] == active_id:
                label = "✔  " + label
            self.profile_list.addItem(label)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Settings
# ─────────────────────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        self._win = win
        self._mic_map:     dict[str, int | None] = {}
        self._speaker_map: dict[str, int | None] = {}
        self._build()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _section(self, parent_layout: QVBoxLayout, title: str) -> QVBoxLayout:
        card = _make_card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 18)
        cl.setSpacing(10)
        cl.addWidget(_label(title, "sec_title"))
        parent_layout.addWidget(card)
        return cl

    def _toggle_row(
        self, layout: QVBoxLayout, label_text: str, checked: bool, callback
    ) -> QCheckBox:
        row = QHBoxLayout()
        row.setSpacing(8)
        cb = QCheckBox(label_text)
        cb.setChecked(checked)
        cb.toggled.connect(callback)
        row.addWidget(cb)
        row.addStretch()
        layout.addLayout(row)
        return cb

    def _info_row(self, layout: QVBoxLayout, label: str, value: str) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_label(label, "muted"))
        val = QLabel(value)
        val.setStyleSheet(f"color:{_C['text']};font-size:13px;")
        row.addWidget(val, 1)
        layout.addLayout(row)
        return val

    # ── build ─────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setObjectName("page_scroll")
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        inner.setObjectName("page_scroll_inner")
        scroll.setWidget(inner)

        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 16, 20, 24)
        root.setSpacing(14)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # ── Voice & Input ─────────────────────────────────────────────────────
        vi = self._section(root, "Voice & Input")
        self.chk_voice = self._toggle_row(
            vi, "Voice replies (TTS spoken output)",
            False, self._on_voice_toggled,
        )
        self.chk_handsfree = self._toggle_row(
            vi, "Hands-free mode (auto-listen after reply)",
            False, self._on_handsfree_toggled,
        )
        self.chk_mic_mute = self._toggle_row(
            vi, "Mic muted (block new captures)",
            False, self._on_mic_mute_toggled,
        )

        # ── Audio Devices ─────────────────────────────────────────────────────
        ad = self._section(root, "Audio Devices")
        hdr = QHBoxLayout()
        hdr.addStretch()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_secondary")
        self.btn_refresh.setMaximumWidth(120)
        hdr.addWidget(self.btn_refresh)
        ad.addLayout(hdr)
        ad.addWidget(_label("Microphone", "muted"))
        self.mic_combo = QComboBox()
        ad.addWidget(self.mic_combo)
        ad.addWidget(_label("Speaker / Output", "muted"))
        self.speaker_combo = QComboBox()
        ad.addWidget(self.speaker_combo)
        self.btn_apply_audio = QPushButton("Apply Audio Devices")
        self.btn_apply_audio.setMaximumWidth(200)
        ad.addWidget(self.btn_apply_audio)

        # ── Web Search ────────────────────────────────────────────────────────
        ws = self._section(root, "Web Search")
        self.chk_web = self._toggle_row(
            ws, "Enable web browsing",
            True, self._on_web_toggled,
        )
        self.chk_auto_search = self._toggle_row(
            ws, "Auto-search (LLM decides when to search)",
            False, self._on_auto_search_toggled,
        )
        self._web_provider_lbl = self._info_row(ws, "Provider:", "")
        self._web_url_lbl      = self._info_row(ws, "Search URL:", "")

        # ── LLM / Model ──────────────────────────────────────────────────────
        llm = self._section(root, "LLM / Model")
        self._llm_provider_lbl  = self._info_row(llm, "Provider:", "")
        self._llm_model_lbl     = self._info_row(llm, "Model:", "")
        self._llm_perf_lbl      = self._info_row(llm, "Perf profile:", "")
        self._llm_hardware_lbl  = self._info_row(llm, "Hardware:", "")

        # ── TTS / STT ────────────────────────────────────────────────────────
        ts = self._section(root, "TTS / STT")
        self._tts_lbl  = self._info_row(ts, "TTS:", "")
        self._stt_lbl  = self._info_row(ts, "STT:", "")

        root.addStretch()

        # ── Wire ──────────────────────────────────────────────────────────────
        self.btn_refresh.clicked.connect(self._refresh_devices)
        self.btn_apply_audio.clicked.connect(self._apply_audio)

    # ── toggle callbacks ──────────────────────────────────────────────────────
    def _on_voice_toggled(self, checked: bool) -> None:
        self._win.state.voice_enabled = checked
        self._win.dash_page.refresh()
        self._win._sb_voice.setText("Voice: " + ("On" if checked else "Off"))
        self._win.status_bar.showMessage(
            f"Voice replies {'enabled' if checked else 'disabled'}."
        )

    def _on_handsfree_toggled(self, checked: bool) -> None:
        self._win.hands_free_enabled = checked
        self._win.config.input_mode = "voice" if checked else "text"
        self._win.dash_page.refresh()
        self._win._sb_mode.setText("Mode: " + ("Voice" if checked else "Text"))
        if checked and not self._win.busy and not self._win.mic_muted and self._win.session_started:
            QTimer.singleShot(300, lambda: self._win._start_listen(auto=True))

    def _on_mic_mute_toggled(self, checked: bool) -> None:
        self._win.mic_muted = checked
        self._win.dash_page.refresh()
        self._win.chat_page.refresh_controls()
        self._win.status_bar.showMessage("Mic muted." if checked else "Mic live.")

    def _on_web_toggled(self, checked: bool) -> None:
        self._win.config.web_browsing_enabled = checked

    def _on_auto_search_toggled(self, checked: bool) -> None:
        self._win.config.web_auto_search = checked

    # ── audio devices ─────────────────────────────────────────────────────────
    def _refresh_devices(self) -> None:
        try:
            mics     = list_input_devices_compact()
            speakers = list_output_devices_compact()
        except Exception:
            mics = speakers = []

        self._mic_map = {"System default": None}
        for dev in mics:
            self._mic_map[dev["name"]] = dev["index"]
        self._speaker_map = {"System default": None}
        for dev in speakers:
            self._speaker_map[dev["name"]] = dev["index"]

        self.mic_combo.clear()
        self.mic_combo.addItems(list(self._mic_map.keys()))
        self.speaker_combo.clear()
        self.speaker_combo.addItems(list(self._speaker_map.keys()))

        win = self._win
        if win.config.mic_device_index is not None:
            for name, idx in self._mic_map.items():
                if idx == win.config.mic_device_index:
                    self.mic_combo.setCurrentText(name)
                    break
        if win.config.speaker_device_index is not None:
            for name, idx in self._speaker_map.items():
                if idx == win.config.speaker_device_index:
                    self.speaker_combo.setCurrentText(name)
                    break

    def _apply_audio(self) -> None:
        win = self._win
        win.config.mic_device_index     = self._mic_map.get(self.mic_combo.currentText())
        win.config.speaker_device_index = self._speaker_map.get(self.speaker_combo.currentText())
        win.state.mic_calibrated        = False
        win.state.speech_recognizer     = None
        win.state.speech_recognizer_signature = None
        win.status_bar.showMessage("Audio devices applied.")

    # ── populate all info labels from config ──────────────────────────────────
    def populate_info(self) -> None:
        cfg = self._win.config
        # Sync checkboxes to current state
        self.chk_voice.setChecked(self._win.state.voice_enabled)
        self.chk_handsfree.setChecked(self._win.hands_free_enabled)
        self.chk_mic_mute.setChecked(self._win.mic_muted)
        self.chk_web.setChecked(cfg.web_browsing_enabled)
        self.chk_auto_search.setChecked(cfg.web_auto_search)
        # Info labels
        self._web_provider_lbl.setText(cfg.web_search_provider)
        self._web_url_lbl.setText(cfg.web_search_url)
        self._llm_provider_lbl.setText(cfg.llm_provider)
        self._llm_model_lbl.setText(cfg.model)
        self._llm_perf_lbl.setText(cfg.performance_profile)
        self._llm_hardware_lbl.setText(cfg.system_summary)
        self._tts_lbl.setText(f"{cfg.tts_provider}  /  {describe_tts_voice(cfg)}")
        self._stt_lbl.setText(f"{cfg.stt_provider}  /  {cfg.stt_model}")


# ─────────────────────────────────────────────────────────────────────────────
# Page: Avatar (placeholder)
# ─────────────────────────────────────────────────────────────────────────────

class AvatarPage(QWidget):
    def __init__(self, win: "NovaAIWindow") -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setAlignment(Qt.AlignCenter)
        root.addStretch()
        icon = QLabel("⬡")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size:64px;color:{_C['muted']};")
        root.addWidget(icon)
        lbl = _label("Avatar AI  -  Coming Soon", "sec_title")
        lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(lbl)
        sub = _label("Live 3D avatar integration will appear here.", "muted")
        sub.setAlignment(Qt.AlignCenter)
        root.addWidget(sub)
        root.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# Nav sidebar
# ─────────────────────────────────────────────────────────────────────────────

_NAV_ITEMS = [
    ("dashboard",  "⊞  Dashboard"),
    ("chat",       "💬  Chat"),
    ("reminders",  "🔔  Reminders"),
    ("calendar",   "📅  Calendar"),
    ("shopping",   "🛒  Shopping"),
    ("todo",       "✅  To-Do"),
    ("profiles",   "👤  Profiles"),
    ("settings",   "⚙  Settings"),
    ("avatar",     "⬡  Avatar"),
]


class NavSidebar(QWidget):
    page_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("nav_sidebar")
        self._buttons: dict[str, QPushButton] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Logo / branding
        logo_area = QWidget()
        logo_area.setObjectName("nav_logo_area")
        la = QVBoxLayout(logo_area)
        la.setContentsMargins(18, 18, 18, 14)
        la.setSpacing(2)
        title = QLabel("NovaAI")
        title.setObjectName("nav_logo_title")
        la.addWidget(title)
        sub = QLabel("AI Companion Studio")
        sub.setObjectName("nav_logo_sub")
        la.addWidget(sub)
        root.addWidget(logo_area)

        # Nav buttons
        for key, label in _NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("nav_item")
            btn.setProperty("active", False)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda _c, k=key: self.page_changed.emit(k))
            self._buttons[key] = btn
            root.addWidget(btn)

        root.addStretch()

    def set_active(self, key: str) -> None:
        for k, btn in self._buttons.items():
            active = k == key
            btn.setProperty("active", active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class NovaAIWindow(QMainWindow):
    _sig_append_msg  = Signal(str, str, str)
    _sig_system_msg  = Signal(str)
    _sig_set_status  = Signal(str)
    _sig_features_ok = Signal()
    _sig_done        = Signal(str)   # internal use

    def __init__(self) -> None:
        super().__init__()
        ensure_runtime_dirs()
        self.config            = Config.from_env()
        self.active_profile_id = get_active_profile_id()
        self.profile           = load_profile() or {}
        self.state             = SessionState(
            voice_enabled=False,
            input_mode=self.config.input_mode,
        )
        self.config.voice_enabled = False

        self.session_started   = False
        self.hands_free_enabled = self.config.input_mode == "voice"
        self.mic_muted         = False
        self.busy              = False
        self.closing           = False
        self._worker: QThread | None = None

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(30_000)

        self._populate_pages()
        self._show_page("dashboard")

    # ── Window setup ──────────────────────────────────────────────────────────
    def _setup_window(self) -> None:
        self.setWindowTitle(
            f"{self.profile.get('companion_name','NovaAI')} Studio"
        )
        screen = QApplication.primaryScreen().availableGeometry()
        w = min(1380, max(960, screen.width() - 40))
        h = min(860,  max(600, screen.height() - 80))
        self.resize(w, h)
        self.move(
            max(0, (screen.width()  - w) // 2),
            max(0, (screen.height() - h) // 2),
        )

    def _setup_ui(self) -> None:
        # Central container
        central = QWidget()
        self.setCentralWidget(central)
        main_row = QHBoxLayout(central)
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)

        # Nav
        self.nav = NavSidebar()
        self.nav.page_changed.connect(self._show_page)
        main_row.addWidget(self.nav)

        # Content stack
        content = QWidget()
        content.setObjectName("content_stack")
        content_l = QVBoxLayout(content)
        content_l.setContentsMargins(0, 0, 0, 0)
        content_l.setSpacing(0)

        # Page header
        self._header_widget = QWidget()
        self._header_widget.setObjectName("page_header")
        self._header_widget.setFixedHeight(62)
        hl = QHBoxLayout(self._header_widget)
        hl.setContentsMargins(20, 10, 20, 10)
        hl.setSpacing(8)
        self._page_title_lbl = QLabel("Dashboard")
        self._page_title_lbl.setObjectName("page_title")
        self._page_sub_lbl   = QLabel("")
        self._page_sub_lbl.setObjectName("page_sub")
        hl.addWidget(self._page_title_lbl)
        hl.addWidget(self._page_sub_lbl)
        hl.addStretch()
        content_l.addWidget(self._header_widget)

        # Stack
        self.stack = QStackedWidget()
        self.stack.setObjectName("content_stack")
        content_l.addWidget(self.stack, 1)
        main_row.addWidget(content, 1)

        # Pages
        self.dash_page     = DashboardPage(self)
        self.chat_page     = ChatPage(self)
        self.remind_page   = RemindersPage(self)
        self.calendar_page = CalendarPage(self)
        self.shop_page     = ShoppingPage(self)
        self.todo_page     = TodoPage(self)
        self.profiles_page = ProfilesPage(self)
        self.settings_page = SettingsPage(self)
        self.avatar_page   = AvatarPage(self)

        self._pages = {
            "dashboard": (self.dash_page,     "Dashboard",    "Session controls and status"),
            "chat":      (self.chat_page,      "Chat",         "Conversation with your companion"),
            "reminders": (self.remind_page,    "Reminders",    "Reminders and alarms"),
            "calendar":  (self.calendar_page,  "Calendar",     "Upcoming events"),
            "shopping":  (self.shop_page,      "Shopping",     "Shopping list"),
            "todo":      (self.todo_page,       "To-Do",        "Task list"),
            "profiles":  (self.profiles_page,  "Profiles",     "Manage companion profiles"),
            "settings":  (self.settings_page,  "Settings",     "Audio devices and diagnostics"),
            "avatar":    (self.avatar_page,    "Avatar",       "3D avatar system"),
        }
        for page, _title, _sub in self._pages.values():
            self.stack.addWidget(page)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("NovaAI ready.")
        self._sb_session = QLabel("Session: Off")
        self._sb_voice   = QLabel("Voice: Off")
        self._sb_mode    = QLabel("Mode: Text")
        for lbl in (self._sb_session, self._sb_voice, self._sb_mode):
            lbl.setStyleSheet(f"color:{_C['muted2']};padding:0 10px;font-size:11px;")
            self.status_bar.addPermanentWidget(lbl)

        # F8 hotkey
        QShortcut(QKeySequence("F8"), self, activated=self.start_listen_once)

    def _connect_signals(self) -> None:
        self._sig_append_msg.connect(self._on_append_msg)
        self._sig_system_msg.connect(self._on_system_msg)
        self._sig_set_status.connect(self._on_set_status)
        self._sig_features_ok.connect(self._on_features_ok)

    def _populate_pages(self) -> None:
        self.dash_page.refresh()
        self.profiles_page.refresh()
        self.settings_page.populate_info()
        self.settings_page._refresh_devices()
        self._refresh_all_features()
        self._load_recent_history()

        self.chat_page.append_message(
            "System", "NovaAI is online in standby. Press Start Session to begin.", "system"
        )
        self.chat_page.append_message(
            "System", "Voice replies are off by default. Toggle Voice Replies when ready.", "system"
        )

    # ── Page navigation ───────────────────────────────────────────────────────
    _PAGE_TITLES = {
        "dashboard": ("Dashboard",   "Session controls and status"),
        "chat":      ("Chat",        "Conversation with your companion"),
        "reminders": ("Reminders",   "Reminders and alarms"),
        "calendar":  ("Calendar",    "Upcoming events"),
        "shopping":  ("Shopping",    "Shopping list"),
        "todo":      ("To-Do",       "Task list"),
        "profiles":  ("Profiles",    "Manage companion profiles"),
        "settings":  ("Settings",    "Audio devices and diagnostics"),
        "avatar":    ("Avatar",      "3D avatar system"),
    }

    def _show_page(self, key: str) -> None:
        if key not in self._pages:
            return
        page, _t, _s = self._pages[key]
        self.stack.setCurrentWidget(page)
        self.nav.set_active(key)
        title, sub = self._PAGE_TITLES.get(key, (key, ""))
        self._page_title_lbl.setText(title)
        self._page_sub_lbl.setText(sub)
        if key == "settings":
            self.settings_page.populate_info()
        elif key == "dashboard":
            self.dash_page.refresh()

    # ── Slot receivers (thread-safe) ──────────────────────────────────────────
    @Slot(str, str, str)
    def _on_append_msg(self, author: str, text: str, role: str) -> None:
        self.chat_page.append_message(author, text, role)

    @Slot(str)
    def _on_system_msg(self, text: str) -> None:
        self.chat_page.append_message("System", text, "system")

    @Slot(str)
    def _on_set_status(self, text: str) -> None:
        self.dash_page.set_status(text)
        self.status_bar.showMessage(text)

    @Slot()
    def _on_features_ok(self) -> None:
        self._refresh_all_features()

    def _on_worker_done(self, status: str) -> None:
        self.busy = False
        self._on_set_status(status)
        self.dash_page.refresh()
        self.chat_page.refresh_controls()
        self._sb_session.setText("Session: " + ("On" if self.session_started else "Off"))
        if (self.hands_free_enabled and not self.mic_muted
                and not self.closing and self.session_started):
            QTimer.singleShot(300, lambda: self._start_listen(auto=True))

    # ── History ───────────────────────────────────────────────────────────────
    def _load_recent_history(self) -> None:
        try:
            for entry in read_recent_history():
                role   = entry.get("role", "system")
                text   = entry.get("content", "")
                author = (
                    self.profile.get("user_name", "You")
                    if role == "user"
                    else self.profile.get("companion_name", "NovaAI")
                    if role == "assistant"
                    else "System"
                )
                self.chat_page.append_message(author, text, role)
        except Exception:
            pass

    # ── Session & controls ────────────────────────────────────────────────────
    def start_session(self) -> None:
        if self.session_started:
            self._on_set_status("Session is already running.")
            return
        self.session_started = True
        self._on_set_status("Session started.")
        self.dash_page.refresh()
        self.chat_page.refresh_controls()
        self._sb_session.setText("Session: On")
        self.chat_page.append_message(
            "System",
            "Session started. Voice replies are off by default. "
            "Toggle Voice Replies when you want spoken output.",
            "system",
        )
        if self.hands_free_enabled and not self.mic_muted and not self.busy:
            QTimer.singleShot(250, lambda: self._start_listen(auto=True))

    def toggle_hands_free(self) -> None:
        self.hands_free_enabled = not self.hands_free_enabled
        self.config.input_mode  = "voice" if self.hands_free_enabled else "text"
        self.dash_page.refresh()
        self._sb_mode.setText("Mode: " + ("Voice" if self.hands_free_enabled else "Text"))
        if self.hands_free_enabled:
            self._on_set_status("Hands-free mode on.")
            if not self.busy and not self.mic_muted and self.session_started:
                QTimer.singleShot(300, lambda: self._start_listen(auto=True))
        else:
            self._on_set_status("Hands-free mode off.")

    def toggle_mic_muted(self) -> None:
        self.mic_muted = not self.mic_muted
        self.dash_page.refresh()
        self.chat_page.refresh_controls()
        if self.mic_muted:
            self._on_set_status("Mic muted.")
        else:
            self._on_set_status("Mic live.")
            if self.hands_free_enabled and not self.busy and self.session_started:
                QTimer.singleShot(250, lambda: self._start_listen(auto=True))

    def toggle_voice_output(self) -> None:
        self.state.voice_enabled = not self.state.voice_enabled
        self.dash_page.refresh()
        self._sb_voice.setText("Voice: " + ("On" if self.state.voice_enabled else "Off"))
        self._on_set_status(
            f"Voice replies {'enabled' if self.state.voice_enabled else 'disabled'}."
        )

    def start_recalibration(self) -> None:
        if not self._begin_task():
            return
        self._on_set_status("Calibrating microphone...")
        t = _RecalibThread(self)
        t.done.connect(self._on_worker_done)
        t.finished.connect(t.deleteLater)
        self._worker = t
        t.start()

    def clear_history(self) -> None:
        r = QMessageBox.question(self, "Clear History", "Clear all conversation history?")
        if r != QMessageBox.Yes:
            return
        reset_history()
        self.chat_page.chat_log.clear()
        self.chat_page.append_message("System", "History cleared.", "system")
        self._on_set_status("History cleared.")

    def show_performance(self) -> None:
        lines = [
            f"Model: {self.config.model}",
            f"Provider: {self.config.llm_provider}",
            f"Performance profile: {self.config.performance_profile}",
            f"System: {self.config.system_summary}",
            "",
        ] + list(self.config.performance_notes)
        QMessageBox.information(self, "Performance Info", "\n".join(lines))

    # ── Send message ──────────────────────────────────────────────────────────
    def send_message(self, text: str) -> None:
        if not text or not self.session_started:
            return
        # Handle slash commands
        if text.startswith("/"):
            self._handle_command(text)
            return
        if not self._begin_task():
            return
        t = _ReplyThread(self, text, False)
        self._connect_worker(t)
        self._worker = t
        t.start()

    def _handle_command(self, cmd: str) -> None:
        lower = cmd.strip().lower()
        if lower in {"/listen", "/ask", "/voiceask"}:
            self.start_listen_once()
        elif lower == "/reset":
            self.clear_history()
        elif lower == "/voice":
            self.toggle_voice_output()
        elif lower == "/performance":
            self.show_performance()
        else:
            self.chat_page.append_message("System", f"Unknown command: {cmd}", "system")

    # ── Voice input ───────────────────────────────────────────────────────────
    def start_listen_once(self) -> None:
        if not self.session_started:
            return
        self._start_listen(auto=False)

    def _start_listen(self, auto: bool = False) -> None:
        if self.busy or self.mic_muted or self.closing:
            return
        if not self._begin_task():
            return
        self._on_set_status("Listening...")
        t = _VoiceThread(self, auto)
        self._connect_worker(t)
        self._worker = t
        t.start()

    def _connect_worker(self, t: _ReplyThread | _VoiceThread) -> None:
        t.append_msg.connect(self._sig_append_msg)
        t.system_msg.connect(self._sig_system_msg)
        t.set_status.connect(self._sig_set_status)
        t.features_ok.connect(self._sig_features_ok)
        t.done.connect(self._on_worker_done)
        t.finished.connect(t.deleteLater)

    # ── Reply pipeline (runs in worker thread) ────────────────────────────────
    def _pipeline(
        self,
        user_text: str,
        from_voice: bool,
        worker: _ReplyThread | _VoiceThread,
    ) -> str:
        worker.append_msg.emit(
            self.profile.get("user_name", "You"), user_text, "user"
        )
        worker.set_status.emit("Thinking through your message...")

        # Media
        media_action = handle_media_request(user_text, self.profile, self.config)
        if media_action.handled:
            self.profile = save_profile_by_id(self.active_profile_id, self.profile)
            append_history("user", user_text)
            append_history("assistant", media_action.response)
            worker.append_msg.emit(
                self.profile.get("companion_name", "NovaAI"),
                media_action.response,
                "assistant",
            )
            return "Media request handled."

        # Features
        feature_result = handle_feature_request(user_text, self.profile)
        if feature_result.handled:
            if feature_result.save_needed:
                self.profile = save_profile_by_id(self.active_profile_id, self.profile)
            append_history("user", user_text)
            append_history("assistant", feature_result.response)
            worker.append_msg.emit(
                self.profile.get("companion_name", "NovaAI"),
                feature_result.response,
                "assistant",
            )
            worker.features_ok.emit()
            if self.state.voice_enabled:
                speak_text(feature_result.response, self.config, self.state)
            return "Feature request handled."

        # Web context
        web_context: str | None = None
        web_note:    str | None = None
        if self.config.web_browsing_enabled:
            web_query = self.state.pending_web_query
            if self.state.pending_web_context:
                web_context = self.state.pending_web_context
                self.state.pending_web_context = None
                self.state.pending_web_query   = None
                if web_query:
                    web_note = f"Using queued web results for: {web_query}"
            else:
                if not web_query:
                    inferred = extract_web_query_from_request(user_text)
                    if inferred:
                        web_query = inferred
                        web_note  = f"Interpreted as lookup: {web_query}"
                if not web_query and self.config.web_auto_search and should_auto_search(user_text):
                    web_query = user_text
                if web_query:
                    try:
                        bundle = fetch_web_context(web_query, self.config)
                        web_context = bundle.context
                        web_note = (
                            f"Web: {bundle.result_count} results for: {bundle.query}"
                        )
                    except RuntimeError as exc:
                        web_note = f"Web search skipped: {exc}"
                    finally:
                        self.state.pending_web_query = None

        if web_note:
            worker.system_msg.emit(web_note)

        worker.set_status.emit("Generating reply...")
        reply = request_reply(user_text, self.profile, self.config, web_context=web_context)
        append_history("user",      user_text)
        append_history("assistant", reply)
        worker.append_msg.emit(
            self.profile.get("companion_name", "NovaAI"), reply, "assistant"
        )

        if self.state.voice_enabled:
            worker.set_status.emit("Speaking reply...")
            audio_path = speak_text(reply, self.config, self.state)
            if should_play_audio_after_synthesis(self.config):
                play_audio_file(audio_path, self.config.speaker_device_index)

        if from_voice and self.hands_free_enabled and not self.mic_muted:
            return "Reply done. Hands-free will listen again."
        return "System idle. Ready when you are."

    # ── Task busy guard ───────────────────────────────────────────────────────
    def _begin_task(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        self.dash_page.refresh()
        self.chat_page.refresh_controls()
        return True

    # ── Reminder check ────────────────────────────────────────────────────────
    def _check_reminders(self) -> None:
        try:
            fired = check_due_reminders(self.profile)
            for r in fired:
                msg = r.get("title", "Reminder!")
                self.chat_page.append_message("System", f"Reminder: {msg}", "system")
                self.status_bar.showMessage(f"Reminder: {msg}")
            fired_alarms = check_due_alarms(self.profile)
            for a in fired_alarms:
                label = a.get("label", "Alarm!")
                self.chat_page.append_message("System", f"Alarm: {label}", "system")
                self.status_bar.showMessage(f"Alarm: {label}")
            if fired or fired_alarms:
                self.profile = save_profile_by_id(self.active_profile_id, self.profile)
        except Exception:
            pass

    # ── Feature refresh ───────────────────────────────────────────────────────
    def _refresh_all_features(self) -> None:
        self.remind_page.refresh_all()
        self.calendar_page.refresh()
        self.shop_page.refresh()
        self.todo_page.refresh()

    # ── Close ─────────────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        self.closing = True
        self._reminder_timer.stop()
        try:
            stop_media_playback()
        except Exception:
            pass
        if self._worker and self._worker.isRunning():
            self._worker.wait(3000)
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setApplicationName("NovaAI")

    win = NovaAIWindow()
    win.show()
    sys.exit(app.exec())
