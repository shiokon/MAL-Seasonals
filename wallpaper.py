import sys
import ctypes
import requests
import math
import win32gui
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QGridLayout, QVBoxLayout, QHBoxLayout, QScrollArea, QSizePolicy,
    QSystemTrayIcon, QMenu
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction, QCursor
from PyQt6.QtCore import Qt
from mal import fetch_anime_data

class AnimeWidget(QWidget):
    def __init__(self, title, mal_id, watched_eps, total_eps, next_in_hours, status, cover_url, score):
        super().__init__()
        self.title = title
        self.anime_id = mal_id

        try:
            self.total_eps = int(total_eps)
        except (TypeError, ValueError):
            self.total_eps = None

        self.original_eps = watched_eps
        self.current_eps = watched_eps
        self.cover_url = cover_url
        self.score = score

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(160, 224)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self.get_pixmap_from_url(cover_url)
        if pixmap:
            self.cover_label.setPixmap(
                pixmap.scaled(
                    160, 224,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)

        button_bar_widget = QWidget()
        button_bar_widget.setObjectName("buttonBar")
        button_bar_widget.setFixedWidth(160)
        button_bar_widget.setStyleSheet("""
            #buttonBar {
                background-color: rgba(0, 0, 0, 128);
                border: none;
                border-radius: 0;
            }
        """)


        button_bar_layout = QHBoxLayout(button_bar_widget)
        button_bar_layout.setContentsMargins(0, 0, 0, 0)
        button_bar_layout.setSpacing(0)

        self.minus_button = QPushButton("-")
        self.equal_button = QPushButton("=")
        self.plus_button = QPushButton("+")

        for btn in [self.minus_button, self.equal_button, self.plus_button]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(24)
            btn.setFixedWidth(52)


        self.minus_button.clicked.connect(self.decrease_episode)
        self.plus_button.clicked.connect(self.increase_episode)
        self.equal_button.clicked.connect(self.submit_and_refresh)

        button_bar_layout.addWidget(self.minus_button)
        button_bar_layout.addWidget(self.equal_button)
        button_bar_layout.addWidget(self.plus_button)

        layout.addWidget(button_bar_widget, alignment=Qt.AlignmentFlag.AlignCenter)


        # Title
        color = "lime" if status == "GREEN" else "tomato"
        self.title_label = QLabel(f'<b><span style="color:{color};">{title}</span></b>')
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.title_label.setFixedHeight(24)
        layout.addWidget(self.title_label)

        # Episodes
        self.eps_label = QLabel(f"{self.current_eps}/{self.total_eps if self.total_eps else '?'} episodes")
        self.eps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.eps_label)

        # Countdown
        countdown_text = f"Next in {math.floor(next_in_hours/24)}d {next_in_hours%24}h" if next_in_hours is not None else "Next: ?"
        self.countdown_label = QLabel(countdown_text)
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.countdown_label)

        self.setLayout(layout)
        self.setFixedHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def get_pixmap_from_url(self, url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            image = QImage.fromData(response.content)
            return QPixmap.fromImage(image)
        except Exception as e:
            print(f"Failed to load image {url}: {e}")
            return None

    def increase_episode(self):
        if self.total_eps is None or self.current_eps < self.total_eps:
            self.current_eps += 1
            self.update_eps_label()


    def decrease_episode(self):
        if self.current_eps > 0:
            self.current_eps -= 1
            self.update_eps_label()

    def update_eps_label(self):
        total = self.total_eps if self.total_eps is not None else "?"
        self.eps_label.setText(f"{self.current_eps}/{total} episodes")


    def submit_and_refresh(self):
        if not self.anime_id:
            print(f"Could not determine MAL ID for {self.title}")
            return

        from auth.tokenrefresh import load_tokens
        token = load_tokens()["access_token"]

        status = "completed" if self.current_eps == self.total_eps else "watching"
        payload = {
            "status": status,
            "score": self.score,
            "num_watched_episodes": self.current_eps
        }

        url = f"https://api.myanimelist.net/v2/anime/{self.anime_id}/my_list_status"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.put(url, headers=headers, data=payload)
            response.raise_for_status()
            # print(f"Updated {self.title} to {self.current_eps} episodes watched.")
            self.parentWidget().parentWidget().parentWidget().window().refresh_data()
        except Exception as e:
            print(f"Failed to update MAL status: {e}")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Seasonal Anime Watchlist")
        self.resize(1600, 900)

        self.main_layout = QHBoxLayout()
        self.day_columns = []

        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        for i, day in enumerate(days):
            day_widget = QWidget()
            day_layout = QVBoxLayout()
            day_label = QLabel(f"<h2>{day}</h2>")
            day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day_layout.addWidget(day_label)

            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            content_widget = QWidget()

            content_layout = QGridLayout() if i == 0 else QVBoxLayout()
            content_layout.setSpacing(12)


            content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            content_widget.setLayout(content_layout)
            scroll_area.setWidget(content_widget)

            day_layout.addWidget(scroll_area)
            day_widget.setLayout(day_layout)

            self.main_layout.addWidget(day_widget)
            self.day_columns.append(content_layout)


        layout = QVBoxLayout()
        layout.addLayout(self.main_layout)
        self.setLayout(layout)

        self.refresh_data()

    def refresh_data(self):
        for col in self.day_columns:
            while col.count():
                item = col.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        anime_by_day = self.get_anime_data()

        for i, anime_list in enumerate(anime_by_day):
            if i == 0:
                for idx, anime in enumerate(anime_list):
                    anime_copy = anime.copy()
                    anime_copy.pop("weekday_idx", None)
                    widget = AnimeWidget(**anime_copy)
                    widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
                    row, col = divmod(idx, 2)
                    self.day_columns[i].addWidget(widget, row, col)
            else:
                for anime in anime_list:
                    anime_copy = anime.copy()
                    anime_copy.pop("weekday_idx", None)
                    widget = AnimeWidget(**anime_copy)
                    widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
                    self.day_columns[i].addWidget(widget)

    def get_anime_data(self):
        return fetch_anime_data()

def set_as_wallpaper(window):
    hwnd_progman = ctypes.windll.user32.FindWindowW("Progman", None)
    ctypes.windll.user32.SendMessageTimeoutW(hwnd_progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(ctypes.c_ulong()))

    windows = []
    def enum_windows(hwnd, lParam):
        if win32gui.GetClassName(hwnd) == "WorkerW":
            if win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None) != 0:
                windows.append(hwnd)
        return True
    win32gui.EnumWindows(enum_windows, None)

    if windows:
        workerw = windows[0]
        hwnd = int(window.winId())

        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        style &= ~WS_CAPTION
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        ctypes.windll.user32.SetParent(hwnd, workerw)

        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, window.width(), window.height(),
                                         0x0040 | 0x0004 | 0x0010)

def create_tray_icon(app, window):
    tray = QSystemTrayIcon()
    tray.setIcon(QIcon("sora.ico"))

    tray.menu = QMenu()
    tray.refresh_action = QAction("Refresh")
    tray.quit_action = QAction("Quit")

    tray.menu.addAction(tray.refresh_action)
    tray.menu.addAction(tray.quit_action)

    tray.refresh_action.triggered.connect(window.refresh_data)
    tray.quit_action.triggered.connect(app.quit)

    tray.setContextMenu(tray.menu)
    tray.show()

    def on_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if window.isVisible():
                window.hide()
            else:
                window.show()
                window.raise_()
                window.activateWindow()


    tray.activated.connect(on_activated)
    return tray




def main():
    app = QApplication([])

    try:
        with open("style.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("style.qss not found — using default style.")

    window = MainWindow()

    screens = app.screens()
    if len(screens) > 1:
        screen2 = screens[1]
    else:
        screen2 = screens[0]

    geo = screen2.availableGeometry()
    window.setGeometry(geo)

    window.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.Tool
    )
    window.show()

    set_as_wallpaper(window)

    tray = create_tray_icon(app, window)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
