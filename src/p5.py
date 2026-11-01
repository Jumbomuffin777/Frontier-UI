
_HTML += r'''<script nonce="__NONCE__">
(function(){
"use strict";
var I=window.IUI;
var h=I.h,txt=I.txt,arr=I.arr,md=I.md,photo=I.photo,scroller=I.scroller,label=I.label,icon=I.icon,SVG=I.SVG;
var MAPS=[];/* registry: {places, select(name)} */
function findPlace(name){name=String(name||'').toLowerCase().trim();if(!name)return null;for(var i=0;i<MAPS.length;i++){var m=MAPS[i];for(var j=0;j<m.places.length;j++){var p=m.places[j];var n=String(p.name||'').toLowerCase();if(n===name||n.indexOf(name)>=0||name.indexOf(n)>=0)return {map:m,idx:j};}}return null;}
/* ---------- maplibre loader ---------- */
var libP=null;
function loadLib(){if(window.maplibregl)return Promise.resolve(window.maplibregl);if(libP)return libP;libP=new Promise(function(res,rej){var s=document.createElement('script');s.src=I.CDN+'/dist/maplibre-gl.js';s.nonce=I.NONCE;s.onload=function(){window.maplibregl?res(window.maplibregl):rej(new Error('maplibre missing'));};s.onerror=rej;document.head.appendChild(s);});return libP;}
var PAL={light:{bg:'#f4f2f0',green:'#bce9b0',park:'#b7e7aa',campus:'#ede8d7',water:'#a2dff5',waterway:'#91d6ef',building:'#e9e6e2',street:'#d6d9df',road:'#b9c0cc',ferry:'#89cfe9',label:'#50545a',minor:'#687078',halo:'#ffffff'},
 dark:{bg:'#1c1d1f',green:'#1f2b22',park:'#20301f',campus:'#26241f',water:'#1d3540',waterway:'#23414d',building:'#28292b',street:'#36393e',road:'#4b5058',ferry:'#2b5566',label:'#b4b9bf',minor:'#8d939a',halo:'#1c1d1f'}};
function vstyle(dark){var c=dark?PAL.dark:PAL.light;var name=['coalesce',['get','name_en'],['get','name']];
 return {version:8,glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
 sources:{p:{type:'vector',url:'https://tiles.openfreemap.org/planet',attribution:'© OpenFreeMap © OpenMapTiles © OpenStreetMap'}},
 layers:[{id:'bg',type:'background',paint:{'background-color':c.bg}},
 {id:'lc',type:'fill',source:'p','source-layer':'landcover',filter:['in','class','wood','grass'],paint:{'fill-color':c.green,'fill-opacity':.8}},
 {id:'park',type:'fill',source:'p','source-layer':'park',paint:{'fill-color':c.park}},
 {id:'lu',type:'fill',source:'p','source-layer':'landuse',filter:['in','class','school','university','hospital'],paint:{'fill-color':c.campus}},
 {id:'water',type:'fill',source:'p','source-layer':'water',paint:{'fill-color':c.water}},
 {id:'ww',type:'line',source:'p','source-layer':'waterway',paint:{'line-color':c.waterway,'line-width':1}},
 {id:'bld',type:'fill',minzoom:14,source:'p','source-layer':'building',paint:{'fill-color':c.building}},
 {id:'st',type:'line',source:'p','source-layer':'transportation',filter:['!in','class','rail','transit','ferry','motorway','trunk','primary'],layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':c.street,'line-width':['interpolate',['linear'],['zoom'],9,.3,12,1.5,14,2.8,17,8]}},
 {id:'rd',type:'line',source:'p','source-layer':'transportation',filter:['in','class','motorway','trunk','primary'],layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':c.road,'line-width':['interpolate',['linear'],['zoom'],9,.7,12,3,14,5,17,12]}},
 {id:'fe',type:'line',source:'p','source-layer':'transportation',filter:['==','class','ferry'],paint:{'line-color':c.ferry,'line-width':.8}},
 {id:'nb',type:'symbol',source:'p','source-layer':'place',minzoom:10,maxzoom:15,filter:['in','class','suburb','quarter','neighbourhood'],layout:{'text-field':name,'text-font':['Noto Sans Regular'],'text-size':10,'text-letter-spacing':.08,'text-transform':'uppercase','text-max-width':8},paint:{'text-color':c.minor,'text-halo-color':c.halo,'text-halo-width':1.2}},
 {id:'city',type:'symbol',source:'p','source-layer':'place',minzoom:5,maxzoom:13,filter:['in','class','city','town'],layout:{'text-field':name,'text-font':['Noto Sans Regular'],'text-size':14,'text-max-width':8},paint:{'text-color':c.label,'text-halo-color':c.halo,'text-halo-width':1.5}}]};}
function rstyle(dark){return {version:8,sources:{r:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/'+(dark?'Canvas/World_Dark_Gray_Base':'World_Street_Map')+'/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:19,attribution:'Tiles © Esri · © OpenStreetMap'}},layers:[{id:'r',type:'raster',source:'r'}]};}
function fmtKm(km){return km<10?km.toFixed(1)+' km':Math.round(km)+' km';}
function fmtMin(m){m=Math.round(m);return m<60?m+' min':Math.floor(m/60)+' h '+(m%60?m%60+' min':'');}
function mapBlock(b){
 var places=arr(b.places).filter(function(p){return p&&p.lat!=null&&p.lng!=null&&isFinite(p.lat)&&isFinite(p.lng);});
 var wrap=h('div','blk');if(b.title)wrap.appendChild(label(b.title));
 if(!places.length){var l=h('div','maplist');arr(b.places).forEach(function(p){l.appendChild(txt('span','tag',(p.icon?p.icon+' ':'')+(p.name||'')));});wrap.appendChild(l);return wrap;}
 var base=Math.min(560,Math.max(240,+b.height||380));var box=h('div','mapbox');box.style.height=base+'px';wrap.appendChild(box);
 var groups=[];places.forEach(function(p){if(p.group&&groups.indexOf(p.group)<0)groups.push(p.group);});
 var ctlL=h('div','mctl l'),ctlR=h('div','mctl r');box.appendChild(ctlL);box.appendChild(ctlR);
 var sel=null;if(groups.length>1){sel=document.createElement('select');sel.className='mbtn';var o=document.createElement('option');o.value='';o.textContent='All groups';sel.appendChild(o);groups.forEach(function(g){var oo=document.createElement('option');oo.value=g;oo.textContent=g;sel.appendChild(oo);});ctlL.appendChild(sel);}
 var bFit=h('button','mbtn ic',[icon('nav')]);bFit.title='Fit all places';ctlL.appendChild(bFit);
 var bExp=h('button','mbtn',[icon('exp'),txt('span','','Expand')]);ctlR.appendChild(bExp);
 var pop=h('div','mpop');box.appendChild(pop);
 var rg=b.route_geo;if(rg&&rg.km){box.appendChild(txt('div','mstat',(rg.mode==='walk'?'🚶 ':'🚗 ')+fmtKm(rg.km)+' · '+fmtMin(rg.min)+(rg.mode==='walk'?' walking':' by car')+' · '+places.length+' stops'));}
 var reg={places:places,select:function(){}};MAPS.push(reg);
 loadLib().then(function(lib){
  var dark=I.isDark();var usedRaster=false;
  var map=new lib.Map({container:box,style:vstyle(dark),attributionControl:{compact:true},dragRotate:false,pitchWithRotate:false,cooperativeGestures:false,fadeDuration:150});
  map.scrollZoom.disable();box.addEventListener('wheel',function(e){if(e.ctrlKey||e.metaKey){map.scrollZoom.enable();}else{map.scrollZoom.disable();}},{passive:true});
  var failT=setTimeout(function(){if(!map.isStyleLoaded()&&!usedRaster){usedRaster=true;map.setStyle(rstyle(I.isDark()));}},7000);
  map.on('error',function(){if(!usedRaster&&!map.isStyleLoaded()){usedRaster=true;map.setStyle(rstyle(I.isDark()));}});
  var line=(rg&&rg.line&&rg.line.length>1)?rg.line:(b.route?places.map(function(p){return [p.lat,p.lng];}):null);
  function addRoute(){if(!line||map.getSource('route'))return;var gj={type:'Feature',geometry:{type:'LineString',coordinates:line.map(function(c){return [c[1],c[0]];})}};
   map.addSource('route',{type:'geojson',data:gj});
   map.addLayer({id:'route-case',type:'line',source:'route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':getComputedStyle(document.documentElement).getPropertyValue('--routecase').trim()||'#fff','line-width':7,'line-opacity':.95}});
   map.addLayer({id:'route',type:'line',source:'route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':getComputedStyle(document.documentElement).getPropertyValue('--route').trim()||'#111','line-width':3.6,'line-dasharray':(rg&&rg.line)?[1,0]:[1.5,1.5]}});}
  map.on('styledata',function(){if(map.isStyleLoaded()){clearTimeout(failT);addRoute();}});
  map.on('load',addRoute);
  var mk=[];
  places.forEach(function(p,i){var el=h('div','pin');var dot=txt('div','dot',p.icon||String(i+1));var lab=txt('div','lab',p.name||'');el.appendChild(dot);el.appendChild(lab);
   el.addEventListener('click',function(e){e.stopPropagation();choose(i,true);});
   var m=new lib.Marker({element:el,anchor:'top',offset:[0,-15]}).setLngLat([p.lng,p.lat]).addTo(map);mk.push({m:m,el:el,p:p});});
  function bounds(list){var bb=new lib.LngLatBounds();list.forEach(function(p){bb.extend([p.lng,p.lat]);});if(line&&!(sel&&sel.value))line.forEach(function(c){bb.extend([c[1],c[0]]);});return bb;}
  function fit(list,anim){if(!list.length)return;if(list.length===1){map.jumpTo({center:[list[0].lng,list[0].lat],zoom:14});return;}map.fitBounds(bounds(list),{padding:{top:56,bottom:48,left:44,right:44},maxZoom:15,duration:anim?600:0});}
  fit(places,false);
  var cur=-1;
  /* label decluttering: greedily hide labels that would overlap an earlier (or the selected) one */
  function declutter(){var placed=[];var order=mk.map(function(o,j){return j;});if(cur>=0){order.splice(order.indexOf(cur),1);order.unshift(cur);}
   order.forEach(function(j){var o=mk[j];var pt=map.project([o.p.lng,o.p.lat]);var w=Math.min(220,(o.p.name||'').length*6.6+8);var r={x0:pt.x-w/2,x1:pt.x+w/2,y0:pt.y+2,y1:pt.y+20};var dot={x0:pt.x-15,x1:pt.x+15,y0:pt.y-15,y1:pt.y+15};
    var hit=placed.some(function(q){return !(r.x1<q.x0||r.x0>q.x1||r.y1<q.y0||r.y0>q.y1);});
    o.el.querySelector('.lab').style.visibility=hit?'hidden':'visible';placed.push(dot);if(!hit)placed.push(r);});}
  map.on('moveend',declutter);map.once('idle',declutter);setTimeout(declutter,50);
  function choose(i,fly){cur=i;mk.forEach(function(o,j){o.el.classList.toggle('sel',j===i);});var p=places[i];
   pop.innerHTML='';pop.appendChild(txt('b','',(p.icon?p.icon+'  ':'')+(p.name||'')));var meta=[p.time,p.note].filter(Boolean).join(' · ');if(meta)pop.appendChild(txt('span','',meta));pop.style.display='block';
   if(fly)map.easeTo({center:[p.lng,p.lat],zoom:Math.max(map.getZoom(),14),duration:600});
   declutter();document.dispatchEvent(new CustomEvent('iui-place',{detail:{name:p.name}}));}
  reg.select=function(i){choose(i,true);box.scrollIntoView({block:'nearest',behavior:'smooth'});};
  map.on('click',function(){cur=-1;pop.style.display='none';mk.forEach(function(o){o.el.classList.remove('sel');});});
  bFit.onclick=function(){fit(sel&&sel.value?places.filter(function(p){return p.group===sel.value;}):places,true);};
  if(sel)sel.onchange=function(){var g=sel.value;mk.forEach(function(o){o.el.classList.toggle('dim',!!g&&o.p.group!==g);});fit(g?places.filter(function(p){return p.group===g;}):places,true);};
  var big=false;bExp.onclick=function(){big=!big;box.style.height=(big?Math.max(560,Math.round(base*1.7)):base)+'px';bExp.innerHTML='';bExp.appendChild(icon(big?'col':'exp'));bExp.appendChild(txt('span','',big?'Collapse':'Expand'));setTimeout(function(){map.resize();fit(places,true);},380);};
  document.addEventListener('iui-theme',function(){usedRaster=false;map.setStyle(vstyle(I.isDark()));});
  new ResizeObserver(function(){map.resize();}).observe(box);
 }).catch(function(){box.style.height='auto';box.style.padding='12px';var l=h('div','maplist');places.forEach(function(p,i){l.appendChild(txt('span','tag',(p.icon||(i+1)+'.')+' '+p.name));});box.appendChild(l);});
 return wrap;}
/* ---------- other blocks ---------- */
function images(b){var it=arr(b.items).slice(0,9);var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','gal'+(it.length>3?' scroll':' n'+it.length));
 it.forEach(function(x){g.appendChild(photo(x,'',{bookmark:true,caption:true,zoom:true}));});w.appendChild(it.length>3?scroller(g):g);return w;}
function stars(r){r=+r;if(!isFinite(r))return null;var s=h('span','');s.appendChild(txt('span','star','★ '));s.appendChild(document.createTextNode(r.toFixed(1)));return s;}
function places(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var row=h('div','cards');
 arr(b.items).forEach(function(it){if(!it)return;var c=h('div','card'+(it.url?' link':''));c.appendChild(photo(it,'',{noText:true}));var cb=h('div','cb');cb.appendChild(txt('div','nm',it.name||it.title||''));
  var meta=h('div','meta');var bits=[];var st=stars(it.rating);if(st)bits.push(st);[it.price,it.subtitle].forEach(function(x){if(x)bits.push(document.createTextNode(String(x)));});
  bits.forEach(function(x,i){if(i)meta.appendChild(document.createTextNode(' · '));meta.appendChild(x);});if(bits.length)cb.appendChild(meta);
  if(it.description)cb.appendChild(txt('div','ds',it.description));
  var tg=arr(it.tags).slice(0,3);if(tg.length){var t=h('div','tags');tg.forEach(function(x){t.appendChild(txt('span','tag',x));});cb.appendChild(t);}
  c.appendChild(cb);if(it.url)c.addEventListener('click',function(){I.openLink(it.url);});
  c.addEventListener('mouseenter',function(){var f=findPlace(it.name);if(f)f.map.select&&0;});
  row.appendChild(c);});
 w.appendChild(scroller(row));return w;}
function timeline(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var tl=h('div','tl');
 arr(b.items).forEach(function(it){if(!it)return;var f=findPlace(it.place||it.title);var row=h('div','ti'+(f?' go':''));row.appendChild(txt('div','tm',it.time||''));var rail=h('div','rail',[h('div','bul')]);row.appendChild(rail);
  var body=h('div','tbody');if(it.candidates&&it.candidates.length){var th=h('div','thumb');th.appendChild(photo(it,'',{noText:true}));body.appendChild(th);}
  var tx=h('div','');tx.appendChild(txt('div','tt',it.title||''));if(it.detail)tx.appendChild(txt('div','td',it.detail));body.appendChild(tx);row.appendChild(body);
  if(f){row.addEventListener('click',function(){f.map.select(f.idx);});row.dataset.place=String(f.map.places[f.idx].name||'').toLowerCase();}
  tl.appendChild(row);});
 document.addEventListener('iui-place',function(e){var n=String(e.detail.name||'').toLowerCase();tl.querySelectorAll('.ti').forEach(function(r){r.classList.toggle('hl',!!n&&r.dataset.place===n);});});
 w.appendChild(tl);return w;}
function table(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var t=h('table');var th=h('thead'),tr=h('tr');arr(b.columns).forEach(function(c){tr.appendChild(txt('th','',c));});th.appendChild(tr);t.appendChild(th);
 var tb=h('tbody');arr(b.rows).forEach(function(r){var row=h('tr');arr(r).forEach(function(c){var td=h('td');td.appendChild(md(c).firstChild||document.createTextNode(''));if(td.firstChild&&td.firstChild.tagName==='P'){td.innerHTML=td.firstChild.innerHTML;}row.appendChild(td);});tb.appendChild(row);});t.appendChild(tb);w.appendChild(h('div','tbl',[t]));return w;}
function stats(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','stats');arr(b.items).forEach(function(s){if(!s)return;var c=h('div','st');c.appendChild(txt('div','sl',s.label));c.appendChild(txt('div','sv',s.value));if(s.delta){var tone=s.tone||(/^\s*[-−]/.test(s.delta)?'down':'up');c.appendChild(txt('div','sd '+tone,s.delta));}g.appendChild(c);});w.appendChild(g);return w;}
var COLORS=['#4f8ef7','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4'];
function chart(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var labels=arr(b.labels),series=arr(b.series).filter(function(s){return s&&Array.isArray(s.data);});if(!labels.length||!series.length)return w;
 var W=640,H=240,P={l:44,r:12,t:12,b:30};var all=[];series.forEach(function(s){s.data.forEach(function(v){if(isFinite(+v))all.push(+v);});});var mx=Math.max.apply(null,all.concat([0])),mn=Math.min.apply(null,all.concat([0]));
 var step=Math.pow(10,Math.floor(Math.log10((mx-mn)||1)));var top=Math.ceil(mx/step)*step||1,bot=Math.floor(mn/step)*step;var iw=W-P.l-P.r,ih=H-P.t-P.b;function y(v){return P.t+ih-(v-bot)/(top-bot)*ih;}
 var ns='http://www.w3.org/2000/svg';function s(tag,a){var e=document.createElementNS(ns,tag);for(var k in a)e.setAttribute(k,a[k]);return e;}
 var svg=s('svg',{viewBox:'0 0 '+W+' '+H});var muted=getComputedStyle(document.documentElement).getPropertyValue('--muted');var lineC=getComputedStyle(document.documentElement).getPropertyValue('--line');
 for(var k=0;k<=4;k++){var v=bot+(top-bot)*k/4;var yy=y(v);svg.appendChild(s('line',{x1:P.l,x2:W-P.r,y1:yy,y2:yy,stroke:lineC,'stroke-width':1}));var tt=s('text',{x:P.l-8,y:yy+4,'text-anchor':'end','font-size':11,fill:muted});tt.textContent=(Math.abs(v)>=1000?(v/1000).toFixed(v%1000?1:0)+'k':+v.toFixed(2))+(b.unit&&k===4?b.unit:'');svg.appendChild(tt);}
 var bw=iw/labels.length;labels.forEach(function(l,i){var t=s('text',{x:P.l+bw*i+bw/2,y:H-10,'text-anchor':'middle','font-size':11,fill:muted});t.textContent=String(l).slice(0,14);svg.appendChild(t);});
 if(b.kind==='line'){series.forEach(function(se,si){var c=se.color||COLORS[si%6];var pts=se.data.map(function(v,i){return [P.l+bw*i+bw/2,y(+v)];});svg.appendChild(s('polyline',{points:pts.map(function(p){return p.join(',');}).join(' '),fill:'none',stroke:c,'stroke-width':2.4,'stroke-linejoin':'round','stroke-linecap':'round'}));pts.forEach(function(p,i){var d=s('circle',{cx:p[0],cy:p[1],r:3.4,fill:c});var ti=s('title',{});ti.textContent=se.name+' · '+labels[i]+': '+se.data[i]+(b.unit||'');d.appendChild(ti);svg.appendChild(d);});});}
 else{var gw=bw*.72/series.length;series.forEach(function(se,si){var c=se.color||COLORS[si%6];se.data.forEach(function(v,i){v=+v;var x=P.l+bw*i+bw*.14+gw*si;var y0=y(Math.max(0,bot)),y1=y(v);var r=s('rect',{x:x,y:Math.min(y0,y1),width:Math.max(2,gw-3),height:Math.max(1,Math.abs(y0-y1)),rx:4,fill:c});var ti=s('title',{});ti.textContent=se.name+' · '+labels[i]+': '+v+(b.unit||'');r.appendChild(ti);svg.appendChild(r);});});}
 var box=h('div','chart');if(series.length>1){var lg=h('div','legend');series.forEach(function(se,si){var sp=h('span');var ii=h('i');ii.style.background=se.color||COLORS[si%6];sp.appendChild(ii);sp.appendChild(document.createTextNode(se.name||''));lg.appendChild(sp);});box.appendChild(lg);}
 box.appendChild(svg);w.appendChild(box);return w;}
function callout(b){var ic={info:'ℹ️',tip:'💡',warning:'⚠️',danger:'⛔'}[b.tone]||'ℹ️';var c=h('div','co '+(b.tone||'info'));c.appendChild(txt('div','ci',ic));var body=h('div','');if(b.title)body.appendChild(txt('div','ct',b.title));body.appendChild(md(b.md||b.text||''));c.appendChild(body);return h('div','blk',[c]);}
function compare(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','cmp');arr(b.items).forEach(function(it){if(!it)return;var c=h('div','cmpc');c.appendChild(txt('div','h',it.title||''));var ul=h('ul');arr(it.points).forEach(function(p){var neg=/^\s*[-–−]\s*/.test(p);ul.appendChild(txt('li',neg?'neg':'',String(p).replace(/^\s*[-–−+]\s*/,'')));});arr(it.cons).forEach(function(p){ul.appendChild(txt('li','neg',p));});c.appendChild(ul);if(it.verdict)c.appendChild(txt('div','v',it.verdict));g.appendChild(c);});w.appendChild(g);return w;}
function steps(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var d=h('div','steps');arr(b.items).forEach(function(it,i){if(!it)return;var r=h('div','step');r.appendChild(txt('div','n',String(i+1)));var x=h('div','');x.appendChild(txt('div','tt',it.title||it));if(it.detail)x.appendChild(txt('div','td',it.detail));r.appendChild(x);d.appendChild(r);});w.appendChild(d);return w;}
function hero(b){var w=h('div','blk');var c=h('div','hero');c.appendChild(photo(b,'',{noText:true}));var ov=h('div','ov');if(b.eyebrow)ov.appendChild(txt('div','eb',b.eyebrow));if(b.title)ov.appendChild(txt('div','ht',b.title));if(b.md)ov.appendChild(md(b.md));c.appendChild(ov);w.appendChild(c);return w;}
function quote(b){var q=h('div','quote');q.appendChild(md(b.md||b.text||''));if(b.by)q.appendChild(txt('div','by','— '+b.by));return h('div','blk',[q]);}
function text(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));w.appendChild(md(b.md||b.text||''));return w;}
var R={text:text,images:images,map:mapBlock,places:places,cards:places,timeline:timeline,table:table,stats:stats,chart:chart,callout:callout,compare:compare,steps:steps,hero:hero,quote:quote};
/* ---------- render ---------- */
var S=I.S,app=I.app;
if(S.title)app.appendChild(txt('h1','t blk',S.title));if(S.subtitle)app.appendChild(txt('div','sub blk',S.subtitle));
var blocks=arr(S.blocks);var deferred=[];
/* maps first so timelines can link to them */
blocks.forEach(function(b,i){if(b&&b.type==='map')deferred[i]=mapBlock(b);});
blocks.forEach(function(b,i){if(!b)return;var f=R[b.type]||text;var node;try{node=b.type==='map'?deferred[i]:f(b);}catch(e){node=txt('div','blk','['+b.type+' could not render]');}
 if(node){node.style.animationDelay=Math.min(i*60,420)+'ms';app.appendChild(node);}});
if(I.SRC.length){var sw=h('div','blk');sw.appendChild(txt('div','lbl','Sources'));var sr=h('div','srcs');I.SRC.forEach(function(s,i){var c=h('button','src');c.setAttribute('data-url',s.url);var d=h('div','d');var im=document.createElement('img');im.src=I.fav(s.url);im.alt='';im.onerror=function(){im.remove();};d.appendChild(im);d.appendChild(document.createTextNode((i+1)+'. '+I.domain(s.url)));c.appendChild(d);c.appendChild(txt('div','s',s.title||s.url));sr.appendChild(c);});sw.appendChild(sr);app.appendChild(sw);}
var fu=arr(S.followups).filter(Boolean).slice(0,4);if(fu.length){var fw=h('div','blk');fw.appendChild(txt('div','lbl','Related'));var l=h('div','fu');fu.forEach(function(q){var bt=h('button','');bt.appendChild(icon('arrow'));bt.appendChild(document.createTextNode(String(q)));bt.onclick=function(){I.sendPrompt(String(q));};l.appendChild(bt);});fw.appendChild(l);app.appendChild(fw);}
document.querySelectorAll('.cite img').forEach(function(im){im.onerror=function(){im.remove();};});
setTimeout(I.reportHeight,50);
})();
</script>
</body>
</html>'''
