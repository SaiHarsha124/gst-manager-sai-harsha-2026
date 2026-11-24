import React, { useCallback, useEffect, useState } from "react";
import { SafeAreaView, ScrollView, Text, TextInput, TouchableOpacity, View, Alert, StyleSheet } from "react-native";
import * as Clipboard from "expo-clipboard";
import { call, connect, login, logout, Role, Session } from "./src/api";
import { listenForOtp, smsConsentAvailable } from "./src/sms";

const Btn = ({ t, onPress, kind }: { t: string; onPress: () => void; kind?: "danger" }) => (
  <TouchableOpacity style={[s.btn, kind === "danger" && { backgroundColor: "#b42318" }]} onPress={onPress}><Text style={s.btnT}>{t}</Text></TouchableOpacity>);
const fail = (e: any) => Alert.alert("Error", String(e.message ?? e));

/* ---------- Login / device registration ---------- */
function Login({ onDone }: { onDone: (r: Role) => void }) {
  const [email, setEmail] = useState(""), [pw, setPw] = useState("");
  return (<View style={s.card}>
    <Text style={s.h}>GST OTP Reader</Text>
    <TextInput style={s.in} placeholder="Email" autoCapitalize="none" value={email} onChangeText={setEmail} />
    <TextInput style={s.in} placeholder="Password" secureTextEntry value={pw} onChangeText={setPw} />
    <Btn t="Sign in & register device" onPress={() => login(email, pw).then(r => onDone(r.role)).catch(fail)} />
  </View>);
}

/* ---------- Shared list with live refresh ---------- */
function useSessions() {
  const [list, setList] = useState<Session[]>([]);
  const load = useCallback(() => { call<Session[]>("GET", "/api/otp/sessions").then(setList).catch(fail); }, []);
  useEffect(() => { load(); return connect(load); }, [load]);   // events carry status only; refetch for details
  return { list, load };
}

/* ---------- CLIENT: request detail -> approve -> SMS consent / manual -> confirm & share ---------- */
function ClientRequest({ sess, onBack }: { sess: Session; onBack: () => void }) {
  const [st, setSt] = useState(sess.status), [otp, setOtp] = useState(""), [busy, setBusy] = useState(false);
  const act = (p: string, body?: object) => call<Session>("POST", `/api/otp/sessions/${sess.id}/${p}`, body).then(r => { setSt(r.status); return r; }).catch(fail);
  const detect = async () => {            // starts only after approval; Google's consent dialog decides
    setBusy(true); const c = await listenForOtp(); setBusy(false);
    if (c) { setOtp(c); } else Alert.alert("No SMS shared", "Enter the OTP manually.");
  };
  return (<View style={s.card}>
    <Text style={s.h}>{sess.return_type} · {sess.filing_period}</Text>
    <Text>{sess.purpose}</Text><Text>Status: {st} · Expires {new Date(sess.expires_at).toLocaleTimeString()}</Text>
    {["REQUESTED", "CLIENT_NOTIFIED"].includes(st) && <><Btn t="Approve request" onPress={() => act("approve")} /><Btn kind="danger" t="Reject" onPress={() => act("reject").then(onBack)} /></>}
    {st === "WAITING_FOR_SMS" && <>
      <Text style={s.note}>Android will ask your permission before any SMS is shared with this app. Nothing is read silently.</Text>
      {smsConsentAvailable && <Btn t={busy ? "Listening…" : "Detect OTP from SMS"} onPress={detect} />}
      <TextInput style={s.in} placeholder="OTP (detected or manual)" keyboardType="number-pad" maxLength={8} value={otp} onChangeText={setOtp} />
      <Btn t="Confirm OTP" onPress={() => act("manual-otp", { otp, source: smsConsentAvailable ? "SMS_CONSENT" : "MANUAL" })} /></>}
    {st === "WAITING_FOR_SHARING_APPROVAL" && <>
      <Text style={s.note}>Share this OTP once, only with the assigned auditor?</Text><Text style={s.big}>{otp || "••••••"}</Text>
      <Btn t="Share OTP with auditor" onPress={() => act("authorize-share", { confirm: true }).then(() => setOtp(""))} /></>}
    {!["REJECTED", "CANCELLED", "EXPIRED", "FAILED", "PORTAL_VERIFIED"].includes(st) && <Btn kind="danger" t="Cancel request" onPress={() => act("cancel")} />}
    <Btn t="Back" onPress={onBack} />
  </View>);
}

