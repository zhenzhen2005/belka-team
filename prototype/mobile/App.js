// Belka mobile (Expo) — flow เดียวกับ web app: แตะการ์ด 3 ขั้น → การ์ดงานวันละ 1 ใบ
// ใช้ API เดียวกัน: POST /api/plan, POST /api/redline
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator, Linking, Pressable, SafeAreaView, ScrollView, StatusBar,
  StyleSheet, Text, TextInput, View,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { API_URL } from "./config";

const C = {
  bg: "#F6EFE6", card: "#FFFFFF", ink: "#2B2118", muted: "#6E6257", line: "#E7DCCF",
  brand: "#C8622A", brandSoft: "#FBE7D8", ok: "#2F7D4F", warn: "#A23B2A", warnSoft: "#FBE4DF",
};

const STEPS = [
  { key: "shop_type", title: "ร้านคุณขายอะไร?", sub: "เลือก 1 อย่างที่ตรงที่สุด", multi: false, options: [
    { v: "drink", em: "☕", t: "เครื่องดื่ม", s: "กาแฟ ชา น้ำปั่น" },
    { v: "bakery", em: "🍰", t: "เบเกอรี่", s: "ขนมอบ เค้ก ขนมปัง" },
    { v: "food", em: "🍜", t: "อาหาร", s: "อาหารจานเดียว ร้านข้าว" },
  ] },
  { key: "customer", title: "ลูกค้าส่วนใหญ่คือใคร?", sub: "Belka จะเลือกเวลาโพสต์ให้ตรงกับตอนที่เขาว่าง", multi: false, options: [
    { v: "workers", em: "🏢", t: "คนทำงาน" },
    { v: "students", em: "🎓", t: "นักศึกษา" },
    { v: "locals", em: "🏠", t: "คนในย่าน" },
    { v: "tourists", em: "🧳", t: "นักท่องเที่ยว" },
  ] },
  { key: "channels", title: "ตอนนี้ร้านใช้ช่องทางไหนบ้าง?", sub: "เลือกได้หลายอัน", multi: true, options: [
    { v: "line", em: "💬", t: "LINE" },
    { v: "facebook", em: "📘", t: "Facebook" },
    { v: "google_maps", em: "📍", t: "Google Maps" },
    { v: "delivery", em: "🛵", t: "Grab / LINE MAN" },
    { v: "none", em: "🌱", t: "ยังไม่มีเลย" },
  ] },
];

const OPEN_APP = {
  google_maps: ["เปิด Google Business Profile", "https://business.google.com/"],
  line: ["เปิด LINE OA Manager", "https://manager.line.biz/"],
  facebook: ["เปิด Facebook", "https://www.facebook.com/"],
};

const EMPTY_PROFILE = { shop_type: null, customer: null, channels: [] };
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

