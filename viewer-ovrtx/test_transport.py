"""SDK lifecycle regression tests without native imports or listening sockets."""
from types import SimpleNamespace
import unittest
from transport import open_stream


class LifecycleTests(unittest.TestCase):
    def sdk(self, failure=None):
        events = []
        def event(name):
            events.append(name)
            if failure == name:
                raise RuntimeError(name)
        class Server:
            def __init__(self, kind): event('create')
            def start(self, config): event('start')
            def stop(self): event('stop')
            def close(self): event('close')
        return SimpleNamespace(initialize=lambda: event('initialize'),
                               shutdown=lambda: event('shutdown'), Server=Server,
                               ServerType=SimpleNamespace(WEBRTC=0)), events

    def test_successful_lifetime(self):
        sdk, events = self.sdk()
        with open_stream(sdk, object()):
            events.append('frame')
        self.assertEqual(events, ['initialize', 'create', 'start', 'frame', 'stop', 'close', 'shutdown'])

    def test_creation_failure_shuts_down(self):
        sdk, events = self.sdk('create')
        with self.assertRaisesRegex(RuntimeError, 'create'):
            with open_stream(sdk, object()): pass
        self.assertEqual(events, ['initialize', 'create', 'shutdown'])

    def test_start_failure_closes_server(self):
        sdk, events = self.sdk('start')
        with self.assertRaisesRegex(RuntimeError, 'start'):
            with open_stream(sdk, object()): pass
        self.assertEqual(events, ['initialize', 'create', 'start', 'close', 'shutdown'])

    def test_stop_failure_still_closes_and_shuts_down(self):
        sdk, events = self.sdk('stop')
        with self.assertRaisesRegex(RuntimeError, 'stop'):
            with open_stream(sdk, object()): pass
        self.assertEqual(events[-3:], ['stop', 'close', 'shutdown'])


if __name__ == '__main__':
    unittest.main()
