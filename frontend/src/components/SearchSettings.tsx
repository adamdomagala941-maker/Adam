import { useEffect, useState } from 'react';
import { Check, ExternalLink, KeyRound, LoaderCircle, Search, Trash2, X } from 'lucide-react';
import './SearchSettings.css';

export type SearchConfiguration = {ai_enabled:boolean;key_configured:boolean;key_source:string};
export default function SearchSettings({onClose,onSaved}:{onClose:()=>void;onSaved:(s:SearchConfiguration)=>void}) {
  const [settings,setSettings]=useState<SearchConfiguration>({ai_enabled:false,key_configured:false,key_source:''});
  const [key,setKey]=useState('');const [clearKey,setClearKey]=useState(false);const [saving,setSaving]=useState(false);const [loading,setLoading]=useState(true);const [error,setError]=useState('');
  useEffect(()=>{let active=true;fetch('/api/settings').then(async r=>{if(!r.ok)throw new Error('Nie udało się wczytać ustawień.');return r.json();}).then(s=>{if(active)setSettings(s);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[]);
  const save=async(e:React.FormEvent)=>{e.preventDefault();setSaving(true);setError('');try{const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ai_enabled:settings.ai_enabled,...(key?{openai_api_key:key}:{}),clear_key:clearKey})});const body=await r.json();if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:'Nie udało się zapisać ustawień.');setKey('');onSaved(body);onClose();}catch(e){setError((e as Error).message);}finally{setSaving(false);}};
  return <div className="modal-backdrop no-print" onClick={onClose}><section className="help-modal search-settings" role="dialog" aria-modal="true" aria-labelledby="settings-title" onClick={e=>e.stopPropagation()}><button className="modal-close" aria-label="Zamknij ustawienia" onClick={onClose}><X size={20}/></button><div className="eyebrow">WYSZUKIWANIE KART</div><h2 id="settings-title">Wyszukiwanie i moduł AI</h2>
    {loading?<p role="status">Wczytywanie ustawień…</p>:<form onSubmit={save}>
      <div className="search-method"><Search size={21}/><div><strong>Wyszukiwanie standardowe</strong><p>Wiele wyszukiwarek, polskie i angielskie nazwy, odczyt linków do PDF na stronach produktów. Dostępne bez klucza API.</p></div></div>
      <label className="ai-toggle"><input type="checkbox" checked={settings.ai_enabled} onChange={e=>setSettings(s=>({...s,ai_enabled:e.target.checked}))}/><span><strong>Włącz wyszukiwanie z AI</strong><small>OpenAI wyszukuje źródłowe karty w internecie. Program pobiera wskazane dokumenty i odczytuje z nich dane.</small></span></label>
      <div className="ai-cost">Wymaga własnego klucza OpenAI API oraz aktywnego rozliczania API. Abonament ChatGPT nie obejmuje tych wywołań. Wyszukiwanie z AI może być płatne według cennika dostawcy.</div>
      <label className="field api-key-field"><span><KeyRound size={13}/> Klucz OpenAI API</span><input aria-label="Klucz OpenAI API" type="password" autoComplete="off" spellCheck={false} value={key} onChange={e=>{setKey(e.target.value);setClearKey(false);}} placeholder={settings.key_configured&&!clearKey?'Klucz jest zapisany — pozostaw puste, aby go zachować':'Wklej własny klucz API'}/></label>
      {settings.key_configured&&!clearKey&&<div className="key-status"><span><Check size={13}/> Klucz skonfigurowany {settings.key_source==='environment'?'w środowisku':'na tym komputerze'}</span>{settings.key_source!=='environment'&&<button type="button" className="text-button" onClick={()=>{setClearKey(true);setKey('');setSettings(s=>({...s,ai_enabled:false}));}}><Trash2 size={12}/> Usuń klucz</button>}</div>}
      {clearKey&&<p className="key-removal">Klucz zostanie usunięty po zapisaniu ustawień.</p>}
      <a className="api-link" href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">Utwórz klucz na platform.openai.com <ExternalLink size={12}/></a>
      <p className="key-privacy">Klucz jest przechowywany w lokalnej konfiguracji serwera i nie jest dołączany do repozytorium ani paczki programu. Nie trafia do etykiety ani do kopii JSON. AI służy do wyszukania dokumentów; nie tworzy treści zagrożeń.</p>
      {error&&<div className="message error" role="alert">{error}</div>}
      <button type="submit" className="button primary" disabled={saving}>{saving?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>} Zapisz ustawienia</button>
    </form>}
  </section></div>;
}
