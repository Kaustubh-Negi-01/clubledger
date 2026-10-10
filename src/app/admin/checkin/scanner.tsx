"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CheckCircle, IdentificationCard, Question, Ticket, WarningCircle, XCircle } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { checkinAction, verifyMemberAction, type CheckinResult, type VerifyResult } from "@/app/actions/staff";
import { cn } from "@/lib/cn";

type Ev = { id: number; title: string; sold: number; attended: number };
type Outcome = { kind: "good" | "warn" | "bad"; title: string; detail: string; at: number };

export function Scanner({ events, initialId }: { events: Ev[]; initialId?: number }) {
  const [mode, setMode] = useState<"ticket" | "member">("ticket");
  const [eventId, setEventId] = useState(initialId ?? events[0]?.id ?? 0);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<Outcome | null>(null);
  const [log, setLog] = useState<Outcome[]>([]);
  const [attended, setAttended] = useState<Record<number, number>>(() => Object.fromEntries(events.map((e) => [e.id, e.attended])));
  const [cam, setCam] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const ev = events.find((e) => e.id === eventId);

  const submit = useCallback(
    async (raw: string) => {
      const value = raw.trim();
      if (!value || busy) return;
      setBusy(true);
      let out: Outcome;
      if (mode === "ticket") {
        const r = (await checkinAction(eventId, value)) as CheckinResult & { error?: string };
        if ("error" in r && r.error) out = { kind: "bad", title: "Could not check in", detail: r.error, at: Date.now() };
        else if (r.result === "OK") {
          out = { kind: "good", title: `Welcome, ${r.holder}`, detail: `${r.tier === "MEMBER" ? "Member" : "Public"} ticket, seat ${r.seat}`, at: Date.now() };
          setAttended((a) => ({ ...a, [eventId]: (a[eventId] ?? 0) + 1 }));
        } else if (r.result === "ALREADY_USED") out = { kind: "warn", title: "Already checked in", detail: `${r.holder} was scanned earlier`, at: Date.now() };
        else out = { kind: "bad", title: r.result === "WRONG_EVENT" ? "Wrong event" : r.result === "NOT_FOUND" ? "Unknown ticket" : "Not valid", detail: r.message, at: Date.now() };
      } else {
        const r = (await verifyMemberAction(value)) as VerifyResult & { error?: string };
        if ("error" in r && r.error) out = { kind: "bad", title: "Could not verify", detail: r.error, at: Date.now() };
        else if (!r.found) out = { kind: "bad", title: "No such member", detail: "That code is not on the register", at: Date.now() };
        else out = r.valid ? { kind: "good", title: `${r.name} is a member`, detail: `${r.plan}, valid for ${r.year}`, at: Date.now() } : { kind: "bad", title: `${r.name} is not a current member`, detail: `Status: ${r.status?.toLowerCase()}`, at: Date.now() };
      }
      setLast(out);
      setLog((l) => [out, ...l].slice(0, 8));
      setCode("");
      setBusy(false);
      input.current?.focus();
    },
    [busy, eventId, mode],
  );

  useEffect(() => {
    input.current?.focus();
  }, [mode]);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
          <Select aria-label="Event" value={eventId} onChange={(e) => setEventId(Number(e.target.value))} disabled={mode === "member"}>
            {events.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
          </Select>
          <div role="tablist" aria-label="What are you scanning" className="grid grid-cols-2 gap-1 rounded-ctl bg-surface-2 p-1 text-sm">
            {([["ticket", "Ticket", Ticket], ["member", "Member card", IdentificationCard]] as const).map(([m, label, I]) => (
              <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={cn("flex items-center justify-center gap-2 rounded-[9px] px-4 py-2 font-medium transition-colors", mode === m ? "bg-surface shadow-sm" : "text-muted hover:text-ink")}>
                <I size={18} /> {label}
              </button>
            ))}
          </div>
        </div>

        <div
          aria-live="assertive"
          className={cn(
            "grid min-h-64 place-items-center rounded-card border p-8 text-center transition-colors duration-300",
            !last && "border-dashed border-line bg-surface",
            last?.kind === "good" && "border-ok/40 bg-ok-soft text-ok",
            last?.kind === "warn" && "border-warn/40 bg-warn-soft text-warn",
            last?.kind === "bad" && "border-bad/40 bg-bad-soft text-bad",
          )}
        >
          {last ? (
            <div key={last.at} className="animate-[rise_0.4s_ease-out]">
              {last.kind === "good" ? <CheckCircle size={64} weight="fill" className="mx-auto" /> : last.kind === "warn" ? <WarningCircle size={64} weight="fill" className="mx-auto" /> : <XCircle size={64} weight="fill" className="mx-auto" />}
              <p className="display mt-4 text-3xl md:text-4xl">{last.title}</p>
              <p className="mt-2 text-lg opacity-90">{last.detail}</p>
            </div>
          ) : (
            <div className="text-muted">
              <Question size={48} className="mx-auto" />
              <p className="mt-3 text-lg">Waiting for the first scan.</p>
            </div>
          )}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(code);
          }}
          className="flex gap-2"
        >
          <Input ref={input} value={code} onChange={(e) => setCode(e.target.value)} placeholder={mode === "ticket" ? "Ticket code, e.g. 7K2Q9M4DX81B" : "Member code, e.g. CL-7K2Q9M4D"} autoComplete="off" autoCapitalize="characters" spellCheck={false} aria-label="Code" className="num h-14 flex-1 text-lg" />
          <Button type="submit" size="lg" disabled={busy || !code.trim()}>{mode === "ticket" ? "Check in" : "Verify"}</Button>
          <Button type="button" variant="secondary" size="lg" onClick={() => setCam((c) => !c)} aria-pressed={cam} aria-label="Scan with camera"><Camera size={22} /></Button>
        </form>
        {cam ? <CameraScan onCode={(c) => submit(c)} onClose={() => setCam(false)} /> : null}
      </div>

      <aside className="space-y-5">
        {mode === "ticket" && ev ? (
          <div className="rounded-card border border-line bg-surface p-5 shadow-card">
            <p className="text-sm text-muted">Checked in</p>
            <p className="num display mt-1 text-5xl">{attended[ev.id] ?? 0}<span className="text-2xl text-muted"> / {ev.sold}</span></p>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${ev.sold ? Math.min(100, ((attended[ev.id] ?? 0) / ev.sold) * 100) : 0}%` }} />
            </div>
          </div>
        ) : null}
        <div className="rounded-card border border-line bg-surface p-5 shadow-card">
          <h2 className="text-sm font-semibold">Recent scans</h2>
          <ul className="mt-3 space-y-2.5 text-sm">
            {log.length === 0 ? <li className="text-muted">Nothing yet.</li> : null}
            {log.map((l) => (
              <li key={l.at} className="flex items-start gap-2.5">
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", l.kind === "good" ? "bg-ok" : l.kind === "warn" ? "bg-warn" : "bg-bad")} aria-hidden />
                <span><span className="font-medium">{l.title}</span><span className="block text-muted">{l.detail}</span></span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}

/** Camera scanning via the browser's BarcodeDetector where it exists. Typing a code always works. */
function CameraScan({ onCode, onClose }: { onCode: (c: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const cb = useRef(onCode);
  cb.current = onCode;
  useEffect(() => {
    let stop = false;
    let stream: MediaStream | null = null;
    const Detector = (window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> } }).BarcodeDetector;
    if (!Detector) {
      setErr("This browser cannot scan QR codes. Type the code instead.");
      return;
    }
    const det = new Detector({ formats: ["qr_code"] });
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (!video.current) return;
        video.current.srcObject = stream;
        await video.current.play();
        let lastValue = "";
        let lastAt = 0;
        const loop = async () => {
          if (stop || !video.current) return;
          try {
            const found = await det.detect(video.current);
            const v = found[0]?.rawValue;
            if (v && (v !== lastValue || Date.now() - lastAt > 3000)) {
              lastValue = v;
              lastAt = Date.now();
              cb.current(v);
            }
          } catch {}
          setTimeout(loop, 250);
        };
        loop();
      } catch {
        setErr("Camera permission was denied. Type the code instead.");
      }
    })();
    return () => {
      stop = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);
  return (
    <div className="overflow-hidden rounded-card border border-line bg-black">
      {err ? <p className="p-6 text-sm text-white/80">{err}</p> : <video ref={video} muted playsInline className="aspect-video w-full object-cover" />}
      <div className="flex justify-end bg-surface p-2"><Button variant="ghost" size="sm" onClick={onClose}>Close camera</Button></div>
    </div>
  );
}
