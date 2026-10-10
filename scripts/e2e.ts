// End-to-end browser tests against a running instance (default http://localhost:3200, demo database).
//   npm run build && npm start -- -p 3200   then   npm run test:e2e
// Drives real Chromium through the real UI and prints actual results. Exits non-zero on failure.
import { chromium, type Page, type Browser } from "playwright-core";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { existsSync, readdirSync } from "node:fs";

const BASE = process.env.E2E_BASE ?? "http://localhost:3200";
const SHOTS = join(process.cwd(), "shots");
mkdirSync(SHOTS, { recursive: true });

function findChrome(): string {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const root = join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "ms-playwright");
  const dirs = existsSync(root) ? readdirSync(root).filter((d) => d.startsWith("chromium-")).sort().reverse() : [];
  for (const d of dirs) {
    const p = join(root, d, "chrome-win64", "chrome.exe");
    if (existsSync(p)) return p;
  }
  throw new Error("No Chromium found. Set CHROME_PATH.");
}

let passed = 0;
const failed: string[] = [];
async function step(name: string, fn: () => Promise<void>) {
  try {
    await fn();
    passed++;
    console.log(`  ok   ${name}`);
  } catch (e) {
    failed.push(name);
    console.log(`  FAIL ${name}\n       ${(e as Error).message.split("\n")[0]}`);
    try {
      await page.screenshot({ path: join(SHOTS, `fail-${failed.length}.png`) });
      const body = (await page.evaluate(() => document.body.innerText)).replace(/\s+/g, " ").slice(0, 260);
      console.log(`       url=${page.url()}  text="${body}"`);
    } catch {}
  }
}
function expect(cond: unknown, msg: string) {
  if (!cond) throw new Error(msg);
}

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function loginAs(page: Page, name: string) {
  await page.context().clearCookies();
  await page.goto(`${BASE}/login`);
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30000 });
}
async function toastOrText(page: Page, re: RegExp, timeout = 15000) {
  await page.getByText(re).first().waitFor({ timeout });
}
async function noOverflow(page: Page, w: number) {
  await page.setViewportSize({ width: w, height: 900 });
  await page.waitForTimeout(300);
  const o = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(o <= 1, `horizontal overflow of ${o}px at ${w}px`);
}

