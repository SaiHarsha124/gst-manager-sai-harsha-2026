import { NativeModules, Platform } from "react-native";
/**
 * Contract for the isolated native Android bridge around Google's SMS User Consent API
 * (see README "Native SMS bridge"). Android shows its own consent dialog; the app never
 * reads SMS silently. If the bridge is absent or the user declines, callers fall back to manual entry.
 */
type Bridge = { start(senderFilter: string | null): Promise<string | null>; stop(): void };
const bridge = NativeModules.SmsUserConsent as Bridge | undefined;

export const smsConsentAvailable = Platform.OS === "android" && !!bridge;
export const extractOtp = (body: string) => body.match(/\b\d{6}\b/)?.[0] ?? null;

/** Returns a *candidate* OTP only; the SMS body is discarded here and never uploaded. */
export async function listenForOtp(): Promise<string | null> {
  if (!bridge) return null;
  try { const body = await bridge.start(null); return body ? extractOtp(body) : null; }
  catch { return null; } finally { bridge.stop(); }
}
