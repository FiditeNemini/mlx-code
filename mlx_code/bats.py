_UI_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>MLX Code</title>\n<style>\n*{margin:0;padding:0;box-sizing:border-box}\nbody{font-family:system-ui,-apple-system,sans-serif;background:#0d1117;color:#c9d1d9;height:100vh;display:flex;flex-direction:column}\n#hdr{padding:8px 16px;background:#161b22;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}\n#hdr h1{font-size:14px;font-weight:600}\n#hdr .info{display:flex;gap:8px;align-items:center;font-size:12px;color:#8b949e}\n#hdr button{background:transparent;color:#8b949e;border:1px solid #30363d;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px}\n#hdr button:hover{color:#c9d1d9;border-color:#8b949e}\n#chat{flex:1;overflow-y:auto;padding:16px}\n.chat-inner{max-width:920px;margin:0 auto}\n.msg{margin-bottom:14px}\n.msg-role{font-size:12px;color:#8b949e;margin-bottom:3px}\n.msg-body{padding:10px 14px;border-radius:8px;line-height:1.6;white-space:pre-wrap;word-break:break-word;font-size:14px}\n.msg-user .msg-body{background:#1c2128;border:1px solid #30363d}\n.msg-assistant .msg-body{background:#161b22;border:1px solid #30363d}\n.msg-thinking .msg-body{color:#6e7681;font-style:italic;background:rgba(136,144,150,0.05);border-left:2px solid #30363d;font-size:13px}\n.msg-tool .msg-body{background:rgba(210,153,34,0.08);border-left:2px solid #d29922;font-family:ui-monospace,SFMono-Regular,monospace;font-size:13px}\n.msg-error .msg-body{color:#f85149}\n.cursor{display:inline-block;width:7px;height:15px;background:#58a6ff;animation:blink 1s steps(2) infinite;vertical-align:text-bottom;margin-left:2px;border-radius:1px}\n@keyframes blink{50%{opacity:0}}\n#input-area{padding:12px 16px;background:#161b22;border-top:1px solid #30363d;flex-shrink:0}\n.input-inner{max-width:920px;margin:0 auto;display:flex;gap:8px}\n#input{flex:1;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:8px;padding:10px 14px;font-family:inherit;font-size:14px;resize:none;height:44px;max-height:200px;line-height:1.5}\n#input:focus{outline:none;border-color:#58a6ff}\n#send{background:#238636;color:#fff;border:none;border-radius:8px;padding:0 20px;cursor:pointer;font-size:14px;font-weight:500;white-space:nowrap}\n#send:hover{background:#2ea043}\n#send:disabled{background:#21262d;color:#484f58;cursor:not-allowed}\n</style>\n</head>\n<body>\n<div id="hdr">\n  <h1>⚡ MLX Code</h1>\n  <div class="info">\n    <span id="status">connecting...</span>\n    <button onclick="clearChat()">Clear</button>\n  </div>\n</div>\n<div id="chat"><div class="chat-inner" id="chatInner"></div></div>\n<div id="input-area">\n  <div class="input-inner">\n    <textarea id="input" placeholder="Send a message... (Enter=send, Shift+Enter=newline)" rows="1"></textarea>\n    <button id="send" onclick="send()">Send</button>\n  </div>\n</div>\n<script>\nconst chatEl=document.getElementById(\'chat\');\nconst innerEl=document.getElementById(\'chatInner\');\nconst inputEl=document.getElementById(\'input\');\nconst sendBtn=document.getElementById(\'send\');\nconst statusEl=document.getElementById(\'status\');\nconst SYSTEM_PROMPT = \'You are a helpful assistant. You are running in a web chat mode with no tool execution capabilities. Answer the user directly and concisely.\';\nlet messages=[{role:\'system\',content:SYSTEM_PROMPT}];\nlet streaming=false;\n\ninputEl.addEventListener(\'keydown\',e=>{\n  if(e.key===\'Enter\'&&!e.shiftKey){e.preventDefault();send();}\n});\ninputEl.addEventListener(\'input\',()=>{\n  inputEl.style.height=\'auto\';\n  inputEl.style.height=Math.min(inputEl.scrollHeight,200)+\'px\';\n});\n\nfunction scrollBottom(){chatEl.scrollTop=chatEl.scrollHeight;}\n\nfunction addMsg(role,label){\n  const d=document.createElement(\'div\');\n  d.className=\'msg msg-\'+role;\n  const r=document.createElement(\'div\');r.className=\'msg-role\';r.textContent=label;\n  const b=document.createElement(\'div\');b.className=\'msg-body\';\n  d.appendChild(r);d.appendChild(b);\n  innerEl.appendChild(d);scrollBottom();return b;\n}\n\nfunction clearChat(){\n  if(streaming)return;\n  messages=[{role:\'system\',content:SYSTEM_PROMPT}];innerEl.innerHTML=\'\';inputEl.focus();\n}\n\nfunction stripToolXml(text){\n  // Remove complete <tool_call>...</tool_call> blocks\n  text=text.replace(/<tool_call>[\\s\\S]*?<\\/tool_call>/g,\'\');\n  // Handle incomplete <tool_call> at end (closing tag not yet received)\n  const idx=text.lastIndexOf(\'<tool_call>\');\n  if(idx!==-1&&text.indexOf(\'</tool_call>\',idx)===-1)return text.substring(0,idx);\n  // Handle partial opening tag at end (e.g. "<tool", "<tool_c")\n  const tag=\'<tool_call>\';\n  for(let i=tag.length-1;i>0;i--){\n    if(text.endsWith(tag.substring(0,i)))return text.substring(0,text.length-i);\n  }\n  return text;\n}\n\nfunction checkHealth(){\n  fetch(\'/health\').then(r=>r.json()).then(d=>{\n    statusEl.textContent=d.model||\'ready\';\n  }).catch(()=>{statusEl.textContent=\'offline\';});\n}\n\nasync function send(){\n  const text=inputEl.value.trim();\n  if(!text||streaming)return;\n  inputEl.value=\'\';inputEl.style.height=\'auto\';\n  messages.push({role:\'user\',content:text});\n  addMsg(\'user\',\'≫ You\').textContent=text;\n  streaming=true;sendBtn.disabled=true;statusEl.textContent=\'generating...\';\n\n  const aBody=addMsg(\'assistant\',\'○ Assistant\');\n  let tBody=null,displayText=\'\',thinkText=\'\',rawText=\'\',toolCalls=[];\n  const cursor=document.createElement(\'span\');cursor.className=\'cursor\';aBody.appendChild(cursor);\n\n  try{\n    const resp=await fetch(\'/v1/chat/completions\',{\n      method:\'POST\',\n      headers:{\'Content-Type\':\'application/json\'},\n      body:JSON.stringify({messages,max_tokens:8192})\n    });\n\n    if(!resp.ok){\n      cursor.remove();\n      let msg=\'HTTP \'+resp.status;\n      try{const e=await resp.json();msg+=\': \'+(e.error||JSON.stringify(e));}catch(_){try{msg+=\': \'+await resp.text();}catch(_){}}\n      aBody.textContent=\'✗ \'+msg;\n      aBody.parentElement.classList.add(\'msg-error\');\n      messages.pop();return;\n    }\n\n    const reader=resp.body.getReader();\n    const dec=new TextDecoder();\n    let buf=\'\';\n\n    while(true){\n      const{done,value}=await reader.read();\n      if(done)break;\n      buf+=dec.decode(value,{stream:true});\n      const lines=buf.split(\'\\n\');\n      buf=lines.pop();  // keep partial line in buffer\n\n      for(const line of lines){\n        if(!line.startsWith(\'data: \'))continue;\n        const data=line.slice(6).trim();\n        if(!data||data===\'[DONE]\')continue;\n        let ch;try{ch=JSON.parse(data);}catch(_){continue;}\n        const delta=ch.choices&&ch.choices[0]&&ch.choices[0].delta;\n        if(!delta)continue;\n\n        if(delta.reasoning_content){\n          if(!tBody){\n            cursor.remove();\n            tBody=addMsg(\'thinking\',\'◌ Thinking\');\n            tBody.appendChild(cursor.cloneNode());\n          }\n          thinkText+=delta.reasoning_content;\n          const c=tBody.querySelector(\'.cursor\');if(c)c.remove();\n          tBody.textContent=thinkText;\n          tBody.appendChild(cursor.cloneNode());\n          scrollBottom();\n        }\n\n        if(delta.content){\n          if(tBody){\n            const c=tBody.querySelector(\'.cursor\');if(c)c.remove();\n            tBody=null;aBody.appendChild(cursor);\n          }\n          rawText+=delta.content;\n          displayText=stripToolXml(rawText);\n          cursor.remove();aBody.textContent=displayText;aBody.appendChild(cursor);\n          scrollBottom();\n        }\n\n        if(delta.tool_calls){\n          cursor.remove();\n          for(const tc of delta.tool_calls){\n            const fn=tc.function||{};\n            if(fn.name){\n              toolCalls.push({name:fn.name,args:\'\'});\n              addMsg(\'tool\',\'⚙ \'+fn.name).textContent=fn.name;\n            }\n            if(fn.arguments&&toolCalls.length>0){\n              toolCalls[toolCalls.length-1].args+=fn.arguments;\n              const tbs=innerEl.querySelectorAll(\'.msg-tool .msg-body\');\n              if(tbs.length>0){\n                let disp=toolCalls[toolCalls.length-1].name+\'\\n\';\n                try{disp+=JSON.stringify(JSON.parse(toolCalls[toolCalls.length-1].args),null,2);}\n                catch(_){disp+=toolCalls[toolCalls.length-1].args;}\n                tbs[tbs.length-1].textContent=disp;\n              }\n            }\n          }\n          scrollBottom();\n        }\n      }\n    }\n\n    cursor.remove();\n    if(displayText.trim()){\n      aBody.textContent=displayText;\n      messages.push({role:\'assistant\',content:displayText});\n    }else{\n      aBody.textContent=thinkText?\'(thinking only)\':\'(no output)\';\n      messages.push({role:\'assistant\',content:displayText});\n    }\n    if(toolCalls.length>0){\n      addMsg(\'tool\',\'⚠ Note\').textContent=\'Tool calls cannot be executed in the web UI. Use the terminal REPL (--bare) for full tool support.\';\n    }\n  }catch(e){\n    cursor.remove();\n    aBody.textContent=\'✗ \'+e.message;\n    aBody.parentElement.classList.add(\'msg-error\');\n    if(messages.length>0&&messages[messages.length-1].role===\'user\')messages.pop();\n  }finally{\n    streaming=false;sendBtn.disabled=false;\n    checkHealth();inputEl.focus();\n  }\n}\n\ncheckHealth();inputEl.focus();\n</script>\n</body>\n</html>'
import asyncio
import json
import queue as _queue
import time
import uuid
import threading
import hashlib
from array import array
from contextlib import asynccontextmanager
from pathlib import Path
import mlx.core as mx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse, JSONResponse, HTMLResponse
from starlette.routing import Route
import logging
logger = logging.getLogger(__name__)
MIN_PREFIX_TOKENS = 256

def _hash_tokens(tokens):
    arr = array('I', tokens)
    return hashlib.blake2b(arr.tobytes(), digest_size=8).hexdigest()

class PrefixCache:

    def __init__(self, model_name, cache_dir):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, prefix_tokens):
        safe = ''.join((c for c in self.model_name if c.isalnum()))
        h = _hash_tokens(prefix_tokens)
        return self.cache_dir / f'{safe}_{len(prefix_tokens)}_{h}.safetensors'

    def lookup(self, prefix_tokens):
        if not prefix_tokens or len(prefix_tokens) < MIN_PREFIX_TOKENS:
            return None
        path = self._path(prefix_tokens)
        if not path.exists():
            return None
        try:
            from mlx_lm.models.cache import load_prompt_cache
            cache, _ = load_prompt_cache(str(path), return_metadata=True)
            mx.async_eval(cache)
            return cache
        except Exception as exc:
            logger.info(f'[batch] failed to load prefix cache {path.name}: {exc}')
            return None

    def store(self, prefix_tokens, kv_cache):
        if not prefix_tokens or len(prefix_tokens) < MIN_PREFIX_TOKENS:
            return
        path = self._path(prefix_tokens)
        if path.exists():
            return
        try:
            from mlx_lm.models.cache import save_prompt_cache
            save_prompt_cache(str(path), kv_cache)
            logger.info(f'[batch] saved prefix cache  len={len(prefix_tokens)}  file={path.name}')
        except Exception as exc:
            logger.info(f'[batch] failed to save prefix cache: {exc}')