/* ---------- AUDITOR: create request, receive OTP once, record portal result ---------- */
function AuditorRequest({ sess, onBack }: { sess: Session; onBack: () => void }) {
  const [st, setSt] = useState(sess.status), [otp, setOtp] = useState<string | null>(null);
  useEffect(() => connect(e => e.session_id === sess.id && e.status && setSt(e.status)), [sess.id]);
  const get = () => call("GET", `/api/otp/sessions/${sess.id}/otp`).then(r => setOtp(r.otp)).catch(fail);
  const result = (verified: boolean) => call("POST", `/api/otp/sessions/${sess.id}/portal-result`, { verified }).then(r => { setSt(r.status); setOtp(null); }).catch(fail);
  return (<View style={s.card}>
    <Text style={s.h}>{sess.return_type} · {sess.filing_period}</Text><Text>Status: {st}</Text>
    {st === "OTP_AUTHORIZED" && <Btn t="Reveal OTP (one time)" onPress={get} />}
    {otp && <><Text style={s.big}>{otp}</Text><Btn t="Copy" onPress={() => Clipboard.setStringAsync(otp)} />
      <Text style={s.note}>Type it into the official GST Portal yourself, then record the real result.</Text></>}
    {(st === "OTP_DELIVERED") && <><Btn t="Portal accepted the OTP" onPress={() => result(true)} /><Btn kind="danger" t="Portal rejected the OTP" onPress={() => result(false)} /></>}
    <Btn t="Back" onPress={onBack} />
  </View>);
}
function AuditorNew({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ client_id: "", gstin_id: "", return_type: "GSTR-3B", filing_period: "", purpose: "" });
  return (<View style={s.card}><Text style={s.h}>New OTP request</Text>
    {(Object.keys(f) as (keyof typeof f)[]).map(k => <TextInput key={k} style={s.in} placeholder={k} value={f[k]} onChangeText={v => setF({ ...f, [k]: v })} />)}
    <Btn t="Request OTP" onPress={() => call("POST", "/api/otp/sessions", f).then(onDone).catch(fail)} /></View>);
}

/* ---------- ADMIN: devices + audit history (never shows OTPs) ---------- */
function Admin() {
  const [devs, setDevs] = useState<any[]>([]), [log, setLog] = useState<any[]>([]);
  const load = () => { call("GET", "/api/devices").then(setDevs).catch(fail); call("GET", "/api/admin/audit").then(setLog).catch(fail); };
  useEffect(load, []);
  return (<View><Text style={s.h}>Devices</Text>
    {devs.map(d => <View key={d.id} style={s.card}><Text>{d.device_name} · last seen {d.last_seen_at ?? "—"}</Text>
      {d.revoked_at ? <Text>Revoked</Text> : <Btn kind="danger" t="Revoke" onPress={() => call("POST", `/api/devices/${d.id}/revoke`).then(load).catch(fail)} />}</View>)}
    <Text style={s.h}>Audit history</Text>{log.map(a => <Text key={a.id} style={s.row}>{a.created_at.slice(0, 19)} · {a.event_type}</Text>)}</View>);
}

export default function App() {
  const [role, setRole] = useState<Role | null>(null), [sel, setSel] = useState<Session | null>(null), [adding, setAdding] = useState(false);
  const { list, load } = useSessions2(role);
  return (<SafeAreaView style={{ flex: 1 }}><ScrollView contentContainerStyle={{ padding: 16 }}>
    {!role ? <Login onDone={setRole} /> : <>
      <Btn t={`Sign out (${role})`} onPress={() => logout().then(() => setRole(null))} />
      {role === "ADMIN" ? <Admin /> : adding ? <AuditorNew onDone={() => { setAdding(false); load(); }} /> :
       sel ? (role === "CLIENT" ? <ClientRequest sess={sel} onBack={() => { setSel(null); load(); }} /> : <AuditorRequest sess={sel} onBack={() => { setSel(null); load(); }} />) : <>
        {role === "AUDITOR" && <Btn t="+ New OTP request" onPress={() => setAdding(true)} />}
        <Text style={s.h}>{role === "CLIENT" ? "Pending OTP requests" : "Your requests"}</Text>
        {list.map(x => <TouchableOpacity key={x.id} style={s.card} onPress={() => setSel(x)}><Text>{x.return_type} · {x.filing_period}</Text><Text>{x.status}</Text></TouchableOpacity>)}</>}
    </>}
  </ScrollView></SafeAreaView>);
}
function useSessions2(role: Role | null) {   // only subscribe once signed in
  const [list, setList] = useState<Session[]>([]);
  const load = useCallback(() => { if (role && role !== "ADMIN") call<Session[]>("GET", "/api/otp/sessions").then(setList).catch(() => {}); }, [role]);
  useEffect(() => { load(); if (!role || role === "ADMIN") return; return connect(load); }, [role, load]);
  return { list, load };
}
const s = StyleSheet.create({
  card: { backgroundColor: "#fff", borderRadius: 10, padding: 14, marginVertical: 6, gap: 8, borderWidth: 1, borderColor: "#e4e7ec" },
  h: { fontSize: 18, fontWeight: "700", marginVertical: 6 }, in: { borderWidth: 1, borderColor: "#d0d5dd", borderRadius: 8, padding: 10 },
  btn: { backgroundColor: "#175cd3", padding: 12, borderRadius: 8, alignItems: "center" }, btnT: { color: "#fff", fontWeight: "600" },
  note: { color: "#475467" }, big: { fontSize: 32, letterSpacing: 6, fontWeight: "700", textAlign: "center" }, row: { fontSize: 12, paddingVertical: 2 },
});
