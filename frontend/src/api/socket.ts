import { io } from "socket.io-client";
import type { Realtime, RealtimeEvents } from "@/api/backend";
import { Emitter } from "@/lib/emitter";

/** Realtime channel over Socket.IO at `/socket.io` (same origin; proxied to the API). */
export function createSocketRealtime(): Realtime {
  const emitter = new Emitter<RealtimeEvents>();
  const socket = io({ path: "/socket.io", transports: ["websocket", "polling"] });
  socket.on("connect", () => emitter.emit("connection", true));
  socket.on("disconnect", () => emitter.emit("connection", false));
  socket.on("alert", (payload: RealtimeEvents["alert"]) => emitter.emit("alert", payload));
  socket.on("finding_updated", (payload: RealtimeEvents["finding_updated"]) =>
    emitter.emit("finding_updated", payload),
  );
  socket.on("job", (payload: RealtimeEvents["job"]) => emitter.emit("job", payload));
  return {
    on: (event, handler) => emitter.on(event, handler),
    isConnected: () => socket.connected,
  };
}
