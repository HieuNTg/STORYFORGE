/**
 * dirty.ts — RHF dirtyFields helpers for delta-only PUT payloads.
 *
 * Security rationale (F4/F5): when sending updates to `PUT /api/config`, the
 * frontend must include ONLY fields the user actually edited. Otherwise the
 * masked echo (`sk-***1234`) returned by `GET /api/config` could be sent back
 * as a "new" value, overwriting the real key with the mask.
 *
 * `react-hook-form`'s `formState.dirtyFields` reports exactly which fields the
 * user touched. We build the PUT body from that intersection.
 */

import type { FieldValues } from "react-hook-form";

type Dirty<T> = Partial<Record<keyof T, unknown>>;

/**
 * Pick fields from `values` whose keys appear (truthy) in `dirtyFields`.
 *
 * `dirtyFields` is RHF's structural map of "what the user typed in". For flat
 * form shapes (no nested objects/arrays) the value at each key is `true | undefined`.
 * We treat any truthy entry as "include this field".
 */
export function pickDirty<TValues extends FieldValues>(
  values: TValues,
  dirtyFields: Dirty<TValues>,
): Partial<TValues> {
  const out: Partial<TValues> = {};
  for (const key of Object.keys(dirtyFields) as Array<keyof TValues>) {
    if (dirtyFields[key]) {
      out[key] = values[key];
    }
  }
  return out;
}
