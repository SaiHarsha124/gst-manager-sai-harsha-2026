import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";

export const BASE = process.env.EXPO_PUBLIC_API_URL ?? "https://api.example.com"; // HTTPS/WSS only in production
export type Role = "CLIENT" | "AUDITOR" | "ADMIN";
export type Session = { id: string; status: string; return_type: string; filing_period: string; purpose: string;
  client_id: string; gstin_id: string; expires_at: string; filing_arn?: string | null };

let access = "", refreshTok = "", deviceId = "";
export const setDeviceId = (id: string) => { deviceId = id; };

async function raw(method: string, path: string, body?: unknown) {
  return fetch(BASE + path, { method, body: body ? JSON.stringify(body) : undefined,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${access}`, "X-Device-Id": deviceId } });
}
async function refresh() {
  const r = await fetch(BASE + "/api/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refreshTok }) });
  if (!r.ok) return false;
  const j = await r.json(); access = j.access_token; refreshTok = j.refresh_token;
  await SecureStore.setItemAsync("refresh", refreshTok); return true;
}
export async function call<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  let r = await raw(method, path, body);
  if (r.status === 401 && refreshTok && (await refresh())) r = await raw(method, path, body);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}

export async function login(email: string, password: string): Promise<{ role: Role; deviceId: string }> {
  const r = await fetch(BASE + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  if (!r.ok) throw new Error("Invalid credentials");
  const j = await r.json(); access = j.access_token; refreshTok = j.refresh_token;
  await SecureStore.setItemAsync("refresh", refreshTok);
  let uuid = await SecureStore.getItemAsync("device_uuid");
  if (!uuid) { uuid = Crypto.randomUUID(); await SecureStore.setItemAsync("device_uuid", uuid); }
  const d = await call("POST", "/api/devices/register", { device_uuid: uuid, platform: "android", device_name: "Android device" });
  setDeviceId(d.id);
  return { role: j.role as Role, deviceId: d.id }; // role is advisory UI only; the server enforces everything
}
export const logout = async () => { await call("POST", "/api/auth/logout").catch(() => {}); access = refreshTok = ""; await SecureStore.deleteItemAsync("refresh"); };

/** Status-only live channel. The access token is sent as the first message, never in the URL. */
export function connect(onEvent: (e: { event: string; session_id?: string; status?: string }) => void) {
  const ws = new WebSocket(BASE.replace(/^http/, "ws") + `/api/otp/ws/${deviceId}`);
  ws.onopen = () => ws.send(JSON.stringify({ token: access }));
  ws.onmessage = (m) => onEvent(JSON.parse(m.data));
  return () => ws.close();
}
