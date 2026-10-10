"use client";

import { Media } from "@/components/media";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Minus, Plus, ShoppingBagOpen } from "@phosphor-icons/react";
import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Button } from "@/components/ui/button";
import { reserveCartAction } from "@/app/actions/member";
import { inr } from "@/lib/format";
import { cn } from "@/lib/cn";
import type { Product } from "@/lib/types";

export function Cart({ products, signedIn, member }: { products: Product[]; signedIn: boolean; member: boolean }) {
  const [qty, setQty] = useState<Record<number, number>>({});
  const set = (id: number, n: number) => setQty((q) => ({ ...q, [id]: Math.max(0, n) }));

  const lines = useMemo(() => {
    const out: { name: string; size: string; qty: number; unit: number }[] = [];
    for (const p of products) for (const v of p.variants) if ((qty[v.id] ?? 0) > 0) out.push({ name: p.name, size: v.size, qty: qty[v.id], unit: p.my_price });
    return out;
  }, [products, qty]);
  const total = lines.reduce((s, l) => s + l.qty * l.unit, 0);
  const count = lines.reduce((s, l) => s + l.qty, 0);

  return (
    <ActionForm action={reserveCartAction} className="grid gap-10 lg:grid-cols-[1fr_22rem]">
      <div className="grid gap-6 sm:grid-cols-2">
        {products.map((p) => (
          <article key={p.id} className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
            <div className="relative aspect-[5/4] bg-surface-2">
              <Media src={p.image_url} title={p.name} sizes="(min-width:1024px) 28vw, 100vw" />
            </div>
            <div className="space-y-4 p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold tracking-tight">{p.name}</h2>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{p.description}</p>
                </div>
                <div className="text-right">
                  <p className="num text-lg font-semibold">{inr(p.my_price)}</p>
                  {!member && p.my_price === p.base_price_paise ? <p className="num text-xs text-muted">members {inr(Math.floor((p.base_price_paise * 9000) / 10000))}</p> : null}
                </div>
              </div>
              <ul className="space-y-2">
                {p.variants.map((v) => {
                  const n = qty[v.id] ?? 0;
                  const out = v.available <= 0;
                  return (
                    <li key={v.id} className={cn("flex items-center justify-between rounded-ctl border px-3 py-2", n > 0 ? "border-accent bg-accent-soft/50" : "border-line")}>
                      <div>
                        <p className={cn("font-medium", out && "text-muted line-through")}>{v.size}</p>
                        <p className={cn("num text-xs", v.available <= 3 && !out ? "text-warn" : "text-muted")}>{out ? "Sold out" : v.available <= 3 ? `Only ${v.available} left` : `${v.available} in stock`}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        <button type="button" aria-label={`Fewer ${p.name} ${v.size}`} disabled={n === 0} onClick={() => set(v.id, n - 1)} className="grid size-9 place-items-center rounded-full hover:bg-surface-2 disabled:opacity-30"><Minus size={16} /></button>
                        <span className="num w-6 text-center" aria-live="polite">{n}</span>
                        <button type="button" aria-label={`More ${p.name} ${v.size}`} disabled={out || n >= Math.min(10, v.available)} onClick={() => set(v.id, n + 1)} className="grid size-9 place-items-center rounded-full hover:bg-surface-2 disabled:opacity-30"><Plus size={16} /></button>
                      </div>
                      {n > 0 ? <input type="hidden" name={`qty_${v.id}`} value={n} /> : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          </article>
        ))}
      </div>

      <aside className="lg:sticky lg:top-24 lg:self-start">
        <div className="rounded-card border border-line bg-surface p-6 shadow-card">
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight"><ShoppingBagOpen size={22} /> Your cart</h2>
          {lines.length ? (
            <ul className="mt-5 divide-y divide-line text-sm">
              {lines.map((l) => (
                <li key={`${l.name}-${l.size}`} className="flex items-start justify-between gap-3 py-3">
                  <span>{l.name} <span className="text-muted">{l.size} x {l.qty}</span></span>
                  <span className="num">{inr(l.unit * l.qty)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm leading-relaxed text-muted">Choose a size and quantity to start an order.</p>
          )}
          <div className="mt-5 flex items-baseline justify-between border-t border-line pt-5">
            <span className="text-muted">Total ({count})</span>
            <span className="num text-2xl font-semibold">{inr(total)}</span>
          </div>
          <div className="mt-5">
            {signedIn ? (
              <SubmitButton size="lg" className="w-full" pendingLabel="Reserving stock">Reserve and pay</SubmitButton>
            ) : (
              <Button href="/login?next=/store" size="lg" className="w-full">Sign in to order</Button>
            )}
          </div>
          <p className="mt-3 text-center text-xs text-muted">Stock for the whole cart is held, or none of it is. <Link href="/me/orders" className="underline underline-offset-4">My orders</Link></p>
        </div>
      </aside>
    </ActionForm>
  );
}
