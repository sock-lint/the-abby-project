// Category names identify valid same-name skills without exposing IDs in labels.
export function skillDisplayLabel(skill, choices) {
  const duplicateName = choices.some((choice) =>
    choice.name === skill.name && choice.category_name !== skill.category_name);
  return duplicateName && skill.category_name
    ? `${skill.name} (${skill.category_name})`
    : skill.name;
}
