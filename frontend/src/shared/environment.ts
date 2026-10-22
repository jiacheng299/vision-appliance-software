import { ref } from 'vue'
import { client } from './api/client'
import type { components } from './api/generated'
export const environment = ref<components['schemas']['EnvironmentDTO'] | null>(null)
export async function loadEnvironment() {
  try { environment.value = (await client.get<components['schemas']['EnvironmentDTO']>('/agent-environment')).data }
  catch { environment.value = null }
}
