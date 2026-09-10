import { AppStreamer, StreamType } from '@nvidia/ov-web-rtc';
import './style.css';
const $ = (id) => document.getElementById(id);
let active = false, generation = 0, firstError = '', teardown = Promise.resolve();
let endpoint = null;
const status = (message) => { $('status').textContent = message; };
async function checkReadiness() {
  endpoint = null;
  $('connect').disabled = true;
  $('host').value = ''; $('port').value = '';
  try {
    const response = await fetch('/v1/ovrtx/readiness', {cache: 'no-store'});
    if (!response.ok) throw new Error('Readiness service unavailable');
    const result = await response.json();
    if (result.ready === true && result.host && Number.isInteger(result.port)) {
      endpoint = result;
      $('host').value = result.host; $('port').value = result.port;
      $('connect').disabled = active;
    }
    status(result.reason || 'Renderer not ready.');
  } catch { status('Readiness unavailable. Connect is disabled; open this viewer through the workbench API.'); }
  return endpoint;
}
$('refresh').onclick = () => { if (!active) void checkReadiness(); };
void checkReadiness();
async function disconnect() {
  ++generation;
  $('disconnect').disabled = true;
  teardown = teardown.then(() => AppStreamer.terminate(false)).catch(() => {});
  await teardown;
  active = false;
  $('connect').disabled = true;
  $('refresh').disabled = false;
  status(firstError || 'Disconnected.');
}
$('disconnect').onclick = disconnect;
$('connect').onclick = async () => {
  if (active) return;
  active = true;
  const verified = await checkReadiness();
  if (!verified) { active = false; return; }
  const server = verified.host, port = verified.port;
  if (!server || /[\s/<>]/.test(server) || !Number.isInteger(port) || port < 1 || port > 65535) {
    active = false; status('Invalid deployment endpoint.'); return;
  }
  active = true; firstError = ''; const attempt = ++generation;
  $('connect').disabled = true; $('disconnect').disabled = false;
  $('refresh').disabled = true;
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
