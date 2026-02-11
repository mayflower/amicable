from __future__ import annotations

import json
import re
from typing import Any

# NOTE: Vite dev server treats `/<name>.js` requests as source modules before public assets.
# Writing to `/amicable-db.js` (workspace root) ensures it is served correctly.
_VITE_DB_JS_PATH = "/amicable-db.js"
_VITE_RUNTIME_JS_PATH = "/amicable-runtime.js"
_PUBLIC_DB_JS_PATH = "/public/amicable-db.js"
_PUBLIC_RUNTIME_JS_PATH = "/public/amicable-runtime.js"
_VITE_INDEX_HTML_PATH = "/index.html"
_SVELTEKIT_APP_HTML_PATH = "/src/app.html"
_NUXT_CONFIG_TS_PATHS = ("/nuxt.config.ts",)
_LARAVEL_WELCOME_BLADE_PATHS = ("/resources/views/welcome.blade.php",)
_NEXT_LAYOUT_PATHS = ("/app/layout.tsx", "/src/app/layout.tsx")
_REMIX_ROOT_PATHS = ("/app/root.tsx",)


def render_db_js(
    *, app_id: str, graphql_url: str, app_key: str, preview_origin: str
) -> str:
    payload = {
        "appId": app_id,
        "graphqlUrl": graphql_url,
        "appKey": app_key,
        "previewOrigin": preview_origin,
    }
    # JSON is safe to parse back out; browser can read window.__AMICABLE_DB__.
    return f"window.__AMICABLE_DB__ = {json.dumps(payload, separators=(',', ':'), sort_keys=True)};\n"


