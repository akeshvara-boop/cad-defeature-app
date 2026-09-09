import { useCallback, useEffect, useRef, useState } from "react";

interface StreamViewportProps {
  host: string;
  signalingPort: number;
  mediaPort: number | null;
}

type ConnectionState = "idle" | "connecting" | "connected" | "error";

export function StreamViewport({ host, signalingPort, mediaPort }: StreamViewportProps) {
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [detail, setDetail] = useState("Enter the public Kit host and connect when port 49100 is listening.");
  const streamer = useRef<{ stop: () => void } | null>(null);

  const disconnect = useCallback(() => {
    try {
      streamer.current?.stop();
    } catch {
      // The singleton may not have an active stream yet.
    }
    setConnection("idle");
    setDetail("Stream disconnected.");
  }, []);

  useEffect(() => () => {
    try {
      streamer.current?.stop();
    } catch {
      // No active stream during unmount.
    }
  }, []);

  const connect = useCallback(async () => {
    if (!host.trim()) {
      setConnection("error");
      setDetail("A Kit signalling host is required.");
      return;
    }

    setConnection("connecting");
    setDetail(`Connecting to ${host}:${signalingPort}…`);
    const streamConfig: Record<string, unknown> = {
      videoElementId: "kit-remote-video",
      audioElementId: "kit-remote-audio",
      signalingServer: host.trim(),
      signalingPort,
      mediaServer: host.trim(),
      authenticate: false,
      maxReconnects: 20,
      nativeTouchEvents: true,
      width: 1920,
      height: 1080,
      fps: 60,
      onStart: (message: Record<string, unknown>) => {
        if (message.status === "success") {
          setConnection("connected");
          setDetail("Kit-CAE stream connected.");
        } else if (message.status === "error") {
          setConnection("error");
          setDetail(String(message.info ?? "Kit stream failed to start."));
        }
      },
      onUpdate: (message: Record<string, unknown>) => {
        if (message.status === "error") {
          setConnection("error");
          setDetail(String(message.info ?? "Kit stream reported an error."));
        }
      },
      onStop: () => {
        setConnection("idle");
        setDetail("Kit-CAE stream stopped.");
      },
      onTerminate: () => {
        setConnection("idle");
        setDetail("Kit-CAE stream terminated.");
      },
      onCustomEvent: (message: unknown) => {
        console.info("Kit-CAE data-channel event", message);
      }
    };
    if (mediaPort !== null) {
      streamConfig.mediaPort = mediaPort;
    }

    try {
      const { AppStreamer, StreamType } = await import(
        "@nvidia/omniverse-webrtc-streaming-library"
      );
      streamer.current = AppStreamer;
      await AppStreamer.connect({
        streamSource: StreamType.DIRECT,
        streamConfig
      } as never);
    } catch (error) {
      setConnection("error");
      setDetail(error instanceof Error ? error.message : "Unable to connect to Kit-CAE.");
    }
  }, [host, mediaPort, signalingPort]);

  return (
    <section className="viewport-card" aria-label="Kit-CAE viewport">
      <div className="viewport-toolbar">
        <div>
          <span className={`status-dot status-${connection}`} />
          <strong>Kit-CAE live viewport</strong>
          <span className="toolbar-detail">{detail}</span>
        </div>
        <div className="button-row compact">
          <button className="button secondary" onClick={connect} disabled={connection === "connecting"}>
            {connection === "connecting" ? "Connecting…" : "Connect stream"}
          </button>
          <button className="button ghost" onClick={disconnect} disabled={connection === "idle"}>
            Disconnect
          </button>
        </div>
      </div>
      <div className="viewport-stage">
        <video id="kit-remote-video" tabIndex={0} playsInline muted autoPlay />
        <audio id="kit-remote-audio" muted />
        {connection !== "connected" && (
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
