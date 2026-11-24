"""Build the MP91 route / speed / parking dashboard (single self-contained HTML).

Usage (from the repo root):
    aws s3 sync s3://iap-dev-lake-313092058964/raw/mp91/ data/mp91_samples/ --region ca-central-1
    python scripts/build_mp91_dashboard.py
    start dashboard/mp91_dashboard.html

Reads bronze JSONL from data/mp91_samples, runs the H02 parser + gold logic,
and writes dashboard/mp91_dashboard.html with the data embedded. Nothing is
published — the file contains your home/parking locations, keep it local.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from edge.h02_parser import parse_bronze_event  # noqa: E402
from edge.mp91_gold import build  # noqa: E402

TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>MP91 Tracking</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 *{box-sizing:border-box} body{margin:0;font:13px Segoe UI,Arial,sans-serif;color:#333;height:100vh;display:grid;grid-template-columns:300px 1fr;grid-template-rows:38px 1fr 190px}
 #top{grid-column:1/3;background:#fafafa;border-bottom:1px solid #ddd;display:flex;align-items:center;padding:0 12px;gap:16px}
 #top b{font-size:14px} #top .sp{flex:1}
 #left{grid-row:2/4;border-right:1px solid #ddd;display:flex;flex-direction:column;overflow:hidden}
 .tabs{display:flex;border-bottom:1px solid #ddd} .tabs div{padding:8px 12px;cursor:pointer} .tabs .on{border-bottom:2px solid #2b7cd3;color:#2b7cd3}
 .pane{display:none;overflow:auto;flex:1} .pane.on{display:block}
 .obj{display:flex;align-items:center;gap:8px;padding:8px;border-bottom:1px solid #eee}
 .obj .nm{font-weight:600} .obj small{color:#888;display:block}
 .dot{width:10px;height:10px;border-radius:50%}
 .form{padding:8px;display:grid;grid-template-columns:80px 1fr;gap:6px;align-items:center;border-bottom:1px solid #ddd}
 .form input,.form select{padding:3px;border:1px solid #ccc}
 table{width:100%;border-collapse:collapse} th{background:#f3f3f3;font-weight:600;text-align:left;padding:5px 8px;position:sticky;top:0}
 td{padding:4px 8px;border-bottom:1px solid #f0f0f0;cursor:pointer} tr:hover td{background:#eef5fd} tr.sel td{background:#d6e8fb}
 .ic{display:inline-block;width:16px;height:16px;border-radius:3px;color:#fff;font-size:10px;text-align:center;line-height:16px;margin-right:6px;font-weight:700}
 .P{background:#2b7cd3}.D{background:#d33}
 #map{grid-column:2}
 #bottom{grid-column:2;border-top:1px solid #ddd;display:flex;flex-direction:column}
 #ctrl{display:flex;align-items:center;gap:6px;padding:4px 8px;border-bottom:1px solid #eee}
 #ctrl button{border:1px solid #ccc;background:#fff;padding:2px 8px;cursor:pointer}
 #ctrl span{color:#666}
 #g{flex:1;width:100%}
 .pin{background:#2b7cd3;color:#fff;font-weight:700;border-radius:4px;text-align:center;line-height:20px;border:1px solid #fff;box-shadow:0 0 2px #000}
</style></head><body>
<div id="top"><b>MP91 Tracking</b><span>Device __DEVICE__</span><span class="sp"></span><span id="now"></span></div>
<div id="left">
 <div class="tabs"><div data-t="objects" class="on">Objects</div><div data-t="history">History</div></div>
 <div class="pane on" id="objects"></div>
 <div class="pane" id="history">
  <div class="form"><label>Date</label><select id="day"></select>
   <label>Stops</label><select id="minstop"><option value="1">&gt; 1 min</option><option value="5">&gt; 5 min</option><option value="15">&gt; 15 min</option></select></div>
  <table><thead><tr><th>Time</th><th>Information</th></tr></thead><tbody id="hist"></tbody></table>
 </div>
</div>
<div id="map"></div>
<div id="bottom">
 <div id="ctrl"><b>Speed</b>
  <button id="play">&#9654;</button><button id="pause">&#10074;&#10074;</button><button id="stop">&#9632;</button>
  <select id="rate"><option>1</option><option selected>10</option><option>30</option><option>60</option></select><span>x</span>
  <span id="info"></span></div>
 <canvas id="g"></canvas>
</div>
<script>
const G=__DATA__, TZ='America/Toronto';
const tm=s=>new Date(s).toLocaleTimeString('en-CA',{timeZone:TZ,hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
const dt=s=>new Date(s).toLocaleDateString('en-CA',{timeZone:TZ});
const dur=m=>{if(m==null)return 'ongoing';const s=Math.round(m*60),h=Math.floor(s/3600),mi=Math.floor(s%3600/60),se=s%60;return (h?h+' h ':'')+(mi?mi+' min ':'')+(h?'':se+' s')};

document.querySelectorAll('.tabs div').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tabs div,.pane').forEach(e=>e.classList.remove('on'));t.classList.add('on');document.getElementById(t.dataset.t).classList.add('on')});

const map=L.map('map',{zoomControl:true});
// Basemap. Opening this file from disk (file://) sends no Referer, which OSM and
// CARTO now reject. Esri World Street Map serves tiles without a key/Referer.
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors'}).addTo(map);
let layer=L.layerGroup().addTo(map), car=null, pts=[];
const c=G.current;
if(c){
 document.getElementById('objects').innerHTML=`<div class="obj"><span class="dot" style="background:${c.acc_on?'#2a2':'#999'}"></span>
 <div style="flex:1"><div class="nm">MP91-${G.device_id.slice(-4)}</div><small>${dt(c.fix_time)} ${tm(c.fix_time)}</small></div><div>${Math.round(c.speed_kmh)} kph</div></div>`;
 document.getElementById('now').textContent=(c.acc_on?'Moving':'Parked')+' · last update '+dt(c.fix_time)+' '+tm(c.fix_time);
}
const days=[...new Set([...G.trips.map(t=>dt(t.start)),...G.parking.map(p=>dt(p.start))])].sort().reverse();
const sel=document.getElementById('day'); days.forEach(d=>sel.add(new Option(d,d)));
sel.onchange=render; document.getElementById('minstop').onchange=render;
document.querySelector('.obj')?.addEventListener('click',()=>c&&map.setView([c.lat,c.lon],16));

function render(){
 const d=sel.value, min=+document.getElementById('minstop').value;
 layer.clearLayers(); stop();
 const trips=G.trips.filter(t=>dt(t.start)===d);
 const parks=G.parking.filter(p=>(dt(p.start)===d||(p.end&&dt(p.end)===d)||(!p.end&&dt(p.start)<=d)) && (p.duration_min==null||p.duration_min>=min));
 pts=trips.flatMap(t=>t.points);
 const b=[];
 trips.forEach(t=>{const ll=t.points.map(q=>[q[0],q[1]]);L.polyline(ll,{color:'#e00',weight:3}).addTo(layer);b.push(...ll)});
 if(trips.length){const f=trips[0],l=trips[trips.length-1];
  L.circleMarker([f.start_lat,f.start_lon],{radius:7,color:'#fff',fillColor:'#2a2',fillOpacity:1,weight:2}).bindTooltip('Start '+tm(f.start)).addTo(layer);
  L.circleMarker([l.end_lat,l.end_lon],{radius:7,color:'#fff',fillColor:'#d33',fillOpacity:1,weight:2}).bindTooltip('End '+tm(l.end)).addTo(layer);}
 const pm={};
 parks.forEach(p=>{const m=L.marker([p.lat,p.lon],{icon:L.divIcon({className:'',html:'<div class="pin">P</div>',iconSize:[20,20]})})
  .bindPopup(`<b>Parking</b><br>Arrived: ${dt(p.start)} ${tm(p.start)}<br>Left: ${p.end?dt(p.end)+' '+tm(p.end):'still parked'}<br>Duration: ${dur(p.duration_min)}`).addTo(layer);pm[p.start]=m;b.push([p.lat,p.lon])});
 if(b.length)map.fitBounds(b,{padding:[30,30]});
 // history list: parking + drive entries in time order
 const ev=[...parks.map(p=>({t:p.start,k:'P',txt:dur(p.duration_min),go:()=>{map.setView([p.lat,p.lon],17);pm[p.start].openPopup()}})),
  ...trips.map(t=>({t:t.start,k:'D',txt:`${dur(t.duration_min)} · ${t.distance_km} km · max ${Math.round(t.max_speed_kmh)} kph`,go:()=>map.fitBounds(t.points.map(q=>[q[0],q[1]]),{padding:[30,30]})}))]
  .sort((a,b)=>a.t<b.t?-1:1);
 const hb=document.getElementById('hist');hb.innerHTML='';
 ev.forEach(e=>{const r=hb.insertRow();r.innerHTML=`<td><span class="ic ${e.k}">${e.k}</span>${dt(e.t)===d?tm(e.t):dt(e.t)+' '+tm(e.t)}</td><td>${e.txt}</td>`;
  r.onclick=()=>{[...hb.rows].forEach(x=>x.classList.remove('sel'));r.classList.add('sel');e.go()}});
 const km=trips.reduce((s,t)=>s+t.distance_km,0);
 document.getElementById('info').textContent=`${trips.length} trips · ${km.toFixed(1)} km · max ${Math.round(Math.max(0,...trips.map(t=>t.max_speed_kmh)))} kph`;
 drawGraph(d,-1);
}

// speed graph: full day 00:00-24:00 local
const cv=document.getElementById('g');
function dayStart(d){return new Date(new Date(d+'T00:00:00').toLocaleString('en-US',{timeZone:'UTC'}))}
function drawGraph(d,cur){
 const w=cv.width=cv.clientWidth,h=cv.height=cv.clientHeight,x=cv.getContext('2d');
 const L0=40,B=18,top=6,max=Math.max(75,...pts.map(p=>p[2]));
 const t0=+new Date(new Date(d+'T00:00:00-05:00')),span=864e5;
 const X=t=>L0+(new Date(t)-t0)/span*(w-L0-8),Y=v=>h-B-v/max*(h-B-top);
 x.font='10px Segoe UI';x.fillStyle='#888';x.strokeStyle='#eee';
 for(let v=0;v<=max;v+=25){x.beginPath();x.moveTo(L0,Y(v));x.lineTo(w,Y(v));x.stroke();x.fillText(v+' kph',2,Y(v)+3)}
 for(let hr=0;hr<=24;hr+=2){const xx=L0+hr/24*(w-L0-8);x.fillText(String(hr).padStart(2,'0')+':00',xx-12,h-4)}
 x.fillStyle='rgba(43,124,211,.35)';x.strokeStyle='#2b7cd3';
 G.trips.filter(t=>dt(t.start)===d).forEach(t=>{const p=t.points;x.beginPath();x.moveTo(X(p[0][3]),Y(0));p.forEach(q=>x.lineTo(X(q[3]),Y(q[2])));x.lineTo(X(p[p.length-1][3]),Y(0));x.closePath();x.fill();x.stroke()});
 if(cur>=0&&pts[cur]){x.strokeStyle='#d33';x.beginPath();x.moveTo(X(pts[cur][3]),top);x.lineTo(X(pts[cur][3]),h-B);x.stroke()}
 cv.onclick=e=>{const r=cv.getBoundingClientRect(),t=t0+(e.clientX-r.left-L0)/(w-L0-8)*span;
  let bi=-1,bd=1e18;pts.forEach((p,i)=>{const dd=Math.abs(new Date(p[3])-t);if(dd<bd){bd=dd;bi=i}});if(bi>=0&&bd<6e5){idx=bi;show()}};
}
// playback
let idx=0,timer=null;
function show(){const p=pts[idx];if(!p)return;
 if(!car)car=L.circleMarker([p[0],p[1]],{radius:8,color:'#fff',fillColor:'#f80',fillOpacity:1,weight:2}).addTo(map);
 car.setLatLng([p[0],p[1]]).bindTooltip(`${tm(p[3])} · ${Math.round(p[2])} kph`,{permanent:true,direction:'top'}).openTooltip();
 map.panTo([p[0],p[1]],{animate:false});drawGraph(sel.value,idx)}
function play(){if(!pts.length)return;clearInterval(timer);timer=setInterval(()=>{
 const r=+document.getElementById('rate').value;if(++idx>=pts.length){pause();return}
 show()},Math.max(30,1000/r*5))}
function pause(){clearInterval(timer);timer=null}
function stop(){pause();idx=0;if(car){map.removeLayer(car);car=null}}
document.getElementById('play').onclick=()=>{if(!car)idx=0;show();play()};
document.getElementById('pause').onclick=pause;
document.getElementById('stop').onclick=()=>{stop();drawGraph(sel.value,-1)};
window.onresize=()=>drawGraph(sel.value,idx);
render();
</script></body></html>"""


def main():
    src = os.path.join(ROOT, "data", "mp91_samples")
    records = []
    for f in sorted(glob.glob(os.path.join(src, "**", "*.jsonl"), recursive=True)):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    records += parse_bronze_event(json.loads(line))[0]
    gold = build(records)
    out = os.path.join(ROOT, "dashboard", "mp91_dashboard.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(gold)).replace("__DEVICE__", gold["device_id"])
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    t = gold["totals"]
    print(f"{len(records)} records -> {t['trips']} trips, {t['distance_km']} km, {len(gold['parking'])} parking periods")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
