# gateway/monitor.py
"""Optional terminal monitor sharing GatewayController state."""

import time


def run_monitor(controller):
    try:
        from rich.live import Live
        from rich.table import Table
    except ImportError:
        while controller.running:
            time.sleep(1)
        return

    def render():
        snap = controller.snapshot()
        table = Table(title="VoiceEdge")
        for column in ("Gateway", "Calls", "Latency", "Packets", "Plugin", "Mode", "Status"):
            table.add_column(column)
        table.add_row(
            snap["gateway"], str(snap["calls"]), f'{snap["latency_ms"]} ms',
            str(snap["packets"]), snap["plugin"], snap["mode"], snap["health"],
        )
        return table

    from rich.live import Live
    with Live(render(), refresh_per_second=1) as live:
        while controller.running:
            live.update(render())
            _handle_key(controller)
            time.sleep(1)


def _handle_key(controller):
    try:
        import msvcrt
        if not msvcrt.kbhit():
            return
        key = msvcrt.getwch().lower()
        if key == "s":
            controller.start()
        elif key == "x":
            controller.stop()
        elif key == "r":
            controller.restart()
        elif key == "m":
            controller.toggle_maintenance()
    except (ImportError, OSError):
        return
