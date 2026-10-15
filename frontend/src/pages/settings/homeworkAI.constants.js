// Suggested API model IDs verified against provider documentation. Availability
// depends on the family's provider account; custom IDs remain supported.
export const HOMEWORK_AI_PROVIDERS = [
  { id: 'openai', name: 'OpenAI (ChatGPT)' },
  { id: 'anthropic', name: 'Anthropic (Claude)' },
];

export const HOMEWORK_AI_MODELS = {
  openai: [
    { id: 'gpt-5.4-mini', name: 'GPT-5.4 mini' },
    { id: 'gpt-5.6-terra', name: 'GPT-5.6 Terra' },
  ],
  anthropic: [
    { id: 'claude-haiku-5-5', name: 'Claude Haiku 5.5' },
    { id: 'claude-sonnet-5-5', name: 'Claude Sonnet 5.5' },
  ],
};
