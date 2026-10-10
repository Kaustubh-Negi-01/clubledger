import type { Metadata } from "next";
import { Storefront } from "@phosphor-icons/react/dist/ssr";
import { rpc } from "@/lib/db";
import { getMe } from "@/lib/session";
import type { Product } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Empty } from "@/components/ui/empty";
import { Cart } from "./cart";

export const metadata: Metadata = { title: "Store" };

export default async function StorePage() {
  const [products, me] = await Promise.all([rpc<Product[]>("api_products_list"), getMe()]);
  const member = me?.membership?.status === "ACTIVE";
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
      <PageHeader
        title="Store"
        description={member ? "Member prices are applied. Your cart is reserved for 15 minutes while you pay." : "Members get 10% off everything here. Your cart is reserved for 15 minutes while you pay."}
      />
      {products.length ? <Cart products={products} signedIn={!!me} member={member} /> : <Empty icon={Storefront} title="The store is restocking">Merchandise will appear here when the team adds it.</Empty>}
    </div>
  );
}