async function post(path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState("welcome");
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [plan, setPlan] = useState(null);
  const [status, setStatus] = useState({});
  const [ticks, setTicks] = useState({});
  const [view, setView] = useState("today");
  const [focus, setFocus] = useState(null);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState("");
  const [issues, setIssues] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  // โหลดแผนที่เคยบันทึกไว้
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem("belka");
        if (raw) {
          const s = JSON.parse(raw);
          if (s.plan) { setPlan(s.plan); setProfile(s.profile); setStatus(s.status || {}); setTicks(s.ticks || {}); setScreen("plan"); }
        }
      } catch {}
      setReady(true);
    })();
  }, []);

  useEffect(() => {
    if (!ready) return;
    AsyncStorage.setItem("belka", JSON.stringify({ plan, profile, status, ticks })).catch(() => {});
  }, [plan, profile, status, ticks, ready]);

  const showToast = msg => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 1800);
  };

  async function requestPlan(p = profile) {
    setScreen("loading"); setError(null);
    try {
      const data = await post("/api/plan", p);
      setPlan(data); setStatus({}); setTicks({}); setFocus(null); setView("today"); setScreen("plan");
    } catch {
      setScreen("step"); setStep(2);
      setError("เชื่อมต่อ Belka ไม่ได้ ตรวจว่า backend เปิดอยู่ และ API_URL ใน config.js ถูกต้อง");
    }
  }

  function pick(v) {
    const s = STEPS[step];
    if (s.multi) {
      let cur = profile.channels;
      if (v === "none") cur = cur.includes("none") ? [] : ["none"];
      else cur = cur.includes(v) ? cur.filter(x => x !== v) : [...cur.filter(x => x !== "none"), v];
      setProfile({ ...profile, channels: cur });
    } else {
      setProfile({ ...profile, [s.key]: v });
      setTimeout(() => setStep(step + 1), 180);
    }
  }

  async function saveEdit(slot) {
    try {
      const result = await post("/api/redline", { text: draft.trim() });
      if (!result.passed) { setIssues(result.issues); return; }
      setPlan({ ...plan, tasks: plan.tasks.map(t => t.slot === slot ? { ...t, caption: draft.trim(), redline: result } : t) });
      setEditing(null); setIssues(null); showToast("บันทึกแล้ว ผ่านการตรวจ ✓");
    } catch { showToast("ตรวจข้อความไม่ได้ ลองใหม่อีกครั้ง"); }
  }

  function mark(slot, value) {
    setStatus({ ...status, [slot]: value }); setFocus(null); setEditing(null);
    if (value === "done") showToast("เยี่ยมมาก! 🎉");
  }

  function current() {
    const tasks = plan.tasks, today = todayISO(), todo = t => !status[t.slot];
    if (focus) return { task: tasks.find(t => t.slot === focus), mode: "focus" };
    const t1 = tasks.find(t => t.date === today && todo(t)); if (t1) return { task: t1, mode: "today" };
    const t2 = tasks.find(t => t.date < today && todo(t)); if (t2) return { task: t2, mode: "overdue" };
    const t3 = tasks.find(todo); if (t3) return { task: t3, mode: "rest" };
    return { task: null, mode: "complete" };
  }

  if (!ready) return <View style={[st.fill, st.center]}><ActivityIndicator color={C.brand} /></View>;

  const Header = ({ right }) => (
    <View style={st.header}>
      <Text style={st.logo}>🐿️ Belka</Text>
      {right}
    </View>
  );

  let body;
  if (screen === "welcome") {
    body = (
      <>
        <Header />
        <Text style={{ fontSize: 72, textAlign: "center", marginTop: 24 }}>🐿️</Text>
        <Text style={st.h1}>สวัสดี ฉันคือ Belka{"\n"}เพื่อนคู่คิดการตลาดของร้านคุณ</Text>
        <Text style={st.lead}>ตอบ 3 คำถามด้วยการแตะ ไม่ต้องพิมพ์ ใช้เวลาไม่ถึง 1 นาที แล้วรับแผนการตลาดสัปดาห์นี้ วันละไม่เกิน 10 นาที</Text>
        <View style={st.fill} />
        <Btn kind="primary" label="เริ่มเลย" onPress={() => { setProfile(EMPTY_PROFILE); setStep(0); setScreen("step"); }} />
        <Text style={st.hint}>ไม่ต้องกรอกต้นทุนหรือยอดขาย</Text>
      </>
    );
  } else if (screen === "step") {
    const s = STEPS[step];
    const val = profile[s.key];
    const on = v => (s.multi ? val.includes(v) : val === v);
    body = (
      <>
        <Header right={<Pressable onPress={() => { setError(null); step === 0 ? setScreen("welcome") : setStep(step - 1); }}><Text style={st.ghost}>‹ ย้อนกลับ</Text></Pressable>} />
        <View style={st.dots}>{STEPS.map((_, i) => <View key={i} style={[st.dot, i <= step && { backgroundColor: C.brand }]} />)}</View>
        <Text style={[st.hint, { textAlign: "left", marginTop: 0 }]}>ขั้น {step + 1} จาก 3</Text>
        <Text style={st.h1}>{s.title}</Text>
        <Text style={st.lead}>{s.sub}</Text>
        <View style={st.grid}>
          {s.options.map(o => (
            <Pressable key={o.v} onPress={() => pick(o.v)} style={[st.choice, step === 0 && st.choiceWide, on(o.v) && st.choiceOn]}>
              <Text style={{ fontSize: 30 }}>{o.em}</Text>
              <View style={{ flexShrink: 1 }}>
                <Text style={st.choiceT}>{o.t}</Text>
                {o.s ? <Text style={st.small}>{o.s}</Text> : null}
              </View>
            </Pressable>
          ))}
        </View>
        <View style={st.fill} />
        {s.multi ? <Btn kind="primary" label="รับแผนของร้าน ✨" disabled={!val.length} onPress={() => requestPlan()} /> : null}
        {error ? <Text style={[st.hint, { color: C.warn }]}>{error}</Text> : null}
      </>
    );
  } else if (screen === "loading") {
    body = (
      <View style={[st.fill, st.center]}>
        <Text style={{ fontSize: 64 }}>🐿️</Text>
        <Text style={st.h2}>Belka กำลังคิดแผนให้ร้านคุณ</Text>
        <ActivityIndicator color={C.brand} style={{ marginTop: 12 }} />
      </View>
    );
  } else {
    const { task, mode } = current();
    const todayTask = plan.tasks.find(t => t.date === todayISO());
    const done = plan.tasks.filter(t => status[t.slot] === "done").length;
    body = (
      <>
        <Header right={<Pressable onPress={() => { AsyncStorage.removeItem("belka").catch(() => {}); setPlan(null); setScreen("welcome"); }}><Text style={st.ghost}>เริ่มใหม่</Text></Pressable>} />
        {plan.notice ? <View style={st.notice}><Text style={st.small}>{plan.notice}</Text></View> : null}
        <View style={st.tabs}>
          {[["today", "วันนี้"], ["week", "ทั้งสัปดาห์"]].map(([k, l]) => (
            <Pressable key={k} onPress={() => { setView(k); setFocus(null); }} style={[st.tab, view === k && st.tabOn]}>
              <Text style={[st.tabT, view === k && { color: C.ink }]}>{l}</Text>
            </Pressable>
          ))}
        </View>
        {view === "week" ? plan.tasks.map(t => (
          <Pressable key={t.slot} style={st.weekItem} onPress={() => { setFocus(t.slot); setView("today"); }}>
            <Text style={{ fontSize: 22 }}>{status[t.slot] === "done" ? "✅" : status[t.slot] === "skipped" ? "⏭️" : t.date === todayISO() ? "👉" : "⬜"}</Text>
            <View style={st.fill}>
              <Text style={st.bold}>{t.title}</Text>
              <Text style={st.small}>{t.day_label} · {t.channel_label} · {t.minutes} นาที</Text>
            </View>
            <Text style={st.small}>›</Text>
          </Pressable>
        )) : (
          <>
            <View style={st.daybar}>
              <Text style={st.h2}>{todayTask ? `วันนี้ · ${todayTask.day_label}` : "สัปดาห์นี้"}</Text>
              <Text style={st.small}>{plan.tasks.map(t => status[t.slot] === "done" ? "🟢" : status[t.slot] === "skipped" ? "⚪" : "◯").join(" ")}  {done}/3</Text>
            </View>
            {mode === "complete" ? (
              <View style={[st.card, st.center]}>
                <Text style={{ fontSize: 56 }}>🎉</Text>
                <Text style={st.h2}>ครบทั้งสัปดาห์แล้ว</Text>
                <Text style={st.lead}>ทำไปแล้ว {done} จาก 3 งาน</Text>
                <Btn kind="primary" label="รับแผนสัปดาห์ใหม่" onPress={() => requestPlan()} />
              </View>
            ) : mode === "rest" ? (
              <View style={[st.card, st.center]}>
                <Text style={{ fontSize: 56 }}>🌿</Text>
                <Text style={st.h2}>วันนี้พักได้</Text>
                <Text style={[st.lead, { textAlign: "center" }]}>งานถัดไป: {task.day_label}{"\n"}{task.title}</Text>
                <Btn kind="secondary" label="ทำล่วงหน้าเลย" onPress={() => setFocus(task.slot)} />
              </View>
            ) : (
              <TaskCard
                t={task}
                label={mode === "overdue" ? `งานที่ค้างไว้จาก${task.day_label} ยังทำได้นะ` : mode === "focus" ? `งานของ${task.day_label}` : null}
                ticks={ticks[task.slot] || []}
                onTick={i => { const cur = ticks[task.slot] || []; setTicks({ ...ticks, [task.slot]: cur.includes(i) ? cur.filter(x => x !== i) : [...cur, i] }); }}
                editing={editing === task.slot}
                draft={draft}
                issues={issues}
                onDraft={setDraft}
                onEdit={() => { setEditing(task.slot); setDraft(task.caption); setIssues(null); }}
                onCancel={() => { setEditing(null); setIssues(null); }}
                onSave={() => saveEdit(task.slot)}
                onCopy={async () => { await Clipboard.setStringAsync(task.caption); showToast("คัดลอกแคปชันแล้ว 📋"); }}
                onDone={() => mark(task.slot, "done")}
                onSkip={() => mark(task.slot, "skipped")}
              />
            )}
          </>
        )}
      </>
    );
  }

  return (
    <SafeAreaView style={[st.fill, { backgroundColor: C.bg }]}>
      <StatusBar barStyle="dark-content" />
      <ScrollView contentContainerStyle={st.page} keyboardShouldPersistTaps="handled">{body}</ScrollView>
      {toast ? <View style={st.toast}><Text style={{ color: "#fff" }}>{toast}</Text></View> : null}
    </SafeAreaView>
  );
}

