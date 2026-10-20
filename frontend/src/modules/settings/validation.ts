export function validateSettings(section: string, values: Record<string, unknown>): string {
  if (section === 'general') {
    if (typeof values.system_name !== 'string' || !values.system_name.trim() || values.system_name.length > 100) return '系统名称需要 1–100 个字符。'
    try { Intl.DateTimeFormat('zh-CN', {timeZone:String(values.timezone)}).format() } catch { return '请输入有效的时区，例如 Asia/Shanghai。' }
  }
  const ranges: Record<string,Record<string,[number,number]>> = {
    resources:{max_concurrent_jobs:[1,8],connection_timeout_seconds:[1,60],reconnect_attempts:[0,20]},
    storage:{retention_days:[1,3650],max_upload_mb:[1,102400]}, security:{},
  }
  for (const [key,[min,max]] of Object.entries(ranges[section] ?? {})) {
    const number = values[key]
    if (typeof number !== 'number' || !Number.isInteger(number) || number < min || number > max) return `数值需要为 ${min}–${max} 范围内的整数。`
  }
  if (section === 'security') {
    const networks = values.camera_allowed_networks
    if (!Array.isArray(networks) || networks.some(value => {
      if(typeof value!=='string')return true
      const parts=value.split('/');if(parts.length!==2||!/^\d+$/.test(parts[1]!))return true
      const address=parts[0]!,prefix=Number(parts[1])
      if(address.includes(':')){
        try{new URL(`http://[${address}]/`);return prefix>128}catch{return true}
      }
      return prefix>32||!/^\d{1,3}(\.\d{1,3}){3}$/.test(address)||address.split('.').some(v=>Number(v)>255)
    })) return '请填写有效的 IPv4 或 IPv6 CIDR 网段，每行一项。'
  }
  return ''
}
