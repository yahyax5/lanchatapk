import base64
import io
import json
import os
import queue
import re
import socket
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex

Window.softinput_mode = "below_target"

TCP_PORT = 5050
UDP_PORT = 5051
DEPARTMENTS = ["Accounting", "Mini Shop", "Dispatch Store", "HR", "Lab", "Management", "Other"]

DEFAULT_BRANDING = {
    "company": "Company LAN Chat",
    "tagline": "Internal messenger - works without internet",
    "industry": "Milling & Food Processing",
    "preset": "2go Green",
    "header": "",
    "accent": "",
    "font": 10,
}

EMOTICONS = {
    ":)": "☺", ":-)": "☺", ":D": "☻", ":(": "☹", ":-(": "☹",
    "<3": "♥", "(y)": "✔", "(n)": "✘", "(*)": "★",
}
_EMO_RE = re.compile(r"(?<!\S)(" + "|".join(re.escape(k) for k in EMOTICONS) + r")(?!\S)")


def _theme(bg, panel, grid, text, dim, acc, acc2, pal, ok=None, bad="#ff5a4a"):
    return {
        "bg": bg, "panel": panel, "grid": grid, "text": text, "muted": dim,
        "acc": acc, "acc2": acc2, "pal": pal, "ok": ok or acc, "bad": bad,
    }


PRESETS = {
    "Classic Blue": _theme("#070b0f", "#0c141c", "#17293a", "#d8ecff", "#5d7f9c", "#4aa8ff", "#22e0ff",
                           ["#4aa8ff", "#22e0ff", "#3cf0b0", "#ffd166", "#a78bfa", "#7fc4ff"], ok="#3cf0b0"),
    "2go Green":    _theme("#050a07", "#09130d", "#16331f", "#d6ffe4", "#5f8f72", "#39ff88", "#9dff5b",
                           ["#39ff88", "#9dff5b", "#2fd6c0", "#ffd23f", "#7ae0ff", "#c5ff9a"]),
    "Grain & Gold": _theme("#0b0802", "#150f04", "#3a2a0a", "#ffe9c0", "#9a7a3c", "#ffb000", "#ff7a1a",
                           ["#ffb000", "#ff7a1a", "#ffe27a", "#ffcf8a", "#ff9f40", "#ffd9a0"], ok="#ffc933"),
    "Steel & Safety": _theme("#08090a", "#111315", "#272b2f", "#f1f3f5", "#7b838a", "#f1f3f5", "#aab2b8",
                             ["#f1f3f5", "#c3c9ce", "#9aa2a9", "#e0e4e7", "#7b838a", "#b0b7bd"]),
    "Teal Care":    _theme("#050c0c", "#091615", "#12332f", "#d4fffb", "#5b9490", "#19e6d3", "#5cf2a8",
                           ["#19e6d3", "#5cf2a8", "#7ae0ff", "#ffd23f", "#c5ff9a", "#2fd6c0"], ok="#5cf2a8"),
    "Retail Rose":  _theme("#0d0609", "#170b11", "#3a1625", "#ffdce8", "#9a6a7c", "#ff4f93", "#ff9ac0",
                           ["#ff4f93", "#ff9ac0", "#ffd23f", "#7ae0ff", "#c5a0ff", "#ffb36b"], ok="#7dffb0"),
    "Night Mode":   _theme("#070914", "#0d1124", "#1c2750", "#dfe6ff", "#6b79ad", "#8f9bff", "#4de1ff",
                           ["#8f9bff", "#4de1ff", "#3cf0b0", "#ffd166", "#c5a0ff", "#ff8fb0"], ok="#3cf0b0"),
    "Daylight":     _theme("#eef1f4", "#ffffff", "#d5dbe1", "#10161c", "#6a7681", "#0a7f5a", "#1264d6",
                           ["#0a7f5a", "#1264d6", "#b7791f", "#7c3aed", "#d6392b", "#0891b2"], ok="#0a8f4e"),
}


def hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix_hex(a, b, t):
    ra, rb = hex_rgb(a), hex_rgb(b)
    vals = [max(0, min(255, int(round(ra[i] + (rb[i] - ra[i]) * t)))) for i in range(3)]
    return "#%02x%02x%02x" % tuple(vals)


def rgba(h, alpha=1.0):
    c = get_color_from_hex(h)
    return [c[0], c[1], c[2], alpha]


