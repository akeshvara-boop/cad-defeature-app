"""Bounded transport-only diagnostic; never labels its pixels as customer CAD.

Run instead of the CAD renderer, not beside it on the same ports. The caller
must restore the CAD service afterward. No OVRTX, OVStage or CAD imports.
"""
import argparse
import json
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def main():
    import warp as wp
    import ovstream
    from transport import open_stream
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=int,default=120)
    parser.add_argument('--http-port',type=int,default=8081)
    parser.add_argument('--signal-port',type=int,default=49200)
    parser.add_argument('--media-port',type=int,default=49100)
    args=parser.parse_args()
    if not 1 <= args.seconds <= 180: parser.error('Use a bounded duration of 1–180 seconds')
    stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set())
    signal.signal(signal.SIGINT,lambda *_:stop.set())
    state=dict(status='starting',phase='starting_stream',mode='test_pattern',
               workflow_id='000000000000',asset_id='11111111111111111111111111111111',
               rendered_frames=0,submitted_frames=0,client_connected=False)
    class Health(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path!='/healthz':self.send_error(404);return
            body=json.dumps(state).encode()
            self.send_response(200 if state['status']=='ready' else 503)
            self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
    http=ThreadingHTTPServer(('127.0.0.1',args.http_port),Health)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    wp.init()
    pixels=wp.empty((720,1280,4),dtype=wp.uint8,device='cuda:0')
    @wp.kernel
    def fill(output:wp.array3d(dtype=wp.uint8),tick:int):
        y,x=wp.tid()
        output[y,x,0]=wp.uint8((x+tick*4)%256)
        output[y,x,1]=wp.uint8((y+tick*2)%256)
        output[y,x,2]=wp.uint8((x+y+tick)%256)
        output[y,x,3]=wp.uint8(255)
    try:
        config=ovstream.ServerConfig(width=1280,height=720,target_fps=30,cuda_device=0,
            cuda_context=int(wp.get_device('cuda:0').context),webrtc_signal_port=args.signal_port,stream_port=args.media_port)
        with open_stream(ovstream,config,diagnostic=True) as server:
            deadline=time.monotonic()+args.seconds
            while not stop.is_set() and time.monotonic()<deadline:
                started=time.monotonic()
                wp.launch(fill,dim=(720,1280),inputs=[pixels,state['rendered_frames']],device='cuda:0')
                wp.synchronize_device('cuda:0')
                state.update(status='ready',phase='rendering',client_connected=bool(server.is_client_connected))
                state['rendered_frames']+=1
                if state['client_connected']:
                    server.stream_video(ovstream.VideoFrame.from_cuda_array(pixels))
                    state['submitted_frames']+=1
                stop.wait(max(0,1/30-(time.monotonic()-started)))
    finally:
        print('PATTERN_TEST_RESULT '+json.dumps(state),flush=True)
        http.shutdown();http.server_close()

if __name__=='__main__':main()
