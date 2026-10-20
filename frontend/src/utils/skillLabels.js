// Category names identify valid same-name skills without exposing IDs in labels.
export function skillDisplayLabel(skill, choices) {
  const categoryByName = new Map();
  const duplicateNames = new Set();
  for (const choice of choices) {
    if (categoryByName.has(choice.name) && categoryByName.get(choice.name) !== choice.category_name) {
      duplicateNames.add(choice.name);
    }
    categoryByName.set(choice.name, choice.category_name);
  }
  const label = (choice) => duplicateNames.has(choice.name) && choice.category_name
    ? `${choice.name} (${choice.category_name})`
    : choice.name;
  const labels = choices.map(label);
  // Literal names can imitate the category suffix. Quote and escape both
  // parts, so that fallback cannot create another delimiter-based collision.
  return new Set(labels).size < labels.length
    ? `${JSON.stringify(skill.name)} (${JSON.stringify(skill.category_name)})`
    : label(skill);
}
