
_HTML += r'''window.IUI={S:S,app:app,SRC:SRC,h:h,txt:txt,arr:arr,md:md,photo:photo,scroller:scroller,label:label,icon:icon,SVG:SVG,isDark:isDark,openLink:openLink,sendPrompt:sendPrompt,reportHeight:reportHeight,fav:fav,domain:domain,CDN:'__CDN__',NONCE:'__NONCE__'};
})();
</script>
'''
_HTML = _HTML.replace(' onerror="this.remove()"', '').replace(
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}",
    ".ti .thumb img{width:100%;height:100%;object-fit:cover}.ti .thumb .ph{aspect-ratio:auto;height:100%;border-radius:0}")
