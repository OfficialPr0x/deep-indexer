from prometheus_client import Counter, start_http_server
import threading

class Telemetry:
    def __init__(self):
        self.scan_counter = Counter('file_scans_total', 'Total file scans')
        self._start_metrics_server()

    def _start_metrics_server(self):
        threading.Thread(target=start_http_server, args=(8000,), daemon=True).start()

    def send_metrics(self):
        self.scan_counter.inc() 