def lum(h):
    r, g, b = hex_rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def contrast_hex(h):
    return "#ffffff" if lum(h) < 0.62 else "#1b1b1b"


def set_bg(widget, hex_color, radius=0):
    widget.canvas.before.clear()
    with widget.canvas.before:
        Color(*rgba(hex_color))
        if radius:
            rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(radius)])
        else:
            rect = Rectangle(pos=widget.pos, size=widget.size)

    def _upd(inst, _):
        rect.pos = inst.pos
        rect.size = inst.size

    widget.bind(pos=_upd, size=_upd)


def discover(timeout=1.5):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(timeout)
    try:
        for _ in range(2):
            try:
                s.sendto(b"LANCHAT_DISCOVER", ("255.255.255.255", UDP_PORT))
                data, addr = s.recvfrom(256)
                if data.startswith(b"LANCHAT_SERVER"):
                    return addr[0]
            except socket.timeout:
                pass
            except OSError:
                break
    finally:
        s.close()
    return None


class Net:
    def __init__(self, inbox):
        self.inbox = inbox
        self.sock = None
        self.lock = threading.Lock()

    def connect(self, host):
        s = socket.create_connection((host, TCP_PORT), timeout=5)
        s.settimeout(None)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.sock = s
        threading.Thread(target=self._reader, args=(s,), daemon=True).start()

    def _reader(self, s):
        try:
            f = s.makefile("r", encoding="utf-8", newline="\n")
            for line in f:
                try:
                    self.inbox.put(json.loads(line))
                except ValueError:
                    pass
        except OSError:
            pass
        self.inbox.put({"type": "_disconnected", "sock": s})

    def send(self, obj):
        try:
            with self.lock:
                self.sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        except (OSError, AttributeError):
            pass

    def close(self):
        try:
            self.sock.close()
        except (OSError, AttributeError):
            pass


class DotWidget(Widget):
    def __init__(self, color_hex, **kw):
        super().__init__(size_hint=(None, None), size=(dp(12), dp(12)), **kw)
        with self.canvas:
            Color(*rgba(color_hex))
            self.dot = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self.dot.pos = self.pos
        self.dot.size = self.size


class LoginScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        p = self.app.pal
        root = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
        set_bg(root, p["bg"])

        hdr = BoxLayout(size_hint_y=None, height=dp(64), padding=[dp(14), dp(8)], spacing=dp(10))
        set_bg(hdr, p["panel"], radius=8)
        if self.app.logo_tex:
            hdr.add_widget(Image(texture=self.app.logo_tex, size_hint=(None, 1), width=dp(46)))
        titles = BoxLayout(orientation="vertical")
        titles.add_widget(Label(
            text=self.app.branding.get("company", "LAN Chat").upper(),
            color=rgba(p["acc"]), bold=True, font_size=sp(16), halign="left", valign="middle",
            text_size=(Window.width - dp(120), None),
        ))
        titles.add_widget(Label(
            text=self.app.branding.get("tagline", ""),
            color=rgba(p["muted"]), font_size=sp(11), halign="left", valign="middle",
            text_size=(Window.width - dp(120), None),
        ))
        hdr.add_widget(titles)
        root.add_widget(hdr)

        scroll = ScrollView()
        card = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(18), spacing=dp(10))
        card.bind(minimum_height=card.setter("height"))
        set_bg(card, p["panel"], radius=10)

        card.add_widget(Label(
            text="Sign in", color=rgba(p["text"]), bold=True, font_size=sp(22),
            size_hint_y=None, height=dp(36), halign="left", text_size=(Window.width - dp(72), None),
        ))

        def field_label(txt):
            lbl = Label(
                text=txt, color=rgba(p["muted"]), font_size=sp(11), bold=True,
                size_hint_y=None, height=dp(20), halign="left",
            )
            lbl.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
            return lbl

        def make_input(text="", hint="", password=False):
            return TextInput(
                text=text, hint_text=hint, password=password, multiline=False,
                size_hint_y=None, height=dp(44), padding=[dp(10), dp(11)],
                background_normal="", background_active="",
                background_color=rgba(p["bg"]), foreground_color=rgba(p["text"]),
                hint_text_color=rgba(p["muted"]), cursor_color=rgba(p["acc"]),
                font_size=sp(15),
            )

        card.add_widget(field_label("YOUR NAME"))
        self.in_name = make_input(self.app.conf.get("name", ""), "Enter your name")
        card.add_widget(self.in_name)

        card.add_widget(field_label("DEPARTMENT"))
        self.in_dept = Spinner(
            text=self.app.conf.get("dept", DEPARTMENTS[0]), values=DEPARTMENTS,
            size_hint_y=None, height=dp(44), background_normal="",
            background_color=rgba(p["bg"]), color=rgba(p["text"]), font_size=sp(15),
        )
        card.add_widget(self.in_dept)

        card.add_widget(field_label("PASSWORD"))
        self.in_pw = make_input("", "Password", password=True)
        self.in_pw.bind(on_text_validate=lambda *_: self.do_connect())
        card.add_widget(self.in_pw)

        card.add_widget(field_label("SERVER IP (LEAVE BLANK FOR AUTO-DISCOVER)"))
        self.in_srv = make_input(self.app.conf.get("server", ""), "e.g. 192.168.1.10 or blank")
        card.add_widget(self.in_srv)

        self.btn_connect = Button(
            text="Connect", size_hint_y=None, height=dp(48), bold=True, font_size=sp(16),
            background_normal="", background_color=rgba(p["acc"]), color=rgba(contrast_hex(p["acc"])),
        )
        self.btn_connect.bind(on_release=lambda *_: self.do_connect())
        card.add_widget(Widget(size_hint_y=None, height=dp(6)))
        card.add_widget(self.btn_connect)

        self.lbl_msg = Label(
            text="Use the name and password your administrator gave you.",
            color=rgba(p["muted"]), font_size=sp(12), size_hint_y=None, height=dp(48),
            halign="left", valign="top",
        )
        self.lbl_msg.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        card.add_widget(self.lbl_msg)

        scroll.add_widget(card)
        root.add_widget(scroll)
        self.add_widget(root)

    def set_msg(self, text, bad=False):
        p = self.app.pal
        self.lbl_msg.text = text
        self.lbl_msg.color = rgba(p["bad"] if bad else p["muted"])
        self.btn_connect.disabled = False

    def do_connect(self):
        name = self.in_name.text.strip()
        dept = self.in_dept.text.strip()
        pw = self.in_pw.text
        srv = self.in_srv.text.strip()
        if not name or not pw:
            self.set_msg("Please enter your name and password.", bad=True)
            return
        self.btn_connect.disabled = True
        self.set_msg("Connecting to server...")
        self.app.start_connect(name, dept, pw, srv)


class DirectoryScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        p = self.app.pal
        root = BoxLayout(orientation="vertical")
        set_bg(root, p["bg"])

        top = BoxLayout(size_hint_y=None, height=dp(58), padding=[dp(12), dp(8)], spacing=dp(10))
        set_bg(top, p["panel"])
        if self.app.logo_tex:
            top.add_widget(Image(texture=self.app.logo_tex, size_hint=(None, 1), width=dp(38)))
        title_box = BoxLayout(orientation="vertical")
        self.lbl_company = Label(
            text=self.app.branding.get("company", "LAN Chat"), color=rgba(p["acc"]),
            bold=True, font_size=sp(15), halign="left", valign="middle",
        )
        self.lbl_company.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.lbl_live = Label(
            text="ONLINE", color=rgba(p["ok"]), font_size=sp(11), bold=True, halign="left",
        )
        self.lbl_live.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        title_box.add_widget(self.lbl_company)
        title_box.add_widget(self.lbl_live)
        top.add_widget(title_box)

        btn_menu = Button(
            text="Menu", size_hint=(None, 1), width=dp(76), bold=True, font_size=sp(13),
            background_normal="", background_color=rgba(p["grid"]), color=rgba(p["text"]),
        )
        btn_menu.bind(on_release=lambda *_: self.app.open_menu())
        top.add_widget(btn_menu)
        root.add_widget(top)

        self.scroll = ScrollView()
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, padding=[dp(10), dp(8)], spacing=dp(4))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.scroll.add_widget(self.list_box)
        root.add_widget(self.scroll)

        self.lbl_status = Label(
            text="", size_hint_y=None, height=dp(30), color=rgba(p["muted"]),
            font_size=sp(11), padding=[dp(12), 0], halign="left", valign="middle",
        )
        self.lbl_status.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        set_bg(self.lbl_status, p["panel"])
        root.add_widget(self.lbl_status)

        self.add_widget(root)
        self.refresh_list()

    def set_live(self, on):
        p = self.app.pal
        self.lbl_live.text = "● LIVE" if on else "○ RECONNECTING..."
        self.lbl_live.color = rgba(p["ok"] if on else p["bad"])

    def refresh_list(self):
        p = self.app.pal
        self.list_box.clear_widgets()

        def add_header(text):
            lbl = Label(
                text=text, color=rgba(p["muted"]), bold=True, font_size=sp(11),
                size_hint_y=None, height=dp(28), halign="left", valign="bottom",
            )
            lbl.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
            self.list_box.add_widget(lbl)

        def add_row(conv_id, title, dot_color, unread_cnt, muted=False):
            row = BoxLayout(size_hint_y=None, height=dp(48), padding=[dp(12), dp(6)], spacing=dp(10))
            set_bg(row, p["panel"], radius=8)

            dot_wrap = AnchorLayout(size_hint=(None, 1), width=dp(14))
            dot_wrap.add_widget(DotWidget(dot_color))
            row.add_widget(dot_wrap)

            btn = Button(
                text=title, halign="left", valign="middle",
                background_normal="", background_color=(0, 0, 0, 0),
                color=rgba(p["muted"] if muted and not unread_cnt else (p["acc"] if unread_cnt else p["text"])),
                bold=bool(unread_cnt), font_size=sp(15),
            )
            btn.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
            btn.bind(on_release=lambda *_: self.app.open_conv(conv_id))
            row.add_widget(btn)

            if unread_cnt:
                badge = Label(
                    text=str(unread_cnt), size_hint=(None, None), size=(dp(28), dp(24)),
                    color=rgba(contrast_hex(p["acc"])), bold=True, font_size=sp(12),
                )
                set_bg(badge, p["acc"], radius=12)
                b_wrap = AnchorLayout(size_hint=(None, 1), width=dp(32))
                b_wrap.add_widget(badge)
                row.add_widget(b_wrap)

            self.list_box.add_widget(row)

        if self.app.channels:
            add_header("CHANNELS")
            for ch in self.app.channels:
                add_row(ch, ch, p["acc"], self.app.unread.get(ch, 0))

        depts = {}
        for u in self.app.users.values():
            if u["name"] != self.app.user:
                depts.setdefault(u.get("dept") or "Other", []).append(u)

        for d in sorted(depts):
            add_header(d.upper())
            members = sorted(depts[d], key=lambda x: (not x.get("online"), x["name"].lower()))
            for u in members:
                on = bool(u.get("online"))
                add_row(
                    u["name"], u["name"], p["ok"] if on else p["muted"],
                    self.app.unread.get(u["name"], 0), muted=not on,
                )

        online = sum(1 for u in self.app.users.values() if u.get("online"))
        if self.app.user:
            self.lbl_status.text = f"Signed in as {self.app.user}  •  {online}/{len(self.app.users)} online"


class ChatScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.last_day = None
        self.last_sender = None
        self.last_ts = 0
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        p = self.app.pal
        root = BoxLayout(orientation="vertical")
        set_bg(root, p["bg"])

        top = BoxLayout(size_hint_y=None, height=dp(58), padding=[dp(8), dp(8)], spacing=dp(8))
        set_bg(top, p["panel"])
        btn_back = Button(
            text="< Back", size_hint=(None, 1), width=dp(72), bold=True, font_size=sp(13),
            background_normal="", background_color=rgba(p["grid"]), color=rgba(p["text"]),
        )
        btn_back.bind(on_release=lambda *_: self.app.go_directory())
        top.add_widget(btn_back)

        titles = BoxLayout(orientation="vertical")
        self.lbl_title = Label(
            text="", color=rgba(p["text"]), bold=True, font_size=sp(16), halign="left", valign="middle",
        )
        self.lbl_title.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.lbl_sub = Label(
            text="", color=rgba(p["acc"]), font_size=sp(11), halign="left", valign="middle",
        )
        self.lbl_sub.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        titles.add_widget(self.lbl_title)
        titles.add_widget(self.lbl_sub)
        top.add_widget(titles)
        root.add_widget(top)

        self.scroll = ScrollView(do_scroll_x=False)
        self.feed = BoxLayout(orientation="vertical", size_hint_y=None, padding=[dp(10), dp(10)], spacing=dp(4))
        self.feed.bind(minimum_height=self.feed.setter("height"))
        self.scroll.add_widget(self.feed)
        root.add_widget(self.scroll)

        bar = BoxLayout(size_hint_y=None, height=dp(58), padding=[dp(8), dp(8)], spacing=dp(8))
        set_bg(bar, p["panel"])
        self.entry = TextInput(
            hint_text="Type a message...", multiline=True, font_size=sp(15),
            padding=[dp(10), dp(10)], background_normal="", background_active="",
            background_color=rgba(p["bg"]), foreground_color=rgba(p["text"]),
            hint_text_color=rgba(p["muted"]), cursor_color=rgba(p["acc"]),
        )
        btn_send = Button(
            text="Send", size_hint=(None, 1), width=dp(76), bold=True, font_size=sp(15),
            background_normal="", background_color=rgba(p["acc"]), color=rgba(contrast_hex(p["acc"])),
        )
        btn_send.bind(on_release=lambda *_: self.send_msg())
        bar.add_widget(self.entry)
        bar.add_widget(btn_send)
        root.add_widget(bar)

        self.add_widget(root)

    def update_heading(self):
        conv = self.app.current
        if not conv:
            return
        self.lbl_title.text = conv
        if conv.startswith("#"):
            self.lbl_sub.text = "CHANNEL • EVERYONE CAN READ"
        else:
            u = self.app.users.get(conv, {})
            st = "ONLINE" if u.get("online") else "OFFLINE"
            self.lbl_sub.text = f"{u.get('dept', '')} • {st}".upper()

    def render_all(self):
        self.feed.clear_widgets()
        self.last_day = None
        self.last_sender = None
        self.last_ts = 0
        for m in self.app.msgs[-250:]:
            self.add_msg(m, scroll=False)
        Clock.schedule_once(lambda *_: setattr(self.scroll, "scroll_y", 0), 0.05)

    def add_msg(self, m, scroll=True):
        p = self.app.pal
        lt = time.localtime(m["ts"])
        day = time.strftime("%A, %d %b %Y", lt)
        if day != self.last_day:
            day_lbl = Label(
                text=day.upper(), color=rgba(p["muted"]), font_size=sp(10), bold=True,
                size_hint_y=None, height=dp(26),
            )
            self.feed.add_widget(day_lbl)
            self.last_day = day
            self.last_sender = None

        mine = m["from"] == self.app.user
        group = bool(self.app.current and self.app.current.startswith("#"))
        new_run = not (self.last_sender == m["from"] and m["ts"] - self.last_ts < 300)

        max_w = min(dp(300), max(dp(180), Window.width * 0.74))
        dark = lum(p["bg"]) < 0.4
        bub_other = mix_hex(p["bg"], p["text"], 0.10) if dark else p["panel"]
        bub_me = mix_hex(p["bg"], p["acc"], 0.28) if dark else mix_hex(p["panel"], p["acc"], 0.20)

        bubble = BoxLayout(orientation="vertical", size_hint=(None, None), padding=[dp(12), dp(8)], spacing=dp(2))
        set_bg(bubble, bub_me if mine else bub_other, radius=14)

        sender_w = 0
        sender_h = 0
        if group and not mine and new_run:
            pal = p["pal"]
            ncol = pal[sum(map(ord, m["from"])) % len(pal)]
            s_lbl = Label(
                text=m["from"], color=rgba(ncol), bold=True, font_size=sp(12),
                size_hint=(None, None), halign="left",
            )
            s_lbl.texture_update()
            sender_w = min(s_lbl.texture_size[0], max_w)
            sender_h = dp(17)
            bubble.add_widget(s_lbl)
        else:
            s_lbl = None

        msg_lbl = Label(
            text=m["text"], color=rgba(p["text"]), font_size=sp(15),
            size_hint=(None, None), halign="left", valign="top",
        )
        msg_lbl.texture_update()
        if msg_lbl.texture_size[0] > max_w:
            msg_lbl.text_size = (max_w, None)
            msg_lbl.texture_update()
        msg_lbl.size = msg_lbl.texture_size
        bubble.add_widget(msg_lbl)

        t_lbl = Label(
            text=time.strftime("%H:%M", lt), color=rgba(p["muted"]), font_size=sp(10),
            size_hint=(None, None), halign="right", valign="middle",
        )
        t_lbl.texture_update()
        time_w = t_lbl.texture_size[0]
        bubble.add_widget(t_lbl)

        content_w = max(msg_lbl.width, sender_w, time_w, dp(36))
        if s_lbl:
            s_lbl.text_size = (content_w, None)
            s_lbl.size = (content_w, sender_h)
        t_lbl.text_size = (content_w, None)
        t_lbl.size = (content_w, dp(14))

        bubble.width = content_w + dp(24)
        bubble.height = msg_lbl.height + dp(14) + (sender_h + dp(2) if s_lbl else 0) + dp(18)

        row = AnchorLayout(
            anchor_x="right" if mine else "left",
            size_hint_y=None, height=bubble.height + (dp(6) if new_run else dp(2)),
        )
        row.add_widget(bubble)
        self.feed.add_widget(row)

        self.last_sender = m["from"]
        self.last_ts = m["ts"]
        if scroll:
            Clock.schedule_once(lambda *_: setattr(self.scroll, "scroll_y", 0), 0.03)

    def send_msg(self):
        text = self.entry.text.strip()
        if not text or not self.app.current:
            return
        text = _EMO_RE.sub(lambda mo: EMOTICONS[mo.group(1)], text)
        self.app.net.send({"type": "msg", "to": self.app.current, "text": text})
        self.entry.text = ""


