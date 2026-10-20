/** Standard JSON unicode escapes preserve text through local browser/proxy transports. */
export function agentJson(value: unknown): string {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, character => `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`)
}
