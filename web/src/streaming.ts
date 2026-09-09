export interface StreamEndpointValidation {
  ok: boolean;
  host: string;
  port: number;
  pageProtocol: "http:" | "https:" | string;
  signalingProtocol: "ws:" | "wss:";
  endpoint: string;
  message: string;
}

function isPlaceholder(value: string): boolean {
  const upper = value.toUpperCase();
  return (
    value.startsWith("<") ||
    value.endsWith(">") ||
    upper.includes("BREV_PUBLIC") ||
    upper.includes("PUBLIC_STREAM_HOST")
  );
}

export function validateStreamEndpoint(
  rawHost: string,
  rawPort: number,
  secure: boolean,
  pageProtocol = window.location.protocol
): StreamEndpointValidation {
  const host = rawHost.trim();
  const port = Number(rawPort);
  const signalingProtocol = secure ? "wss:" : "ws:";
  const endpoint = host && Number.isInteger(port)
    ? `${signalingProtocol}//${host}:${port}`
    : "not configured";

  if (!host) {
    return {
      ok: false, host, port, pageProtocol, signalingProtocol, endpoint,
      message: "Enter the public Kit signaling hostname before connecting."
    };
  }
  if (isPlaceholder(host)) {
    return {
      ok: false, host, port, pageProtocol, signalingProtocol, endpoint,
      message: "Replace the BREV_PUBLIC_STREAM_HOST placeholder with the endpoint shown in Brev Access."
    };
  }
  if (/\s|:\/\/|[/?#]/.test(host)) {
    return {
      ok: false, host, port, pageProtocol, signalingProtocol, endpoint,
      message: "Use only the signaling hostname—do not include ws://, wss://, a path, or spaces."
    };
  }
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return {
      ok: false, host, port, pageProtocol, signalingProtocol, endpoint,
      message: "The signaling port must be an integer between 1 and 65535."
    };
  }
  if (pageProtocol === "https:" && !secure) {
    return {
      ok: false, host, port, pageProtocol, signalingProtocol, endpoint,
      message: "This portal is HTTPS but Kit signaling is plain WS. Open the raw HTTP portal endpoint or configure a TLS/WSS reverse proxy."
    };
  }
  if (pageProtocol === "http:" && secure) {
    return {
      ok: false, host, port, pageProtocol, signalingProtocol, endpoint,
      message: "The portal is HTTP but the endpoint is configured as WSS. Use the HTTPS portal served by the signaling proxy."
    };
  }
  return {
    ok: true, host, port, pageProtocol, signalingProtocol, endpoint,
    message: "Endpoint configuration is protocol-compatible with this page."
  };
}

export function describeStreamError(value: unknown): string {
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (record.info !== undefined) return describeStreamError(record.info);
    if (record.message !== undefined) return describeStreamError(record.message);
    try {
      return JSON.stringify(record);
    } catch {
      return "Unknown streaming error.";
    }
  }
  return "Unknown streaming error.";
}

export function actionableStreamError(value: unknown, endpoint: string): string {
  const message = describeStreamError(value);
  if (/sign-in request|signaling server|websocket/i.test(message)) {
    return `Signaling handshake failed at ${endpoint}. Verify the public TCP mapping and that WS/WSS matches the portal protocol.`;
  }
  if (/ice|candidate|media|video/i.test(message)) {
    return `Signaling reached Kit, but WebRTC media failed. Verify the Kit public IP and required UDP media exposure. Detail: ${message}`;
  }
  return message;
}
