import type { FixedTemplate } from './api'

// Business choices appear once; retain all raw model/version references for old drafts.
export function uniqueTaskTemplates(items:FixedTemplate[]):FixedTemplate[]{
  const seen=new Set<string>()
  return items.filter(t=>{const key=JSON.stringify([t.target,t.rule]);if(seen.has(key))return false;seen.add(key);return true})
}
export function templateChoiceId(items:FixedTemplate[],selected:FixedTemplate|undefined):string|null{
  return selected?uniqueTaskTemplates(items).find(t=>t.target===selected.target&&t.rule===selected.rule)?.id??null:null
}
