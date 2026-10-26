export type Point = [number, number]
export const POINT_SNAP_PX = 10
export function nearPoint(a: Point, b: Point, width: number, height: number): boolean {
  return Math.hypot((a[0]-b[0])*width,(a[1]-b[1])*height) <= POINT_SNAP_PX
}
const cross=(a:Point,b:Point,c:Point)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
const onSegment=(a:Point,b:Point,p:Point)=>Math.abs(cross(a,b,p))<1e-10&&p[0]>=Math.min(a[0],b[0])-1e-10&&p[0]<=Math.max(a[0],b[0])+1e-10&&p[1]>=Math.min(a[1],b[1])-1e-10&&p[1]<=Math.max(a[1],b[1])+1e-10
function intersects(a:Point,b:Point,c:Point,d:Point){
  return (cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0)||onSegment(a,b,c)||onSegment(a,b,d)||onSegment(c,d,a)||onSegment(c,d,b)
}
/** Stored polygons omit the repeated first point; the last edge closes implicitly. */
export function regionError(points:Point[]):string {
  if(points.length<3)return '至少需要三个不同的边界点，才能围成封闭区域。'
  if(points.length>64)return '一个区域最多支持64个边界点。'
  if(points.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v)||v<0||v>1)))return '边界点必须在画面范围内。'
  if(new Set(points.map(p=>p.join(','))).size!==points.length)return '区域存在重复边界点，请撤销后重新绘制。'
  const n=points.length
  for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){
    if(j===i+1||(i===0&&j===n-1))continue
    if(intersects(points[i]!,points[(i+1)%n]!,points[j]!,points[(j+1)%n]!))return '区域边界不能交叉或重叠，请撤销后重新绘制。'
  }
  const area=points.reduce((sum,p,i)=>sum+p[0]*points[(i+1)%n]![1]-points[(i+1)%n]![0]*p[1],0)
  if(Math.abs(area)<1e-10)return '这些点没有围成有效面积，请重新绘制区域。'
  for(let i=0;i<n;i++){
    const a=points[(i+n-1)%n]!,b=points[i]!,c=points[(i+1)%n]!
    if(Math.abs(cross(a,b,c))<1e-10&&(a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])>0)return '相邻边不能折返重叠，请撤销后重新绘制。'
  }
  return ''
}