def _prefill_prefix(model, tokens, prefill_step_size=2048):
    from mlx_lm.models.cache import make_prompt_cache
    prompt_cache = make_prompt_cache(model)
    prompt = mx.array(tokens)
    while prompt.shape[0] > 0:
        n = min(prefill_step_size, prompt.shape[0])
        model(prompt[:n][None], cache=prompt_cache)
        mx.eval([c.state for c in prompt_cache])
        prompt = prompt[n:]
        mx.clear_cache()
    return prompt_cache

def _get_prefix(tokens, ckpts):
    if not ckpts:
        return (None, 0)
    first_ckpt = min(ckpts)
    if first_ckpt < MIN_PREFIX_TOKENS:
        return (None, 0)
    return (tokens[:first_ckpt], first_ckpt)

def make_batch_app(model_name: str, cache_dir: str='.cache'):
    state = {'model': None, 'tokenizer': None, 'batch_gen': None, 'request_queue': _queue.Queue(), 'active': {}, 'loop': None, 'prefix_cache': None}

    def _engine():
        rq = state['request_queue']
        active = state['active']
        bg = state['batch_gen']
        tok = state['tokenizer']
        loop = state['loop']
        model = state['model']
        pcache = state['prefix_cache']
        while True:
            while not rq.empty():
                try:
                    tokens, max_tokens, token_queue, ckpts = rq.get_nowait()
                    _insert(bg, active, pcache, model, tok, loop, tokens, max_tokens, token_queue, ckpts)
                except _queue.Empty:
                    break
            if not active:
                tokens, max_tokens, token_queue, ckpts = rq.get()
                _insert(bg, active, pcache, model, tok, loop, tokens, max_tokens, token_queue, ckpts)
            try:
                results = bg.next_generated()
            except Exception:
                for uid, meta in list(active.items()):
                    loop.call_soon_threadsafe(meta['q'].put_nowait, None)
                active.clear()
                continue
            for r in results:
                meta = active.get(r.uid)
                if meta is None:
                    continue
                detok = meta['detok']
                detok.add_token(r.token)
                seg = detok.last_segment
                if r.finish_reason is not None:
                    detok.finalize()
                    if (final := detok.last_segment):
                        loop.call_soon_threadsafe(meta['q'].put_nowait, final)
                    loop.call_soon_threadsafe(meta['q'].put_nowait, None)
                    del active[r.uid]
                elif seg:
                    loop.call_soon_threadsafe(meta['q'].put_nowait, seg)

    def _insert(bg, active, pcache, model, tok, loop, tokens, max_tokens, token_queue, ckpts):
        prefix_tokens, prefix_len = _get_prefix(tokens, ckpts)
        if prefix_tokens is not None:
            cached_kv = pcache.lookup(prefix_tokens)
            if cached_kv is not None:
                suffix = tokens[prefix_len:]
                try:
                    uids = bg.insert([suffix], [max_tokens], caches=[cached_kv])
                except Exception as exc:
                    logger.info(f'[batch] cache insert failed ({exc}), falling back to full prompt')
                    uids = bg.insert([tokens], [max_tokens])
                    prefix_len = 0
                else:
                    logger.info(f'[batch] cache HIT  prefix={prefix_len}  suffix={len(suffix)}')
                del cached_kv
                mx.clear_cache()
            else:
                logger.info(f'[batch] prefilling prefix  prefix={prefix_len}  suffix={len(tokens) - prefix_len}')
                prefix_kv = _prefill_prefix(model, prefix_tokens)
                pcache.store(prefix_tokens, prefix_kv)
                suffix = tokens[prefix_len:]
                try:
                    uids = bg.insert([suffix], [max_tokens], caches=[prefix_kv])
                except Exception as exc:
                    logger.info(f'[batch] cache insert failed ({exc}), falling back to full prompt')
                    uids = bg.insert([tokens], [max_tokens])
                    prefix_len = 0
                del prefix_kv
                mx.clear_cache()
            active[uids[0]] = {'q': token_queue, 'detok': tok.detokenizer}
        else:
            uids = bg.insert([tokens], [max_tokens])
            logger.info(f'[batch] no cache  prompt={len(tokens)}')
            active[uids[0]] = {'q': token_queue, 'detok': tok.detokenizer}

    @asynccontextmanager
    async def lifespan(_app):
        from mlx_lm import load
        from mlx_lm.generate import BatchGenerator
        from mlx_lm.tokenizer_utils import TokenizerWrapper
        logger.info(f'[batch] Loading model {model_name!r} …')
        model, tokenizer = load(model_name)
        if not isinstance(tokenizer, TokenizerWrapper):
            tokenizer = TokenizerWrapper(tokenizer)
        eos = set(tokenizer.eos_token_ids) | {tokenizer.eos_token_id}
        stop_tokens = [[t] for t in eos]
        batch_gen = BatchGenerator(model, stop_tokens=stop_tokens)
        state.update(model=model, tokenizer=tokenizer, batch_gen=batch_gen, loop=asyncio.get_running_loop(), prefix_cache=PrefixCache(model_name, cache_dir))
        logger.info('[batch] Model ready. Starting engine thread.')
        threading.Thread(target=_engine, daemon=True).start()
        yield
        batch_gen.close()

    @staticmethod
    def _detect_api(path: str) -> str:
        if path.startswith('/v1beta/models/'):
            return 'gemini'
        if path.startswith('/v1/messages'):
            return 'claude'
        if path.startswith('/v1/responses'):
            return 'codex'
        return 'noapi'

    async def _stream_sse(token_queue, api, msg_id, in_tokens):
        from . import main as _m
        adapters = {'claude': _m.ClaudeAdapter, 'codex': _m.CodexAdapter, 'gemini': _m.GeminiAdapter, 'noapi': _m.DefaultAdapter}
        adapter = adapters.get(api, _m.DefaultAdapter)(msg_id, in_tokens)
        yield adapter.start()
        st = 'thinking'
        buf = ''
        think_tags = ['<think>', '</think>']
        while True:
            text = await token_queue.get()
            if text is None:
                break
            buf += text
            seg = text
            while any((t in seg for t in think_tags)):
                if st == 'text' and think_tags[0] in seg:
                    before, _, seg = seg.partition(think_tags[0])
                    if before:
                        yield adapter.text('text', before)
                    st = 'thinking'
                if st == 'thinking' and think_tags[1] in seg:
                    before, _, seg = seg.partition(think_tags[1])
                    if before:
                        yield adapter.text('thinking', before)
                    st = 'text'
            if seg:
                yield adapter.text(st, seg)
        if (tools := _m._parse_tools_xml(buf)):
            for tool in tools:
                yield adapter.tool(tool)
            yield adapter.end(True)
        else:
            yield adapter.end(False)

    async def generate_endpoint(request: Request):
        from . import main as _m
        if state['batch_gen'] is None:
            return JSONResponse({'error': 'model not loaded'}, status_code=503)
        path = request.url.path.split('?')[0].rstrip('/')
        api = _detect_api(path)
        if api == 'gemini':
            q = str(request.url.query) or ''
            if 'alt=sse' not in q and 'streamGenerateContent' not in path:
                return JSONResponse({'candidates': [{'content': {'role': 'model', 'parts': [{'text': '{"complexity_reasoning":"local","complexity_score":50}'}]}, 'finishReason': 'STOP'}], 'usageMetadata': {'promptTokenCount': 0, 'candidatesTokenCount': 0}})
        body = await request.json()
        max_tokens = int(body.get('max_tokens', body.get('max_completion_tokens', 8192)))
        try:
            prompt, ckpts = _m.encode(body, api, state['tokenizer'], None, None, None)
        except Exception as exc:
            return JSONResponse({'error': f'encode: {exc}'}, status_code=500)
        if ckpts is None or not prompt:
            return JSONResponse({'error': 'empty prompt'}, status_code=400)
        msg_id = f'msg_{uuid.uuid4().hex}'
        token_queue = asyncio.Queue()
        state['request_queue'].put((prompt, max_tokens, token_queue, ckpts))

        async def _sse():
            async for chunk in _stream_sse(token_queue, api, msg_id, len(prompt)):
                yield chunk
        return StreamingResponse(_sse(), media_type='text/event-stream')

    async def simple_generate(request: Request):
        if state['batch_gen'] is None:
            return JSONResponse({'error': 'model not loaded'}, status_code=503)
        body = await request.json()
        tok = state['tokenizer']
        max_tokens = body.get('max_tokens', 256)
        if 'messages' in body:
            text = tok.apply_chat_template(body['messages'], tokenize=False, add_generation_prompt=True)
        else:
            text = body.get('prompt', '')
        tokens = tok.encode(text)
        if not tokens:
            return JSONResponse({'error': 'empty prompt'}, status_code=400)
        token_queue = asyncio.Queue()
        state['request_queue'].put((tokens, max_tokens, token_queue, []))
        if body.get('stream', True):

            async def _raw():
                while True:
                    chunk = await token_queue.get()
                    if chunk is None:
                        break
                    yield chunk
            return StreamingResponse(_raw(), media_type='text/plain')
        parts = []
        while True:
            chunk = await token_queue.get()
            if chunk is None:
                break
            parts.append(chunk)
        return JSONResponse({'text': ''.join(parts)})

    async def list_models(_req):
        return JSONResponse({'data': [{'id': 'local', 'object': 'model', 'created': int(time.time()), 'owned_by': 'local'}]})

    async def count_tokens(_req):
        return JSONResponse({'input_tokens': 0})

    async def health(_req):
        pc = state['prefix_cache']
        n_cached = 0
        if pc and pc.cache_dir.exists():
            n_cached = sum((1 for _ in pc.cache_dir.glob('*.safetensors')))
        return JSONResponse({'status': 'ok', 'model': model_name, 'active_sequences': len(state['active']), 'prefix_cache_files': n_cached})
    return Starlette(routes=[Route('/v1/models', list_models, methods=['GET']), Route('/v1/messages/count_tokens', count_tokens, methods=['POST']), Route('/v1/chat/completions', generate_endpoint, methods=['POST']), Route('/v1/messages', generate_endpoint, methods=['POST']), Route('/v1/responses', generate_endpoint, methods=['POST']), Route('/v1beta/models/{rest:path}', generate_endpoint, methods=['POST']), Route('/generate', simple_generate, methods=['POST']), Route('/health', health, methods=['GET'])], lifespan=lifespan)
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(make_batch_app('mlx-community/Qwen3.5-4B-OptiQ-4bit'), host='0.0.0.0', port=8000)