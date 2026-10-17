/** Existing title rarity controls presentation, never competition placement. */
export function EditorTitle({ name, rarity }: { name?: string | null; rarity?: string | null }) {
  if (!name) return null;
  const tier = ['ordinary', 'rare', 'epic', 'legendary'].includes(rarity?.toLowerCase() || '') ? rarity!.toLowerCase() : 'ordinary';
  return <span className={`v2-editor-title v2-editor-title--${tier}`} title={`${tier[0].toUpperCase()}${tier.slice(1)} title`}>{name}</span>;
}