def render_runtime_js() -> str:
    # Dependency-free bridge script: captures runtime errors and GraphQL errors and
    # forwards them to the editor via postMessage.
    return (
        "(function(){\n"
        "  var PARENT_ORIGIN_KEY='__amicable_parent_origin';\n"
        "  function _param(name){\n"
        "    try{\n"
        "      var s=String(location.search||'');\n"
        "      if(!s||s.length<2) return '';\n"
        "      var parts=s.substring(1).split('&');\n"
        "      for(var i=0;i<parts.length;i++){\n"
        "        var kv=parts[i].split('=');\n"
        "        if(kv[0]===name) return kv.slice(1).join('=');\n"
        "      }\n"
        "    }catch(e){}\n"
        "    return '';\n"
        "  }\n"
        "  function _originFromUrl(u){\n"
        "    try{\n"
        "      var x=new URL(String(u||''),location.href);\n"
        "      if(x.protocol==='https:' || x.protocol==='http:') return x.origin;\n"
        "    }catch(e){}\n"
        "    return '';\n"
        "  }\n"
        "  function _resolveParentOrigin(){\n"
        "    var v='';\n"
        "    try{v=decodeURIComponent(_param('amicableParentOrigin')||'');}catch(e){v='';}\n"
        "    v=_originFromUrl(v);\n"
        "    if(v) return v;\n"
        "    try{v=_originFromUrl(sessionStorage.getItem(PARENT_ORIGIN_KEY)||'');}catch(e){v='';}\n"
        "    if(v) return v;\n"
        "    try{v=_originFromUrl(document.referrer||'');}catch(e){v='';}\n"
        "    return v || '';\n"
        "  }\n"
        "  function _trunc(s,n){\n"
        "    try{s=String(s||'');}catch(e){s='';}\n"
        "    if(!n||n<=0) return '';\n"
        "    if(s.length<=n) return s;\n"
        "    return s.substring(0,Math.max(0,n-3))+'...';\n"
        "  }\n"
        "  function _hash(s){\n"
        "    s=String(s||'');\n"
        "    var h=5381;\n"
        "    for(var i=0;i<s.length;i++) h=((h<<5)+h) ^ s.charCodeAt(i);\n"
        "    return (h>>>0).toString(16);\n"
        "  }\n"
        "  function _safePreview(v){\n"
        "    try{\n"
        "      if(typeof v==='string') return _trunc(v,4000);\n"
        "      if(v===undefined) return 'undefined';\n"
        "      if(v===null) return 'null';\n"
        "      var seen=[];\n"
        "      var out=JSON.stringify(v,function(k,val){\n"
        "        if(typeof val==='bigint') return String(val)+'n';\n"
        "        if(typeof val==='function') return '[Function]';\n"
        "        if(val && typeof val==='object'){\n"
        "          if(seen.indexOf(val)!==-1) return '[Circular]';\n"
        "          seen.push(val);\n"
        "        }\n"
        "        return val;\n"
        "      });\n"
        "      if(typeof out==='string' && out) return _trunc(out,4000);\n"
        "    }catch(e){}\n"
        "    try{return _trunc(String(v),4000);}catch(e2){return '[Unserializable]';}\n"
        "  }\n"
        "  var parentOrigin=_resolveParentOrigin();\n"
        "  if(!parentOrigin) return;\n"
        "  try{sessionStorage.setItem(PARENT_ORIGIN_KEY,parentOrigin);}catch(e){}\n"
        "  var recent=new Map();\n"
        "  var lastSentAt=0;\n"
        "  var MIN_INTERVAL_MS=2000;\n"
        "  var WINDOW_MS=10*60*1000;\n"
        "  var _sendingConsoleError=false;\n"
        "  function _gc(){\n"
        "    if(recent.size<=200) return;\n"
        "    var items=[];\n"
        "    recent.forEach(function(v,k){items.push([k,v]);});\n"
        "    items.sort(function(a,b){return a[1]-b[1];});\n"
        "    for(var i=0;i<items.length-200;i++) recent.delete(items[i][0]);\n"
        "  }\n"
        "  function _send(kind,message,stack,url,extra,level,source,argsPreview){\n"
        "    var now=Date.now();\n"
        "    if(now-lastSentAt<MIN_INTERVAL_MS) return;\n"
        "    var base=String(kind||'')+'|'+String(message||'')+'|'+String(stack||'')+'|'+String(url||'')+'|'+String(argsPreview||'');\n"
        "    var fp='rt_'+_hash(base);\n"
        "    var prev=recent.get(fp);\n"
        "    if(typeof prev==='number' && now-prev<WINDOW_MS) return;\n"
        "    recent.set(fp,now);\n"
        "    _gc();\n"
        "    lastSentAt=now;\n"
        "    var payload={\n"
        "      kind:String(kind||'window_error'),\n"
        "      message:_trunc(message,2000),\n"
        "      stack:stack? _trunc(stack,8000) : undefined,\n"
        "      url:url? _trunc(url,2000) : undefined,\n"
        "      level:level? String(level) : undefined,\n"
        "      source:source? String(source) : undefined,\n"
        "      args_preview:argsPreview? _trunc(argsPreview,4000) : undefined,\n"
        "      ts_ms:now,\n"
        "      fingerprint:fp,\n"
        "      extra:extra||undefined\n"
        "    };\n"
        "    try{window.parent.postMessage({type:'amicable_runtime_error',payload:payload},parentOrigin);}catch(e){}\n"
        "  }\n"
        "  window.addEventListener('message',function(ev){\n"
        "    try{\n"
        "      if(!ev || ev.origin!==parentOrigin) return;\n"
        "      var d=ev.data;\n"
        "      if(!d || typeof d!=='object' || d.type!=='amicable_runtime_probe') return;\n"
        "      var ack={type:'amicable_runtime_probe_ack',probe_id:d.probe_id||''};\n"
        "      window.parent.postMessage(ack,parentOrigin);\n"
        "    }catch(e){}\n"
        "  });\n"
        "  if(window.console && typeof window.console.error==='function'){\n"
        "    var _origConsoleError=window.console.error;\n"
        "    window.console.error=function(){\n"
        "      try{\n"
        "        if(!_sendingConsoleError){\n"
        "          _sendingConsoleError=true;\n"
        "          var msg='';\n"
        "          var st='';\n"
        "          if(arguments.length>0){\n"
        "            var first=arguments[0];\n"
        "            if(first && typeof first==='object'){\n"
        "              try{msg=String(first.message||first.toString());}catch(e){msg='';}\n"
        "              try{st=String(first.stack||'');}catch(e2){st='';}\n"
        "            }else{\n"
        "              msg=String(first||'');\n"
        "            }\n"
        "          }\n"
        "          if(!msg) msg='console.error called';\n"
        "          var parts=[];\n"
        "          for(var i=0;i<arguments.length;i++) parts.push(_safePreview(arguments[i]));\n"
        "          var argsPreview=_trunc(parts.join(' '),4000);\n"
        "          _send('console_error',msg,st,location.href,null,'error','console',argsPreview);\n"
        "        }\n"
        "      }catch(e){}\n"
        "      finally{_sendingConsoleError=false;}\n"
        "      try{return _origConsoleError.apply(this,arguments);}catch(e3){return undefined;}\n"
        "    };\n"
        "  }\n"
        "  window.addEventListener('error',function(ev){\n"
        "    try{\n"
        "      var msg='';\n"
        "      var st='';\n"
        "      if(ev){\n"
        "        msg=ev.message||'';\n"
        "        if(ev.error){\n"
        "          msg=msg||ev.error.message||String(ev.error);\n"
        "          st=ev.error.stack||'';\n"
        "        }\n"
        "        if(!msg && ev.target && ev.target.tagName){\n"
        "          msg='Resource error: '+String(ev.target.tagName);\n"
        "        }\n"
        "      }\n"
        "      _send('window_error',msg,st,(ev&&ev.filename)||location.href,null,'error','window','');\n"
        "    }catch(e){}\n"
        "  },true);\n"
        "  window.addEventListener('unhandledrejection',function(ev){\n"
        "    try{\n"
        "      var r=ev&&ev.reason;\n"
        "      var msg='';\n"
        "      var st='';\n"
        "      if(r && typeof r==='object'){\n"
        "        msg=String(r.message||r.toString());\n"
        "        st=String(r.stack||'');\n"
        "      }else{\n"
        "        msg=String(r);\n"
        "      }\n"
        "      _send('unhandled_rejection',msg,st,location.href,null,'error','promise','');\n"
        "    }catch(e){}\n"
        "  });\n"
        "  function _isGraphqlUrl(u){\n"
        "    try{\n"
        "      var db=window.__AMICABLE_DB__;\n"
        "      if(db && typeof db==='object' && typeof db.graphqlUrl==='string' && db.graphqlUrl){\n"
        "        var dbu=db.graphqlUrl;\n"
        "        if(dbu.indexOf('://')!==-1){\n"
        "          return u.indexOf(dbu)!==-1;\n"
        "        }\n"
        "        var up=new URL(u,location.href).pathname;\n"
        "        return up===dbu || String(u).endsWith(dbu);\n"
        "      }\n"
        "    }catch(e){}\n"
        "    return String(u||'').indexOf('/db/apps/')!==-1 && String(u||'').endsWith('/graphql');\n"
        "  }\n"
        "  var _origFetch=window.fetch;\n"
        "  if(typeof _origFetch==='function'){\n"
        "    window.fetch=function(input,init){\n"
        "      var url='';\n"
        "      try{\n"
        "        if(typeof input==='string') url=input;\n"
        "        else if(input && typeof input.url==='string') url=input.url;\n"
        "      }catch(e){}\n"
        "      return _origFetch.apply(this,arguments).then(function(resp){\n"
        "        try{\n"
        "          if(url && _isGraphqlUrl(url)){\n"
        "            var cloned=resp.clone();\n"
        "            cloned.json().then(function(j){\n"
        "              try{\n"
        "                if(j && typeof j==='object' && j.errors && j.errors.length){\n"
        "                  var first=j.errors[0]||{};\n"
        "                  var m=first.message || JSON.stringify(first);\n"
        "                  _send('graphql_error',String(m||'GraphQL error'),'',url,{first_error:first},'error','bridge','');\n"
        "                }\n"
        "              }catch(e){}\n"
        "            }).catch(function(){});\n"
        "          }\n"
        "        }catch(e){}\n"
        "        return resp;\n"
        "      });\n"
        "    };\n"
        "  }\n"
        "})();\n"
    )


