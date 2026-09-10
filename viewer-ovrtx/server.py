"""Isolated remote-render proof. Operator supplies a prepared USD stage.

No remote filesystem API, no modifications to user USD, no Kit dependencies.
"""
import argparse
import json
import os
from pathlib import Path
import signal
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--product", default="/Render/Camera")
    parser.add_argument("--signal-port", type=int, default=49200)
    parser.add_argument("--media-port", type=int, default=48098)
    parser.add_argument("--http-port", type=int, default=8081)
    parser.add_argument("--public-ip", default=None)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--snapshot", type=Path, help="Write first RGB frame as a new PPM file")
    args = parser.parse_args()
    if not args.stage.is_file() or args.stage.suffix.lower() not in {".usd", ".usda", ".usdc"}:
        parser.error("--stage must be an existing prepared USD stage")
    if any(not 1 <= p <= 65535 for p in (args.signal_port, args.media_port, args.http_port)):
        parser.error("Invalid port")
    if args.frames < 0:
        parser.error("--frames must be nonnegative")
    os.environ.setdefault("OVRTX_SKIP_USD_CHECK", "1")
    import ovrtx
    import ovstage
    import ovstream
    import warp as wp
    from pixels import rgba_to_bgra
    stop = threading.Event()
    state = {"status": "starting", "rendered_frames": 0, "submitted_frames": 0,
             "client_connected": False, "last_error": None}
    lock = threading.Lock()
    webroot = Path(__file__).parent / "client" / "dist"
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(webroot), **kw)
        def do_GET(self):
            if self.path != "/healthz":
                return super().do_GET()
            with lock:
                body = json.dumps(state).encode()
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
    attached = False
    try:
        wp.init()
        print("CREATING_RENDERER", flush=True)
        renderer = ovrtx.Renderer()
        print("CREATING_STAGE", flush=True)
        stage = ovstage.Stage("cad.remote.viewer")
        print("POPULATING_STAGE", flush=True)
        ovstage.population.open_usd(stage, str(args.stage.resolve()), ordinal=1)
        stage.advance_write_floor(1, ovstage.Scope.ALL).wait()
        renderer.attach_ovstage(stage)
        print("STAGE_ATTACHED", flush=True)
        attached = True
        while not stop.is_set():
            started = time.monotonic()
            products = renderer.step(render_products={args.product}, delta_time=1 / 30, ordinal=1)
            copied = False
            for product in products.values():
                for frame in product.frames:
                    key = next((k for k in frame.render_vars if str(k).split("/")[-1] == "LdrColor"), None)
                    if key is None:
                        raise RuntimeError("Missing LdrColor RenderVar")
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
                    copied = True
            if not copied:
                raise RuntimeError("Renderer returned no frames")
            del products, product, frame
            if stream is None:
                print(f"FIRST_BGRA_FRAME_READY {w}x{h}", flush=True)
                rgb = buffer.numpy()[:, :, [2, 1, 0]].copy()
                print(f"FIRST_FRAME_RANGE min={rgb.min()} max={rgb.max()}", flush=True)
                if args.snapshot:
                    with args.snapshot.open("xb") as output:
                        output.write(f"P6\n{w} {h}\n255\n".encode())
                        output.write(rgb.tobytes())
                stream = ovstream.Server(ovstream.ServerType.WEBRTC)
                stream.start(ovstream.ServerConfig(width=w, height=h, target_fps=30,
                    cuda_device=0, cuda_context=int(wp.get_device("cuda:0").context),
                    webrtc_signal_port=args.signal_port, stream_port=args.media_port,
                    webrtc_public_ip=args.public_ip))
            connected = stream.is_client_connected
            submitted = False
            if connected:
                try:
                    stream.stream_video(ovstream.VideoFrame.from_cuda_array(buffer))
                    submitted = True
                except ovstream.OvstreamError as error:
                    with lock:
                        state["last_error"] = str(error)
            with lock:
                state.update(status="ready", client_connected=bool(connected))
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
        if stream is not None:
            stream.stop()
            stream.close()
        if renderer is not None:
            if attached:
                renderer.detach_ovstage()
            if stage is not None:
                stage.destroy()
            renderer.destroy()
        http.shutdown()
        http.server_close()

if __name__ == "__main__":
    main()
