/** Marks a value that must be sent to Postgres as jsonb (arrays of plain values are sent as text[]). */
export class Json {
  constructor(public value: unknown) {}
}
