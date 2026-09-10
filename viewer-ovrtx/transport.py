"""Explicit ovstream SDK lifetime; importing this module loads no native SDK."""
from contextlib import contextmanager


@contextmanager
def open_stream(sdk, config, diagnostic=False):
    if diagnostic:
        sdk.initialize(log_fn=lambda level, channel, message, timestamp: print(
            f'OVSTREAM [{level.name}][{channel}] {message}', flush=True),
            log_min_severity=sdk.LogLevel.INFO)
    else:
        sdk.initialize()
    server = None
    started = False
    try:
        server = sdk.Server(sdk.ServerType.WEBRTC)
        if diagnostic:
            server.on_connection = lambda connected: print(f'OVSTREAM_CONNECTION={connected}', flush=True)
        server.start(config)
        started = True
        yield server
    finally:
        try:
            if server is not None:
                try:
                    if started:
                        server.stop()
                finally:
                    server.close()
        finally:
            sdk.shutdown()
