

_HTML += r'''SVG.ext='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>';
SVG.copy='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/></svg>';
SVG.mail='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>';
SVG.cal='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>';
SVG.doc='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/></svg>';
SVG.note='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/></svg>';
SVG.dl='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>';
SVG.chev='<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>';
window.IUI={S:S,app:app,SRC:SRC,h:h,txt:txt,arr:arr,md:md,photo:photo,scroller:scroller,label:label,icon:icon,SVG:SVG,isDark:isDark,openLink:openLink,sendPrompt:sendPrompt,reportHeight:reportHeight,fav:fav,domain:domain,esc:esc,
 CDN:'__CDN__',NONCE:'__NONCE__',UI:(S&&S._ui)||{},X:{}};
})();
</script>
'''
_HTML = _HTML.replace(' onerror="this.remove()"', '').replace(
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}",
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}.ti .thumb .ph{aspect-ratio:auto;height:100%;border-radius:0}").replace(
    "var p=new URL(String(u||''),location.href);", "var p=new URL(String(u||''),origin!=='*'?origin+'/':location.href);")