function TaskCard({ t, label, ticks, onTick, editing, draft, issues, onDraft, onEdit, onCancel, onSave, onCopy, onDone, onSkip }) {
  const [whyOpen, setWhyOpen] = useState(false);
  const open = OPEN_APP[t.channel];
  return (
    <>
      <View style={st.card}>
        <View style={st.chips}>
          <Text style={[st.chip, { backgroundColor: C.brandSoft, color: C.brand }]}>{t.channel_label}</Text>
          <Text style={st.chip}>🕒 {t.time_window}</Text>
          <Text style={st.chip}>⏱️ {t.minutes} นาที</Text>
        </View>
        {label ? <Text style={[st.small, { marginBottom: 2 }]}>{label}</Text> : null}
        <Text style={st.h2}>{t.title}</Text>

        <View style={st.caption}>
          {editing ? (
            <>
              <Text style={st.small}>แก้แคปชัน</Text>
              <TextInput value={draft} onChangeText={onDraft} multiline style={st.input} />
              {issues ? (
                <View style={st.issues}>
                  <Text style={[st.bold, { color: C.warn }]}>ยังใช้ไม่ได้</Text>
                  {issues.map((i, k) => <Text key={k} style={{ color: C.warn, fontSize: 14 }}>• “{i.term}” {i.reason} → {i.suggestion}</Text>)}
                </View>
              ) : null}
            </>
          ) : (
            <>
              <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 6 }}>
                <Text style={st.small}>💬 แคปชันพร้อมใช้</Text>
                {t.redline.passed ? <Text style={[st.small, { color: C.ok, fontWeight: "600" }]}>ผ่านการตรวจแล้ว ✓</Text> : null}
              </View>
              <Text style={st.body}>{t.caption}</Text>
            </>
          )}
        </View>
        <View style={st.row}>
          {editing ? (
            <>
              <MiniBtn label="ยกเลิก" onPress={onCancel} />
              <MiniBtn label="ตรวจและบันทึก" onPress={onSave} primary />
            </>
          ) : (
            <>
              <MiniBtn label="📋 คัดลอก" onPress={onCopy} />
              <MiniBtn label="✏️ แก้" onPress={onEdit} />
            </>
          )}
        </View>

        {t.steps.map((s, i) => (
          <Pressable key={i} onPress={() => onTick(i)} style={st.stepRow}>
            <View style={[st.box, ticks.includes(i) && { backgroundColor: C.ok, borderColor: C.ok }]}>
              {ticks.includes(i) ? <Text style={{ color: "#fff", fontSize: 13 }}>✓</Text> : null}
            </View>
            <Text style={[st.body, st.fill, ticks.includes(i) && { color: C.muted, textDecorationLine: "line-through" }]}>{s}</Text>
          </Pressable>
        ))}
        {open ? <Pressable onPress={() => Linking.openURL(open[1])}><Text style={st.link}>{open[0]} ↗</Text></Pressable> : null}

        <Pressable onPress={() => setWhyOpen(!whyOpen)} style={st.why}>
          <Text style={[st.bold, { color: C.brand }]}>❓ ทำไมต้องทำ?</Text>
          {whyOpen ? <Text style={[st.body, { color: C.muted, marginTop: 6 }]}>{t.why}</Text> : null}
        </Pressable>
      </View>
      <Text style={[st.hint, { marginTop: 0 }]}>{t.source === "ai" ? "✨ Belka คิดให้ร้านคุณโดยเฉพาะ" : "📘 แผนมาตรฐานของ Belka"}</Text>
      <View style={st.row}>
        <View style={st.fill}><Btn kind="secondary" label="⏭️ ข้าม" onPress={onSkip} /></View>
        <View style={st.fill}><Btn kind="ok" label="✅ ทำแล้ว" onPress={onDone} /></View>
      </View>
    </>
  );
}

