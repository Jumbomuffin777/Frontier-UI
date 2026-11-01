

_HTML = r'''<!DOCTYPE html>
<html lang="en" data-theme="__THEME__" class="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-__NONCE__' __CDNHOST__; style-src 'unsafe-inline' __CDNHOST__; img-src https: http: data: blob:; connect-src https: __TILESHOST__; worker-src blob:; child-src blob:; font-src https: data:; base-uri 'none'; form-action 'none'">
<link rel="stylesheet" href="__CDN__/dist/maplibre-gl.css">
<style>
:root{--fg:#0d0d0d;--muted:#5d5d5d;--faint:#8f8f8f;--bg:transparent;--surface:#f4f4f5;--surface2:#ffffff;--line:rgba(0,0,0,.09);--accent:#0b6bcb;--ok:#15803d;--bad:#b91c1c;--warn:#b45309;--shadow:0 1px 2px rgba(0,0,0,.06),0 4px 14px rgba(0,0,0,.06);--route:#111;--routecase:#fff;--pin:#fff;--pinfg:#111;--chip:#ececee}
html.dark{--fg:#ececec;--muted:#a3a3a3;--faint:#7a7a7a;--surface:#232325;--surface2:#2b2b2e;--line:rgba(255,255,255,.09);--accent:#6cb4ff;--ok:#4ade80;--bad:#f87171;--warn:#fbbf24;--shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.35);--route:#f2f2f2;--routecase:#1c1d1f;--pin:#1f2023;--pinfg:#f2f2f2;--chip:#333336}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:transparent;color:var(--fg);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
body{padding:2px 2px 6px;overflow:hidden}
#app{max-width:780px}
.blk{margin:0 0 18px;animation:rise .38s ease}
@keyframes rise{from{transform:translateY(5px)}to{transform:none}}
@media (prefers-reduced-motion:reduce){.blk{animation:none}}
h1.t{font-size:18px;font-weight:650;letter-spacing:-.01em;margin-bottom:4px}
.sub{color:var(--muted);font-size:14px;margin-bottom:14px}
.h2{font-size:15px;font-weight:620;margin:0 0 8px}
.prose p{margin:0 0 10px}.prose p:last-child{margin:0}
.prose strong{font-weight:640}.prose a{color:var(--accent);text-decoration:none}.prose a:hover{text-decoration:underline}
.prose ul,.prose ol{margin:4px 0 10px 20px}.prose li{margin:2px 0}
.prose code{font:13px ui-monospace,Menlo,monospace;background:var(--surface);padding:1px 5px;border-radius:5px}
.cite{display:inline-flex;align-items:center;gap:4px;vertical-align:1px;margin-left:3px;padding:1px 7px 1px 4px;border-radius:999px;background:var(--chip);color:var(--muted);font-size:11px;line-height:17px;cursor:pointer;white-space:nowrap;max-width:170px;overflow:hidden;text-overflow:ellipsis;border:0}
.cite img{width:12px;height:12px;border-radius:3px}
.cite:hover{color:var(--fg)}
/* images */
.gal{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.gal.n1{grid-template-columns:1fr}.gal.n2{grid-template-columns:1fr 1fr}
.gal.scroll{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none}.gal.scroll::-webkit-scrollbar{display:none}
.gal.scroll .ph{flex:0 0 calc(33.333% - 6px);scroll-snap-align:start}
.ph{position:relative;aspect-ratio:1.26;border-radius:14px;overflow:hidden;background:var(--surface);cursor:zoom-in}
.gal.n1 .ph{aspect-ratio:2}
.ph img{width:100%;height:100%;object-fit:cover;display:block;opacity:0;transition:opacity .35s,transform .5s}
.ph img.ok{opacity:1}.ph:hover img.ok{transform:scale(1.035)}
.ph .bm{position:absolute;top:8px;right:8px;width:26px;height:26px;border-radius:8px;background:rgba(0,0,0,.28);backdrop-filter:blur(6px);display:grid;place-items:center;color:#fff;opacity:.9}
.ph .cap{position:absolute;left:0;right:0;bottom:0;padding:18px 10px 8px;font-size:12px;color:#fff;background:linear-gradient(transparent,rgba(0,0,0,.55));opacity:0;transition:opacity .2s}
.ph:hover .cap{opacity:1}
.ph.miss{cursor:default;display:grid;place-items:center;text-align:center;padding:12px;color:var(--muted);font-size:13px;background:linear-gradient(135deg,var(--surface),var(--surface2))}
.shimmer{position:absolute;inset:0;background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.08) 50%,transparent 70%);background-size:200% 100%;animation:sh 1.3s linear infinite}
html:not(.dark) .shimmer{background-image:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.6) 50%,transparent 70%)}
@keyframes sh{to{background-position:-200% 0}}
.wrap{position:relative}
.arrow{position:absolute;top:50%;transform:translateY(-50%);width:30px;height:30px;border-radius:50%;border:0;background:var(--surface2);color:var(--fg);box-shadow:var(--shadow);cursor:pointer;display:none;place-items:center;z-index:3}
.wrap:hover .arrow.on{display:grid}.arrow.l{left:-8px}.arrow.r{right:-8px}
/* lightbox */
.lb{position:fixed;inset:0;background:rgba(0,0,0,.82);display:flex;align-items:center;justify-content:center;z-index:50;flex-direction:column;gap:10px;padding:16px;cursor:zoom-out}
.lb img{max-width:100%;max-height:82%;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.5)}
.lb .lbc{color:#ddd;font-size:13px;text-align:center}.lb a{color:#9cc9ff}
/* map */
.mapbox{position:relative;border-radius:16px;overflow:hidden;background:var(--surface);box-shadow:inset 0 0 0 1px var(--line);transition:height .35s ease}
.mapbox .maplibregl-map{position:absolute;inset:0}
.mctl{position:absolute;top:10px;z-index:4;display:flex;gap:6px}
.mctl.l{left:10px}.mctl.r{right:10px}
.mbtn{height:30px;padding:0 10px;border-radius:999px;border:0;background:var(--surface2);color:var(--fg);box-shadow:var(--shadow);font:12.5px/30px inherit;font-family:inherit;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.mbtn.ic{width:30px;padding:0;justify-content:center}
select.mbtn{appearance:none;padding-right:26px;background-image:linear-gradient(45deg,transparent 50%,currentColor 50%),linear-gradient(135deg,currentColor 50%,transparent 50%);background-position:calc(100% - 13px) 13px,calc(100% - 9px) 13px;background-size:4px 4px;background-repeat:no-repeat}
.mstat{position:absolute;left:10px;bottom:10px;z-index:4;font-size:12px;padding:5px 10px;border-radius:999px;background:var(--surface2);box-shadow:var(--shadow);color:var(--muted)}
.pin{display:flex;flex-direction:column;align-items:center;cursor:pointer;transition:opacity .2s}
.pin .dot{width:30px;height:30px;border-radius:50%;background:var(--pin);color:var(--pinfg);display:grid;place-items:center;font-size:15px;font-weight:650;box-shadow:0 1px 3px rgba(0,0,0,.25),0 0 0 2px var(--routecase);transition:transform .18s}
.pin .lab{margin-top:3px;font-size:11.5px;font-weight:600;color:var(--fg);white-space:nowrap;text-shadow:0 0 3px var(--routecase),0 0 3px var(--routecase),0 0 2px var(--routecase)}
.pin.sel .dot,.pin:hover .dot{transform:scale(1.18)}
.pin.sel .dot{background:var(--fg);color:var(--routecase)}
.pin.dim{opacity:.25}
.mpop{position:absolute;z-index:5;left:50%;bottom:12px;transform:translateX(-50%);max-width:88%;background:var(--surface2);border-radius:14px;box-shadow:var(--shadow);padding:10px 14px;font-size:13px;display:none}
.mpop b{display:block;font-size:14px}.mpop span{color:var(--muted)}
.maplibregl-ctrl-attrib{font-size:10px!important;background:transparent!important;opacity:.7}
html.dark .maplibregl-ctrl-attrib a{color:#aaa!important}
.maplist{display:flex;flex-wrap:wrap;gap:6px}
/* cards */
.cards{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;padding:2px}
.cards::-webkit-scrollbar{display:none}
.card{flex:0 0 232px;scroll-snap-align:start;border-radius:16px;background:var(--surface);overflow:hidden;cursor:default;box-shadow:inset 0 0 0 1px var(--line);transition:transform .18s}
.card.link{cursor:pointer}.card.link:hover{transform:translateY(-2px)}
.card .ph{border-radius:0;aspect-ratio:1.45}
.card .cb{padding:10px 12px 12px}
.card .nm{font-weight:620;font-size:14.5px;line-height:1.3}
.card .meta{color:var(--muted);font-size:12.5px;margin-top:2px}
.card .ds{font-size:13px;margin-top:6px;color:var(--fg);opacity:.9;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px}
.tag{font-size:11px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--muted)}
.star{color:#f5a524}
/* timeline */
.tl{position:relative}
.ti{display:grid;grid-template-columns:74px 18px 1fr;gap:0 10px;padding:6px 6px;border-radius:12px;cursor:default}
.ti.go{cursor:pointer}.ti.go:hover,.ti.hl{background:var(--surface)}
.ti .tm{color:var(--muted);font-size:12.5px;text-align:right;padding-top:2px;font-variant-numeric:tabular-nums}
.ti .rail{position:relative;display:flex;justify-content:center}
.ti .rail:before{content:"";position:absolute;top:0;bottom:-12px;width:2px;background:var(--line)}
.ti:last-child .rail:before{bottom:50%}
.ti .bul{position:relative;margin-top:5px;width:12px;height:12px;border-radius:50%;background:var(--surface2);box-shadow:0 0 0 2px var(--fg)}
.ti .tt{font-weight:600;font-size:14.5px}
.ti .td{color:var(--muted);font-size:13.5px}
.ti .tbody{display:flex;gap:10px;align-items:flex-start}
.ti .thumb{flex:0 0 56px;height:56px;border-radius:10px;overflow:hidden;position:relative;background:var(--surface)}
.ti .thumb img{width:100%;height:100%;object-fit:cover}
/* table */
.tbl{overflow-x:auto;border-radius:14px;box-shadow:inset 0 0 0 1px var(--line)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{font-weight:560;color:var(--muted);text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap;font-size:12.5px}
td{padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}td:first-child{font-weight:560}
tbody tr:hover td{background:var(--surface)}
/* stats */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
.st{background:var(--surface);border-radius:14px;padding:12px 14px}
.st .sl{color:var(--muted);font-size:12.5px}.st .sv{font-size:22px;font-weight:650;letter-spacing:-.01em;margin-top:2px}
.st .sd{font-size:12.5px;margin-top:2px}.up{color:var(--ok)}.down{color:var(--bad)}
/* chart */
.chart{background:var(--surface);border-radius:14px;padding:12px 12px 8px}
.chart svg{width:100%;height:auto;display:block;overflow:visible}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:2px 4px 6px}
.legend i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:5px;vertical-align:-1px}
/* callout */
.co{display:flex;gap:10px;padding:12px 14px;border-radius:14px;background:var(--surface);position:relative;overflow:hidden}
.co:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
.co.warning:before{background:var(--warn)}.co.danger:before{background:var(--bad)}.co.tip:before{background:var(--ok)}
.co .ci{font-size:16px;line-height:22px}.co .ct{font-weight:620;font-size:14px;margin-bottom:2px}.co .prose{font-size:14px}
/* compare */
.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}
.cmpc{background:var(--surface);border-radius:14px;padding:12px 14px;display:flex;flex-direction:column}
.cmpc .h{font-weight:620;margin-bottom:6px}
.cmpc ul{list-style:none;font-size:13.5px}.cmpc li{padding:3px 0 3px 20px;position:relative}
.cmpc li:before{content:"✓";position:absolute;left:2px;color:var(--ok);font-weight:700}
.cmpc li.neg:before{content:"–";color:var(--bad)}
.cmpc .v{margin-top:auto;padding-top:8px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
/* steps */
.steps{counter-reset:s}
.step{display:flex;gap:12px;padding:6px 0}
.step .n{flex:0 0 26px;height:26px;border-radius:50%;background:var(--fg);color:var(--routecase);display:grid;place-items:center;font-size:13px;font-weight:650}
.step .tt{font-weight:600}.step .td{color:var(--muted);font-size:13.5px}
/* hero */
.hero{position:relative;border-radius:18px;overflow:hidden;aspect-ratio:2.2;background:var(--surface)}
.hero .ph{position:absolute;inset:0;border-radius:0;aspect-ratio:auto;cursor:default}
.hero .ov{position:absolute;inset:0;background:linear-gradient(180deg,transparent 35%,rgba(0,0,0,.72));display:flex;flex-direction:column;justify-content:flex-end;padding:16px 18px;color:#fff}
.hero .eb{font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;opacity:.85}.hero .ht{font-size:22px;font-weight:680;letter-spacing:-.01em}.hero .prose{color:#eee;font-size:14px}
.quote{border-left:3px solid var(--fg);padding:4px 0 4px 14px;font-size:16px;font-style:italic}.quote .by{font-style:normal;color:var(--muted);font-size:13px;margin-top:4px}
/* sources + followups */
.srcs{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}
.src{flex:0 0 190px;background:var(--surface);border-radius:12px;padding:9px 11px;cursor:pointer;border:0;text-align:left;color:var(--fg);font-family:inherit}
.src:hover{background:var(--chip)}
.src .d{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)}.src .d img{width:14px;height:14px;border-radius:3px}
.src .s{font-size:13px;margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.fu{display:flex;flex-direction:column}
.fu button{display:flex;align-items:center;gap:10px;width:100%;text-align:left;border:0;background:transparent;color:var(--fg);font:14px/1.4 inherit;font-family:inherit;padding:9px 6px;border-top:1px solid var(--line);cursor:pointer;border-radius:0}
.fu button:hover{background:var(--surface);border-radius:10px}
.fu button svg{flex:0 0 auto;color:var(--muted)}
.lbl{font-size:12.5px;color:var(--muted);font-weight:560;margin:0 0 6px;text-transform:none}
</style>
</head>
<body>
<div id="app"></div>
<script type="application/json" id="spec">__SPEC__</script>
'''
