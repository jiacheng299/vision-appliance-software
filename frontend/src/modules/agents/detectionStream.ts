export interface DetectionFrame { image: Blob; observedAt: string }
const maximum=2*1024*1024,decoder=new TextDecoder()

export async function* detectionFrames(response:Response,signal:AbortSignal):AsyncGenerator<DetectionFrame> {
  if(!response.ok||!response.body||!response.headers.get('content-type')?.startsWith('multipart/x-mixed-replace'))throw new Error('Detection stream unavailable')
  const reader=response.body.getReader()
  const abort=()=>{void reader.cancel().catch(()=>{})}
  signal.addEventListener('abort',abort,{once:true})
  let buffer=new Uint8Array(0)
  try {
    while(!signal.aborted){
      const {done,value}=await reader.read()
      if(done)return
      if(buffer.length+value.length>maximum+1024)throw new Error('Detection frame too large')
      const next=new Uint8Array(buffer.length+value.length);next.set(buffer);next.set(value,buffer.length);buffer=next
      while(buffer.length){
        let end=-1
        for(let i=0;i<Math.min(buffer.length-3,1024);i++)if(buffer[i]===13&&buffer[i+1]===10&&buffer[i+2]===13&&buffer[i+3]===10){end=i;break}
        if(end<0){if(buffer.length>1024)throw new Error('Invalid detection headers');break}
        const header=decoder.decode(buffer.subarray(0,end))
        const size=Number(/^Content-Length: (\d+)$/mi.exec(header)?.[1])
        const observedAt=/^X-Detection-Observed-At: (.+)$/mi.exec(header)?.[1]?.trim()
        if(!header.startsWith('--vision-frame\r\n')||!/^Content-Type: image\/jpeg$/mi.test(header)||!Number.isInteger(size)||size<1||size>maximum||!observedAt||!Number.isFinite(Date.parse(observedAt)))throw new Error('Invalid detection frame')
        const total=end+4+size+2
        if(buffer.length<total)break
        if(buffer[total-2]!==13||buffer[total-1]!==10)throw new Error('Invalid detection boundary')
        const pixels=buffer.slice(end+4,end+4+size)
        buffer=buffer.slice(total)
        yield {image:new Blob([pixels],{type:'image/jpeg'}),observedAt}
      }
    }
  } finally {
    signal.removeEventListener('abort',abort)
    await reader.cancel().catch(()=>{});reader.releaseLock()
  }
}
