import { describe,expect,it } from 'vitest'
import { detectionFrames } from '../src/modules/agents/detectionStream'
const encode=new TextEncoder()
function part(pixels:string,stamp:string){return `--vision-frame\r\nContent-Type: image/jpeg\r\nContent-Length: ${pixels.length}\r\nX-Detection-Observed-At: ${stamp}\r\n\r\n${pixels}\r\n`}
describe('bounded detection stream parser',()=>{
  it('keeps pixels and their own timestamp together across fragmented and batched chunks',async()=>{
    const wire=encode.encode(part('one','2026-10-30T01:00:00Z')+part('two','2026-10-30T01:00:01Z'))
    const response=new Response(new ReadableStream({start(c){for(let i=0;i<wire.length;i+=17)c.enqueue(wire.slice(i,i+17));c.close()}}),{headers:{'content-type':'multipart/x-mixed-replace; boundary=vision-frame'}})
    const result=[]
    for await(const frame of detectionFrames(response,new AbortController().signal)){
      const text=await new Promise(resolve=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.readAsText(frame.image)})
      result.push([text,frame.observedAt])
    }
    expect(result).toEqual([['one','2026-10-30T01:00:00Z'],['two','2026-10-30T01:00:01Z']])
  })
  it('rejects oversized or invalid headers and cancels the reader',async()=>{
    let canceled=false
    const response=new Response(new ReadableStream({start(c){c.enqueue(encode.encode('--vision-frame\r\nContent-Type: image/jpeg\r\nContent-Length: 999999999\r\n\r\n'))},cancel(){canceled=true}}),{headers:{'content-type':'multipart/x-mixed-replace'}})
    const consume=async()=>{for await(const _ of detectionFrames(response,new AbortController().signal)){/* empty */}}
    await expect(consume()).rejects.toThrow('Invalid detection frame')
    expect(canceled).toBe(true)
  })
})
