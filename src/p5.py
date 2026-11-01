

_HTML += r'''<script nonce="__NONCE__">
(function(){
"use strict";
var I=window.IUI;
var h=I.h,txt=I.txt,arr=I.arr,md=I.md,photo=I.photo,scroller=I.scroller,label=I.label,icon=I.icon,SVG=I.SVG,UI=I.UI;
var COLORS=['#4f8ef7','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
var MAPS=[];/* registry: {places, select(name)} */
function words(s){return String(s||'').toLowerCase().split(/[^a-z0-9À-￿]+/).filter(function(w){return w.length>=4&&['temple','shrine','park','street','the','with','from','walk','tour','visit'].indexOf(w)<0;});}
function findPlace(name){name=String(name||'').toLowerCase().trim();if(!name)return null;var best=null,bs=0,qw=words(name);
 for(var i=0;i<MAPS.length;i++){var m=MAPS[i];for(var j=0;j<m.places.length;j++){var p=m.places[j];var n=String(p.name||'').toLowerCase();if(n===name||n.indexOf(name)>=0||name.indexOf(n)>=0)return {map:m,idx:j};
  var pw=words(n);var sc=qw.filter(function(w){return pw.some(function(x){return x===w||(w.length>=5&&x.indexOf(w.slice(0,5))===0);});}).length;if(sc>bs){bs=sc;best={map:m,idx:j};}}}
 return bs>=1?best:null;}
/* ---------- maplibre + local basemap loaders ---------- */
function loadScript(src){return new Promise(function(res,rej){var s=document.createElement('script');s.src=src;s.nonce=I.NONCE;s.onload=res;s.onerror=rej;document.head.appendChild(s);});}
var libP=null,localP=null,protoAdded=false;
function loadLib(){if(window.maplibregl)return Promise.resolve(window.maplibregl);if(libP)return libP;var T=UI.tiles;
 var local=T?loadScript(T+'/js/maplibre-gl.js').then(function(){var l=document.createElement('link');l.rel='stylesheet';l.href=T+'/js/maplibre-gl.css';document.head.appendChild(l);}):Promise.reject(0);
 libP=local.catch(function(){return loadScript(I.CDN+'/dist/maplibre-gl.js');}).then(function(){if(!window.maplibregl)throw new Error('maplibre missing');return window.maplibregl;});return libP;}
/* a self-hosted planet PMTiles (served on the LAN) when reachable; otherwise OpenFreeMap, then Esri raster */
function localBase(lib){if(localP)return localP;var T=UI.tiles;if(!T)return localP=Promise.resolve(false);
 var probe=fetch(T+'/planet.pmtiles',{headers:{Range:'bytes=0-126'}}).then(function(r){if(r.status!==206&&r.status!==200)throw 0;return Promise.all([window.pmtiles?0:loadScript(T+'/js/pmtiles.js'),window.basemaps?0:loadScript(T+'/js/basemaps.js')]);})
  .then(function(){if(!protoAdded){protoAdded=true;lib.addProtocol('pmtiles',new pmtiles.Protocol().tile);}return true;});
 localP=Promise.race([probe,new Promise(function(r){setTimeout(function(){r(false);},2500);})]).catch(function(){return false;});return localP;}
function lstyle(dark){var T=UI.tiles,fl=dark?'dark':'light';return {version:8,glyphs:T+'/fonts/{fontstack}/{range}.pbf',sprite:T+'/sprites/v4/'+fl,
 sources:{protomaps:{type:'vector',url:'pmtiles://'+T+'/planet.pmtiles',attribution:'© OpenStreetMap · Protomaps · self-hosted'}},layers:basemaps.layers('protomaps',basemaps.namedFlavor(fl),{lang:'en'})};}
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
function fmtKm(km){if(I.units()==='imperial'){var mi=km/1.609344;return mi<10?mi.toFixed(1)+' mi':Math.round(mi)+' mi';}return km<10?km.toFixed(1)+' km':Math.round(km)+' km';}
/* map apps: Google Maps keeps every stop; Apple Maps and OpenStreetMap take start -> end; GPX carries all stops plus
   the street route for OsmAnd, Organic Maps, Garmin, motorcycle navigators and Google My Maps */
function ll(p){return (+p.lat).toFixed(6)+','+(+p.lng).toFixed(6);}
function appleUrl(list,mode){if(list.length===1)return 'https://maps.apple.com/?ll='+ll(list[0])+'&q='+encodeURIComponent(list[0].name||'Pin');
 return 'https://maps.apple.com/?saddr='+ll(list[0])+'&daddr='+ll(list[list.length-1])+'&dirflg='+(mode==='walk'?'w':'d');}
function osmUrl(list,mode){var a=list[0];if(list.length===1)return 'https://www.openstreetmap.org/?mlat='+(+a.lat).toFixed(6)+'&mlon='+(+a.lng).toFixed(6)+'#map=16/'+(+a.lat).toFixed(5)+'/'+(+a.lng).toFixed(5);
 var eng={walk:'fossgis_osrm_foot',bike:'fossgis_osrm_bike'}[mode]||'fossgis_osrm_car';return 'https://www.openstreetmap.org/directions?engine='+eng+'&route='+encodeURIComponent(ll(a)+';'+ll(list[list.length-1]));}
function gpx(name,list,line){var e=function(s){return String(s==null?'':s).replace(/[<>&"]/g,function(c){return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c];});};
 var x=['<?xml version="1.0" encoding="UTF-8"?>','<gpx version="1.1" creator="Frontier UI" xmlns="http://www.topografix.com/GPX/1/1">','<metadata><name>'+e(name)+'</name></metadata>'];
 list.forEach(function(p){x.push('<wpt lat="'+(+p.lat).toFixed(6)+'" lon="'+(+p.lng).toFixed(6)+'"><name>'+e(p.name)+'</name>'+(p.note||p.time?'<desc>'+e([p.time,p.note].filter(Boolean).join(' - '))+'</desc>':'')+'</wpt>');});
 x.push('<rte><name>'+e(name)+'</name>');list.forEach(function(p){x.push('<rtept lat="'+(+p.lat).toFixed(6)+'" lon="'+(+p.lng).toFixed(6)+'"><name>'+e(p.name)+'</name></rtept>');});x.push('</rte>');
 if(line&&line.length>1){x.push('<trk><name>'+e(name)+' (street route)</name><trkseg>');line.forEach(function(c){x.push('<trkpt lat="'+(+c[0]).toFixed(6)+'" lon="'+(+c[1]).toFixed(6)+'"/>');});x.push('</trkseg></trk>');}
 x.push('</gpx>');return x.join('\n');}
function saveFile(name,text,mime){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:mime}));a.download=name;document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},2000);}
function fmtMin(m){m=Math.round(m);return m<60?m+' min':Math.floor(m/60)+' h '+(m%60?m%60+' min':'');}
function gmapsUrl(list,mode){list=list.slice(0,10);if(!list.length)return '';var ll=function(p){return (+p.lat).toFixed(6)+','+(+p.lng).toFixed(6);};
 if(list.length===1)return 'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(list[0].name?list[0].name+' '+ll(list[0]):ll(list[0]));
 var u='https://www.google.com/maps/dir/?api=1&origin='+ll(list[0])+'&destination='+ll(list[list.length-1]);if(list.length>2)u+='&waypoints='+encodeURIComponent(list.slice(1,-1).map(ll).join('|'));return u+'&travelmode='+(mode==='walk'?'walking':'driving');}
I.gmapsUrl=gmapsUrl;
function mapBlock(b){
 var places=arr(b.places).filter(function(p){return p&&p.lat!=null&&p.lng!=null&&isFinite(p.lat)&&isFinite(p.lng);});
 var wrap=h('div','blk');if(b.title)wrap.appendChild(label(b.title));
 if(!places.length){var l=h('div','maplist');arr(b.places).forEach(function(p){l.appendChild(txt('span','tag',(p.icon?p.icon+' ':'')+(p.name||'')));});wrap.appendChild(l);return wrap;}
 var days=arr(b.days_order).slice();if(!days.length){places.forEach(function(p){if(p.day&&days.indexOf(p.day)<0)days.push(p.day);});}if(days.length<2)days=[];
 var DR=b.day_routes||{};var dayColor=function(d){var i=days.indexOf(d);return i<0?null:COLORS[i%COLORS.length];};
 var curDay='';var tabs=null;
 if(days.length){tabs=h('div','dtabs');var mkTab=function(d,lab){var bt=h('button','dtab'+(d===''?' on':''));if(d){var dot=h('i');dot.style.background=dayColor(d);bt.appendChild(dot);}bt.appendChild(document.createTextNode(lab));bt.dataset.day=d;return bt;};
  tabs.appendChild(mkTab('','All days'));days.forEach(function(d){tabs.appendChild(mkTab(d,d));});wrap.appendChild(tabs);}
 var base=Math.min(560,Math.max(240,+b.height||380));var box=h('div','mapbox');box.style.height=base+'px';wrap.appendChild(box);
 var groups=[];if(!days.length)places.forEach(function(p){if(p.group&&groups.indexOf(p.group)<0)groups.push(p.group);});
 var ctlL=h('div','mctl l'),ctlR=h('div','mctl r');box.appendChild(ctlL);box.appendChild(ctlR);
 var sel=null;if(groups.length>1){sel=document.createElement('select');sel.className='mbtn';var o=document.createElement('option');o.value='';o.textContent='All groups';sel.appendChild(o);groups.forEach(function(g){var oo=document.createElement('option');oo.value=g;oo.textContent=g;sel.appendChild(oo);});ctlL.appendChild(sel);}
 var bFit=h('button','mbtn ic',[icon('nav')]);bFit.title='Fit all places';ctlL.appendChild(bFit);
 var APPS={google:'Google Maps',apple:'Apple Maps',osm:'OpenStreetMap',gpx:'GPX file'};var primary=APPS[UI.map_app]?UI.map_app:'google';
 var gw=h('div','mgrp');var bG=h('button','mbtn',[icon('ext'),txt('span','',APPS[primary])]);bG.title='Open this route in '+APPS[primary];var bM=h('button','mbtn ic',[icon('chev')]);bM.title='Other map apps';gw.appendChild(bG);gw.appendChild(bM);ctlR.appendChild(gw);
 var mm=h('div','mmenu');[['google','Google Maps','all stops'],['apple','Apple Maps','start → end'],['osm','OpenStreetMap','start → end'],['gpx','Download GPX','OsmAnd, Organic Maps, Garmin…']].forEach(function(o){var it=h('button','',[txt('span','',o[1]),txt('small','',o[2])]);it.onclick=function(e){e.stopPropagation();mm.classList.remove('on');openApp(o[0]);};mm.appendChild(it);});
 gw.appendChild(mm);bM.onclick=function(e){e.stopPropagation();mm.classList.toggle('on');};document.addEventListener('click',function(){mm.classList.remove('on');});
 var bExp=h('button','mbtn',[icon('exp'),txt('span','','Expand')]);ctlR.appendChild(bExp);
 var pop=h('div','mpop');box.appendChild(pop);
 var stat=txt('div','mstat','');box.appendChild(stat);
 function visible(){return places.filter(function(p){return (!curDay||p.day===curDay)&&(!sel||!sel.value||p.group===sel.value);});}
 function routeFor(d){return d?DR[d]:(days.length?null:b.route_geo);}
 function setStat(){var rs=curDay?[DR[curDay]]:(days.length?days.map(function(d){return DR[d];}):[b.route_geo]);rs=rs.filter(function(r){return r&&r.km;});
  if(!rs.length){stat.style.display='none';return;}var km=0,mn=0;rs.forEach(function(r){km+=r.km;mn+=r.min;});var walk=rs[0].mode==='walk';
  stat.textContent=(walk?'🚶 ':'🚗 ')+fmtKm(km)+' · '+fmtMin(mn)+(walk?' walking':' by car')+' · '+visible().length+' stops'+(curDay?' · '+curDay:'');stat.style.display='block';}
 setStat();
 function openApp(kind){var r=routeFor(curDay)||b.route_geo||{};var md=r.mode||b.mode;var list=visible();if(!list.length)return;
  if(kind==='gpx'){saveFile(((I.S.title||'route')+(curDay?' '+curDay:'')).replace(/[^\w -]+/g,'').trim()+'.gpx',gpx((I.S.title||'Route')+(curDay?' - '+curDay:''),list,r.line),'application/gpx+xml');return;}
  I.openLink(kind==='apple'?appleUrl(list,md):kind==='osm'?osmUrl(list,md):gmapsUrl(list,md));}
 bG.onclick=function(e){e.stopPropagation();openApp(primary);};
 if(b.route_status){wrap.appendChild(txt('div','rstat','⚠ '+b.route_status));}
 var reg={places:places,select:function(){}};MAPS.push(reg);
 loadLib().then(function(lib){return localBase(lib).then(function(ok){return [lib,ok];});}).then(function(r){var lib=r[0],useLocal=r[1];
  var usedRaster=false;function styleFor(dark){return useLocal?lstyle(dark):vstyle(dark);}
  var map=new lib.Map({container:box,style:styleFor(I.isDark()),attributionControl:{compact:true},dragRotate:false,pitchWithRotate:false,cooperativeGestures:false,fadeDuration:150});
  box.dataset.base=useLocal?'local':'openfreemap';
  map.scrollZoom.disable();box.addEventListener('wheel',function(e){if(e.ctrlKey||e.metaKey){map.scrollZoom.enable();}else{map.scrollZoom.disable();}},{passive:true});
  function fallback(){if(useLocal){useLocal=false;box.dataset.base='openfreemap';map.setStyle(vstyle(I.isDark()));return;}if(!usedRaster){usedRaster=true;box.dataset.base='raster';map.setStyle(rstyle(I.isDark()));}}
  var failT=setTimeout(function(){if(!map.isStyleLoaded())fallback();},7000);
  map.on('error',function(){if(!map.isStyleLoaded())fallback();});
  var css=getComputedStyle(document.documentElement);
  function lines(){var out=[];if(days.length){days.forEach(function(d,i){var rg=DR[d];var ln=(rg&&rg.line&&rg.line.length>1)?rg.line:null;var pts=places.filter(function(p){return p.day===d;});if(!ln&&pts.length>1)ln=pts.map(function(p){return [p.lat,p.lng];});if(ln)out.push({id:'r'+i,day:d,line:ln,solid:!!(rg&&rg.line),color:COLORS[i%COLORS.length]});});}
   else{var rg=b.route_geo;var ln=(rg&&rg.line&&rg.line.length>1)?rg.line:(b.route?places.map(function(p){return [p.lat,p.lng];}):null);if(ln)out.push({id:'r0',day:'',line:ln,solid:!!(rg&&rg.line),color:css.getPropertyValue('--route').trim()||'#111'});}return out;}
  var LINES=lines();
  function addRoutes(){LINES.forEach(function(L){if(map.getSource(L.id))return;map.addSource(L.id,{type:'geojson',data:{type:'Feature',geometry:{type:'LineString',coordinates:L.line.map(function(c){return [c[1],c[0]];})}}});
    map.addLayer({id:L.id+'-case',type:'line',source:L.id,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':css.getPropertyValue('--routecase').trim()||'#fff','line-width':7,'line-opacity':.95}});
    map.addLayer({id:L.id,type:'line',source:L.id,layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':L.color,'line-width':3.6,'line-dasharray':L.solid?[1,0]:[1.5,1.5]}});});showRoutes();}
  function showRoutes(){LINES.forEach(function(L){var v=(!curDay||L.day===curDay)?'visible':'none';[L.id,L.id+'-case'].forEach(function(id){if(map.getLayer(id))map.setLayoutProperty(id,'visibility',v);});});}
  map.on('styledata',function(){if(map.isStyleLoaded()){clearTimeout(failT);addRoutes();}});
  map.on('load',addRoutes);
  var mk=[];var dayIdx={};
  places.forEach(function(p,i){var el=h('div','pin');var n=p.day?(dayIdx[p.day]=(dayIdx[p.day]||0)+1):i+1;var dot=txt('div','dot',p.icon||String(n));var lab=txt('div','lab',p.name||'');
   var dc=dayColor(p.day);if(dc){dot.style.borderColor=dc;dot.style.boxShadow='0 0 0 2px '+dc+'55';}el.appendChild(dot);el.appendChild(lab);
   el.addEventListener('click',function(e){e.stopPropagation();choose(i,true);});
   var m=new lib.Marker({element:el,anchor:'top',offset:[0,-15]}).setLngLat([p.lng,p.lat]).addTo(map);mk.push({m:m,el:el,p:p});});
  function bounds(list){var bb=new lib.LngLatBounds();list.forEach(function(p){bb.extend([p.lng,p.lat]);});LINES.forEach(function(L){if((!curDay&&!(sel&&sel.value))||(curDay&&L.day===curDay))L.line.forEach(function(c){bb.extend([c[1],c[0]]);});});return bb;}
  function fit(list,anim){if(!list.length)return;if(list.length===1){map.jumpTo({center:[list[0].lng,list[0].lat],zoom:14});return;}map.fitBounds(bounds(list),{padding:{top:56,bottom:48,left:44,right:44},maxZoom:15,duration:anim?600:0});}
  fit(places,false);
  var cur=-1;
  function declutter(){var placed=[];var order=mk.map(function(o,j){return j;}).filter(function(j){return mk[j].el.style.display!=='none';});if(cur>=0&&order.indexOf(cur)>=0){order.splice(order.indexOf(cur),1);order.unshift(cur);}
   order.forEach(function(j){var o=mk[j];var pt=map.project([o.p.lng,o.p.lat]);var w=Math.min(220,(o.p.name||'').length*6.6+8);var r={x0:pt.x-w/2,x1:pt.x+w/2,y0:pt.y+2,y1:pt.y+20};var dot={x0:pt.x-15,x1:pt.x+15,y0:pt.y-15,y1:pt.y+15};
    var hit=placed.some(function(q){return !(r.x1<q.x0||r.x0>q.x1||r.y1<q.y0||r.y0>q.y1);});
    o.el.querySelector('.lab').style.visibility=hit?'hidden':'visible';placed.push(dot);if(!hit)placed.push(r);});}
  map.on('moveend',declutter);map.once('idle',declutter);setTimeout(declutter,50);
  function choose(i,fly){cur=i;mk.forEach(function(o,j){o.el.classList.toggle('sel',j===i);});var p=places[i];
   pop.innerHTML='';pop.appendChild(txt('b','',(p.icon?p.icon+'  ':'')+(p.name||'')));var meta=[p.day,p.time,p.note].filter(Boolean).join(' · ');if(meta)pop.appendChild(txt('span','',meta));
   var go=txt('a','mlink','Directions ↗');go.href='#';go.setAttribute('data-url',gmapsUrl([p]));pop.appendChild(go);pop.style.display='block';
   if(fly)map.easeTo({center:[p.lng,p.lat],zoom:Math.max(map.getZoom(),14),duration:600});
   declutter();document.dispatchEvent(new CustomEvent('iui-place',{detail:{name:p.name}}));}
  function applyFilter(){mk.forEach(function(o){var on=(!curDay||o.p.day===curDay);o.el.style.display=on?'':'none';o.el.classList.toggle('dim',!!(sel&&sel.value)&&o.p.group!==sel.value);});showRoutes();setStat();fit(visible(),true);setTimeout(declutter,650);}
  function setDay(d){curDay=d;if(tabs)tabs.querySelectorAll('.dtab').forEach(function(t){t.classList.toggle('on',t.dataset.day===d);});pop.style.display='none';applyFilter();document.dispatchEvent(new CustomEvent('iui-day',{detail:{day:d}}));}
  reg.select=function(i){var p=places[i];if(curDay&&p.day!==curDay)setDay(p.day);choose(i,true);box.scrollIntoView({block:'nearest',behavior:'smooth'});};
  map.on('click',function(){cur=-1;pop.style.display='none';mk.forEach(function(o){o.el.classList.remove('sel');});});
  bFit.onclick=function(){fit(visible(),true);};
  if(tabs)tabs.addEventListener('click',function(e){var t=e.target.closest('.dtab');if(t)setDay(t.dataset.day);});
  if(sel)sel.onchange=applyFilter;
  var big=false;bExp.onclick=function(){big=!big;box.style.height=(big?Math.max(560,Math.round(base*1.7)):base)+'px';bExp.innerHTML='';bExp.appendChild(icon(big?'col':'exp'));bExp.appendChild(txt('span','',big?'Collapse':'Expand'));setTimeout(function(){map.resize();fit(visible(),true);},380);};
  document.addEventListener('iui-theme',function(){usedRaster=false;map.setStyle(styleFor(I.isDark()));});
  new ResizeObserver(function(){map.resize();}).observe(box);
 }).catch(function(err){
   /* No WebGL (GPU blocklisted, hardened Firefox/LibreWolf profiles, some VMs) or the map library was blocked:
      draw a static sketch of the stops and street routes instead of a broken strip. Map-app links and GPX still work. */
   [].slice.call(box.querySelectorAll('.maplibregl-canvas-container,.maplibregl-control-container,canvas')).forEach(function(e){e.remove();});
   box.classList.add('nogl');box.style.height='auto';bExp.style.display='none';bFit.style.display='none';
   var lines=[];if(days.length){days.forEach(function(d){var r=DR[d];if(r&&r.line)lines.push([r.line,dayColor(d)]);});}else if(b.route_geo&&b.route_geo.line)lines.push([b.route_geo.line,'#4f8ef7']);
   var pts=places.filter(function(p){return p.lat!=null&&p.lng!=null;});var all=pts.map(function(p){return [p.lat,p.lng];});lines.forEach(function(l){all=all.concat(l[0]);});
   if(all.length){var la=all.map(function(x){return x[0];}),lo=all.map(function(x){return x[1];});var y0=Math.min.apply(null,la),y1=Math.max.apply(null,la),x0=Math.min.apply(null,lo),x1=Math.max.apply(null,lo);
    var k=Math.cos((y0+y1)/2*Math.PI/180),W=640,H=300,P=34,sw=Math.max((x1-x0)*k,1e-4),sh=Math.max(y1-y0,1e-4),sc=Math.min((W-2*P)/sw,(H-2*P)/sh);
    var X=function(x){return W/2+((x-(x0+x1)/2)*k)*sc;},Y=function(y){return H/2-(y-(y0+y1)/2)*sc;};
    var NS='http://www.w3.org/2000/svg',sv=document.createElementNS(NS,'svg');sv.setAttribute('viewBox','0 0 '+W+' '+H);sv.setAttribute('class','msketch');sv.setAttribute('role','img');sv.setAttribute('aria-label','Route sketch');
    var mk=function(t,a){var e=document.createElementNS(NS,t);for(var q in a)e.setAttribute(q,a[q]);sv.appendChild(e);return e;};
    lines.forEach(function(l){mk('polyline',{points:l[0].map(function(c){return X(c[1]).toFixed(1)+','+Y(c[0]).toFixed(1);}).join(' '),fill:'none',stroke:l[1]||'#4f8ef7','stroke-width':4,'stroke-linejoin':'round','stroke-linecap':'round',opacity:.9});});
    if(!lines.length&&pts.length>1)mk('polyline',{points:pts.map(function(p){return X(p.lng).toFixed(1)+','+Y(p.lat).toFixed(1);}).join(' '),fill:'none',stroke:'#8a8f98','stroke-width':2,'stroke-dasharray':'6 6'});
    var cnt={};pts.forEach(function(p,i){var n=p.day?(cnt[p.day]=(cnt[p.day]||0)+1):i+1;var cx=X(p.lng),cy=Y(p.lat);mk('circle',{cx:cx,cy:cy,r:11,fill:dayColor(p.day)||'#4f8ef7',stroke:'#fff','stroke-width':2});
     var t=mk('text',{x:cx,y:cy+4,'text-anchor':'middle','font-size':11,'font-weight':700,fill:'#fff'});t.textContent=String(n);
     var lb=mk('text',{x:cx+15,y:cy+4,'font-size':12,'class':'mslab'});lb.textContent=(p.name||'').slice(0,34);});
    box.appendChild(sv);}
   box.appendChild(txt('div','faint mnote','Interactive map unavailable in this browser (WebGL is off or the map library was blocked) - showing a route sketch. Use the map-app button for turn-by-turn.'));
   var l=h('div','maplist');places.forEach(function(p,i){l.appendChild(txt('span','tag',(p.icon||(i+1)+'.')+' '+p.name));});box.appendChild(l);
   try{console.warn('Frontier UI map fallback:',err&&err.message||err);}catch(e){}});
 return wrap;}
'''
_HTML += r'''/* ---------- other blocks ---------- */
function images(b){var it=arr(b.items).slice(0,9);var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','gal'+(it.length>3?' scroll':' n'+it.length));
 it.forEach(function(x){g.appendChild(photo(x,'',{bookmark:true,caption:true,zoom:true}));});w.appendChild(it.length>3?scroller(g):g);return w;}
function stars(r){r=+r;if(!isFinite(r))return null;var s=h('span','');s.appendChild(txt('span','star','★ '));s.appendChild(document.createTextNode(r.toFixed(1)));return s;}
function priceLevel(p){var m=String(p||'').match(/[$€£¥₩]+/);if(m)return m[0].length;var n=parseFloat(String(p||'').replace(/[^0-9.]/g,''));return isFinite(n)?n:99;}
function places(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var items=arr(b.items).filter(Boolean);var row=h('div','cards');
 var cards=items.map(function(it,idx){var c=h('div','card'+(it.url?' link':''));c.appendChild(photo(it,'',{noText:true}));var cb=h('div','cb');cb.appendChild(txt('div','nm',it.name||it.title||''));
  var meta=h('div','meta');var bits=[];var st=stars(it.rating);if(st)bits.push(st);[it.price,it.subtitle].forEach(function(x){if(x)bits.push(document.createTextNode(String(x)));});
  bits.forEach(function(x,i){if(i)meta.appendChild(document.createTextNode(' · '));meta.appendChild(x);});if(bits.length)cb.appendChild(meta);
  if(it.description)cb.appendChild(txt('div','ds',it.description));
  var tg=arr(it.tags).slice(0,3);if(tg.length){var t=h('div','tags');tg.forEach(function(x){t.appendChild(txt('span','tag',x));});cb.appendChild(t);}
  c.appendChild(cb);c.addEventListener('click',function(){var f=findPlace(it.name);if(f&&!it.url){f.map.select(f.idx);return;}if(it.url)I.openLink(it.url);});
  return {el:c,it:it,idx:idx};});
 cards.forEach(function(c){row.appendChild(c.el);});
 /* interactive filters + sort (4+ items) */
 if(items.length>=4){var bar=h('div','fbar');var sort=document.createElement('select');sort.className='fsel';[['','Recommended'],['rating','Top rated'],['price','Price: low → high'],['price-','Price: high → low'],['name','Name A–Z']].forEach(function(o){var op=document.createElement('option');op.value=o[0];op.textContent=o[1];sort.appendChild(op);});bar.appendChild(sort);
  var tags={};items.forEach(function(it){arr(it.tags).forEach(function(t){tags[t]=(tags[t]||0)+1;});});var tagList=Object.keys(tags).sort(function(a,b){return tags[b]-tags[a];}).slice(0,8);
  var prices=[];items.forEach(function(it){var p=String(it.price||'').match(/^[$€£¥₩]{1,4}$/);if(p&&prices.indexOf(p[0])<0)prices.push(p[0]);});prices.sort(function(a,b){return a.length-b.length;});
  var active={tags:{},price:'',top:false};
  function chip(lab,on,cls){var c=txt('button','fchip'+(cls?' '+cls:''),lab);c.onclick=function(){on(c);apply();};return c;}
  prices.forEach(function(p){bar.appendChild(chip(p,function(){active.price=active.price===p?'':p;bar.querySelectorAll('.fchip.pr').forEach(function(x){x.classList.toggle('on',x.textContent===active.price);});},'pr'));});
  tagList.forEach(function(t){bar.appendChild(chip(t,function(c){active.tags[t]=!active.tags[t];c.classList.toggle('on',!!active.tags[t]);}));});
  if(items.some(function(it){return it.rating!=null;}))bar.appendChild(chip('★ 4.5+',function(c){active.top=!active.top;c.classList.toggle('on',active.top);}));
  var count=txt('span','fcount','');bar.appendChild(count);
  var apply=function(){var want=Object.keys(active.tags).filter(function(k){return active.tags[k];});var v=sort.value;var list=cards.slice();
   if(v==='rating')list.sort(function(a,b){return (+b.it.rating||0)-(+a.it.rating||0);});else if(v==='price')list.sort(function(a,b){return priceLevel(a.it.price)-priceLevel(b.it.price);});else if(v==='price-')list.sort(function(a,b){return priceLevel(b.it.price)-priceLevel(a.it.price);});else if(v==='name')list.sort(function(a,b){return String(a.it.name||'').localeCompare(String(b.it.name||''));});else list.sort(function(a,b){return a.idx-b.idx;});
   var shown=0;list.forEach(function(c){var ok=(!active.price||String(c.it.price||'')===active.price)&&want.every(function(t){return arr(c.it.tags).indexOf(t)>=0;})&&(!active.top||(+c.it.rating||0)>=4.5);c.el.style.display=ok?'':'none';if(ok)shown++;row.appendChild(c.el);});
   count.textContent=shown===items.length?'':shown+' of '+items.length;row.scrollLeft=0;row.dispatchEvent(new Event('scroll'));};
  sort.onchange=apply;w.appendChild(bar);}
 w.appendChild(scroller(row));return w;}
function timeline(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var tl=h('div','tl');
 arr(b.items).forEach(function(it){if(!it)return;var f=findPlace(it.place||it.title);var row=h('div','ti'+(f?' go':''));row.appendChild(txt('div','tm',it.time||''));var rail=h('div','rail',[h('div','bul')]);row.appendChild(rail);
  var body=h('div','tbody');if(it.candidates&&it.candidates.length){var th=h('div','thumb');th.appendChild(photo(it,'',{noText:true}));body.appendChild(th);}
  var tx=h('div','');tx.appendChild(txt('div','tt',it.title||''));if(it.detail)tx.appendChild(txt('div','td',it.detail));body.appendChild(tx);row.appendChild(body);
  row.dataset.day=it.day||(f&&f.map.places[f.idx].day)||'';
  if(f){row.addEventListener('click',function(){f.map.select(f.idx);});row.dataset.place=String(f.map.places[f.idx].name||'').toLowerCase();}
  tl.appendChild(row);});
 document.addEventListener('iui-place',function(e){var n=String(e.detail.name||'').toLowerCase();tl.querySelectorAll('.ti').forEach(function(r){r.classList.toggle('hl',!!n&&r.dataset.place===n);});});
 document.addEventListener('iui-day',function(e){var d=e.detail.day;tl.querySelectorAll('.ti').forEach(function(r){r.classList.toggle('off',!!d&&!!r.dataset.day&&r.dataset.day!==d);});});
 w.appendChild(tl);return w;}
function table(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var t=h('table');var th=h('thead'),tr=h('tr');var tb=h('tbody');var dir={};
 arr(b.columns).forEach(function(c,ci){var x=txt('th','',c);x.title='Sort';x.onclick=function(){dir[ci]=!dir[ci];var rows=Array.prototype.slice.call(tb.children);rows.sort(function(a,b){var A=a.children[ci]?a.children[ci].textContent:'',B=b.children[ci]?b.children[ci].textContent:'';var na=parseFloat(A.replace(/[^0-9.\-]/g,'')),nb=parseFloat(B.replace(/[^0-9.\-]/g,''));var r=(isFinite(na)&&isFinite(nb))?na-nb:A.localeCompare(B);return dir[ci]?r:-r;});rows.forEach(function(r){tb.appendChild(r);});};tr.appendChild(x);});th.appendChild(tr);t.appendChild(th);
 arr(b.rows).forEach(function(r){var row=h('tr');arr(r).forEach(function(c){var td=h('td');td.appendChild(md(c).firstChild||document.createTextNode(''));if(td.firstChild&&td.firstChild.tagName==='P'){td.innerHTML=td.firstChild.innerHTML;}row.appendChild(td);});tb.appendChild(row);});t.appendChild(tb);w.appendChild(h('div','tbl',[t]));return w;}
function stats(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','stats');arr(b.items).forEach(function(s){if(!s)return;var c=h('div','st');c.appendChild(txt('div','sl',s.label));c.appendChild(txt('div','sv',s.value));if(s.delta){var tone=s.tone||(/^\s*[-−]/.test(s.delta)?'down':'up');c.appendChild(txt('div','sd '+tone,s.delta));}g.appendChild(c);});w.appendChild(g);return w;}
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
var X=I.X||{};Object.keys(X).forEach(function(k){R[k]=X[k];});
/* ---------- render ---------- */
var S=I.S,app=I.app;
if(S.title)app.appendChild(txt('h1','t blk',S.title));if(S.subtitle)app.appendChild(txt('div','sub blk',S.subtitle));
var blocks=arr(S.blocks);var deferred=[];
blocks.forEach(function(b,i){if(b&&b.type==='map')deferred[i]=mapBlock(b);});
blocks.forEach(function(b,i){if(!b)return;var f=R[b.type]||text;var node;try{node=b.type==='map'?deferred[i]:f(b);}catch(e){node=txt('div','blk','['+b.type+' could not render]');}
 if(node){node.style.animationDelay=Math.min(i*60,420)+'ms';app.appendChild(node);}});
if(I.SRC.length){var sw=h('div','blk');sw.appendChild(txt('div','lbl','Sources'));var sr=h('div','srcs');I.SRC.forEach(function(s,i){var c=h('button','src');c.setAttribute('data-url',s.url);var d=h('div','d');var im=document.createElement('img');im.src=I.fav(s.url);im.alt='';im.onerror=function(){im.remove();};d.appendChild(im);d.appendChild(document.createTextNode((i+1)+'. '+I.domain(s.url)));c.appendChild(d);c.appendChild(txt('div','s',s.title||s.url));sr.appendChild(c);});sw.appendChild(sr);app.appendChild(sw);}
if(I.actions){try{var ab=I.actions(S,MAPS);if(ab)app.appendChild(ab);}catch(e){}}
var fu=arr(S.followups).filter(Boolean).slice(0,4);if(fu.length){var fw=h('div','blk');fw.appendChild(txt('div','lbl','Related'));var l=h('div','fu');fu.forEach(function(q){var bt=h('button','');bt.appendChild(icon('arrow'));bt.appendChild(document.createTextNode(String(q)));bt.onclick=function(){I.sendPrompt(String(q));};l.appendChild(bt);});fw.appendChild(l);app.appendChild(fw);}
document.querySelectorAll('.cite img').forEach(function(im){im.onerror=function(){im.remove();};});
setTimeout(I.reportHeight,50);
})();
</script>
</body>
</html>'''
