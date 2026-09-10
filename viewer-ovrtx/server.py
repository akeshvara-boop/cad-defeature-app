"""Isolated remote-render proof. Operator supplies a prepared USD stage.

No remote filesystem API, no modifications to user USD, no Kit dependencies.
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import queue
import hmac
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--product", default="/Render/Camera")
    parser.add_argument("--render-var", default="/Render/LdrColor", help="Full authored RenderVar path")
    parser.add_argument("--signal-port", type=int, default=49200)
    parser.add_argument("--media-port", type=int, default=48098)
    parser.add_argument("--http-port", type=int, default=8081)
    parser.add_argument("--public-ip", default=None)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--render-only", action="store_true", help="Render bounded frames without importing or starting ovstream")
    parser.add_argument("--snapshot", type=Path, help="Write first RGB frame as a new PPM file")
    args = parser.parse_args()
    if not args.stage.is_file() or args.stage.suffix.lower() not in {".usd", ".usda", ".usdc"}:
        parser.error("--stage must be an existing prepared USD stage")
    if any(not 1 <= p <= 65535 for p in (args.signal_port, args.media_port, args.http_port)):
        parser.error("Invalid port")
    if args.frames < 0:
        parser.error("--frames must be nonnegative")
    if args.render_only and not args.frames:
        parser.error("--render-only requires --frames greater than zero")
    os.environ.setdefault("OVRTX_SKIP_USD_CHECK", "1")
    import ovrtx
    import ovstage
    import warp as wp
    from pixels import rgba_to_bgra
    stop = threading.Event()
    startup_time = phase_time = time.monotonic()
    state = {"status": "starting", "phase": "initializing", "rendered_frames": 0, "submitted_frames": 0,
             "client_connected": False, "last_error": None, "render_only": args.render_only}
    pending_assets = queue.Queue(maxsize=1)
    lock = threading.Lock()
    webroot = Path(__file__).parent / "client" / "dist"
    class Handler(SimpleHTTPRequestHandler):
        def do_POST(self):
            token = os.getenv('CAD_UI_VIEWER_TOKEN', '')
            if self.path != '/asset' or not token or not hmac.compare_digest(self.headers.get('X-Viewer-Token',''), token):
                self.send_error(403); return
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 4096: raise ValueError('Invalid body size')
                from asset_requests import validate_asset
                value = validate_asset(json.loads(self.rfile.read(size)), os.getenv('CAD_UI_REVIEW_ROOT'))
                with lock:
                    if state['client_connected'] or not pending_assets.empty():
                        self.send_error(409, 'Disconnect the current viewer before loading another output'); return
                    pending_assets.put_nowait(value)
                    state.update(status='starting', phase='loading_asset', pending_workflow_id=value['workflow_id'])
                self.send_response(202); self.end_headers()
            except (ValueError, OSError, queue.Full):
                self.send_error(400, 'Invalid asset request')
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(webroot), **kw)
        def do_GET(self):
            if self.path != "/healthz":
                return super().do_GET()
            with lock:
                now = time.monotonic()
                body = json.dumps(dict(state, uptime_seconds=round(now - startup_time, 1),
                                       phase_seconds=round(now - phase_time, 1))).encode()
                code = 200 if state["status"] == "ready" else 503
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    http = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    renderer = stage = stream = buffer = None
    resources = ExitStack()
    attached = False
    def phase(value):
        nonlocal phase_time
        with lock:
            state["phase"] = value
            phase_time = time.monotonic()
        print(f"VIEWER_PHASE={value} elapsed={phase_time - startup_time:.1f}s", flush=True)
    try:
        wp.init()
        print("CREATING_RENDERER", flush=True)
        phase("creating_renderer")
        renderer = ovrtx.Renderer()
        print("CREATING_STAGE", flush=True)
        phase("creating_stage")
        stage = ovstage.Stage("cad.remote.viewer")
        # Match the pinned 0.5 upstream minimal example: attach before population.
        print("Native initialization may compile shaders for several minutes on first use. Do not restart while compilation is progressing.", flush=True)
        phase("attaching_stage")
        renderer.attach_ovstage(stage)
        attached = True
        print("POPULATING_STAGE", flush=True)
        phase("populating_stage")
        ovstage.population.open_usd(stage, str(args.stage.resolve()), ordinal=1)
        stage.advance_write_floor(1, ovstage.Scope.ALL).wait()
        print("STAGE_PUBLISHED", flush=True)
        phase("first_frame")
        while not stop.is_set():
            if not pending_assets.empty():
                asset = pending_assets.get_nowait()
                phase('loading_asset')
                renderer.detach_ovstage()
                attached = False
                stage.destroy()
                stage = ovstage.Stage('cad.remote.viewer.' + asset['asset_id'])
                renderer.attach_ovstage(stage)
                attached = True
                ovstage.population.open_usd(stage, asset['stage'], ordinal=1)
                stage.advance_write_floor(1, ovstage.Scope.ALL).wait()
                with lock:
                    state.update(**asset, rendered_frames=0, submitted_frames=0, last_error=None)
                phase('first_frame')
            started = time.monotonic()
            products = renderer.step(render_products={args.product}, delta_time=1 / 30, ordinal=1)
            copied = False
            for product in products.values():
                for frame in product.frames:
                    key = args.render_var
                    if key not in frame.render_vars:
                        raise RuntimeError(f"Missing RenderVar {key}; available: {list(frame.render_vars)}")
                    with frame.render_vars[key].map(device=ovrtx.Device.CUDA) as mapped:
                        source = wp.from_dlpack(mapped)
                        if source.ndim != 3 or source.shape[2] != 4 or source.dtype != wp.uint8:
                            raise RuntimeError("Expected RGBA8 HxWx4 frame")
                        h, w, _ = source.shape
                        if buffer is None:
                            buffer = wp.empty((h, w, 4), dtype=wp.uint8, device="cuda:0")
                        if buffer.shape != source.shape:
                            raise RuntimeError("Resolution changes unsupported")
                        wp.launch(rgba_to_bgra, dim=(h, w), inputs=[source, buffer], device="cuda:0")
                        wp.synchronize_device("cuda:0")
                        del source
                    del mapped
                    copied = True
            if not copied:
                raise RuntimeError("Renderer returned no frames")
            del products, product, frame
            if state["rendered_frames"] == 0:
                print(f"FIRST_BGRA_FRAME_READY {w}x{h}", flush=True)
                rgb = buffer.numpy()[:, :, [2, 1, 0]].copy()
                print(f"FIRST_FRAME_RANGE min={rgb.min()} max={rgb.max()}", flush=True)
                if args.snapshot:
                    with args.snapshot.open("xb") as output:
                        output.write(f"P6\n{w} {h}\n255\n".encode())
                        output.write(rgb.tobytes())
            if stream is None and not args.render_only:
                import ovstream
                from transport import open_stream
                phase("starting_stream")
                stream = resources.enter_context(open_stream(ovstream, ovstream.ServerConfig(width=w, height=h, target_fps=30,
                    cuda_device=0, cuda_context=int(wp.get_device("cuda:0").context),
                    webrtc_signal_port=args.signal_port, stream_port=args.media_port,
                    webrtc_public_ip=args.public_ip), diagnostic=True))
            connected = stream.is_client_connected if stream is not None else False
            submitted = False
            if connected:
                try:
                    stream.stream_video(ovstream.VideoFrame.from_cuda_array(buffer))
                    submitted = True
                except ovstream.OvstreamError as error:
                    with lock:
                        state["last_error"] = str(error)
            with lock:
                state.update(status="ready", phase="rendering", client_connected=bool(connected))
                state["rendered_frames"] += 1
                state["submitted_frames"] += int(submitted)
                count = state["rendered_frames"]
            if args.frames and count >= args.frames:
                print(f"GPU_SMOKE_COMPLETE frames={count}", flush=True)
                break
            stop.wait(max(0, 1 / 30 - (time.monotonic() - started)))
    except Exception as error:
        with lock:
            state.update(status="failed", last_error=str(error))
        raise
    finally:
        try:
            resources.close()
        finally:
            try:
                if renderer is not None:
                    if attached:
                        renderer.detach_ovstage()
                    if stage is not None:
                        stage.destroy()
                    renderer.destroy()
            finally:
                http.shutdown()
                http.server_close()

if __name__ == "__main__":
    main()
