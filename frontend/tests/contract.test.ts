import {describe,it,expect} from 'vitest'
import {validateSettings} from '../src/modules/settings/validation'
import {humanError} from '../src/shared/api/client'
describe('effective backend validation',()=>{
  it('allows the backend default IPv6 loopback CIDR and rejects malformed ranges',()=>{
    expect(validateSettings('security',{camera_allowed_networks:['127.0.0.0/8','::1/128']})).toBe('')
    expect(validateSettings('security',{camera_allowed_networks:['999.1.1.1/99']})).not.toBe('')
  })
  it('applies the supported resource budget before saving',()=>{
    expect(validateSettings('resources',{max_concurrent_jobs:9,connection_timeout_seconds:30,reconnect_attempts:3})).not.toBe('')
    expect(validateSettings('resources',{max_concurrent_jobs:2,connection_timeout_seconds:61,reconnect_attempts:3})).not.toBe('')
  })
  it('recognizes lowercase server error codes without exposing raw error text',()=>{
    expect(humanError({response:{status:403,data:{error:{code:'cross_origin_forbidden',message:'secret'}}}})).toContain('请求来源')
    expect(humanError({response:{status:422,data:{error:{code:'camera_address_forbidden'}}}})).toContain('网段')
  })
})
