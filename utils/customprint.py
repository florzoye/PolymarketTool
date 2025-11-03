from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from datetime import datetime

class CustomPrint:
    def __init__(self):
        self.console = Console()

    def _format_message(self, level: str, color: str, icon: str, message: str) -> Panel:
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = Text(f"{icon} {level}", style=f"bold {color}")
        body = Text(f"[{timestamp}] {message}", style="white")
        return Panel(body, title=header, border_style=color)

    def debug(self, message: str):
        panel = self._format_message("DEBUG", "white", "🐞", message)
        self.console.print(panel)

    def info(self, message: str):
        panel = self._format_message("INFO", "blue", "ℹ️", message)
        self.console.print(panel)

    def success(self, message: str):
        panel = self._format_message("SUCCESS", "green", "✅", message)
        self.console.print(panel)

    def warning(self, message: str):
        panel = self._format_message("WARNING", "yellow", "⚠️", message)
        self.console.print(panel)

    def error(self, message: str):
        panel = self._format_message("ERROR", "red", "❌", message)
        self.console.print(panel)

