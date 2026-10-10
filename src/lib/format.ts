const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inrFmt2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Paise (integer) to a display string. Money is never a float anywhere except this last step. */
export function inr(paise: number | string | null | undefined, opts: { signed?: boolean } = {}): string {
  const n = Number(paise ?? 0);
  const abs = Math.abs(n);
  const rupees = abs % 100 === 0 ? inrFmt.format(abs / 100) : inrFmt2.format(abs / 100);
  const sign = n < 0 ? "-" : opts.signed && n > 0 ? "+" : "";
  return `${sign}\u20B9${rupees}`;
}

const TZ = "Asia/Kolkata";
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(new Date(iso));
}
export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}
/** Memberships end at 00:00 IST on 1 Aug (exclusive). People think "valid through 31 Jul". */
export function validThrough(expiresIso: string): string {
  return dateOnly(new Date(new Date(expiresIso).getTime() - 60_000).toISOString());
}
export function dayParts(iso: string) {
  const d = new Date(iso);
  return {
    day: new Intl.DateTimeFormat("en-IN", { timeZone: TZ, day: "2-digit" }).format(d),
    month: new Intl.DateTimeFormat("en-IN", { timeZone: TZ, month: "short" }).format(d),
    weekday: new Intl.DateTimeFormat("en-IN", { timeZone: TZ, weekday: "short" }).format(d),
    time: new Intl.DateTimeFormat("en-IN", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(d),
  };
}
export function relative(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 3600_000) return rtf.format(Math.round(diff / 60_000), "minute");
  if (abs < 86_400_000) return rtf.format(Math.round(diff / 3600_000), "hour");
  return rtf.format(Math.round(diff / 86_400_000), "day");
}

/** Rupee text from a form field ("1,499.50") to paise, or null if it is not a valid amount. */
export function toPaise(input: FormDataEntryValue | null): number | null {
  if (input === null) return null;
  const s = String(input).replace(/[,\s\u20B9]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return null;
  return Math.round(parseFloat(s) * 100);
}
export function paiseToInput(p: number | null | undefined): string {
  if (p === null || p === undefined) return "";
  return (p / 100).toFixed(p % 100 === 0 ? 0 : 2);
}
export function istInputToIso(local: string): string {
  // <input type="datetime-local"> value interpreted as IST wall time
  return new Date(`${local}:00+05:30`).toISOString();
}
export function isoToIstInput(iso: string): string {
  const d = new Date(new Date(iso).getTime() + 5.5 * 3600_000);
  return d.toISOString().slice(0, 16);
}
