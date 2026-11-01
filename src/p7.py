

_HTML += r'''<style>
/* ---- v1.1 blocks ---- */
.dtabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px}
.dtab{border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:999px;padding:4px 11px;font:500 12.5px/1.4 inherit;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.dtab i{width:9px;height:9px;border-radius:50%;display:inline-block}
.dtab.on{background:var(--fg);color:var(--surface2);border-color:var(--fg)}
.ti.off{opacity:.32}
.mlink{display:block;margin-top:4px;font-size:12px;color:var(--accent);text-decoration:none}
.fbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0 0 10px}
.fsel{border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:8px;padding:4px 8px;font:500 12.5px inherit}
.fchip{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:3px 10px;font:500 12px/1.4 inherit;cursor:pointer}
.fchip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.fcount{font-size:12px;color:var(--faint);margin-left:4px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.row2{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.muted{color:var(--muted)}.faint{color:var(--faint);font-size:12px}
.big{font-size:30px;font-weight:680;letter-spacing:-.02em;line-height:1.1}
.up{color:var(--ok)}.down{color:var(--bad)}
/* budget */
.bud .ln{display:grid;grid-template-columns:minmax(110px,1.2fr) 2fr auto;gap:12px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line)}
.bud .ln:last-of-type{border-bottom:0}.bud .bl{font-size:13.5px}.bud .bl small{display:block;color:var(--faint);font-size:11.5px}
.bud .amt{font:600 13.5px ui-monospace,Menlo,monospace;text-align:right;min-width:78px}
input[type=range]{width:100%;accent-color:var(--accent)}
.stack{display:flex;height:10px;border-radius:999px;overflow:hidden;margin:12px 0 8px;background:var(--line)}
.stack i{display:block;height:100%}
.legend2{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted)}.legend2 i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}
.ppl{display:inline-flex;align-items:center;gap:6px;font-size:13px}.ppl button{width:24px;height:24px;border-radius:50%;border:1px solid var(--line);background:var(--surface2);color:var(--fg);cursor:pointer}
.capbar{height:6px;border-radius:999px;background:var(--line);overflow:hidden;margin-top:6px}.capbar i{display:block;height:100%;background:var(--ok)}
/* calculator */
.calc{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:560px){.calc{grid-template-columns:1fr}}
.cin label{display:flex;justify-content:space-between;font-size:12.5px;color:var(--muted);margin:6px 0 2px}
.cin input[type=number]{width:96px;border:1px solid var(--line);background:var(--surface2);color:var(--fg);border-radius:7px;padding:2px 6px;font:600 12.5px ui-monospace,Menlo,monospace;text-align:right}
.cout .o{padding:8px 0;border-bottom:1px solid var(--line)}.cout .o:last-child{border:0}.cout .o .v{font-size:22px;font-weight:660}.cout .o.main .v{font-size:30px}
/* weather */
.wx .now{display:flex;align-items:center;gap:14px}.wx .ico{font-size:44px;line-height:1}
.wx .days{display:grid;grid-template-columns:repeat(auto-fit,minmax(74px,1fr));gap:6px;margin-top:12px}
.wx .day{background:var(--surface2);border-radius:12px;padding:8px 6px;text-align:center;font-size:12.5px}.wx .day b{display:block;font-size:12px;color:var(--muted);font-weight:600}.wx .day .e{font-size:22px;margin:2px 0}
.spark{width:100%;height:64px;display:block;margin-top:8px}
/* stocks */
.stk+.stk{margin-top:10px}.rtabs{display:flex;gap:4px}.rtabs button{border:0;background:transparent;color:var(--muted);font:600 12px inherit;padding:3px 8px;border-radius:7px;cursor:pointer}.rtabs button.on{background:var(--surface2);color:var(--fg)}
.r52{position:relative;height:4px;border-radius:999px;background:var(--line);margin:4px 0 2px}.r52 i{position:absolute;top:-3px;width:10px;height:10px;border-radius:50%;background:var(--fg);transform:translateX(-50%)}
.tip{position:absolute;pointer-events:none;background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:3px 7px;font-size:11.5px;box-shadow:var(--shadow);display:none;white-space:nowrap}
/* link previews */
.lp{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.lpc{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;cursor:pointer;display:flex;flex-direction:column;transition:transform .15s}
.lpc:hover{transform:translateY(-2px)}.lpc .ph{aspect-ratio:16/10;border-radius:0}
.lpc .bd{padding:9px 11px 11px}.lpc .site{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--faint)}.lpc .site img{width:13px;height:13px;border-radius:3px}
.lpc .tt{font-weight:620;font-size:13.5px;margin:3px 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lpc .ds{font-size:12.5px;color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.lpc .rd{font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);margin-top:8px;padding-top:8px;display:none}.lpc .rd p{margin:0 0 6px}
.lpc.open .rd{display:block}.lpc .rb{margin-top:6px;border:0;background:transparent;color:var(--accent);font:600 12px inherit;cursor:pointer;padding:0}
/* email draft, files, status, apps */
.mail .hd{font-size:13px;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:8px}.mail .hd b{color:var(--fg);font-weight:600}
.mail .bdy{white-space:pre-wrap;font-size:14px}
.btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.btn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface2);color:var(--fg);border-radius:10px;padding:6px 12px;font:600 13px inherit;cursor:pointer}
.btn.pri{background:var(--fg);color:var(--surface2);border-color:var(--fg)}.btn:hover{filter:brightness(1.06)}
.file{display:flex;gap:14px;align-items:center}
.fprev{display:block;max-width:100%;max-height:420px;margin-top:12px;border-radius:10px;border:1px solid var(--line);background:#fff;cursor:pointer}
.fex{margin-top:10px}.fex summary{cursor:pointer;font-size:12.5px;color:var(--muted)}.fex pre{white-space:pre-wrap;font:12.5px/1.5 ui-monospace,Menlo,monospace;background:var(--surface2);border-radius:10px;padding:10px;margin-top:6px;max-height:260px;overflow:auto}.file .fi{width:52px;height:64px;border-radius:9px;display:flex;align-items:center;justify-content:center;font:700 12px ui-monospace,Menlo,monospace;color:#fff;flex:none}
.sts{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px}
.sti{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:9px 11px}.sti .n{font-weight:600;font-size:13px;display:flex;align-items:center;gap:7px}
.sti .n i{width:8px;height:8px;border-radius:50%;flex:none}.sti .d{font-size:12px;color:var(--muted);margin-top:2px}.sti .v{font:600 13px ui-monospace,Menlo,monospace;margin-top:3px}
.apps{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.app{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:11px;cursor:pointer;transition:transform .15s}.app:hover{transform:translateY(-2px)}
.app .e{font-size:24px}.app .n{font-weight:640;font-size:13.5px;margin-top:4px}.app .d{font-size:12px;color:var(--muted)}
/* action bar */
.acts{display:flex;gap:6px;flex-wrap:wrap;align-items:center;position:relative}
.act{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:5px 11px;font:500 12.5px inherit;cursor:pointer}
.act:hover{color:var(--fg);background:var(--surface)}
.menu{position:absolute;z-index:5;bottom:36px;background:var(--surface2);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:5px;min-width:210px;display:none}
.menu.on{display:block}.menu button{display:flex;width:100%;align-items:center;gap:8px;border:0;background:transparent;color:var(--fg);padding:7px 9px;border-radius:8px;font:500 13px inherit;cursor:pointer;text-align:left}
.menu button:hover{background:var(--surface)}.menu small{color:var(--faint);margin-left:auto}
.toast{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);background:var(--fg);color:var(--surface2);padding:6px 12px;border-radius:999px;font-size:12.5px;z-index:9;opacity:0;transition:opacity .2s}
.toast.on{opacity:1}
.mgrp{position:relative;display:inline-flex;gap:2px}.mgrp .mbtn:first-child{border-radius:999px 4px 4px 999px}.mgrp .mbtn.ic{border-radius:4px 999px 999px 4px;padding:0 8px}
.mmenu{position:absolute;z-index:6;top:36px;right:0;background:var(--surface2);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:5px;min-width:230px;display:none}
.mmenu.on{display:block}.mmenu button{display:flex;width:100%;align-items:center;gap:8px;border:0;background:transparent;color:var(--fg);padding:7px 9px;border-radius:8px;font:500 13px inherit;font-family:inherit;cursor:pointer;text-align:left}
.mmenu button:hover{background:var(--surface)}.mmenu small{color:var(--faint);margin-left:auto;font-size:11px}
.rstat{margin-top:6px;font-size:12.5px;color:var(--muted)}
.mapbox.nogl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px;overflow:visible}.mapbox.nogl .mctl,.mapbox.nogl .mstat{position:static}.mapbox.nogl .mctl.r{margin-left:auto}
.mapbox.nogl .msketch,.mapbox.nogl .mnote,.mapbox.nogl .maplist{flex:1 1 100%}.msketch{width:100%;height:auto;max-height:340px}.msketch .mslab{fill:var(--fg);paint-order:stroke;stroke:var(--surface);stroke-width:3px}.mnote{font-size:12px}
.ph.miss{display:grid;place-items:center;cursor:default}.ph.miss .mi{font-size:28px;font-weight:600;color:var(--faint);opacity:.8}
.lsheet{position:absolute;left:8px;right:8px;z-index:20;display:flex;justify-content:center}
.lsc{width:100%;max-width:520px;background:var(--surface2);color:var(--fg);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:14px;display:flex;flex-direction:column;gap:9px}
.lst{font-weight:600;font-size:14px}.lsi{width:100%;box-sizing:border-box;border:1px solid var(--line);background:var(--surface);color:var(--fg);border-radius:9px;padding:7px 9px;font:12.5px ui-monospace,monospace}
.lsh{font-size:12px;color:var(--muted);line-height:1.45}.lsb{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
</style>
<script nonce="__NONCE__">
(function(){
"use strict";
var I=window.IUI;var h=I.h,txt=I.txt,arr=I.arr,md=I.md,photo=I.photo,label=I.label,icon=I.icon,UI=I.UI,X=I.X;
var COLORS=['#4f8ef7','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16'];
/* units: block override > user/admin valve > browser locale (US, LR, MM use imperial) */
I.units=function(b){var u=String((b&&b.units)||UI.units||'auto').toLowerCase();if(u==='metric'||u==='imperial')return u;
 var l='';try{l=(navigator.languages&&navigator.languages[0])||navigator.language||'';}catch(e){}var m=/[-_]([A-Za-z]{2})\b/.exec(l);var r=m?m[1].toUpperCase():'';return (r==='US'||r==='LR'||r==='MM')?'imperial':'metric';};
function wxUnits(W,b){if(!W||W._conv)return W;var imp=I.units(b)==='imperial';var isF=/F/.test(W.unit||'');if(imp===isF){W._conv=1;return W;}
 var T=imp?function(c){return c==null?c:c*9/5+32;}:function(f){return f==null?f:(f-32)*5/9;};var S=imp?function(k){return k==null?k:k/1.609344;}:function(m){return m==null?m:m*1.609344;};
 if(W.now){W.now.t=T(W.now.t);W.now.feels=T(W.now.feels);W.now.wind=S(W.now.wind);}arr(W.hourly).forEach(function(x){x.t=T(x.t);});arr(W.daily).forEach(function(d){d.hi=T(d.hi);d.lo=T(d.lo);});
 W.unit=imp?'°F':'°C';W.wind_unit=imp?'mph':'km/h';W._conv=1;return W;}
I.wxUnits=wxUnits;
function num(v,d){v=+v;return isFinite(v)?v:(d||0);}
function money(v,cur,dec){cur=cur==null?'$':cur;var n=Math.abs(v);var s=n.toLocaleString(undefined,{minimumFractionDigits:dec||0,maximumFractionDigits:dec==null?0:dec});return (v<0?'−':'')+cur+s;}
function toast(t){var e=document.querySelector('.toast');if(!e){e=h('div','toast');document.body.appendChild(e);}e.textContent=t;e.classList.add('on');clearTimeout(e._t);e._t=setTimeout(function(){e.classList.remove('on');},1600);}
function copyText(t){function fb(){var ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();var ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();return ok;}
 if(navigator.clipboard&&navigator.clipboard.writeText){return navigator.clipboard.writeText(t).then(function(){return true;},function(){return fb();});}return Promise.resolve(fb());}
I.toast=toast;I.copyText=copyText;
function svgEl(tag,a){var e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(var k in a)e.setAttribute(k,a[k]);return e;}
/* area sparkline with hover tooltip; pts=[[x,y],...] */
function spark(pts,opt){opt=opt||{};var W=600,H=opt.h||90;var wrap=h('div','');wrap.style.position='relative';if(pts.length<2)return wrap;
 var xs=pts.map(function(p){return p[0];}),ys=pts.map(function(p){return p[1];});var x0=Math.min.apply(null,xs),x1=Math.max.apply(null,xs),y0=Math.min.apply(null,ys),y1=Math.max.apply(null,ys);if(y1===y0){y1+=1;y0-=1;}
 var pad=4;var X=function(x){return (x-x0)/((x1-x0)||1)*W;},Y=function(y){return pad+(1-(y-y0)/(y1-y0))*(H-2*pad);};
 var col=opt.color||'#4f8ef7';var svg=svgEl('svg',{viewBox:'0 0 '+W+' '+H,preserveAspectRatio:'none','class':'spark'});svg.style.height=H*0.8+'px';
 var gid='g'+Math.random().toString(36).slice(2,8);var defs=svgEl('defs',{});var lg=svgEl('linearGradient',{id:gid,x1:0,y1:0,x2:0,y2:1});lg.appendChild(svgEl('stop',{offset:'0%','stop-color':col,'stop-opacity':.28}));lg.appendChild(svgEl('stop',{offset:'100%','stop-color':col,'stop-opacity':0}));defs.appendChild(lg);svg.appendChild(defs);
 var d=pts.map(function(p,i){return (i?'L':'M')+X(p[0]).toFixed(1)+' '+Y(p[1]).toFixed(1);}).join(' ');
 svg.appendChild(svgEl('path',{d:d+' L'+W+' '+H+' L0 '+H+' Z',fill:'url(#'+gid+')'}));svg.appendChild(svgEl('path',{d:d,fill:'none',stroke:col,'stroke-width':2,'vector-effect':'non-scaling-stroke'}));
 if(opt.base!=null&&opt.base>y0&&opt.base<y1){svg.appendChild(svgEl('line',{x1:0,x2:W,y1:Y(opt.base),y2:Y(opt.base),stroke:'currentColor','stroke-opacity':.25,'stroke-dasharray':'4 4','vector-effect':'non-scaling-stroke'}));}
 var dot=svgEl('circle',{r:4,fill:col,cx:-10,cy:-10});svg.appendChild(dot);wrap.appendChild(svg);var tip=h('div','tip');wrap.appendChild(tip);
 svg.addEventListener('mousemove',function(e){var r=svg.getBoundingClientRect();var fx=(e.clientX-r.left)/r.width*W;var best=0,bd=1e18;pts.forEach(function(p,i){var dd=Math.abs(X(p[0])-fx);if(dd<bd){bd=dd;best=i;}});var p=pts[best];
  dot.setAttribute('cx',X(p[0]));dot.setAttribute('cy',Y(p[1]));tip.style.display='block';tip.textContent=(opt.fmtX?opt.fmtX(p[0]):p[0])+'  ·  '+(opt.fmtY?opt.fmtY(p[1]):p[1]);var px=X(p[0])/W*r.width;tip.style.left=Math.min(r.width-tip.offsetWidth,Math.max(0,px-tip.offsetWidth/2))+'px';tip.style.top='-6px';});
 svg.addEventListener('mouseleave',function(){tip.style.display='none';dot.setAttribute('cx',-10);});return wrap;}
I.spark=spark;
/* ---------- budget ---------- */
X.budget=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var cur=b.currency==null?'$':b.currency;var p=h('div','panel bud');w.appendChild(p);
 var people=b.people?Math.max(1,num(b.people,1)):0;var items=arr(b.items).filter(Boolean).map(function(it,i){var a=num(it.amount);var mn=it.min!=null?num(it.min):Math.round(a*0.4);var mx=it.max!=null?num(it.max):Math.max(Math.round(a*2),a+10);return {it:it,v:a,min:mn,max:mx,step:num(it.step,(mx-mn)>200?10:1),color:it.color||COLORS[i%COLORS.length]};});
 var head=h('div','row2');var tl=h('div','');tl.appendChild(txt('div','faint','Estimated total'));var tot=txt('div','big','');tl.appendChild(tot);var pp=txt('div','faint','');tl.appendChild(pp);head.appendChild(tl);
 var ppl=null,pv=null;if(people){ppl=h('div','ppl');var m=txt('button','','−'),pl=txt('button','','+');pv=txt('b','',people+' people');ppl.appendChild(m);ppl.appendChild(pv);ppl.appendChild(pl);m.onclick=function(){people=Math.max(1,people-1);upd();};pl.onclick=function(){people=Math.min(50,people+1);upd();};head.appendChild(ppl);}
 p.appendChild(head);var stack=h('div','stack');p.appendChild(stack);var leg=h('div','legend2');p.appendChild(leg);var capWrap=null,capTxt=null,capBar=null;
 if(b.cap){capWrap=h('div','');capWrap.style.marginTop='8px';capTxt=txt('div','faint','');capBar=h('div','capbar',[h('i')]);capWrap.appendChild(capTxt);capWrap.appendChild(capBar);p.appendChild(capWrap);}
 var list=h('div','');list.style.marginTop='10px';p.appendChild(list);
 items.forEach(function(x){var ln=h('div','ln');var lb=h('div','bl');lb.appendChild(document.createTextNode((x.it.icon?x.it.icon+' ':'')+(x.it.label||'')));var sub=txt('small','','');lb.appendChild(sub);ln.appendChild(lb);
  var r=document.createElement('input');r.type='range';r.min=x.min;r.max=x.max;r.step=x.step;r.value=x.v;r.oninput=function(){x.v=+r.value;upd();};ln.appendChild(r);var a=txt('div','amt','');ln.appendChild(a);x.sub=sub;x.amt=a;list.appendChild(ln);});
 function sub(x){var q=num(x.it.qty,1);var mult=(x.it.per_person&&people)?people:1;return x.v*q*mult;}
 function upd(){var t=0;items.forEach(function(x){t+=sub(x);});tot.textContent=money(t,cur);pp.textContent=people?money(t/people,cur)+' per person':(b.note||'');if(pv)pv.textContent=people+(people===1?' person':' people');
  stack.innerHTML='';leg.innerHTML='';items.forEach(function(x){var s=sub(x);var seg=h('i');seg.style.width=(t?s/t*100:0)+'%';seg.style.background=x.color;seg.title=(x.it.label||'')+': '+money(s,cur);stack.appendChild(seg);var lg=h('span');var dot=h('i');dot.style.background=x.color;lg.appendChild(dot);lg.appendChild(document.createTextNode((x.it.label||'')+' '+Math.round(t?s/t*100:0)+'%'));leg.appendChild(lg);
   var q=num(x.it.qty,1);x.sub.textContent=(q!==1||x.it.unit?money(x.v,cur)+(x.it.unit?' / '+x.it.unit:'')+(q!==1?' × '+q:''):'')+(x.it.per_person&&people?' × '+people+' ppl':'');x.amt.textContent=money(s,cur);});
  if(capWrap){var c=num(b.cap);var left=c-t;capTxt.innerHTML='';capTxt.appendChild(document.createTextNode('Budget '+money(c,cur)+' · '));var s2=txt('b',left>=0?'up':'down',left>=0?money(left,cur)+' left':money(-left,cur)+' over');capTxt.appendChild(s2);var bar=capBar.firstChild;bar.style.width=Math.min(100,t/c*100)+'%';bar.style.background=left>=0?'var(--ok)':'var(--bad)';}}
 upd();return w;};
'''
_HTML += r'''/* ---------- calculator: safe expression parser (no eval) ---------- */
var FN={min:Math.min,max:Math.max,abs:Math.abs,sqrt:Math.sqrt,pow:Math.pow,exp:Math.exp,ln:Math.log,log:function(x){return Math.log10(x);},floor:Math.floor,ceil:Math.ceil,
 round:function(x,d){var m=Math.pow(10,d||0);return Math.round(x*m)/m;},clamp:function(x,a,b){return Math.min(b,Math.max(a,x));},
 pmt:function(r,n,pv){return r?pv*r/(1-Math.pow(1+r,-n)):pv/n;},fv:function(r,n,pmt,pv){pv=pv||0;return r?pv*Math.pow(1+r,n)+pmt*(Math.pow(1+r,n)-1)/r:pv+pmt*n;},
 pv:function(r,n,pmt){return r?pmt*(1-Math.pow(1+r,-n))/r:pmt*n;},iff:function(c,a,b){return c?a:b;}};
function compile(src){var s=String(src||''),i=0;var toks=[];var re=/\s*(?:(\d+\.?\d*(?:e[+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|==|!=|[-+*\/^%(),<>]))/y;
 while(i<s.length){re.lastIndex=i;var m=re.exec(s);if(!m){if(/^\s*$/.test(s.slice(i)))break;throw new Error('bad char at '+i);}i=re.lastIndex;toks.push(m[1]!=null?{n:+m[1]}:m[2]!=null?{id:m[2]}:{op:m[3]});}
 var p=0;function peek(o){return toks[p]&&toks[p].op===o;}function take(o){if(!peek(o))throw new Error('expected '+o);p++;}
 function cmp(){var a=add();while(toks[p]&&/^(<|>|<=|>=|==|!=)$/.test(toks[p].op||'')){var o=toks[p++].op,b=add();a=(function(a,b,o){return function(v){var x=a(v),y=b(v);return +(o==='<'?x<y:o==='>'?x>y:o==='<='?x<=y:o==='>='?x>=y:o==='=='?x===y:x!==y);};})(a,b,o);}return a;}
 function add(){var a=mul();while(peek('+')||peek('-')){var o=toks[p++].op,b=mul();a=(function(a,b,o){return o==='+'?function(v){return a(v)+b(v);}:function(v){return a(v)-b(v);};})(a,b,o);}return a;}
 function mul(){var a=pw();while(peek('*')||peek('/')||peek('%')){var o=toks[p++].op,b=pw();a=(function(a,b,o){return o==='*'?function(v){return a(v)*b(v);}:o==='/'?function(v){return a(v)/b(v);}:function(v){return a(v)%b(v);};})(a,b,o);}return a;}
 function pw(){var a=un();if(peek('^')){p++;var b=pw();return function(v){return Math.pow(a(v),b(v));};}return a;}
 function un(){if(peek('-')){p++;var a=un();return function(v){return -a(v);};}if(peek('+')){p++;return un();}return prim();}
 function prim(){var t=toks[p++];if(!t)throw new Error('unexpected end');if(t.n!=null){var n=t.n;return function(){return n;};}
  if(t.op==='('){var e=cmp();take(')');return e;}
  if(t.id){var id=t.id;if(peek('(')){p++;var args=[];if(!peek(')')){args.push(cmp());while(peek(',')){p++;args.push(cmp());}}take(')');var f=FN[id==='if'?'iff':id];if(!f)throw new Error('unknown function '+id);return function(v){return f.apply(null,args.map(function(a){return a(v);}));};}
   if(id==='pi')return function(){return Math.PI;};return function(v){if(!(id in v))throw new Error('unknown '+id);return v[id];};}
  throw new Error('unexpected '+(t.op||''));}
 var f=cmp();if(p<toks.length)throw new Error('unexpected '+(toks[p].op||toks[p].id||toks[p].n));return f;}
I.compile=compile;
function fmtVal(v,f,cur,dec){if(!isFinite(v))return '—';if(f==='money')return money(v,cur,dec==null?(Math.abs(v)<100?2:0):dec);if(f==='percent')return (+v).toFixed(dec==null?2:dec)+'%';if(f==='years')return (+v).toFixed(dec==null?1:dec)+' yrs';
 return (+v).toLocaleString(undefined,{maximumFractionDigits:dec==null?2:dec});}
X.calculator=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var cur=b.currency==null?'$':b.currency;var p=h('div','panel calc');w.appendChild(p);
 var cin=h('div','cin'),cout=h('div','cout');p.appendChild(cin);p.appendChild(cout);var vals={};
 arr(b.inputs).forEach(function(inp){if(!inp||!inp.id)return;var v=num(inp.value);vals[inp.id]=v;var mn=inp.min!=null?num(inp.min):0,mx=inp.max!=null?num(inp.max):Math.max(10,v*3),st=inp.step!=null?num(inp.step):((mx-mn)/200>=1?Math.round((mx-mn)/200):((mx-mn)/200));
  var lab=h('label');lab.appendChild(document.createTextNode(inp.label||inp.id));var nb=document.createElement('input');nb.type='number';nb.value=v;nb.step=st;lab.appendChild(nb);cin.appendChild(lab);
  var r=document.createElement('input');r.type='range';r.min=mn;r.max=mx;r.step=st||'any';r.value=v;cin.appendChild(r);
  r.oninput=function(){vals[inp.id]=+r.value;nb.value=r.value;run();};nb.oninput=function(){var x=+nb.value;if(isFinite(x)){vals[inp.id]=x;if(x>=mn&&x<=mx)r.value=x;run();}};});
 var outs=arr(b.outputs).filter(function(o){return o&&o.expr;}).map(function(o,i){var el=h('div','o'+(i===0?' main':''));el.appendChild(txt('div','faint',o.label||''));var v=txt('div','v','');el.appendChild(v);if(o.note)el.appendChild(txt('div','faint',o.note));cout.appendChild(el);var f=null,err=null;try{f=compile(o.expr);}catch(e){err=e.message;}return {o:o,v:v,f:f,err:err};});
 function run(){var scope=Object.assign({},vals);outs.forEach(function(x){if(!x.f){x.v.textContent='⚠ '+x.err;return;}var r;try{r=x.f(scope);}catch(e){x.v.textContent='⚠ '+e.message;return;}if(x.o.id)scope[x.o.id]=r;x.v.textContent=fmtVal(r,x.o.format,cur,x.o.decimals);});}
 run();return w;};
/* ---------- weather (Open-Meteo, resolved server-side) ---------- */
var DOW=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
X.weather=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var W=wxUnits(b.weather,b);var p=h('div','panel wx');w.appendChild(p);
 if(!W){p.appendChild(txt('div','muted','Weather for '+(b.location||'this place')+' is unavailable right now.'));return w;}
 var top=h('div','row2');var now=h('div','now');now.appendChild(txt('div','ico',W.now.icon));var nt=h('div','');nt.appendChild(txt('div','big',Math.round(W.now.t)+W.unit));nt.appendChild(txt('div','muted',W.now.text+' · feels '+Math.round(W.now.feels)+W.unit));now.appendChild(nt);top.appendChild(now);
 var rt=h('div','');rt.style.textAlign='right';rt.appendChild(txt('div','',W.label));rt.appendChild(txt('div','faint','💧 '+W.now.rh+'%  ·  💨 '+Math.round(W.now.wind)+' '+W.wind_unit));top.appendChild(rt);p.appendChild(top);
 var hr=arr(W.hourly).filter(function(x){return x.t!=null;});if(hr.length>2){p.appendChild(spark(hr.map(function(x,i){return [i,x.t];}),{h:70,color:'#f59e0b',fmtX:function(i){return hr[i].time;},fmtY:function(v){return Math.round(v)+W.unit+(hr[Math.round(0)]&&''||'');}}));}
 var ds=h('div','days');arr(W.daily).forEach(function(d,i){var c=h('div','day');var dt=new Date(d.date+'T12:00:00');c.appendChild(txt('b','',i===0?'Today':DOW[dt.getDay()]));c.appendChild(txt('div','e',d.icon));c.title=d.text+(d.sunrise?' · sunrise '+d.sunrise+' · sunset '+d.sunset:'');
  var t=h('div','');t.appendChild(txt('span','',Math.round(d.hi)+'°'));t.appendChild(txt('span','faint',' '+Math.round(d.lo)+'°'));c.appendChild(t);if(d.p!=null)c.appendChild(txt('div','faint','💧'+d.p+'%'));ds.appendChild(c);});p.appendChild(ds);
 p.appendChild(txt('div','faint','Live · '+W.source+' · updated '+new Date(W.fetched*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})));return w;};
/* ---------- stocks / crypto / commodities (Yahoo Finance chart API) ---------- */
X.stock=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));
 arr(b.quotes).forEach(function(q){var p=h('div','panel stk');w.appendChild(p);if(q.error||q.price==null){p.appendChild(txt('div','muted',q.symbol+': quote unavailable ('+(q.error||'no data')+')'));return;}
  var ch=q.prev?q.price-q.prev:0,pc=q.prev?ch/q.prev*100:0;var cls=ch>=0?'up':'down';var dec=q.price<2?4:2;
  var top=h('div','row2');var l=h('div','');var nm=h('div','');nm.appendChild(txt('b','',q.symbol));nm.appendChild(txt('span','faint','  '+q.name+(q.exchange?' · '+q.exchange:'')));l.appendChild(nm);
  var pr=h('div','');pr.appendChild(txt('span','big',q.price.toLocaleString(undefined,{minimumFractionDigits:dec,maximumFractionDigits:dec})));pr.appendChild(txt('span','faint',' '+q.currency));l.appendChild(pr);
  l.appendChild(txt('div',cls,(ch>=0?'▲ +':'▼ ')+ch.toFixed(dec)+' ('+(pc>=0?'+':'')+pc.toFixed(2)+'%) today'));top.appendChild(l);
  var tabs=h('div','rtabs');top.appendChild(tabs);p.appendChild(top);var chartBox=h('div','');p.appendChild(chartBox);
  var keys=['1D','1M','1Y'].filter(function(k){return arr((q.series||{})[k]).length>1;});var cur=keys[0];
  function draw(){chartBox.innerHTML='';var s=arr(q.series[cur]);var first=s[0][1],last=s[s.length-1][1];var up=cur==='1D'?ch>=0:last>=first;
   chartBox.appendChild(spark(s,{h:110,color:up?'#10b981':'#ef4444',base:cur==='1D'?q.prev:null,fmtX:function(t){var d=new Date(t*1000);return cur==='1D'?d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}):d.toLocaleDateString([],{month:'short',day:'numeric',year:cur==='1Y'?'2-digit':undefined});},fmtY:function(v){return v.toFixed(dec)+' '+q.currency;}}));
   tabs.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x.textContent===cur);});}
  keys.forEach(function(k){var bt=txt('button','',k);bt.onclick=function(){cur=k;draw();};tabs.appendChild(bt);});if(cur)draw();
  if(q.low52&&q.high52){var r=h('div','');r.style.marginTop='6px';var pos=Math.max(0,Math.min(100,(q.price-q.low52)/((q.high52-q.low52)||1)*100));var bar=h('div','r52',[h('i')]);bar.firstChild.style.left=pos+'%';
   var lbs=h('div','row2 faint');lbs.appendChild(txt('span','','52-wk low '+q.low52.toFixed(dec)));lbs.appendChild(txt('span','','high '+q.high52.toFixed(dec)));r.appendChild(bar);r.appendChild(lbs);p.appendChild(r);}
  p.appendChild(txt('div','faint','Delayed quote · '+q.source+' · '+(q.time?new Date(q.time*1000).toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'')+' · not investment advice'));});
 return w;};
'''
_HTML += r'''/* ---------- page preview cards ---------- */
X.links=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','lp');
 arr(b.items).forEach(function(it){if(!it||!it.url)return;var c=h('div','lpc');var img=it.shot||it.og_image;c.appendChild(photo({candidates:img?[{src:img}]:[],caption:''},'',{noText:true}));
  var bd=h('div','bd');var site=h('div','site');var fi=document.createElement('img');fi.src=I.fav(it.url);fi.alt='';fi.onerror=function(){fi.remove();};site.appendChild(fi);site.appendChild(document.createTextNode((it.site||I.domain(it.url))+(it.published?' · '+it.published:'')));bd.appendChild(site);
  bd.appendChild(txt('div','tt',it.title||I.domain(it.url)));if(it.description||it.note)bd.appendChild(txt('div','ds',it.note||it.description));
  var rd=arr(it.reader);if(rd.length){var box=h('div','rd');rd.forEach(function(t){box.appendChild(txt('p','',t));});var rb=txt('button','rb','Reader view');rb.onclick=function(e){e.stopPropagation();c.classList.toggle('open');rb.textContent=c.classList.contains('open')?'Hide reader':'Reader view';};bd.appendChild(rb);bd.appendChild(box);}
  c.appendChild(bd);c.addEventListener('click',function(e){if(!e.target.closest('.rb,.rd'))I.openLink(it.url);});g.appendChild(c);});
 w.appendChild(g);return w;};
/* ---------- Gmail draft ---------- */
function gmailUrl(o){var q='https://mail.google.com/mail/?view=cm&fs=1';if(o.to)q+='&to='+encodeURIComponent(o.to);if(o.cc)q+='&cc='+encodeURIComponent(o.cc);if(o.bcc)q+='&bcc='+encodeURIComponent(o.bcc);
 q+='&su='+encodeURIComponent(o.subject||'');var body=String(o.body||'');if(body.length>1800)body=body.slice(0,1790)+'\n…';return q+'&body='+encodeURIComponent(body);}
I.gmailUrl=gmailUrl;
X.email=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var p=h('div','panel mail');var hd=h('div','hd');
 [['To',b.to],['Cc',b.cc],['Subject',b.subject]].forEach(function(r){if(!r[1])return;var d=h('div','');d.appendChild(document.createTextNode(r[0]+': '));d.appendChild(txt('b','',r[1]));hd.appendChild(d);});p.appendChild(hd);p.appendChild(txt('div','bdy',b.body||''));
 var bt=h('div','btns');var g=h('button','btn pri',[icon('mail'),txt('span','','Open in Gmail')]);g.onclick=function(){I.openLink(gmailUrl(b));};bt.appendChild(g);
 var c=h('button','btn',[icon('copy'),txt('span','','Copy text')]);c.onclick=function(){copyText((b.subject?'Subject: '+b.subject+'\n\n':'')+(b.body||'')).then(function(){toast('Copied');});};bt.appendChild(c);
 var m=h('button','btn',[txt('span','','Other mail app')]);m.onclick=function(){var u='mailto:'+encodeURIComponent(b.to||'')+'?subject='+encodeURIComponent(b.subject||'')+'&body='+encodeURIComponent(String(b.body||'').slice(0,1800));try{parent.window.open(u,'_blank');}catch(e){window.open(u,'_blank');}};bt.appendChild(m);
 p.appendChild(bt);w.appendChild(p);return w;};
/* ---------- status board (e.g. homelab services reported by a status tool) ---------- */
var STC={ok:'#10b981',up:'#10b981',healthy:'#10b981',warn:'#f59e0b',warning:'#f59e0b',degraded:'#f59e0b',down:'#ef4444',error:'#ef4444',critical:'#ef4444',info:'#4f8ef7',unknown:'#8f8f8f'};
X.status=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var items=arr(b.items).filter(Boolean);var cnt={};items.forEach(function(s){var st=String(s.state||'unknown').toLowerCase();var k=/ok|up|healthy/.test(st)?'healthy':/warn|degraded/.test(st)?'warning':/down|error|critical/.test(st)?'down':'other';cnt[k]=(cnt[k]||0)+1;});
 w.appendChild(txt('div','faint',Object.keys(cnt).map(function(k){return cnt[k]+' '+k;}).join(' · ')+(b.updated?' · updated '+b.updated:'')));var g=h('div','sts');g.style.marginTop='6px';
 items.forEach(function(s){var c=h('div','sti');var n=h('div','n');var d=h('i');d.style.background=STC[String(s.state||'unknown').toLowerCase()]||STC.unknown;n.appendChild(d);n.appendChild(document.createTextNode(s.name||''));c.appendChild(n);if(s.detail)c.appendChild(txt('div','d',s.detail));if(s.value!=null)c.appendChild(txt('div','v',s.value));g.appendChild(c);});
 w.appendChild(g);return w;};
/* ---------- Craft apps launcher + file results ---------- */
function craftWeb(app){return UI.craft_web?UI.craft_web.replace(/\/$/,'')+'/'+app+'/':'';}
X.apps=function(b){var w=h('div','blk');if(b.title)w.appendChild(label(b.title));var g=h('div','apps');var list=arr(UI.apps);var only=arr(b.apps);
 list.filter(function(a){return !only.length||only.indexOf(a.id)>=0;}).forEach(function(a){var c=h('div','app');c.appendChild(txt('div','e',a.emoji));c.appendChild(txt('div','n',a.name));c.appendChild(txt('div','d',a.desc));c.title='Open '+a.name+' (web)';c.onclick=function(){I.openLink(craftWeb(a.id));};g.appendChild(c);});
 w.appendChild(g);var bt=h('div','btns');if(UI.craft_desktop){var d=h('button','btn pri',[icon('ext'),txt('span','','Craft desktop (all apps)')]);d.onclick=function(){I.openLink(UI.craft_desktop);};bt.appendChild(d);}
 if(UI.craft_web){var l=h('button','btn',[txt('span','','ArtCraft Launcher')]);l.onclick=function(){I.openLink(craftWeb('launcher'));};bt.appendChild(l);}w.appendChild(bt);return w;};
var FCOL={docx:'#2b579a',odt:'#2b579a',rtf:'#2b579a',pdf:'#d93025',xlsx:'#217346',csv:'#217346',pptx:'#d24726',gif:'#8b5cf6',md:'#555',html:'#e44d26'};
X.file=function(b){var w=h('div','blk');var p=h('div','panel');var f=h('div','file');var fi=txt('div','fi',String(b.format||'').toUpperCase());fi.style.background=FCOL[b.format]||'#555';f.appendChild(fi);
 var t=h('div','');t.appendChild(txt('div','',b.name||'file'));t.style.fontWeight='620';var meta=[b.size?(b.size>1e6?(b.size/1e6).toFixed(1)+' MB':Math.max(1,Math.round(b.size/1e3))+' KB'):'',b.maker?'made with '+b.maker:''].filter(Boolean).join(' · ');t.appendChild(txt('div','faint',meta));if(b.note)t.appendChild(txt('div','faint',b.note));if(b.mode==='read')t.appendChild(txt('div','faint','Opened with '+(b.app_name||'Craft')));if(b.opened)t.appendChild(txt('div','up','Opened in '+b.app_name+' on the Craft desktop'));f.appendChild(t);p.appendChild(f);
 if(b.preview){var pv=document.createElement('img');pv.src=b.preview;pv.alt='Preview of '+(b.name||'file');pv.className='fprev';pv.onclick=function(){I.openLink(b.url||'');};p.appendChild(pv);}
 if(b.excerpt){var ex=h('details','fex');ex.appendChild(txt('summary','','Contents'));ex.appendChild(txt('pre','',b.excerpt+(b.excerpt.length>=1500?'\n…':'')));p.appendChild(ex);}
 var bt=h('div','btns');if(b.url){var dl=h('button','btn pri',[icon('dl'),txt('span','','Download')]);dl.onclick=function(){I.openLink(b.url);};bt.appendChild(dl);}
 if(UI.craft_desktop&&b.app){var d=h('button','btn',[icon('ext'),txt('span','',(b.opened?'Go to ':'Open ')+(b.app_name||'Craft')+' desktop')]);d.onclick=function(){I.openLink(UI.craft_desktop);};bt.appendChild(d);}
 if(b.app&&craftWeb(b.app)){var wb=h('button','btn',[txt('span','',(b.app_name||'Craft')+' web')]);wb.title='Opens the web app; drag the downloaded file in';wb.onclick=function(){I.openLink(craftWeb(b.app));};bt.appendChild(wb);}
 p.appendChild(bt);if(b.inbox)p.appendChild(txt('div','faint','Also saved to ~/Inbox on the Craft desktop.'));w.appendChild(p);return w;};
X.note=function(b){var w=h('div','blk');var p=h('div','panel');var r=h('div','row2');var l=h('div','');l.appendChild(txt('div','faint','Saved to Notes'));l.appendChild(txt('div','',b.name||b.title||'Note'));l.firstChild.nextSibling.style.fontWeight='620';r.appendChild(l);
 if(b.url){var o=h('button','btn pri',[icon('note'),txt('span','','Open note')]);o.onclick=function(){I.openLink(b.url);};r.appendChild(o);}p.appendChild(r);w.appendChild(p);return w;};
'''
_HTML += r'''/* ---------- card -> markdown (copy, Gmail) ---------- */
function plain(s){return String(s==null?'':s).replace(/\[(\d{1,2})\]/g,'').replace(/\*\*([^*]+)\*\*/g,'$1');}
function cardText(S){var L=[];if(S.title)L.push('# '+S.title);if(S.subtitle)L.push(S.subtitle);
 arr(S.blocks).forEach(function(b){if(!b)return;var it=arr(b.items).filter(Boolean);if(b.title)L.push('\n## '+b.title);
  switch(b.type){case 'text':case 'quote':L.push(plain(b.md||b.text)+(b.by?'\n— '+b.by:''));break;case 'callout':L.push((b.title?b.title+': ':'')+plain(b.md));break;case 'hero':L.push(plain((b.title||'')+' '+(b.md||'')));break;
   case 'places':case 'cards':it.forEach(function(x){L.push('- '+(x.name||x.title||'')+[x.rating?' ★'+x.rating:'',x.price?' · '+x.price:''].join('')+(x.description?' — '+x.description:'')+(x.url?' ('+x.url+')':''));});break;
   case 'map':var d0=null;arr(b.places).forEach(function(p,i){if(p.day&&p.day!==d0){d0=p.day;L.push('\n'+p.day+':');}L.push((p.icon?p.icon+' ':'• ')+(p.name||'')+(p.time?' — '+p.time:'')+(p.note?': '+p.note:''));});var gm=I.gmapsUrl&&I.gmapsUrl(arr(b.places).filter(function(p){return p.lat!=null;}),(b.route_geo||{}).mode);if(gm)L.push('Route: '+gm);break;
   case 'timeline':it.forEach(function(x){L.push('- '+(x.time?x.time+' ':'')+(x.title||'')+(x.detail?' — '+x.detail:''));});break;
   case 'steps':it.forEach(function(x,i){L.push((i+1)+'. '+(x.title||x)+(x.detail?' — '+x.detail:''));});break;
   case 'table':L.push(arr(b.columns).join(' | '));arr(b.rows).forEach(function(r){L.push(arr(r).map(plain).join(' | '));});break;
   case 'stats':it.forEach(function(s){L.push('- '+s.label+': '+s.value+(s.delta?' ('+s.delta+')':''));});break;
   case 'compare':it.forEach(function(c){L.push(c.title+':');arr(c.points).forEach(function(p){L.push('  - '+p);});if(c.verdict)L.push('  → '+c.verdict);});break;
   case 'budget':var t=0,cur=b.currency==null?'$':b.currency;it.forEach(function(x){var s=num(x.amount)*num(x.qty,1)*((x.per_person&&b.people)?b.people:1);t+=s;L.push('- '+x.label+': '+money(s,cur));});L.push('Total: '+money(t,cur));break;
   case 'weather':if(b.weather){var W=wxUnits(b.weather,b);L.push(W.label+' now: '+Math.round(W.now.t)+W.unit+', '+W.now.text);arr(W.daily).forEach(function(d){L.push('- '+d.date+': '+d.text+' '+Math.round(d.hi)+'/'+Math.round(d.lo)+W.unit);});}break;
   case 'stock':arr(b.quotes).forEach(function(q){if(q.price!=null)L.push('- '+q.symbol+': '+q.price+' '+q.currency+(q.prev?' ('+((q.price-q.prev)/q.prev*100).toFixed(2)+'%)':''));});break;
   case 'links':it.forEach(function(x){L.push('- '+(x.title||x.url)+': '+x.url);});break;
   case 'email':L.push('To: '+(b.to||'')+'\nSubject: '+(b.subject||'')+'\n\n'+(b.body||''));break;
   case 'chart':arr(b.series).forEach(function(s){L.push('- '+s.name+': '+arr(b.labels).map(function(l,i){return l+'='+arr(s.data)[i];}).join(', '));});break;}});
 if(I.SRC.length){L.push('\nSources:');I.SRC.forEach(function(s,i){L.push((i+1)+'. '+(s.title||'')+' '+s.url);});}return L.join('\n').replace(/\n{3,}/g,'\n\n').trim();}
I.cardText=cardText;
/* ---------- calendar ---------- */
function pad(n){return (n<10?'0':'')+n;}
function parseWhen(date,time){var s=String(date||'');var m=s.match(/(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?/);if(!m)return null;var hh=m[4]!=null?+m[4]:null,mm=m[5]!=null?+m[5]:0;
 var t=String(time||'').match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?/i);if(hh==null&&t){hh=+t[1];mm=t[2]?+t[2]:0;var ap=(t[3]||'').toLowerCase();if(ap.indexOf('p')===0&&hh<12)hh+=12;if(ap.indexOf('a')===0&&hh===12)hh=0;}
 return {y:+m[1],mo:+m[2],d:+m[3],h:hh,mi:mm};}
function calStamp(w,addMin){if(w.h==null){var dt=new Date(Date.UTC(w.y,w.mo-1,w.d+(addMin?1:0)));return dt.getUTCFullYear()+pad(dt.getUTCMonth()+1)+pad(dt.getUTCDate());}
 var d=new Date(Date.UTC(w.y,w.mo-1,w.d,w.h,w.mi+(addMin||0)));return d.getUTCFullYear()+pad(d.getUTCMonth()+1)+pad(d.getUTCDate())+'T'+pad(d.getUTCHours())+pad(d.getUTCMinutes())+'00';}
function events(S){var ev=[];arr(S.events).forEach(function(e){if(!e)return;var s=parseWhen(e.start||e.date,e.time);if(!s)return;var en=e.end?parseWhen(e.end,e.end_time):null;ev.push({title:e.title||S.title,s:s,e:en,dur:num(e.duration_min,60),loc:e.location||'',det:e.details||''});});
 if(!ev.length)arr(S.blocks).forEach(function(b){if(b&&b.type==='timeline')arr(b.items).forEach(function(it){if(!it||!it.date)return;var s=parseWhen(it.date,it.time);if(s)ev.push({title:it.title||'',s:s,e:null,dur:num(it.duration_min,60),loc:it.place||it.location||'',det:it.detail||''});});});return ev;}
function gcal(e,tz){var st=calStamp(e.s,0),en=e.e?calStamp(e.e,0):calStamp(e.s,e.s.h==null?1:e.dur);return 'https://calendar.google.com/calendar/render?action=TEMPLATE&text='+encodeURIComponent(e.title)+'&dates='+st+'/'+en+(e.s.h!=null&&tz?'&ctz='+encodeURIComponent(tz):'')+(e.loc?'&location='+encodeURIComponent(e.loc):'')+(e.det?'&details='+encodeURIComponent(e.det):'');}
function ics(evs,tz){var esc=function(s){return String(s||'').replace(/([,;\\])/g,'\\$1').replace(/\n/g,'\\n');};var L=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Frontier UI//EN','CALSCALE:GREGORIAN'];
 evs.forEach(function(e,i){var st=calStamp(e.s,0),en=e.e?calStamp(e.e,0):calStamp(e.s,e.s.h==null?1:e.dur);var tzp=e.s.h!=null&&tz?';TZID='+tz:(e.s.h==null?';VALUE=DATE':'');L.push('BEGIN:VEVENT','UID:iui-'+Date.now()+'-'+i+'@frontier-ui','DTSTAMP:'+new Date().toISOString().replace(/[-:]/g,'').slice(0,15)+'Z','DTSTART'+tzp+':'+st,'DTEND'+tzp+':'+en,'SUMMARY:'+esc(e.title));if(e.loc)L.push('LOCATION:'+esc(e.loc));if(e.det)L.push('DESCRIPTION:'+esc(e.det));L.push('END:VEVENT');});
 L.push('END:VCALENDAR');return L.join('\r\n');}
function download(name,text,mime){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:mime}));a.download=name;document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},2000);}
/* ---------- action bar ---------- */
I.actions=function(S){if(S.actions===false||UI.actions===false)return null;var w=h('div','blk');var bar=h('div','acts');w.appendChild(bar);var title=S.title||'this card';var id=UI.card||'';var tz=S.timezone||(Intl.DateTimeFormat().resolvedOptions().timeZone)||'';
 function act(ic,lab,fn){var b=h('button','act',[icon(ic),txt('span','',lab)]);b.onclick=fn;bar.appendChild(b);return b;}
 function menu(anchor,items){var m=h('div','menu');items.forEach(function(it){var b=h('button','',[txt('span','',it[0])]);if(it[2])b.appendChild(txt('small','',it[2]));b.onclick=function(e){e.stopPropagation();m.classList.remove('on');it[1]();};m.appendChild(b);});bar.appendChild(m);
  anchor.onclick=function(e){e.stopPropagation();var on=!m.classList.contains('on');document.querySelectorAll('.menu.on').forEach(function(x){x.classList.remove('on');});if(on){m.style.left=anchor.offsetLeft+'px';m.classList.add('on');}};document.addEventListener('click',function(){m.classList.remove('on');});return m;}
 act('copy','Copy',function(){copyText(cardText(S)).then(function(ok){toast(ok?'Copied to clipboard':'Copy blocked by the browser');});});
 act('mail','Email',function(){I.openLink(gmailUrl({subject:title,body:cardText(S),to:S.email_to||''}));}).title='Compose in Gmail';
 var ev=events(S);if(ev.length){var cb=act('cal',ev.length>1?'Add to calendar ('+ev.length+')':'Add to calendar',null);if(ev.length===1){cb.onclick=function(){I.openLink(gcal(ev[0],tz));};}
  else{menu(cb,ev.slice(0,12).map(function(e){return [e.title,function(){I.openLink(gcal(e,tz));},e.s.mo+'/'+e.s.d+(e.s.h!=null?' '+pad(e.s.h)+':'+pad(e.s.mi):'')];}).concat([['Download all as .ics',function(){download((title||'events').replace(/[^\w -]+/g,'')+'.ics',ics(ev,tz),'text/calendar');},'Apple/Outlook']]));}}
 var ask=function(fmt,lab,open){I.sendPrompt('Export the Frontier UI card “'+title+'”'+(id?' (card id: '+id+')':'')+' as a '+lab+' file'+(open?' and open it in the Craft desktop':'')+'.');};
 var eb=act('doc','Export',null);eb.appendChild(icon('chev'));
 menu(eb,[['Word document',function(){ask('docx','Word (.docx)');},'.docx · WordCraft'],['PDF',function(){ask('pdf','PDF');},'.pdf'],['Excel spreadsheet',function(){ask('xlsx','Excel (.xlsx)');},'.xlsx · GridCraft'],['PowerPoint deck',function(){ask('pptx','PowerPoint (.pptx)');},'.pptx · DeckCraft'],['Open as a deck in DeckCraft',function(){ask('pptx','PowerPoint (.pptx)',true);},'desktop']]);
 act('note','Save to Notes',function(){I.sendPrompt('Save the Frontier UI card “'+title+'”'+(id?' (card id: '+id+')':'')+' to my Notes.');});
 return w;};
})();
</script>
'''
