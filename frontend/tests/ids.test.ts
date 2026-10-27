import { afterEach, describe, expect, it, vi } from 'vitest'
import { newId } from '../src/shared/ids'
afterEach(()=>vi.unstubAllGlobals())
describe('request ids on appliance HTTP',()=>{
 it('uses the native generator in secure contexts',()=>{const randomUUID=vi.fn(()=> 'native-id');vi.stubGlobal('crypto',{randomUUID});expect(newId()).toBe('native-id');expect(randomUUID).toHaveBeenCalledOnce()})
 it('uses cryptographic v4 bytes when randomUUID is unavailable',()=>{const getRandomValues=vi.fn((a:Uint8Array)=>{a.fill(255);return a});vi.stubGlobal('crypto',{getRandomValues});expect(newId()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');expect(getRandomValues).toHaveBeenCalledOnce()})
 it('generates independent valid UUIDs on HTTP',()=>{const nativeCrypto=crypto;vi.stubGlobal('crypto',{getRandomValues:nativeCrypto.getRandomValues.bind(nativeCrypto)});const values=Array.from({length:100},newId);expect(new Set(values).size).toBe(100);expect(values.every(v=>/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(v))).toBe(true)})
})
