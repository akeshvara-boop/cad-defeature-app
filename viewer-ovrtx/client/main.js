import { AppStreamer, StreamType } from '@nvidia/ov-web-rtc';
import './style.css';
const $ = (id) => document.getElementById(id);
let active = false, generation = 0, firstError = '', teardown = Promise.resolve();
const status = (message) => { $('status').textContent = message; };
async function disconnect() {
  ++generation;
  $('disconnect').disabled = true;
  teardown = teardown.then(() => AppStreamer.terminate(false)).catch(() => {});
  await teardown;
  active = false;
  $('connect').disabled = false;
  status(firstError || 'Disconnected.');
}
$('disconnect').onclick = disconnect;
$('connect').onclick = async () => {
  if (active) return;
  const server = $('host').value.trim(), port = Number($('port').value);
  if (!server || /[\s/<>]/.test(server) || !Number.isInteger(port) || port < 1 || port > 65535) {
    status('Enter a hostname without a URL path and a valid port.'); return;
  }
  active = true; firstError = ''; const attempt = ++generation;
  $('connect').disabled = true; $('disconnect').disabled = false;
  const timeout = setTimeout(() => {
    if (attempt === generation) { firstError = 'Connection/video deadline exceeded (45s).'; void disconnect(); }
  }, 45000);
  try {
    await teardown;
    status('Connecting standalone ovstream session…');
    await AppStreamer.connect({streamSource: StreamType.DIRECT, streamConfig: {
      server, signalingPort: port, videoElementId: 'remote-video', audioElementId: 'remote-audio',
      codec: 'H264', codecList: ['H264'], width: 1280, height: 720, fps: 30,
      maxReconnects: 0, nativeTouchEvents: true,
      onUpdate: (event) => { if (attempt === generation) status(`Stream update: ${String(event.info || event.status)}`); },
      onStop: () => { if (attempt === generation) { firstError ||= 'Stream stopped before validation completed.'; void disconnect(); } },
    }});
    if (attempt !== generation) return;
    status('Transport established; waiting for decoded video…');
    const video = $('remote-video'), deadline = performance.now() + 15000;
    while (attempt === generation && performance.now() < deadline) {
      if (video.readyState >= 2 && video.getVideoPlaybackQuality().totalVideoFrames > 0) {
        status('Live: browser has decoded video frames.'); return;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (attempt === generation) throw new Error('Connected but no decoded frame within 15s.');
  } catch (error) {
    if (attempt === generation) { firstError = String(error); await disconnect(); }
  } finally { clearTimeout(timeout); }
};
