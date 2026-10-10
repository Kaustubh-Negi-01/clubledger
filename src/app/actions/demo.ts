"use server";

import { revalidatePath } from "next/cache";
import { isDemo } from "@/lib/db";
import { demoAdvanceClock } from "@/lib/db/demo";
import { run, type ActionState } from "@/lib/action";
import { rpc } from "@/lib/db";
import { AppError } from "@/lib/db/errors";

/** Preview-mode only: move the database clock forward (or reset it) to demonstrate expiry and term close. */
export async function advanceClockAction(minutes: number | null): Promise<ActionState> {
  return run(async () => {
    if (!isDemo) throw new AppError("VALIDATION", "Time travel only exists in the demo database.");
    const off = demoAdvanceClock(minutes === null ? null : minutes * 60_000);
    await rpc("api_maintenance");
    revalidatePath("/", "layout");
    return off === 0 ? "Clock reset to now" : `Clock is now ${Math.round(off / 60_000)} minutes ahead. Housekeeping ran.`;
  });
}
