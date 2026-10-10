import type { Metadata } from "next";
import { Bag } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { dateTime, inr } from "@/lib/format";
import type { Order } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ActionButton } from "@/components/ui/action-form";
import { cancelOrderAction } from "@/app/actions/member";

export const metadata: Metadata = { title: "My orders" };

export default async function OrdersPage() {
  const orders = await rpc<Order[]>("api_my_orders");
  return (
    <div className="space-y-8">
      <div>
        <h1 className="display text-4xl">My orders</h1>
        <p className="mt-3 text-muted">Paid orders are collected from the store desk at the next event.</p>
      </div>
      {orders.length === 0 ? (
        <Empty icon={Bag} title="No orders yet">
          <p>Hoodies, tees and totes are in the store.</p>
          <Button href="/store" size="sm" className="mt-4">Open the store</Button>
        </Empty>
      ) : (
        <div className="space-y-4">
          {orders.map((o) => (
            <Card key={o.id} className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-semibold">Order <span className="num">#{o.id}</span></p>
                  <p className="mt-1 text-sm text-muted">{dateTime(o.created_at)}{o.picked_up_at ? `, picked up ${dateTime(o.picked_up_at)}` : ""}</p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={o.status} />
                  <span className="num text-lg font-semibold">{inr(o.total_paise)}</span>
                </div>
              </div>
              <ul className="mt-4 divide-y divide-line text-[15px]">
                {(o.items ?? []).map((i, k) => (
                  <li key={k} className="flex justify-between py-2.5"><span>{i.name} <span className="text-muted">{i.size} x {i.qty}</span></span><span className="num">{inr(i.unit * i.qty)}</span></li>
                ))}
              </ul>
              {o.status === "RESERVED" && o.payment_id ? (
                <div className="mt-5 flex flex-wrap gap-2">
                  <Button href={`/pay/${o.payment_id}`} size="sm">Pay now</Button>
                  <ActionButton action={cancelOrderAction.bind(null, o.id)} variant="ghost" confirm="Cancel this order and release the stock?">Cancel order</ActionButton>
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
