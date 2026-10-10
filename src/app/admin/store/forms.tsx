"use client";

import { ActionForm, SubmitButton } from "@/components/ui/action-form";
import { Field, Input, Textarea } from "@/components/ui/field";
import { saveProductAction, setStockAction } from "@/app/actions/staff";
import { paiseToInput } from "@/lib/format";
import type { Product } from "@/lib/types";

export function ProductForm({ product }: { product?: Product }) {
  return (
    <ActionForm action={saveProductAction.bind(null, product?.id ?? null)} reset={!product} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
        <Field label="Name"><Input name="name" required defaultValue={product?.name} /></Field>
        <Field label="Price (rupees)"><Input name="price" inputMode="decimal" required defaultValue={product ? paiseToInput(product.base_price_paise) : ""} /></Field>
      </div>
      <Field label="Description"><Textarea name="description" defaultValue={product?.description} className="min-h-20" /></Field>
      <Field label="Image URL" hint="Optional"><Input name="image_url" type="url" defaultValue={product?.image_url ?? ""} /></Field>
      <label className="flex items-center gap-2.5 text-sm"><input type="checkbox" name="is_active" defaultChecked={product?.is_active ?? true} className="size-4 accent-[var(--accent)]" /> Visible in the store</label>
      <SubmitButton variant={product ? "secondary" : "primary"}>{product ? "Save product" : "Add product"}</SubmitButton>
    </ActionForm>
  );
}

export function StockForm({ productId }: { productId: number }) {
  return (
    <ActionForm action={setStockAction.bind(null, productId)} reset className="mt-5 grid grid-cols-[1fr_1fr_auto] items-end gap-2 border-t border-line pt-5">
      <Field label="Size"><Input name="size" required placeholder="M" maxLength={12} /></Field>
      <Field label="Physical stock"><Input name="physical" type="number" min={0} required placeholder="20" /></Field>
      <SubmitButton variant="secondary">Set stock</SubmitButton>
    </ActionForm>
  );
}
