export class AppError extends Error {
  constructor(public code: string, message: string) {
    super(message);
    this.name = "AppError";
  }
}

/** Database errors are raised as "CODE|human message". Anything else is an unexpected failure. */
export function toAppError(e: unknown): AppError {
  const raw = e instanceof Error ? e.message : typeof e === "string" ? e : (e as { message?: string })?.message ?? "Unknown error";
  const m = /^([A-Z_]+)\|(.*)$/s.exec(raw.replace(/^error:\s*/i, ""));
  if (m) return new AppError(m[1], m[2].trim());
  if (/violates (check|unique|foreign key)/i.test(raw)) return new AppError("VALIDATION", "That change was not allowed by the database rules.");
  return new AppError("INTERNAL", "Something went wrong on our side. Please try again.");
}