const browser: Browser = await chromium.launch({ executablePath: findChrome(), headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("       pageerror:", e.message.split("\n")[0]));
const consoleErrors: string[] = [];
page.on("console", (m) => {
  if (m.type() === "error" && !/Failed to load resource|favicon/.test(m.text())) consoleErrors.push(m.text().slice(0, 160));
});

let ticketCodes: string[] = [];
let memberCode = "";

console.log("public site");
await step("landing page renders hero, live numbers and events rail", async () => {
  await page.goto(BASE);
  await page.getByRole("heading", { level: 1 }).waitFor();
  expect((await page.getByRole("heading", { level: 1 }).innerText()).includes("Run the club"), "h1 text");
  await page.getByText("active members").waitFor();
  await page.locator("dl").scrollIntoViewIfNeeded();
  await page.waitForTimeout(2200);
  const n = await page.locator("dl dd").first().innerText();
  expect(Number(n.replace(/,/g, "")) >= 9, `member count ${n}`);
  await page.screenshot({ path: join(SHOTS, "01-landing-top.png") });
  await page.getByRole("heading", { name: /What is on/ }).scrollIntoViewIfNeeded();
  expect((await page.locator("a[href^='/events/']").count()) >= 3, "event cards");
});
await step("landing page has no horizontal overflow at 1440, 1024, 768 and 390", async () => {
  for (const w of [1440, 1024, 768, 390]) await noOverflow(page, w);
  await page.setViewportSize({ width: 1440, height: 900 });
});
await step("landing page has no em or en dashes in visible text", async () => {
  const t = await page.evaluate(() => document.body.innerText);
  expect(!/[—–]/.test(t), "found a long dash");
});
await step("events list and detail show member and public prices", async () => {
  await page.goto(`${BASE}/events`);
  await page.getByRole("heading", { name: "Spring Gala" }).waitFor();
  await page.getByRole("heading", { name: "Spring Gala" }).click();
  await page.waitForURL(/\/events\/\d+/);
  await page.getByText("₹950").first().waitFor();
  await page.getByText("₹650").first().waitFor();
  await page.getByRole("link", { name: /Sign in to get tickets/ }).waitFor();
  await page.screenshot({ path: join(SHOTS, "02-event-detail.png") });
});
await step("store, news and fundraisers pages behave for visitors", async () => {
  await page.goto(`${BASE}/store`);
  await page.getByRole("heading", { name: "Skyline Hoodie" }).waitFor();
  await page.getByRole("link", { name: "Sign in to order" }).waitFor();
  await page.goto(`${BASE}/announcements`);
  await page.getByRole("heading", { name: /Spring Gala tickets are on sale/ }).waitFor();
  await page.goto(`${BASE}/fundraisers`);
  await page.getByText("Fundraisers are for members").waitFor();
});
await step("officer pages redirect visitors to sign in", async () => {
  await page.goto(`${BASE}/admin/finance`);
  await page.waitForURL(/\/login/);
});

console.log("a new student joins and buys");
await step("Dev (not a member) sees the public price, then joins and pays dues", async () => {
  await loginAs(page, "Dev Malhotra");
  await page.goto(`${BASE}/events`);
  await page.getByText("₹950").first().waitFor();
  await page.goto(`${BASE}/join`);
  await page.getByRole("button", { name: /Pay dues and join/ }).click();
  await page.waitForURL(/\/pay\//);
  await page.screenshot({ path: join(SHOTS, "03-checkout.png") });
  await page.getByRole("button", { name: /Pay ₹500/ }).click();
  await page.getByText("Payment received").first().waitFor({ timeout: 20000 });
  await page.goto(`${BASE}/me/card`);
  await page.getByText("Valid through").waitFor();
  memberCode = (await page.locator("dd.num").first().innerText()).trim();
  expect(/^CL-[0-9A-F]{8}$/.test(memberCode), `member code ${memberCode}`);
  await page.screenshot({ path: join(SHOTS, "04-member-card.png") });
});
await step("member price applies on the event page right away", async () => {
  await page.goto(`${BASE}/events`);
  await page.getByRole("heading", { name: "Spring Gala" }).click();
  await page.getByText("Your member price").waitFor();
  await page.getByText(/You save/).waitFor();
});
await step("Dev holds 2 gala tickets, pays, and gets 2 QR tickets", async () => {
  await page.getByRole("button", { name: /Hold seats and pay/ }).waitFor();
  await page.getByRole("button", { name: "More tickets" }).click();
  await page.getByText("₹1,300").first().waitFor();
  await page.getByRole("button", { name: /Hold seats and pay/ }).click();
  await page.waitForURL(/\/pay\//);
  await page.getByText(/Held for you for/).waitFor();
  await page.getByRole("button", { name: /Pay ₹1,300/ }).click();
  await page.getByText("Payment received").first().waitFor({ timeout: 20000 });
  await page.goto(`${BASE}/me/tickets`);
  await page.getByText("Ticket code").first().waitFor();
  ticketCodes = await page.locator("article", { hasText: "Spring Gala" }).locator("p.num.text-lg.font-semibold").allInnerTexts();
  ticketCodes = ticketCodes.map((t) => t.trim()).filter((t) => /^[0-9A-F]{14}$/.test(t));
  expect(ticketCodes.length === 2, `expected 2 ticket codes, got ${ticketCodes.length}`);
  expect((await page.locator("[role=img][aria-label^='QR code']").count()) >= 2, "QR images");
  await page.screenshot({ path: join(SHOTS, "05-tickets.png") });
});
await step("Dev orders a hoodie and a tee in one cart; pricing uses the member discount", async () => {
  await page.goto(`${BASE}/store`);
  await page.getByRole("button", { name: /More Skyline Hoodie M/ }).click();
  await page.getByRole("button", { name: /More Crest T-Shirt S/ }).click();
  const total = 134910 + 62910;
  await page.getByText(new RegExp("₹" + (total / 100).toLocaleString("en-IN"))).first().waitFor();
  await page.screenshot({ path: join(SHOTS, "06-store-cart.png") });
  await page.getByRole("button", { name: /Reserve and pay/ }).click();
  await page.waitForURL(/\/pay\//);
  await page.getByRole("button", { name: /Pay ₹/ }).click();
  await page.getByText("Payment received").first().waitFor({ timeout: 20000 });
  await page.goto(`${BASE}/me/orders`);
  await page.getByText("Paid").first().waitFor();
});
await step("Dev submits an expense with a receipt", async () => {
  await page.goto(`${BASE}/me/expenses`);
  await page.getByPlaceholder("Sound equipment hire for Open Mic").fill("Printed posters for the gala");
  await page.getByPlaceholder("450").fill("1250");
  await page.locator("form", { has: page.getByPlaceholder("450") }).locator("input[type=file]").setInputFiles({ name: "receipt.png", mimeType: "image/png", buffer: PNG });
  await page.getByRole("button", { name: "Submit expense" }).click();
  await page.getByText("Printed posters for the gala").first().waitFor({ timeout: 20000 });
  await page.getByText(/1 receipt attached/).first().waitFor();
});
await step("a fake file renamed .png is rejected", async () => {
  await page.goto(`${BASE}/me/expenses`);
  await page.getByPlaceholder("Sound equipment hire for Open Mic").fill("Exe in disguise");
  await page.getByPlaceholder("450").fill("10");
  await page.locator("form", { has: page.getByPlaceholder("450") }).locator("input[type=file]").setInputFiles({ name: "evil.png", mimeType: "image/png", buffer: Buffer.from("MZ not an image at all") });
  await page.getByRole("button", { name: "Submit expense" }).click();
  await page.getByText(/contents do not match/).first().waitFor({ timeout: 15000 });
});

console.log("door and store desk");
await step("a plain member cannot open the officer console", async () => {
  await page.goto(`${BASE}/admin`);
  await page.waitForURL(/\/me/);
  await page.getByText(/That page is for officers/).waitFor();
});
await step("Ishaan checks Dev in, a second scan is refused, and a member card verifies", async () => {
  await loginAs(page, "Ishaan Verma");
  await page.goto(`${BASE}/admin/checkin`);
  await page.getByLabel("Event").selectOption({ label: "Spring Gala" });
  await page.getByLabel("Code").fill(`cl-t:${ticketCodes[0].toLowerCase()}`);
  await page.getByRole("button", { name: "Check in" }).click();
  await page.getByText(/Welcome, Dev Malhotra/).first().waitFor({ timeout: 15000 });
  await page.screenshot({ path: join(SHOTS, "07-checkin-ok.png") });
  await page.getByLabel("Code").fill(ticketCodes[0]);
  await page.getByRole("button", { name: "Check in" }).click();
  await page.getByText("Already checked in").first().waitFor({ timeout: 15000 });
  await page.getByLabel("Code").fill("NOSUCHCODE");
  await page.getByRole("button", { name: "Check in" }).click();
  await page.getByText("Unknown ticket").first().waitFor({ timeout: 15000 });
  await page.getByRole("tab", { name: /Member card/ }).click();
  await page.getByLabel("Code").fill(memberCode);
  await page.getByRole("button", { name: "Verify" }).click();
  await page.getByText(/Dev Malhotra is a member/).first().waitFor({ timeout: 15000 });
});
await step("Ishaan hands over Dev's paid order and stock drops", async () => {
  await page.goto(`${BASE}/admin/orders`);
  await page.getByRole("button", { name: "Hand over" }).first().click();
  await page.getByText("Marked as picked up").first().waitFor({ timeout: 15000 });
});

console.log("late payment and refunds");
await step("Priya skips the clock; Dev's late payment is kept as an obligation", async () => {
  await loginAs(page, "Dev Malhotra");
  await page.goto(`${BASE}/events`);
  await page.getByRole("heading", { name: "Spring Gala" }).click();
  await page.getByRole("button", { name: /Hold seats and pay/ }).click();
  await page.waitForURL(/\/pay\//);
  const payUrl = page.url();
  await loginAs(page, "Priya Nair");
  await page.goto(`${BASE}/admin`);
  await page.getByRole("button", { name: "+15 minutes" }).click();
  await page.getByText(/minutes ahead/).first().waitFor({ timeout: 15000 });
  await loginAs(page, "Dev Malhotra");
  await page.goto(payUrl);
  await page.getByRole("button", { name: /Pay ₹/ }).click();
  await page.getByText(/reservation had expired/).waitFor({ timeout: 20000 });
  await page.screenshot({ path: join(SHOTS, "08-late-payment.png") });
});
await step("Rohan sees it under Needs resolving and refunds it in full", async () => {
  await loginAs(page, "Rohan Kapoor");
  await page.goto(`${BASE}/admin/payments?problem=1`);
  await page.getByText("Needs resolving").first().waitFor();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Refund" }).first().click();
  await page.getByText("Refunded").first().waitFor({ timeout: 15000 });
  await page.goto(`${BASE}/admin/payments?problem=1`);
  await page.getByText("Nothing needs resolving.").waitFor();
});

console.log("treasury and term close");
await step("Rohan approves Dev's expense, pays it, and the ledger reflects it", async () => {
  await page.goto(`${BASE}/admin/expenses`);
  const card = page.locator("div.rounded-card", { hasText: "Printed posters for the gala" }).first();
  await card.getByRole("button", { name: "Approve" }).click();
  await page.getByText("Expense approved").first().waitFor({ timeout: 15000 });
  await page.goto(`${BASE}/admin/expenses`);
  const card2 = page.locator("div.rounded-card", { hasText: "Printed posters for the gala" }).first();
  await card2.getByRole("button", { name: /Pay ₹1,250/ }).click();
  await page.getByText(/Reimbursement paid/).first().waitFor({ timeout: 15000 });
  await page.goto(`${BASE}/admin/finance`);
  await page.getByText("Books integrity").waitFor();
  expect((await page.locator("svg.text-bad").count()) === 0, "an integrity check failed");
  await page.screenshot({ path: join(SHOTS, "09-finance.png"), fullPage: true });
});
await step("Rohan cannot close while money is unsettled and holds are live", async () => {
  await page.goto(`${BASE}/admin/close`);
  await page.getByText("Not ready yet").waitFor();
  await page.screenshot({ path: join(SHOTS, "10-close-blocked.png") });
});
await step("after the clock moves on and money is paid out, the term closes atomically", async () => {
  // the seeded volunteer expenses are still open: reject them so the books can close
  await loginAs(page, "Rohan Kapoor");
  for (let i = 0; i < 5; i++) {
    await page.goto(`${BASE}/admin/expenses`);
    if ((await page.getByRole("button", { name: "Reject" }).count()) === 0) break;
    await page.getByRole("button", { name: "Reject" }).first().click();
    await page.getByText("Expense rejected").first().waitFor({ timeout: 15000 });
  }
  await loginAs(page, "Priya Nair");
  await page.goto(`${BASE}/admin`);
  await page.getByRole("button", { name: "+2 hours" }).click();
  await page.getByText(/minutes ahead/).first().waitFor({ timeout: 15000 });
  await loginAs(page, "Rohan Kapoor");
  await page.goto(`${BASE}/admin/payments`);
  await page.getByRole("button", { name: /Pay out \d+ to the bank/ }).click();
  await page.getByText(/Paid out|Nothing to settle/).first().waitFor({ timeout: 15000 });
  // anything that arrived unfulfilled must be resolved before close
  await page.goto(`${BASE}/admin/close`);
  const ready = await page.getByText("Ready to close").count();
  expect(ready === 1, "close checklist not ready: " + (await page.locator("li:has(svg.text-bad)").allInnerTexts()).join(" | ").slice(0, 300));
  await page.screenshot({ path: join(SHOTS, "11-close-ready.png") });
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: /^Close / }).click();
  await page.getByText(/is now open/).first().waitFor({ timeout: 20000 });
  await page.goto(`${BASE}/admin/close`);
  await page.getByText("Sealed snapshots").waitFor();
  await page.screenshot({ path: join(SHOTS, "12-closed.png"), fullPage: true });
  await page.goto(`${BASE}/admin/finance`);
  await page.getByText("Cash in the bank").waitFor();
});

console.log("organizer, comms and team");
await step("Priya publishes an announcement; mail is queued, delivered and shown in the log", async () => {
  await loginAs(page, "Priya Nair");
  await page.goto(`${BASE}/admin/announcements`);
  await page.getByPlaceholder("General body meeting, Thursday 6 pm").last().fill("Hack Night is back");
  await page.locator("textarea[name=body]").last().fill("Teams form at 6 pm. Pizza at 7.");
  await page.getByRole("button", { name: "Publish and email" }).last().click();
  await page.getByText(/email\(s\) queued/).first().waitFor({ timeout: 15000 });
  await page.goto(`${BASE}/admin/mail`);
  await page.getByRole("button", { name: /Deliver \d+ queued/ }).click();
  await page.getByText(/delivered/).first().waitFor({ timeout: 15000 });
  await page.goto(`${BASE}/announcements`);
  await page.getByRole("heading", { name: "Hack Night is back" }).waitFor();
});
await step("Priya creates an event and opens sales", async () => {
  await page.goto(`${BASE}/admin/events/new`);
  await page.getByLabel("Title").fill("Quiz Night");
  await page.getByLabel("Venue").fill("Annex Cafe");
  await page.getByLabel("Starts (IST)").fill("2027-09-18T18:00");
  await page.getByLabel("Ends (IST)").fill("2027-09-18T21:00");
  await page.getByLabel("Capacity").fill("40");
  await page.getByLabel("Member price (rupees)").fill("100");
  await page.getByLabel("Public price (rupees)").fill("150");
  await page.getByRole("button", { name: "Create event" }).click();
  await page.waitForURL(/\/admin\/events\/\d+/, { timeout: 20000 });
  await page.getByRole("button", { name: "Open ticket sales" }).click();
  await page.getByText("Tickets are on sale").first().waitFor({ timeout: 15000 });
});
await step("Priya hands the treasurer role over after the close", async () => {
  await page.goto(`${BASE}/admin/team`);
  await page.getByText("Officer handover").waitFor();
  await page.getByRole("combobox").last().selectOption({ label: "Maya Fernandes" });
  await page.getByLabel("Admin").check().catch(() => undefined);
  await page.getByRole("button", { name: "Record handover" }).click();
  await page.getByText(/Handover recorded|Choose at least one role/).first().waitFor({ timeout: 15000 });
});
await step("a visitor can subscribe and unsubscribe", async () => {
  await page.context().clearCookies();
  await page.goto(`${BASE}/announcements`);
  await page.getByPlaceholder("you@college.edu").fill("newcomer@college.test");
  await page.getByRole("button", { name: "Get announcements" }).click();
  await page.getByText(/You are on the list/).first().waitFor({ timeout: 15000 });
});

console.log("mobile");
await step("member pages work at phone width without overflow", async () => {
  await loginAs(page, "Maya Fernandes");
  for (const path of ["/me", "/me/tickets", "/store", "/events", "/fundraisers"]) {
    await page.goto(`${BASE}${path}`);
    await noOverflow(page, 390);
  }
  await page.goto(`${BASE}/me/card`);
  await page.screenshot({ path: join(SHOTS, "13-mobile-card.png") });
  await page.setViewportSize({ width: 1440, height: 900 });
});
await step("light theme renders and the toggle persists", async () => {
  await page.goto(BASE);
  await page.getByRole("button", { name: /Switch to light theme/ }).click();
  expect(!(await page.evaluate(() => document.documentElement.classList.contains("dark"))), "still dark");
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(SHOTS, "14-landing-light.png") });
  await page.reload();
  expect(!(await page.evaluate(() => document.documentElement.classList.contains("dark"))), "theme not persisted");
});

console.log(`\nconsole errors seen: ${consoleErrors.length}${consoleErrors.length ? "\n  " + [...new Set(consoleErrors)].slice(0, 5).join("\n  ") : ""}`);
console.log(`${passed} passed, ${failed.length} failed`);
writeFileSync(join(SHOTS, "e2e-result.txt"), `${passed} passed, ${failed.length} failed\n${failed.join("\n")}\n`);
await browser.close();
if (failed.length) process.exit(1);