class LanChatApp(App):
    def build(self):
        self.title = "LAN Chat"
        self.conf_path = os.path.join(self.user_data_dir, "lanchat.json")
        self.conf = self.load_conf()
        self.branding = dict(DEFAULT_BRANDING)
        self.branding.update(self.conf.get("branding", {}))
        self.logo_b64 = self.conf.get("logo", "")
        self.logo_tex = self.decode_logo(self.logo_b64)

        self.inbox = queue.Queue()
        self.net = Net(self.inbox)
        self.creds = None
        self.user = None
        self.logged_in = False
        self.reconnecting = False
        self.channels = []
        self.users = {}
        self.unread = {}
        self.current = None
        self.msgs = []

        self.compute_palette()
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.scr_login = LoginScreen(self, name="login")
        self.scr_dir = DirectoryScreen(self, name="dir")
        self.scr_chat = ChatScreen(self, name="chat")
        self.sm.add_widget(self.scr_login)
        self.sm.add_widget(self.scr_dir)
        self.sm.add_widget(self.scr_chat)

        Window.bind(on_keyboard=self.on_back_button)
        Clock.schedule_interval(self.poll, 0.1)
        return self.sm

    def load_conf(self):
        try:
            with open(self.conf_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_conf(self):
        try:
            os.makedirs(os.path.dirname(self.conf_path), exist_ok=True)
            with open(self.conf_path, "w", encoding="utf-8") as f:
                json.dump(self.conf, f)
        except OSError:
            pass

    def decode_logo(self, b64):
        if not b64:
            return None
        try:
            raw = base64.b64decode(b64)
            return CoreImage(io.BytesIO(raw), ext="png").texture
        except Exception:
            return None

    def compute_palette(self):
        mine = self.conf.get("my_theme")
        preset = mine if mine in PRESETS else self.branding.get("preset", "Classic Blue")
        p = dict(PRESETS.get(preset, PRESETS["Classic Blue"]))
        if not mine:
            if self.branding.get("accent"):
                p["acc"] = self.branding["accent"]
            if self.branding.get("header"):
                p["acc2"] = self.branding["header"]
        self.pal = p

    def rebuild_ui(self):
        self.compute_palette()
        cur = self.sm.current
        self.scr_login.build_ui()
        self.scr_dir.build_ui()
        self.scr_chat.build_ui()
        self.scr_chat.update_heading()
        self.scr_chat.render_all()
        self.sm.current = cur

    def on_back_button(self, window, key, *args):
        if key == 27:  # Android back button
            if self.sm.current == "chat":
                self.go_directory()
                return True
        return False

    def start_connect(self, name, dept, pw, host):
        self.creds = (name, dept, pw, host)
        threading.Thread(target=self.connect_worker, daemon=True).start()

    def connect_worker(self, silent=False):
        name, dept, pw, host = self.creds
        auto = not host
        if auto:
            host = discover()
            if not host:
                if not silent:
                    self.inbox.put({
                        "type": "_connect_failed",
                        "text": "Server not found on Wi-Fi. Type the Server IP manually.",
                    })
                return False
        try:
            self.net.close()
            self.net.connect(host)
        except OSError:
            if not silent:
                self.inbox.put({"type": "_connect_failed", "text": f"Could not connect to {host}."})
            return False
        self.conf.update({"name": name, "dept": dept, "server": "" if auto else host})
        self.save_conf()
        self.net.send({"type": "login", "user": name, "dept": dept, "pw": pw})
        return True

    def reconnect_loop(self):
        while self.reconnecting:
            time.sleep(3)
            if not self.reconnecting:
                break
            self.connect_worker(silent=True)
            time.sleep(2)

    def go_directory(self):
        self.current = None
        self.sm.transition.direction = "right"
        self.sm.current = "dir"
        self.scr_dir.refresh_list()

    def open_conv(self, conv):
        self.current = conv
        self.unread.pop(conv, None)
        self.msgs = []
        self.scr_chat.update_heading()
        self.scr_chat.render_all()
        self.net.send({"type": "history", "conv": conv})
        self.scr_dir.refresh_list()
        self.sm.transition.direction = "left"
        self.sm.current = "chat"

    def open_menu(self):
        p = self.pal
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        pop = Popup(title="Menu", content=box, size_hint=(0.86, 0.72),
                    background_color=rgba(p["panel"]), title_color=rgba(p["acc"]))

        def add_btn(txt, cb, col=p["grid"], fg=p["text"]):
            b = Button(text=txt, size_hint_y=None, height=dp(42), background_normal="",
                       background_color=rgba(col), color=rgba(fg), bold=True)
            b.bind(on_release=lambda *_: (pop.dismiss(), cb()))
            box.add_widget(b)

        add_btn("Change Password", self.open_pw_popup)

        box.add_widget(Label(text="THEME", color=rgba(p["muted"]), size_hint_y=None, height=dp(22), font_size=sp(11)))
        scroll = ScrollView()
        tbox = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        tbox.bind(minimum_height=tbox.setter("height"))

        def pick_theme(name):
            if name is None:
                self.conf.pop("my_theme", None)
            else:
                self.conf["my_theme"] = name
            self.save_conf()
            pop.dismiss()
            self.rebuild_ui()

        b_def = Button(text="Company Default", size_hint_y=None, height=dp(38),
                       background_normal="", background_color=rgba(p["bg"]), color=rgba(p["text"]))
        b_def.bind(on_release=lambda *_: pick_theme(None))
        tbox.add_widget(b_def)

        for nm in PRESETS:
            b = Button(text=nm, size_hint_y=None, height=dp(38),
                       background_normal="", background_color=rgba(p["bg"]), color=rgba(PRESETS[nm]["acc"]))
            b.bind(on_release=lambda _, n=nm: pick_theme(n))
            tbox.add_widget(b)

        scroll.add_widget(tbox)
        box.add_widget(scroll)
        add_btn("Sign Out", self.sign_out, col=p["bad"], fg="#ffffff")
        pop.open()

    def open_pw_popup(self):
        p = self.pal
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        old_in = TextInput(hint_text="Current password", password=True, multiline=False, size_hint_y=None, height=dp(42))
        new_in = TextInput(hint_text="New password (min 4 chars)", password=True, multiline=False, size_hint_y=None, height=dp(42))
        box.add_widget(old_in)
        box.add_widget(new_in)
        pop = Popup(title="Change Password", content=box, size_hint=(0.86, 0.38),
                    background_color=rgba(p["panel"]), title_color=rgba(p["acc"]))
        btn = Button(text="Update", size_hint_y=None, height=dp(44), background_normal="",
                     background_color=rgba(p["acc"]), color=rgba(contrast_hex(p["acc"])), bold=True)

        def submit(*_):
            if old_in.text and new_in.text:
                self.net.send({"type": "change_pw", "old": old_in.text, "new": new_in.text})
                pop.dismiss()

        btn.bind(on_release=submit)
        box.add_widget(btn)
        pop.open()

    def sign_out(self):
        self.logged_in = False
        self.reconnecting = False
        self.net.close()
        self.current = None
        self.sm.transition.direction = "right"
        self.sm.current = "login"
        self.scr_login.set_msg("Signed out.")

    def show_alert(self, title, msg):
        p = self.pal
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        lbl = Label(text=msg, color=rgba(p["text"]), halign="center")
        lbl.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        box.add_widget(lbl)
        pop = Popup(title=title, content=box, size_hint=(0.82, 0.3))
        btn = Button(text="OK", size_hint_y=None, height=dp(42))
        btn.bind(on_release=pop.dismiss)
        box.add_widget(btn)
        pop.open()

    def poll(self, _dt):
        while True:
            try:
                m = self.inbox.get_nowait()
            except queue.Empty:
                break
            self.handle(m)

    def handle(self, m):
        t = m.get("type")
        if t == "welcome":
            self.user = m["user"]
            self.channels = m["channels"]
            self.users = {u["name"]: u for u in m["users"]}
            self.unread = m["unread"]
            self.logged_in = True
            self.reconnecting = False

            new_b = dict(DEFAULT_BRANDING)
            new_b.update(m.get("branding") or {})
            self.branding = new_b
            self.logo_b64 = m.get("logo", "")
            self.logo_tex = self.decode_logo(self.logo_b64)
            self.conf["branding"] = self.branding
            self.conf["logo"] = self.logo_b64
            self.save_conf()

            self.rebuild_ui()
            self.scr_dir.set_live(True)
            self.scr_dir.refresh_list()
            if self.sm.current == "login":
                self.sm.transition.direction = "left"
                self.sm.current = "dir"
            elif self.current:
                self.net.send({"type": "history", "conv": self.current})

        elif t == "error":
            self.net.close()
            self.scr_login.set_msg(m.get("text", "Login failed."), bad=True)

        elif t == "_connect_failed":
            self.scr_login.set_msg(m["text"], bad=True)

        elif t == "_disconnected":
            if m["sock"] is not self.net.sock:
                return
            if self.logged_in:
                self.scr_dir.set_live(False)
                if not self.reconnecting:
                    self.reconnecting = True
                    threading.Thread(target=self.reconnect_loop, daemon=True).start()

        elif t == "presence":
            u = self.users.get(m["user"])
            if u is None:
                if not m.get("dept"):
                    return
                u = {"name": m["user"], "dept": m["dept"], "admin": False}
                self.users[m["user"]] = u
            if m.get("dept"):
                u["dept"] = m["dept"]
            u["online"] = m["online"]
            self.scr_dir.refresh_list()
            if self.current == m["user"]:
                self.scr_chat.update_heading()

        elif t == "user_update":
            u = m["user"]
            self.users[u["name"]] = u
            self.scr_dir.refresh_list()

        elif t == "user_removed":
            self.users.pop(m["name"], None)
            self.unread.pop(m["name"], None)
            if self.current == m["name"]:
                self.go_directory()
            else:
                self.scr_dir.refresh_list()

        elif t == "branding":
            new_b = dict(DEFAULT_BRANDING)
            new_b.update(m.get("branding") or {})
            self.branding = new_b
            if "logo" in m and m["logo"] is not None:
                self.logo_b64 = m["logo"]
                self.logo_tex = self.decode_logo(self.logo_b64)
            self.conf["branding"] = self.branding
            self.conf["logo"] = self.logo_b64
            self.save_conf()
            self.rebuild_ui()

        elif t == "pw_result":
            self.show_alert("Password", m.get("text", ""))

        elif t == "kicked":
            self.sign_out()
            self.show_alert("Signed out", m.get("text", "You were signed out."))

        elif t == "history":
            if m["conv"] != self.current:
                return
            self.msgs = m["messages"]
            self.scr_chat.render_all()
            if self.msgs:
                self.net.send({"type": "read", "conv": m["conv"], "last_id": self.msgs[-1]["id"]})

        elif t == "msg":
            conv = m["to"] if m["to"].startswith("#") else (m["from"] if m["from"] != self.user else m["to"])
            mine = m["from"] == self.user
            if conv == self.current and self.sm.current == "chat":
                self.msgs.append(m)
                self.scr_chat.add_msg(m)
                self.net.send({"type": "read", "conv": conv, "last_id": m["id"]})
            elif not mine:
                self.unread[conv] = self.unread.get(conv, 0) + 1
                self.scr_dir.refresh_list()

    def on_stop(self):
        self.logged_in = False
        self.reconnecting = False
        self.net.close()


if __name__ == "__main__":
    LanChatApp().run()
