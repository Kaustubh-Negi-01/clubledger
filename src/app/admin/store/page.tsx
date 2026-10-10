import type { Metadata } from "next";
import { requireRole } from "@/lib/session";
import { rpc } from "@/lib/db";
import { inr } from "@/lib/format";
import type { Product } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ProductForm, StockForm } from "./forms";

export const metadata: Metadata = { title: "Products and stock" };

export default async function AdminStore() {
  await requireRole("/admin/store", "store");
  const products = await rpc<Product[]>("api_products_list", { p_all: true });
  return (
    <>
      <PageHeader title="Products and stock" description="Physical stock is what is on the shelf. Reserved is promised to open orders. Shoppers only ever see available." />
      <div className="space-y-6">
        {products.map((p) => (
          <Card key={p.id} id={`product-${p.id}`}>
            <CardHeader title={<span className="flex items-center gap-3">{p.name} {!p.is_active ? <Badge>Hidden</Badge> : null}</span>} action={<span className="num text-lg font-semibold">{inr(p.base_price_paise)}</span>} />
            <div className="grid gap-8 p-5 lg:grid-cols-2">
              <div>
                <table className="w-full text-[15px]">
                  <thead><tr className="text-left text-xs text-muted"><th className="pb-2 font-medium">Size</th><th className="pb-2 text-right font-medium">Physical</th><th className="pb-2 text-right font-medium">Reserved</th><th className="pb-2 text-right font-medium">Available</th></tr></thead>
                  <tbody>
                    {p.variants.map((v) => (
                      <tr key={v.id} className="border-t border-line">
                        <td className="py-2.5 font-medium">{v.size}</td>
                        <td className="num py-2.5 text-right">{v.physical}</td>
                        <td className="num py-2.5 text-right text-muted">{v.reserved}</td>
                        <td className={`num py-2.5 text-right font-semibold ${v.available <= 3 ? "text-warn" : ""}`}>{v.available}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <StockForm productId={p.id} />
              </div>
              <ProductForm product={p} />
            </div>
          </Card>
        ))}
        <Card>
          <CardHeader title="Add a product" />
          <div className="p-5"><ProductForm /></div>
        </Card>
      </div>
    </>
  );
}
