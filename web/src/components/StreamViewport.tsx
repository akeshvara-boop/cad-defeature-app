import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AppStreamer,
  StreamType,
  eStatus,
  type DirectConfig,
  type StreamEvent
} from "@nvidia/omniverse-webrtc-streaming-library";

import { api } from "../api";
import { actionableStreamError, validateStreamEndpoint } from "../streaming";

interface StreamViewportProps {
  host: string;
  signalingPort: number;
  secure: boolean;
  mediaPort: number | null;
  configurationWarnings?: string[];
}

type ConnectionState =
  | "idle"
  | "checking"
  | "connecting"
  | "live"
  | "lagged"
  | "offline"
  | "failed";

const FRAME_TIMEOUT_MS = 15_000;

async function waitForDecodedFrame(video: HTMLVideoElement): Promise<void> {
  const initial = video.getVideoPlaybackQuality?.().totalVideoFrames ?? 0;
  const deadline = performance.now() + FRAME_TIMEOUT_MS;
  while (performance.now() < deadline) {
    const decoded = video.getVideoPlaybackQuality?.().totalVideoFrames ?? 0;
    if (
      video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
      (decoded > initial || video.currentTime > 0)
    ) return;
    await new Promise((resolve) => window.setTimeout(resolve, 100));
  }
  throw new Error("No decoded H.264 frame arrived within 15 seconds.");
}

