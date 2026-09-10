"""Explicit ovstream SDK lifetime; importing this module loads no native SDK."""
from contextlib import contextmanager


@contextmanager
def open_stream(sdk, config):
    sdk.initialize()
    server = None
    started = False
    try:
        server = sdk.Server(sdk.ServerType.WEBRTC)
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
