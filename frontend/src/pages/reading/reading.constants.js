export const BOOK_STATUSES = [
  ['reading', 'Reading'], ['want_to_read', 'Want to read'], ['finished', 'Finished'], ['paused', 'Paused'],
];
export const READING_INTERESTS = ['adventure', 'fantasy', 'mystery', 'animals', 'friendship', 'science', 'history', 'humor'];
export const REACTIONS = [['', 'Choose a reaction'], ['loved', 'Loved it'], ['liked', 'Liked it'], ['okay', 'It was okay'], ['not_for_me', 'Not for me']];
export const REFLECTION_PROMPTS = ['What surprised you?', 'What do you think happens next?', 'Who would you like to meet?', 'What did you learn?'];
export const labelFor = (value) => value ? value.charAt(0).toUpperCase() + value.slice(1).replaceAll('_', ' ') : '';
