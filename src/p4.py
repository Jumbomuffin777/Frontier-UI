
_HTML += r'''<script nonce="__NONCE__">
(function(){
"use strict";
var S={};try{S=JSON.parse(document.getElementById('spec').textContent)||{};}catch(e){S={blocks:[{type:'text',md:'Could not read the UI spec.'}]};}
var app=document.getElementById('app');
/* ---------- parent bridge ---------- */
var origin='*';try{if(document.referrer)origin=new URL(document.referrer).origin;}catch(e){}
function post(m){try{parent.postMessage(m,origin);}catch(e){}}
function sendPrompt(t){post({type:'input:prompt:submit',text:String(t)});}
/* External links. Open WebUI renders tool cards in <iframe sandbox="allow-scripts allow-popups …"> WITHOUT
   allow-popups-to-escape-sandbox, so a tab opened from the card inherits the sandbox (opaque origin). Chromium then
   refuses to load any site that sends Cross-Origin-Opener-Policy (Google Maps/Gmail/Calendar, Apple Maps,
   OpenStreetMap…) -> ERR_BLOCKED_BY_RESPONSE, while the same URL works in a fresh tab. So:
   1) same-origin embed (Settings > Interface > iframe Sandbox Allow Same Origin): open from the parent window -> normal tab;
   2) Open WebUI's own files (no COOP) and touch devices (the OS hands map/mail links to apps): open directly;
   3) otherwise: copy the link and show a small sheet instead of opening a dead tab. */
function baseUrl(){return (window.IUI&&IUI.UI&&IUI.UI.base)||(origin!=='*'?origin:'');}
function absUrl(u){var B=baseUrl(),s=String(u||'');if(s.charAt(0)==='/'&&s.charAt(1)!=='/'&&B)s=(B.slice(-1)==='/'?B.slice(0,-1):B)+s;return new URL(s,B?B+'/':location.href);}
function parentOpen(href){try{var pw=parent.window;if(pw===window)return false;void pw.location.href;pw.open(href,'_blank','noopener,noreferrer');return true;}catch(e){return false;}}
function touch(){try{return matchMedia('(pointer:coarse)').matches&&!matchMedia('(pointer:fine)').matches;}catch(e){return false;}}
function copyPlain(t){var ta=document.createElement('textarea');ta.value=t;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();var ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();
 if(!ok&&navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(function(){},function(){});ok=true;}return ok;}
function linkSheet(href){var old=document.querySelector('.lsheet');if(old)old.remove();var copied=copyPlain(href);
 var s=h('div','lsheet');s.setAttribute('role','dialog');var c=h('div','lsc');s.appendChild(c);
 c.appendChild(txt('div','lst',copied?'Link copied - paste it into a new tab':'Copy this link into a new tab'));
 var inp=document.createElement('input');inp.className='lsi';inp.readOnly=true;inp.value=href;inp.onclick=function(){inp.select();};c.appendChild(inp);
 c.appendChild(txt('div','lsh','Open WebUI keeps tool cards sandboxed, and sites like Google, Apple Maps and OpenStreetMap refuse to open from a sandboxed tab. An admin can allow direct opening in Settings › Interface › "iframe Sandbox Allow Same Origin" (this relaxes the sandbox for every embed).'));
 var row=h('div','lsb');var cp=txt('button','btn pri','Copy link');cp.onclick=function(){cp.textContent=copyPlain(href)?'Copied ✓':'Press Ctrl+C';inp.select();};
 var tr=txt('button','btn','Try opening anyway');tr.onclick=function(){window.open(href,'_blank','noopener,noreferrer');};var cl=txt('button','btn','Close');cl.onclick=function(){s.remove();};
 row.appendChild(cp);row.appendChild(tr);row.appendChild(cl);c.appendChild(row);
 /* the card iframe is as tall as its content, so a fixed bottom sheet could land off-screen: anchor it under the clicked control */
 var a=document.activeElement,r=(a&&a!==document.body&&a.getBoundingClientRect)?a.getBoundingClientRect():null;document.body.appendChild(s);
 var top=(r?r.bottom:Math.min(innerHeight,600)/2)+scrollY+6,sh=s.offsetHeight,max=Math.max(document.body.scrollHeight,document.documentElement.scrollHeight);
 if(top+sh>max&&r)top=Math.max(0,r.top+scrollY-sh-6);s.style.top=top+'px';
 setTimeout(function(){document.addEventListener('click',function off(e){if(!s.isConnected||!s.contains(e.target)){s.remove();document.removeEventListener('click',off,true);}},true);inp.select();},30);}
function openLink(u){try{var p=absUrl(u);if(!/^https?:$/.test(p.protocol))return;
 if(parentOpen(p.href))return;
 var B=baseUrl(),own=false;try{own=!!B&&p.origin===new URL(B).origin;}catch(e){}
 if(own||touch()){window.open(p.href,'_blank','noopener,noreferrer');return;}
 linkSheet(p.href);}catch(e){}}
var lastH=0,raf=0;
function reportHeight(){var h=Math.ceil(Math.max(document.body.scrollHeight,document.documentElement.scrollHeight));if(Math.abs(h-lastH)<2)return;lastH=h;post({type:'iframe:height',height:h});}
function schedule(){cancelAnimationFrame(raf);raf=requestAnimationFrame(reportHeight);}
new ResizeObserver(schedule).observe(document.body);
window.addEventListener('load',function(){reportHeight();setTimeout(reportHeight,300);setTimeout(reportHeight,1500);});
/* ---------- theme follow ---------- */
function applyTheme(dark){var r=document.documentElement;r.classList.toggle('dark',dark);r.classList.toggle('light',!dark);r.setAttribute('data-theme',dark?'dark':'light');document.dispatchEvent(new Event('iui-theme'));}
try{var pr=parent.document.documentElement;var det=function(){var s='';try{s=parent.localStorage.getItem('theme')||'';}catch(e){}if(s.indexOf('dark')>=0||s.indexOf('oled')>=0)return true;if(s==='light'||s==='her')return false;return pr.classList.contains('dark');};
applyTheme(det());new MutationObserver(function(){applyTheme(det());}).observe(pr,{attributes:true,attributeFilter:['class']});}catch(e){}
function isDark(){return document.documentElement.classList.contains('dark');}
/* ---------- helpers ---------- */
function h(tag,cls,kids){var e=document.createElement(tag);if(cls)e.className=cls;(kids||[]).forEach(function(k){if(k==null)return;e.appendChild(typeof k==='string'?document.createTextNode(k):k);});return e;}
function txt(tag,cls,t){var e=h(tag,cls);e.textContent=t==null?'':String(t);return e;}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function arr(x){return Array.isArray(x)?x:[];}
function domain(u){try{return new URL(u).hostname.replace(/^www\./,'');}catch(e){return '';}}
function fav(u){var d=domain(u);return d?'https://icons.duckduckgo.com/ip3/'+d+'.ico':'';}
var SRC=arr(S.sources).map(function(s){return typeof s==='string'?{url:s,title:domain(s)}:(s||{});}).filter(function(s){return s.url;});
var SVG={
 bm:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3h12v18l-6-4-6 4z"/></svg>',
 arrow:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
 l:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M15 6l-6 6 6 6"/></svg>',
 r:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>',
 exp:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
 col:'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>',
 nav:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"><path d="M3 11l18-8-8 18-2-8z"/></svg>',
 fit:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/></svg>'};
function icon(name){var s=document.createElement('span');s.style.display='inline-flex';s.innerHTML=SVG[name];return s;}
/* inline markdown: escape first, then a safe subset */
function inl(s){
 s=esc(s);
 s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
 s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>');
 s=s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,function(m,t,u){return '<a href="#" data-url="'+u+'">'+t+'</a>';});
 s=s.replace(/\[(\d{1,2})\]/g,function(m,n){var src=SRC[+n-1];if(!src)return '';var d=domain(src.url);var more='';return '<button class="cite" data-url="'+esc(src.url)+'" title="'+esc(src.title||d)+'"><img src="'+esc(fav(src.url))+'" alt="" onerror="this.remove()">'+esc(d)+'</button>';});
 return s;}
function md(src){
 var out=[],list=null,lines=String(src||'').split(/\n/);
 lines.forEach(function(l){var m=l.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/);
  if(m){var tag=m[1]?'ol':'ul';if(!list||list.tag!==tag){if(list)out.push('</'+list.tag+'>');list={tag:tag};out.push('<'+tag+'>');}out.push('<li>'+inl(m[2])+'</li>');return;}
  if(list){out.push('</'+list.tag+'>');list=null;}
  if(l.trim()){var hm=l.match(/^#{1,4}\s+(.*)$/);out.push(hm?'<p><strong>'+inl(hm[1])+'</strong></p>':'<p>'+inl(l)+'</p>');}});
 if(list)out.push('</'+list.tag+'>');
 var d=h('div','prose');d.innerHTML=out.join('');return d;}
document.addEventListener('click',function(e){var a=e.target.closest('[data-url]');if(a){e.preventDefault();openLink(a.getAttribute('data-url'));}});
/* photos with candidate fallback */
function photo(item,cls,opts){
 opts=opts||{};var box=h('div','ph'+(cls?' '+cls:''));var c=arr(item&&item.candidates);
 if(item&&typeof item.image==='string'&&/^https:/.test(item.image))c=[{src:item.image}].concat(c);
 if(item&&typeof item.src==='string'&&/^https:/.test(item.src))c=[{src:item.src}].concat(c);
 var cap=(item&&(item.caption||item.name||item.title||item.query))||'';
 function miss(){box.classList.add('miss');if(opts.noText){var m=txt('span','mi',(item&&item.icon)||String(cap||'?').trim().charAt(0).toUpperCase());box.textContent='';box.appendChild(m);}else{box.textContent=cap;}}
 if(!c.length){miss();return box;}
 var sh=h('div','shimmer');box.appendChild(sh);var img=document.createElement('img');img.alt=cap;img.loading='eager';img.referrerPolicy='no-referrer';var i=0;
 function next(){if(i>=c.length){img.remove();sh.remove();miss();return;}img.src=c[i++].src;}
 img.onload=function(){if(img.naturalWidth<140&&i<c.length){next();return;}img.classList.add('ok');sh.remove();var cc=c[i-1]||{};box.dataset.page=cc.page||'';box.dataset.credit=cc.credit||'';if(cc.credit)img.title=cc.credit;};
 img.onerror=next;next();box.appendChild(img);
 if(opts.bookmark){var b=h('div','bm');b.innerHTML=SVG.bm;box.appendChild(b);}
 if(opts.caption&&cap){box.appendChild(txt('div','cap',cap));}
 if(opts.zoom){box.addEventListener('click',function(){if(img.classList.contains('ok'))lightbox(img.src,cap,box.dataset.page,box.dataset.credit);});}
 return box;}
function lightbox(src,cap,page,credit){var lb=h('div','lb');var im=document.createElement('img');im.src=src;im.referrerPolicy='no-referrer';lb.appendChild(im);var c=h('div','lbc');c.appendChild(document.createTextNode((cap||'')+(credit?'  ·  '+credit:'')));if(page){c.appendChild(document.createTextNode('  ·  '));var a=txt('a','',domain(page));a.href='#';a.setAttribute('data-url',page);c.appendChild(a);}lb.appendChild(c);lb.addEventListener('click',function(e){if(!e.target.closest('a'))lb.remove();});document.body.appendChild(lb);}
function scroller(inner){var w=h('div','wrap',[inner]);var L=h('button','arrow l');L.innerHTML=SVG.l;var R=h('button','arrow r');R.innerHTML=SVG.r;w.appendChild(L);w.appendChild(R);
 function upd(){L.classList.toggle('on',inner.scrollLeft>4);R.classList.toggle('on',inner.scrollLeft+inner.clientWidth<inner.scrollWidth-4);}
 L.onclick=function(){inner.scrollBy({left:-inner.clientWidth*.8,behavior:'smooth'});};R.onclick=function(){inner.scrollBy({left:inner.clientWidth*.8,behavior:'smooth'});};
 inner.addEventListener('scroll',upd);setTimeout(upd,100);window.addEventListener('resize',upd);return w;}
function label(t){return t?txt('div','h2',t):null;}
'''
