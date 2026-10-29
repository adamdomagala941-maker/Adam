import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { ArrowDownToLine, ArrowRight, Check, CheckCheck, ChevronDown, ExternalLink, FileCheck2, FileText, FlaskConical, Info, LoaderCircle, Minus, Plus, Printer, QrCode, RotateCcw, Search, ShieldCheck, SlidersHorizontal, Upload, X } from 'lucide-react';
import Label, { type LabelData } from './components/Label';

type Source = {title:string;url:string;method:string;excerpt:string};
type SearchResult = {title:string;url:string;provider:string};
type Extraction = {data:LabelData;source:Source;warnings:string[];missing:string[]};
const example: LabelData = {
  name:'ALKOHOL IZOBUTYLOWY',cas:'78-83-1',ec:'201-148-0',formula:'C₄H₁₀O',molarMass:'74,12',volume:'500 ml',catalogNumber:'Oc2',signalWord:'NIEBEZPIECZEŃSTWO',pictograms:['GHS02','GHS05','GHS07'],
  hazards:'H226 Łatwopalna ciecz i pary.\nH315 Działa drażniąco na skórę.\nH318 Powoduje poważne uszkodzenie oczu.\nH335 Może powodować podrażnienie dróg oddechowych.\nH336 Może wywoływać uczucie senności lub zawroty głowy.',
  precautions:'P210 Przechowywać z dala od źródeł ciepła/iskrzenia/otwartego ognia/gorących powierzchni. Nie palić.\nP302+P352 W PRZYPADKU KONTAKTU ZE SKÓRĄ: Umyć dużą ilością wody z mydłem.\nP304+P340 W PRZYPADKU DOSTANIA SIĘ DO DRÓG ODDECHOWYCH: Wyprowadzić lub wynieść poszkodowanego na świeże powietrze i zapewnić warunki do odpoczynku w pozycji umożliwiającej swobodne oddychanie.\nP305+P351+P338 W PRZYPADKU DOSTANIA SIĘ DO OCZU: Ostrożnie płukać wodą przez kilka minut. Wyjąć soczewki kontaktowe, jeżeli są i można je łatwo usunąć. Nadal płukać.',supplemental:''
};
const templateSource: Source={title:'DJCHEM_wzor_2x76x51_QR.docm',url:'',method:'template',excerpt:'Dane przepisane z przesłanego wzoru. Nie jest to wynik wyszukiwania karty charakterystyki.'};
const empty:LabelData={name:'',cas:'',ec:'',formula:'',molarMass:'',volume:'',catalogNumber:'',signalWord:'',hazards:'',precautions:'',supplemental:'',pictograms:[]};
const ghsNames=['Materiał wybuchowy','Łatwopalność','Utlenianie','Gaz pod ciśnieniem','Działanie żrące','Toksyczność ostra','Działanie drażniące','Zagrożenie dla zdrowia','Zagrożenie dla środowiska'];
const storageKey='djchem-label-v1';
const defaultZoom=()=>window.innerWidth<400?1:window.innerWidth<=800?1.2:window.innerWidth<=1100?1.15:1.45;
function restored():{data:LabelData;source:Source|null} {
  try {const s=JSON.parse(localStorage.getItem(storageKey)||'null'); if(s?.data && Object.keys(empty).every(k=>k==='pictograms'?Array.isArray(s.data[k]):typeof s.data[k]==='string')) return s;} catch { /* Private browsing or invalid saved data. */ }
  return {data:example,source:templateSource};
}
async function request<T>(url:string,options:RequestInit):Promise<T> {
  const response=await fetch(url,options);
  if(!response.ok){let message=`Błąd serwera (${response.status}).`;try{const body=await response.json();message=typeof body.detail==='string'?body.detail:message;}catch{ /* Non-JSON proxy error. */ }throw new Error(message);}
  return response.json();
}