function Btn({ label, onPress, kind = "primary", disabled }) {
  const bg = { primary: C.brand, ok: C.ok, secondary: C.card }[kind];
  const color = kind === "secondary" ? C.ink : "#fff";
  return (
    <Pressable onPress={disabled ? undefined : onPress} style={({ pressed }) => [st.btn, { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 }, kind === "secondary" && { borderWidth: 1.5, borderColor: C.line }]}>
      <Text style={{ color, fontSize: 18, fontWeight: "600" }}>{label}</Text>
    </Pressable>
  );
}

function MiniBtn({ label, onPress, primary }) {
  return (
    <Pressable onPress={onPress} style={[st.mini, primary && { backgroundColor: C.brand, borderColor: C.brand }]}>
      <Text style={{ fontSize: 15, fontWeight: "500", color: primary ? "#fff" : C.ink }}>{label}</Text>
    </Pressable>
  );
}

const st = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: "center", justifyContent: "center", gap: 8 },
  page: { flexGrow: 1, padding: 18, paddingBottom: 32 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  logo: { fontSize: 20, fontWeight: "700", color: C.ink },
  ghost: { color: C.muted, fontSize: 15, padding: 6 },
  h1: { fontSize: 26, fontWeight: "700", color: C.ink, marginBottom: 6, lineHeight: 36 },
  h2: { fontSize: 20, fontWeight: "700", color: C.ink, lineHeight: 28 },
  lead: { fontSize: 16, color: C.muted, marginBottom: 20, lineHeight: 24 },
  hint: { fontSize: 14, color: C.muted, textAlign: "center", marginVertical: 12 },
  small: { fontSize: 14, color: C.muted },
  body: { fontSize: 16, color: C.ink, lineHeight: 24 },
  bold: { fontSize: 16, fontWeight: "600", color: C.ink },
  dots: { flexDirection: "row", gap: 6, marginBottom: 14 },
  dot: { flex: 1, height: 6, borderRadius: 3, backgroundColor: C.line },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  choice: { width: "47%", minHeight: 96, backgroundColor: C.card, borderRadius: 20, padding: 16, borderWidth: 2, borderColor: "transparent", gap: 6 },
  choiceWide: { width: "100%", minHeight: 76, flexDirection: "row", alignItems: "center", gap: 14 },
  choiceOn: { borderColor: C.brand, backgroundColor: C.brandSoft },
  choiceT: { fontSize: 18, fontWeight: "600", color: C.ink },
  btn: { minHeight: 56, borderRadius: 16, alignItems: "center", justifyContent: "center", paddingHorizontal: 12 },
  tabs: { flexDirection: "row", backgroundColor: C.line, borderRadius: 14, padding: 4, marginBottom: 14 },
  tab: { flex: 1, paddingVertical: 8, borderRadius: 10, alignItems: "center" },
  tabOn: { backgroundColor: C.card },
  tabT: { fontSize: 15, fontWeight: "600", color: C.muted },
  daybar: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  card: { backgroundColor: C.card, borderRadius: 24, padding: 18, marginBottom: 12 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 10 },
  chip: { fontSize: 13, paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999, backgroundColor: C.bg, color: C.muted, overflow: "hidden" },
  caption: { backgroundColor: C.bg, borderRadius: 16, padding: 14, marginTop: 12, marginBottom: 10 },
  input: { backgroundColor: C.card, borderRadius: 12, borderWidth: 1.5, borderColor: C.line, padding: 12, minHeight: 100, fontSize: 16, marginTop: 6, textAlignVertical: "top" },
  issues: { backgroundColor: C.warnSoft, borderRadius: 12, padding: 10, marginTop: 8, gap: 4 },
  row: { flexDirection: "row", gap: 10 },
  mini: { flex: 1, minHeight: 44, borderRadius: 12, borderWidth: 1.5, borderColor: C.line, alignItems: "center", justifyContent: "center", backgroundColor: C.card },
  stepRow: { flexDirection: "row", gap: 10, alignItems: "flex-start", marginTop: 10 },
  box: { width: 24, height: 24, borderRadius: 7, borderWidth: 2, borderColor: C.line, alignItems: "center", justifyContent: "center", marginTop: 1 },
  link: { color: C.brand, fontWeight: "600", marginTop: 12, fontSize: 15 },
  why: { marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.line, borderStyle: "dashed" },
  notice: { backgroundColor: C.brandSoft, borderRadius: 14, padding: 10, marginBottom: 12 },
  weekItem: { flexDirection: "row", gap: 12, alignItems: "center", backgroundColor: C.card, borderRadius: 18, padding: 14, marginBottom: 10 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: C.ink, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 999 },
});
