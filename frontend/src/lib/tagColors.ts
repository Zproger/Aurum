/** A tag carries no color of its own (backend/app/models/tag.py) — the tag
 * ranking borrows the color of the category the tag spent the most on, and
 * falls back to this neutral when there's nothing to borrow from. Kept in
 * step with tag_rollup.py's NEUTRAL_COLOR, which is the same grey the
 * category rollup already uses for a category it can't resolve. */
export const NEUTRAL_TAG_COLOR = "#898781";