export function StreamViewport({
  host,
  signalingPort,
  secure,
  mediaPort,
  configurationWarnings = []
}: StreamViewportProps) {
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [detail, setDetail] = useState(
    "Configure the Kit endpoint, then run the connection preflight."
  );
  const [listenerStatus, setListenerStatus] = useState("not checked");
  const [streamStats, setStreamStats] = useState("");
  const attempt = useRef(0);
  const validation = useMemo(
    () => validateStreamEndpoint(host, signalingPort, secure),
    [host, secure, signalingPort]
  );

  const disconnect = useCallback(() => {
    attempt.current += 1;
    void AppStreamer.terminate(false).catch(() => undefined);
    setConnection("idle");
    setDetail("Stream disconnected.");
    setStreamStats("");
  }, []);

  useEffect(() => {
    if (connection === "idle" && !validation.ok) setDetail(validation.message);
  }, [connection, validation]);

  useEffect(() => () => {
    attempt.current += 1;
    void AppStreamer.terminate(false).catch(() => undefined);
  }, []);

  const fail = useCallback(
    (reason: unknown, endpoint: string, currentAttempt: number) => {
      if (attempt.current !== currentAttempt) return;
      setConnection("failed");
      setDetail(actionableStreamError(reason, endpoint));
    },
    []
  );

  const connect = useCallback(async () => {
    if (!validation.ok) {
      setConnection("failed");
      setDetail(validation.message);
      return;
    }

    const currentAttempt = ++attempt.current;
    setConnection("checking");
    setListenerStatus("checking API-host listener");
    setDetail("Checking that Kit is listening before browser negotiation…");

    try {
      const readiness = await api.streamHealth();
      if (attempt.current !== currentAttempt) return;
      setListenerStatus(`${readiness.status} · ${readiness.latency_ms} ms`);
      if (readiness.status !== "ready") {
        setConnection("offline");
        setDetail(
          `Kit is not listening at ${readiness.probe_host}:${readiness.signaling_port}. ${readiness.detail}`
        );
        return;
      }
    } catch (error) {
      fail(error, validation.endpoint, currentAttempt);
      return;
    }

    setConnection("connecting");
    setDetail(`Negotiating ${validation.endpoint}…`);

    const streamConfig: DirectConfig = {
      videoElementId: "kit-remote-video",
      audioElementId: "kit-remote-audio",
      signalingServer: validation.host,
      signalingPort: validation.port,
      mediaServer: validation.host,
      authenticate: false,
      maxReconnects: 5,
      connectivityTimeout: 5_000,
      codecList: ["H264"],
      nativeTouchEvents: true,
      width: 1920,
      height: 1080,
      fps: 60,
      onStart: (message: StreamEvent) => {
        if (attempt.current !== currentAttempt) return;
        if (message.status === eStatus.success) {
          setConnection("live");
          setDetail("Signaling connected; validating decoded video frames…");
          const video = document.getElementById("kit-remote-video") as HTMLVideoElement | null;
          if (!video) {
            fail("The Kit video element is missing.", validation.endpoint, currentAttempt);
            return;
          }
          void waitForDecodedFrame(video)
            .then(() => {
              if (attempt.current !== currentAttempt) return;
              setConnection("live");
              setDetail("Kit-CAE stream is live and decoding H.264 frames.");
            })
            .catch((error) => {
              if (attempt.current !== currentAttempt) return;
              setConnection("lagged");
              setDetail(
                `Signaling connected but video is unavailable. Check WebRTC ICE/public IP and UDP media ports. ${String(error)}`
              );
            });
        } else if (message.status === eStatus.error) {
          fail(message, validation.endpoint, currentAttempt);
        }
      },
      onUpdate: (message: StreamEvent) => {
        if (attempt.current !== currentAttempt) return;
        if (message.status === eStatus.error) {
          fail(message, validation.endpoint, currentAttempt);
        } else if (message.status === eStatus.warning) {
          setDetail(String(message.info ?? "Kit stream is retrying."));
        }
      },
      onStreamStats: (message: StreamEvent) => {
        if (attempt.current !== currentAttempt || !message.stats) return;
        setStreamStats(
          `${message.stats.fps.toFixed(0)} FPS · ${message.stats.rtd.toFixed(0)} ms RTT`
        );
      },
      onStop: () => {
        if (attempt.current !== currentAttempt) return;
        setConnection("idle");
        setDetail("Kit-CAE stream stopped.");
      },
      onTerminate: () => {
        if (attempt.current !== currentAttempt) return;
        setConnection("idle");
        setDetail("Kit-CAE stream terminated.");
      },
      onCustomEvent: (message: unknown) => {
        console.info("Kit-CAE data-channel event", message);
      }
    };
    if (mediaPort !== null) streamConfig.mediaPort = mediaPort;

    try {
      await AppStreamer.connect({
        streamSource: StreamType.DIRECT,
        streamConfig
      });
    } catch (error) {
      fail(error, validation.endpoint, currentAttempt);
    }
  }, [fail, mediaPort, validation]);

  const showPlaceholder = !["live", "lagged"].includes(connection);
  const statusLabel = connection === "idle" ? "offline" : connection;

  return (
    <section className="viewport-card" aria-label="Kit-CAE viewport">
      <div className="viewport-toolbar">
        <div>
          <span className={`status-dot status-${connection}`} />
          <strong>Kit-CAE live viewport</strong>
          <span className="toolbar-detail">{detail}</span>
        </div>
        <div className="button-row compact">
          <span className={`stream-state stream-state-${connection}`}>{statusLabel}</span>
          <button
            className="button secondary"
            onClick={connect}
            disabled={!validation.ok || ["checking", "connecting"].includes(connection)}
          >
            {["checking", "connecting"].includes(connection) ? "Connecting…" : "Connect stream"}
          </button>
          <button className="button ghost" onClick={disconnect} disabled={connection === "idle"}>
            Disconnect
          </button>
        </div>
      </div>
      <div className={`stream-diagnostic ${validation.ok ? "ready" : "failed"}`}>
        <span><strong>Endpoint</strong> {validation.endpoint}</span>
        <span><strong>Kit listener</strong> {listenerStatus}</span>
        <span><strong>Browser page</strong> {validation.pageProtocol.replace(":", "").toUpperCase()}</span>
        {streamStats && <span><strong>Stream</strong> {streamStats}</span>}
        {!validation.ok && <p>{validation.message}</p>}
        {configurationWarnings.map((warning) => <p key={warning}>{warning}</p>)}
      </div>
      <div className="viewport-stage">
        <video id="kit-remote-video" tabIndex={0} playsInline muted autoPlay />
        <audio id="kit-remote-audio" muted />
        {showPlaceholder && (
          <div className="viewport-placeholder">
            <div className="geometry-mark" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
            </div>
            <p>Interactive engineering view</p>
            <small>CAD geometry, healing findings and verification overlays render here.</small>
          </div>
        )}
        <div className="viewport-badge">RTX · OpenUSD · Kit-CAE</div>
      </div>
    </section>
  );
}