def parse_db_js(text: str) -> dict[str, Any] | None:
    if not isinstance(text, str) or "__AMICABLE_DB__" not in text:
        return None
    # Expect: window.__AMICABLE_DB__ = {...};
    m = re.search(r"__AMICABLE_DB__\s*=\s*({.*?})\s*;", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def ensure_index_includes_db_script(index_html: str) -> str:
    if not isinstance(index_html, str):
        return index_html
    need_db = "/amicable-db.js" not in index_html
    need_rt = "/amicable-runtime.js" not in index_html
    if not need_db and not need_rt:
        return index_html
    tag = ""
    if need_db:
        tag += '  <script src="/amicable-db.js"></script>\n'
    if need_rt:
        tag += '  <script src="/amicable-runtime.js"></script>\n'
    if "</head>" in index_html:
        return index_html.replace("</head>", f"{tag}</head>", 1)
    return index_html + "\n" + tag


def ensure_next_layout_includes_db_script(layout_tsx: str) -> str:
    if not isinstance(layout_tsx, str):
        return layout_tsx
    need_db = "/amicable-db.js" not in layout_tsx
    need_rt = "/amicable-runtime.js" not in layout_tsx
    if not need_db and not need_rt:
        return layout_tsx

    # Prefer injecting into <head> if present; otherwise insert a <head> block
    # right after the opening <html ...> tag.
    tag = ""
    if need_db:
        tag += '        <script src="/amicable-db.js"></script>\n'
    if need_rt:
        tag += '        <script src="/amicable-runtime.js"></script>\n'
    if "<head>" in layout_tsx:
        return layout_tsx.replace("<head>", "<head>\n" + tag, 1)
    if "</head>" in layout_tsx:
        return layout_tsx.replace("</head>", tag + "      </head>", 1)

    m = re.search(r"<html[^>]*>", layout_tsx)
    if m:
        head = "      <head>\n" + tag + "      </head>\n"
        return layout_tsx[: m.end()] + "\n" + head + layout_tsx[m.end() :]

    # Fallback: insert before <body> or at the top of the file.
    if "<body" in layout_tsx:
        return layout_tsx.replace("<body", tag + "      <body", 1)
    return tag + layout_tsx


def ensure_remix_root_includes_db_script(root_tsx: str) -> str:
    if not isinstance(root_tsx, str):
        return root_tsx
    need_db = "/amicable-db.js" not in root_tsx
    need_rt = "/amicable-runtime.js" not in root_tsx
    if not need_db and not need_rt:
        return root_tsx

    # Inject before <Scripts /> when possible.
    tag = ""
    if need_db:
        tag += '      <script src="/amicable-db.js"></script>\n'
    if need_rt:
        tag += '      <script src="/amicable-runtime.js"></script>\n'
    if "<Scripts" in root_tsx:
        return root_tsx.replace("<Scripts", tag + "      <Scripts", 1)
    if "</head>" in root_tsx:
        return root_tsx.replace("</head>", tag + "    </head>", 1)
    return root_tsx + "\n" + tag


def ensure_sveltekit_app_html_includes_db_script(app_html: str) -> str:
    if not isinstance(app_html, str):
        return app_html
    need_db = "/amicable-db.js" not in app_html
    need_rt = "/amicable-runtime.js" not in app_html
    if not need_db and not need_rt:
        return app_html
    tag = ""
    if need_db:
        tag += '  <script src="/amicable-db.js"></script>\n'
    if need_rt:
        tag += '  <script src="/amicable-runtime.js"></script>\n'
    if "</head>" in app_html:
        return app_html.replace("</head>", f"{tag}</head>", 1)
    return app_html + "\n" + tag


def ensure_nuxt_config_includes_db_script(nuxt_config_ts: str) -> str:
    if not isinstance(nuxt_config_ts, str):
        return nuxt_config_ts
    need_db = "/amicable-db.js" not in nuxt_config_ts
    need_rt = "/amicable-runtime.js" not in nuxt_config_ts
    if not need_db and not need_rt:
        return nuxt_config_ts

    # If one script is already present, try a minimal insertion next to it to
    # avoid duplicating the existing entry.
    if not need_db and need_rt:
        out = re.sub(
            r'(\{\s*src\s*:\s*"/amicable-db\.js"\s*\})',
            r'\1, { src: "/amicable-runtime.js" }',
            nuxt_config_ts,
            count=1,
        )
        if out != nuxt_config_ts:
            return out
    if need_db and not need_rt:
        out = re.sub(
            r'(\{\s*src\s*:\s*"/amicable-runtime\.js"\s*\})',
            r'\1, { src: "/amicable-db.js" }',
            nuxt_config_ts,
            count=1,
        )
        if out != nuxt_config_ts:
            return out

    script_items: list[str] = []
    if need_db:
        script_items.append('{ src: "/amicable-db.js" }')
    if need_rt:
        script_items.append('{ src: "/amicable-runtime.js" }')
    script_array = "[ " + ", ".join(script_items) + " ]"

    # Minimal, idempotent insert: add app.head.script entry.
    # Prefer inserting inside defineNuxtConfig({...}).
    m = re.search(r"defineNuxtConfig\(\s*\{", nuxt_config_ts)
    if not m:
        return (
            nuxt_config_ts
            + f"\n\nexport default defineNuxtConfig({{ app: {{ head: {{ script: {script_array} }} }} }});\n"
        )

    # If config already has an `app:` section, try to insert into its `head`.
    if re.search(r"\bapp\s*:\s*\{", nuxt_config_ts):
        if re.search(r"\bhead\s*:\s*\{", nuxt_config_ts):
            # Insert script array after head: {
            return re.sub(
                r"(\bhead\s*:\s*\{)",
                r"\1\n      script: " + script_array + ",",
                nuxt_config_ts,
                count=1,
            )
        return re.sub(
            r"(\bapp\s*:\s*\{)",
            r"\1\n    head: { script: " + script_array + " },",
            nuxt_config_ts,
            count=1,
        )

    # No app section: insert one near the top of the object literal.
    insert = (
        "\n  app: {\n"
        "    head: {\n"
        f"      script: {script_array},\n"
        "    },\n"
        "  },"
    )
    return nuxt_config_ts[: m.end()] + insert + nuxt_config_ts[m.end() :]


def ensure_laravel_welcome_includes_db_script(welcome_blade: str) -> str:
    if not isinstance(welcome_blade, str):
        return welcome_blade
    need_db = "/amicable-db.js" not in welcome_blade
    need_rt = "/amicable-runtime.js" not in welcome_blade
    if not need_db and not need_rt:
        return welcome_blade
    tag = ""
    if need_db:
        tag += '    <script src="/amicable-db.js"></script>\n'
    if need_rt:
        tag += '    <script src="/amicable-runtime.js"></script>\n'
    if "</head>" in welcome_blade:
        return welcome_blade.replace("</head>", f"{tag}</head>", 1)
    return welcome_blade + "\n" + tag


def vite_db_paths() -> tuple[str, str]:
    return (_VITE_DB_JS_PATH, _VITE_INDEX_HTML_PATH)


def next_db_paths() -> tuple[str, tuple[str, ...]]:
    return (_PUBLIC_DB_JS_PATH, _NEXT_LAYOUT_PATHS)


def remix_db_paths() -> tuple[str, tuple[str, ...]]:
    return (_PUBLIC_DB_JS_PATH, _REMIX_ROOT_PATHS)


def sveltekit_db_paths() -> tuple[str, str]:
    # SvelteKit serves static files from /static at /. We write to /static so it
    # is available at /amicable-db.js, then inject a <script> in app.html.
    return ("/static/amicable-db.js", _SVELTEKIT_APP_HTML_PATH)


def nuxt_db_paths() -> tuple[str, tuple[str, ...]]:
    # Nuxt serves /public at /. Use public so it works regardless of server routing.
    return (_PUBLIC_DB_JS_PATH, _NUXT_CONFIG_TS_PATHS)


def laravel_db_paths() -> tuple[str, tuple[str, ...]]:
    return (_PUBLIC_DB_JS_PATH, _LARAVEL_WELCOME_BLADE_PATHS)


def runtime_js_path_for_inject_kind(inject_kind: str) -> str:
    if inject_kind == "vite_index_html":
        return _VITE_RUNTIME_JS_PATH
    if inject_kind == "sveltekit_app_html":
        return "/static/amicable-runtime.js"
    return _PUBLIC_RUNTIME_JS_PATH