export default function App(){
  const [initial]=useState(restored);
  const [data,setData]=useState<LabelData>(initial.data);
  const [source,setSource]=useState<Source|null>(initial.source);
  const [query,setQuery]=useState('');const [url,setUrl]=useState('');const [mode,setMode]=useState<'search'|'url'>('search');
  const [results,setResults]=useState<SearchResult[]>([]);const [warnings,setWarnings]=useState<string[]>([]);
  const [error,setError]=useState('');const [busy,setBusy]=useState('');const [verified,setVerified]=useState(false);
  const [tab,setTab]=useState<'identity'|'safety'>('identity');const [qr,setQr]=useState('');const [qrError,setQrError]=useState('');
  const [fit,setFit]=useState({overflow:false,minFont:5});const [zoom,setZoom]=useState(defaultZoom);
  const [help,setHelp]=useState(false);const [persisted,setPersisted]=useState(true);
  const [exporting,setExporting]=useState(false);
  const fileInput=useRef<HTMLInputElement>(null);const controller=useRef<AbortController|null>(null);
  useEffect(()=>{try{localStorage.setItem(storageKey,JSON.stringify({data,source}));setPersisted(true);}catch{setPersisted(false);}},[data,source]);
  useEffect(()=>{let active=true;setQr('');setQrError('');if(data.catalogNumber.trim()) QRCode.toDataURL(data.catalogNumber,{width:600,margin:4,errorCorrectionLevel:'M'}).then(value=>{if(active)setQr(value);}).catch(()=>{if(active)setQrError('Numer jest za długi, aby utworzyć kod QR.');});return()=>{active=false;};},[data.catalogNumber]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  useEffect(()=>{const resize=()=>setZoom(defaultZoom());window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
  const update=<K extends keyof LabelData>(key:K,value:LabelData[K])=>{setData(d=>({...d,[key]:value}));setVerified(false);};
  const apply=(result:Extraction)=>{setData(old=>({...empty,...result.data,volume:old.volume,catalogNumber:old.catalogNumber}));setSource(result.source);setWarnings([...result.warnings,...(result.missing.length?[`Pola do uzupełnienia lub sprawdzenia: ${result.missing.join(', ')}.`]:[])]);setVerified(false);};
  const run=async(action:(signal:AbortSignal)=>Promise<void>)=>{controller.current?.abort();const c=new AbortController();controller.current=c;setError('');setWarnings([]);try{await action(c.signal);}catch(e){if((e as Error).name!=='AbortError')setError((e as Error).message||'Nie udało się wykonać operacji.');}finally{if(controller.current===c){setBusy('');controller.current=null;}}};
  const extract=(candidate:SearchResult)=>run(async signal=>{setBusy('Odczytywanie karty charakterystyki…');const r=await request<Extraction>('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:candidate.url,expected_name:query}),signal});apply(r);});
  const search=()=>run(async signal=>{
    if(!query.trim())return;setBusy('Wyszukiwanie kart charakterystyki…');setResults([]);
    const found=await request<{results:SearchResult[];warnings:string[]}>('/api/search?q='+encodeURIComponent(query.trim()),{signal});setResults(found.results);setWarnings(found.warnings);
    if(!found.results.length) {setError('Nie znaleziono karty. Doprecyzuj nazwę i producenta lub zaimportuj PDF.');return;}
    let lastError='';for(const candidate of found.results.slice(0,3)) {try{setBusy('Odczytywanie: '+candidate.title);const r=await request<Extraction>('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:candidate.url,expected_name:query}),signal});apply({...r,warnings:[...found.warnings,...r.warnings]});return;}catch(e){if((e as Error).name==='AbortError')throw e;lastError=(e as Error).message;}}
    throw new Error('Znaleziono źródła, ale nie udało się odczytać karty. Wybierz inne źródło lub zaimportuj PDF. '+lastError);
  });
  const upload=(file:File)=>run(async signal=>{setBusy('Odczytywanie pliku PDF…');const form=new FormData();form.append('file',file);apply(await request<Extraction>('/api/upload',{method:'POST',body:form,signal}));});
  const canPrint=!!data.name.trim()&&!!qr&&verified&&!fit.overflow&&!busy&&!exporting;
  const exportPdf=async()=>{setExporting(true);setError('');try{
    const [{toPng},{jsPDF}]=await Promise.all([import('html-to-image'),import('jspdf')]);
    await document.fonts.ready;
    const pages=document.querySelectorAll<HTMLElement>('#print-root .chemical-label');
    const pdf=new jsPDF({orientation:'landscape',unit:'mm',format:[76,51],compress:true,floatPrecision:16});
    pdf.setProperties({title:`DJCHEM — ${data.name}`,subject:`Numer katalogowy: ${data.catalogNumber}`,creator:'DJCHEM Studio etykiet'});
    for(let i=0;i<pages.length;i++){
      const png=await toPng(pages[i],{pixelRatio:6,backgroundColor:'#ffffff',style:{boxShadow:'none',transform:'none',margin:'0',flex:'none'},width:76*96/25.4,height:51*96/25.4});
      if(i)pdf.addPage([76,51],'landscape');
      pdf.addImage(png,'PNG',0,0,76,51);
    }
    pdf.save(`DJCHEM-${data.catalogNumber.replace(/[^\p{L}\p{N}_-]/gu,'_')}.pdf`);
  }catch(e){setError('Nie udało się wygenerować PDF. Możesz użyć drukowania przeglądarki. '+(e as Error).message);}finally{setExporting(false);}};
  const download=()=>{const link=document.createElement('a');const blob=new Blob([JSON.stringify({data,source,warnings},null,2)],{type:'application/json'});link.href=URL.createObjectURL(blob);link.download=`DJCHEM-${data.catalogNumber.replace(/[^\p{L}\p{N}_-]/gu,'_')||'etykieta'}.json`;link.click();URL.revokeObjectURL(link.href);};
  const reset=()=>{if(window.confirm('Wczytać dane z wzoru i zastąpić bieżącą etykietę?')){setData({...example});setSource(templateSource);setWarnings([]);setError('');setVerified(false);}};
  return <>
    <header className="topbar no-print"><a className="brand" href="/" aria-label="DJCHEM studio etykiet"><FlaskConical size={24}/><span>DJCHEM<span className="brand-dot">.</span></span><span className="brand-divider"/><span className="brand-sub">studio etykiet</span></a><div className="header-actions"><span className="session-state"><span/> {persisted?'Szkic zapisany lokalnie':'Zapis lokalny niedostępny'}</span><button className="button ghost help-trigger" onClick={()=>setHelp(true)}><Info size={16}/> Jak to działa</button></div></header>
    <main className="workspace">
      <section className="page-heading no-print"><div><div className="eyebrow">OD KARTY CHARAKTERYSTYKI DO ETYKIETY</div><h1>Twoja etykieta. Gotowa do druku.</h1><p>Wyszukaj substancję, sprawdź dane i wydrukuj w formacie DJCHEM.</p></div><div className="format-badge"><span className="format-icon"><FileText size={21}/></span><div><strong>76 × 51 mm</strong><span>2 etykiety · wzór DJCHEM</span></div></div></section>
      <div className="studio-grid">
        <div className="editor-column no-print">
          <section className="panel search-panel"><div className="section-title"><span className="step">01</span><h2>Znajdź substancję</h2><span className="mini-label">ŹRÓDŁO DANYCH</span></div>
            <div className="source-tabs"><button className={mode==='search'?'active':''} onClick={()=>setMode('search')}><Search size={14}/> Wyszukaj w internecie</button><button className={mode==='url'?'active':''} onClick={()=>setMode('url')}><ExternalLink size={14}/> Adres karty</button></div>
            <form onSubmit={e=>{e.preventDefault();if(mode==='search')void search();else void extract({title:url,url,provider:'URL'});}}>
              <label htmlFor="search-input">{mode==='search'?'Nazwa substancji lub produktu':'Adres URL karty charakterystyki'}</label>
              <div className="search-row"><div className="input-icon"><Search size={17}/><input id="search-input" type={mode==='search'?'text':'url'} value={mode==='search'?query:url} onChange={e=>mode==='search'?setQuery(e.target.value):setUrl(e.target.value)} placeholder={mode==='search'?'np. aceton Chempur, etanol 96%':'https://producent.pl/karta.pdf'} required disabled={!!busy}/></div><button className="button primary" disabled={!!busy} type="submit">{busy?<LoaderCircle size={17} className="spin"/>:<ArrowRight size={18}/>}<span>Szukaj</span></button></div>
            </form>
            <div className="upload-row"><span>Masz już kartę charakterystyki?</span><button className="text-button" onClick={()=>fileInput.current?.click()} disabled={!!busy}><Upload size={14}/> Importuj PDF</button><input ref={fileInput} type="file" accept="application/pdf,.pdf" className="hidden" aria-label="Importuj kartę charakterystyki PDF" onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value='';}}/></div>
            {busy&&<div className="busy-message" role="status"><LoaderCircle className="spin" size={16}/><span>{busy}</span><button onClick={()=>controller.current?.abort()} aria-label="Anuluj"><X size={16}/></button></div>}
            {error&&<div className="message error" role="alert"><Info size={17}/><div>{error}</div></div>}
            {results.length>0&&<details className="results" open={!source||!!error}><summary>Znalezione źródła ({results.length}) <ChevronDown size={14}/></summary>{results.map((r,i)=><button key={r.url+i} className="result-item" disabled={!!busy} onClick={()=>void extract(r)}><FileText size={17}/><span><strong>{r.title}</strong><small>{new URL(r.url).hostname}</small></span><ArrowRight size={15}/></button>)}</details>}
            {source&&<div className={'source-card '+(source.method==='template'?'template-source':'')}><FileCheck2 size={20}/><div><strong>{source.method==='template'?'Podgląd na danych z Twojego wzoru':'Dane odczytane z dokumentu'}</strong><span>{source.title}</span>{source.url&&<a href={source.url} target="_blank" rel="noreferrer">Otwórz dokument źródłowy <ExternalLink size={11}/></a>}{source.excerpt&&<details><summary>Fragment źródłowy</summary><pre>{source.excerpt}</pre></details>}</div></div>}
          </section>

          <section className="panel data-panel"><div className="section-title"><span className="step">02</span><h2>Sprawdź i uzupełnij dane</h2><SlidersHorizontal size={17} className="muted"/></div>
            <div className="editor-tabs" role="tablist" aria-label="Dane etykiety"><button role="tab" aria-selected={tab==='identity'} className={tab==='identity'?'active':''} onClick={()=>setTab('identity')}>Identyfikacja produktu</button><button role="tab" aria-selected={tab==='safety'} className={tab==='safety'?'active':''} onClick={()=>setTab('safety')}>Bezpieczeństwo <span>{data.pictograms.length}</span></button></div>
            {warnings.length>0&&<div className="message warning"><Info size={17}/><div>{warnings.map((w,i)=><p key={i}>{w}</p>)}</div></div>}
            {tab==='identity'?<div className="field-grid">
              <Field label="Nazwa na etykiecie" value={data.name} onChange={v=>update('name',v)} full placeholder="Nazwa substancji"/>
              <Field label="Numer CAS" value={data.cas} onChange={v=>update('cas',v)} placeholder="np. 67-64-1"/><Field label="Numer WE (EC)" value={data.ec} onChange={v=>update('ec',v)} placeholder="np. 200-662-2"/>
              <Field label="Wzór sumaryczny" value={data.formula} onChange={v=>update('formula',v)} placeholder="np. C₃H₆O"/><Field label="Masa molowa · g/mol" value={data.molarMass} onChange={v=>update('molarMass',v)} placeholder="np. 58,08"/>
              <Field label="Ilość / pojemność" value={data.volume} onChange={v=>update('volume',v)} placeholder="np. 500 ml"/><Field label="Numer katalogowy" value={data.catalogNumber} onChange={v=>update('catalogNumber',v)} placeholder="Wpisz numer produktu"/>
              <div className="qr-note"><QrCode size={17}/><span>Kod QR zawiera wyłącznie wpisany numer katalogowy.</span></div>
            </div>:<div className="safety-fields"><label htmlFor="signal-word">Hasło ostrzegawcze</label><select id="signal-word" value={data.signalWord} onChange={e=>update('signalWord',e.target.value)}><option value="">Brak / nie odczytano</option><option value="NIEBEZPIECZEŃSTWO">NIEBEZPIECZEŃSTWO</option><option value="UWAGA">UWAGA</option>{data.signalWord&&!['NIEBEZPIECZEŃSTWO','UWAGA'].includes(data.signalWord)&&<option>{data.signalWord}</option>}</select>
              <div className="pictogram-label">Piktogramy GHS <span>Wybierz zgodnie z sekcją 2.2 karty</span></div><div className="ghs-picker">{ghsNames.map((title,i)=>{const code='GHS'+String(i+1).padStart(2,'0');return <button key={code} title={title} aria-label={code+' '+title} aria-pressed={data.pictograms.includes(code)} className={data.pictograms.includes(code)?'selected':''} onClick={()=>update('pictograms',data.pictograms.includes(code)?data.pictograms.filter(p=>p!==code):[...data.pictograms,code].sort())}><img src={'/template/'+code+'.svg'} alt=""/><span>{code}</span>{data.pictograms.includes(code)&&<Check size={11}/>}</button>;})}</div>
              <TextField label="Zwroty zagrożenia H" value={data.hazards} onChange={v=>update('hazards',v)} rows={5}/><TextField label="Zwroty ostrożności P" value={data.precautions} onChange={v=>update('precautions',v)} rows={7}/><TextField label="Informacje dodatkowe / EUH" value={data.supplemental} onChange={v=>update('supplemental',v)} rows={3}/>
            </div>}
            <div className="editor-footer"><span><CheckCheck size={14}/> Zmiany widoczne na żywo</span><button className="text-button muted" onClick={reset}><RotateCcw size={13}/> Wczytaj wzór</button></div>
          </section>
        </div>

        <section className="preview-panel"><div className="preview-heading no-print"><div><span className="step">03</span><h2>Podgląd etykiety</h2><span className="live-tag"><span/> NA ŻYWO</span></div><div className="zoom-control"><button onClick={()=>setZoom(z=>Math.max(.75,Math.round((z-.1)*100)/100))} aria-label="Pomniejsz podgląd"><Minus size={14}/></button><span>{Math.round(zoom*100)}%</span><button onClick={()=>setZoom(z=>Math.min(2,Math.round((z+.1)*100)/100))} aria-label="Powiększ podgląd"><Plus size={14}/></button></div></div>
          <div className="preview-canvas"><div className="paper-stage" style={{'--preview-zoom':zoom} as React.CSSProperties}><div className="dimension no-print"><span/>76 mm<span/></div><div className="label-captions no-print"><span>01 / IDENTYFIKACJA</span><span>51 mm</span></div><div id="print-root"><Label data={data} qrDataUrl={qr} onFitChange={setFit}/></div><div className="back-caption no-print">02 / BEZPIECZEŃSTWO</div></div></div>
          <div className="fit-status no-print"><span className={'status-dot '+(fit.overflow?'bad':'')}/><strong>{fit.overflow?'Tekst nie mieści się na etykiecie':'Automatyczne dopasowanie czcionki'}</strong><span>{fit.overflow?'Druk zablokowany':`min. ${fit.minFont.toFixed(1)} pt`}</span></div>
          <div className="print-panel no-print"><div className="print-title"><Printer size={20}/><div><h3>Dokładnie w Twoim formacie</h3><p>2 strony po 76 × 51 mm. Drukuj w skali 100%.</p></div></div>
            {source?.method==='template'&&<div className="template-disclaimer">To dane z wzoru, a nie zweryfikowana karta charakterystyki.</div>}
            <label className="verify-checkbox"><input type="checkbox" checked={verified} onChange={e=>setVerified(e.target.checked)}/><span>Sprawdziłem dane i piktogramy z aktualną kartą właściwego produktu.</span></label>
            {(qrError||!data.catalogNumber.trim()||!data.name.trim()||fit.overflow)&&<p className="print-blocker" role="status">{qrError||(!data.name.trim()?'Uzupełnij nazwę produktu.':!data.catalogNumber.trim()?'Wpisz numer katalogowy, aby wygenerować QR.':'Treść jest zbyt długa. Popraw układ lub skróć wyłącznie dane, które nie są wymagane.')}</p>}
            <div className="print-actions"><button className="button primary print-button" disabled={!canPrint} onClick={()=>void exportPdf()}>{exporting?<LoaderCircle size={17} className="spin"/>:<ArrowDownToLine size={17}/>} {exporting?'Generowanie…':'Pobierz PDF'} <ArrowRight size={17}/></button><button className="button secondary export-button" disabled={!canPrint} onClick={()=>window.print()} title="Drukuj z przeglądarki"><Printer size={17}/><span>Drukuj</span></button><button className="button secondary export-button" onClick={download} title="Pobierz dane etykiety w pliku JSON" aria-label="Pobierz dane JSON"><FileText size={17}/></button></div>
            <p className="print-hint"><ShieldCheck size={13}/> Bez obcinania treści. Kod QR generowany lokalnie.</p>
          </div>
        </section>
      </div>
      <footer className="page-footer no-print"><span>DJCHEM <b>studio etykiet</b></span><span>Twój wzór. Precyzyjny druk.</span></footer>
    </main>
    {help&&<div className="modal-backdrop no-print" onClick={()=>setHelp(false)}><section className="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={e=>e.stopPropagation()}><button className="modal-close" aria-label="Zamknij" onClick={()=>setHelp(false)}><X size={20}/></button><div className="eyebrow">KRÓTKA INSTRUKCJA</div><h2 id="help-title">Od nazwy do gotowej etykiety</h2><ol><li>Wpisz nazwę, stężenie i producenta. Program wyszuka kartę i spróbuje odczytać pierwsze dostępne źródło. Możesz wybrać inne, wkleić URL lub wgrać PDF.</li><li>Porównaj pola i piktogramy z sekcją 2.2 aktualnej karty. Skanowane PDF bez warstwy tekstowej wymagają ręcznego uzupełnienia. Niewykryte dane pozostają puste.</li><li>Wpisz pojemność oraz numer katalogowy. QR koduje sam numer, bez linku.</li><li>Potwierdź sprawdzenie danych i wybierz druk lub zapis PDF. Ustaw papier 76 × 51 mm, skalę 100%, bez marginesów, nagłówków i stopek.</li></ol><p>Etykieta ma dwie osobne strony jak w pliku wzorcowym. Font dopasowuje się do dostępnego miejsca; przepełnienie blokuje druk. Podgląd używa Times New Roman lub dołączonego Liberation Serif.</p><p>Ostatni szkic jest przechowywany tylko w tej przeglądarce. Przycisk z ikoną dokumentu pobiera kopię JSON. Importowane PDF są przetwarzane przez serwer bez trwałego zapisu.</p><button className="button primary" onClick={()=>setHelp(false)}>Rozumiem <Check size={16}/></button></section></div>}
  </>;
}

function Field({label,value,onChange,full,placeholder}:{label:string;value:string;onChange:(v:string)=>void;full?:boolean;placeholder?:string}){return <label className={'field '+(full?'full':'')}><span>{label}</span><input value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/></label>;}
function TextField({label,value,onChange,rows}:{label:string;value:string;onChange:(v:string)=>void;rows:number}){return <label className="field"><span>{label}</span><textarea value={value} rows={rows} onChange={e=>onChange(e.target.value)} placeholder="Uzupełnij zgodnie z kartą charakterystyki"/></label>;}
