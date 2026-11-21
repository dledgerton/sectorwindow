// NTEE major sector codes and their plain-English names, shared by the filter bar,
// Sector Pulse and the results table so a letter is never shown without a way to read it.
export const NTEE_OPTIONS: { code: string; label: string }[] = [
  { code: "A", label: "Arts, Culture & Humanities" },
  { code: "B", label: "Education" },
  { code: "C", label: "Environment" },
  { code: "E", label: "Health Care" },
  { code: "F", label: "Mental Health & Crisis Intervention" },
  { code: "G", label: "Disease & Disorder Research" },
  { code: "H", label: "Medical Research" },
  { code: "I", label: "Crime & Legal Services" },
  { code: "J", label: "Employment" },
  { code: "K", label: "Food, Agriculture & Nutrition" },
  { code: "L", label: "Housing & Shelter" },
  { code: "M", label: "Public Safety & Disaster Relief" },
  { code: "N", label: "Recreation & Sports" },
  { code: "O", label: "Youth Development" },
  { code: "P", label: "Human Services" },
  { code: "Q", label: "International & Foreign Affairs" },
  { code: "R", label: "Civil Rights & Advocacy" },
  { code: "S", label: "Community Improvement" },
  { code: "T", label: "Philanthropy & Voluntarism" },
  { code: "U", label: "Science & Technology" },
  { code: "W", label: "Public & Societal Benefit" },
  { code: "X", label: "Religion" },
  { code: "Y", label: "Mutual Benefit" },
]

/** Name for a sector letter or a full NTEE code (only the first letter matters). */
export function nteeLabel(code: string | null | undefined): string | undefined {
  if (!code) return undefined
  const letter = code.trim().charAt(0).toUpperCase()
  return NTEE_OPTIONS.find((n) => n.code === letter)?.label
}
